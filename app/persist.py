"""SQLite と設定を GitHub リポジトリへ退避し、起動時に復元する。

Render の無料枠はファイルシステムが揮発で、スリープ復帰や再デプロイのたびに
data/ 配下が消える。GitHub を外部ストレージ代わりにして回避する。

必須の環境変数:
  BACKUP_REPO   "owner/repo"           （バックアップ先。private推奨）
  BACKUP_TOKEN  contents:write の Personal Access Token
任意:
  BACKUP_BRANCH  既定 main（専用ブランチ名でも可）
  BACKUP_DIR     既定 backup
  BACKUP_EVERY   既定 300（秒）。0 で定期実行なし
  BACKUP_RESTORE 0 で起動時復元を無効化
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import threading
import time

import requests

API = "https://api.github.com"
_BOOT = time.time()
_LOCK = threading.RLock()
_STATE = {"enabled": False, "last_push": 0.0, "last_pull": 0.0,
          "ok": None, "err": "", "files": 0, "restored": 0}
_STARTED = False


def cfg():
    return {
        "repo": (os.getenv("BACKUP_REPO") or "").strip(),
        "token": (os.getenv("BACKUP_TOKEN") or "").strip(),
        "branch": (os.getenv("BACKUP_BRANCH") or "main").strip() or "main",
        "dir": (os.getenv("BACKUP_DIR") or "backup").strip().strip("/") or "backup",
        "every": int(os.getenv("BACKUP_EVERY", "300") or 0),
        "restore": (os.getenv("BACKUP_RESTORE", "1") or "1") != "0",
    }


def enabled():
    c = cfg()
    return bool(c["repo"] and c["token"])


def state():
    return dict(_STATE)


def _h(raw=False):
    return {"Authorization": "Bearer " + cfg()["token"],
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "User-Agent": "igtracker-backup",
            "X-GitHub-Api-Version": "2022-11-28"}


def _paths():
    """退避対象のローカルファイル。tenancy を import しないので起動順に依存しない。"""
    out, seen = [], set()

    def add(p):
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)

    for env in ("ROOT_DB", "SETTINGS_FILE", "SESSION_FILE"):
        v = os.getenv(env)
        if v:
            add(v)
    for base in ("data", os.getenv("TENANT_ROOT") or "", os.getenv("DATA_DIR") or ""):
        if not base or not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.endswith(".db") or f == "settings.json":
                    add(os.path.join(root, f))
    for p in ("data/root.db", "data/settings.json"):
        if os.path.exists(p):
            add(p)
    return out


def _remote(ap):
    return cfg()["dir"] + "/" + ap.lstrip("/").replace("/", "__") + ".b64"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _checkpoint(path):
    try:
        c = sqlite3.connect(path, timeout=10)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass


def _head(path):
    c = cfg()
    r = requests.get(f"{API}/repos/{c['repo']}/contents/{path}",
                     params={"ref": c["branch"]}, headers=_h(), timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _raw(path):
    c = cfg()
    r = requests.get(f"{API}/repos/{c['repo']}/contents/{path}",
                     params={"ref": c["branch"]}, headers=_h(raw=True), timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def _put(path, content, sha=None, message="backup"):
    c = cfg()
    body = {"message": message,
            "content": base64.b64encode(content).decode(),
            "branch": c["branch"]}
    if sha:
        body["sha"] = sha
    r = requests.put(f"{API}/repos/{c['repo']}/contents/{path}",
                     headers=_h(), json=body, timeout=60)
    if r.status_code in (200, 201):
        return r.json().get("content", {}).get("sha")
    if r.status_code == 409:
        return None
    r.raise_for_status()
    return None


def ensure_branch():
    c = cfg()
    try:
        r = requests.get(f"{API}/repos/{c['repo']}/git/ref/heads/{c['branch']}",
                         headers=_h(), timeout=20)
        if r.status_code == 200:
            return True
        base = requests.get(f"{API}/repos/{c['repo']}", headers=_h(),
                            timeout=20).json().get("default_branch", "main")
        sha = requests.get(f"{API}/repos/{c['repo']}/git/ref/heads/{base}",
                           headers=_h(), timeout=20).json()["object"]["sha"]
        requests.post(f"{API}/repos/{c['repo']}/git/refs", headers=_h(),
                      json={"ref": f"refs/heads/{c['branch']}", "sha": sha}, timeout=20)
        print(f"[backup] ブランチ {c['branch']} を作成しました")
        return True
    except Exception as e:
        _STATE["err"] = repr(e)
        return False


def pull(force=False):
    """リモートにあればローカルへ復元する。

    起動直後に「このプロセスが作ったファイル」は中身が空なので必ず上書きする。
    ローカルの方が明確に新しい場合は触らない。
    """
    if not enabled():
        _STATE["enabled"] = False
        return {"ok": False, "why": "disabled"}
    if not force and not cfg()["restore"]:
        return {"ok": False, "why": "restore無効"}
    _STATE["enabled"] = True
    try:
        if not _head(cfg()["dir"] + "/meta.json"):
            return {"ok": False, "why": "バックアップ未作成"}
        doc = json.loads(_raw(cfg()["dir"] + "/meta.json").decode("utf-8"))
    except Exception as e:
        _STATE["err"] = repr(e)
        return {"ok": False, "why": repr(e)}

    remote_ts = float(doc.get("ts") or 0)
    restored, skipped = [], 0
    for rpath, info in (doc.get("files") or {}).items():
        lpath = info.get("path")
        if not lpath:
            continue
        if not force and os.path.exists(lpath):
            mt = os.path.getmtime(lpath)
            fresh = mt >= _BOOT - 1.0
            if not fresh and mt >= remote_ts + 5:
                skipped += 1
                continue
        try:
            data = _raw(rpath)
            if data is None:
                continue
            os.makedirs(os.path.dirname(lpath) or ".", exist_ok=True)
            for suf in ("-wal", "-shm"):
                try:
                    if os.path.exists(lpath + suf):
                        os.remove(lpath + suf)
                except Exception:
                    pass
            with open(lpath, "wb") as f:
                f.write(data)
            restored.append(lpath)
        except Exception as e:
            _STATE["err"] = repr(e)

    _STATE["last_pull"] = time.time()
    _STATE["restored"] = len(restored)
    if restored:
        print("[backup] 復元:", ", ".join(os.path.basename(p) for p in restored))
    return {"ok": True, "restored": restored, "skipped": skipped}


def push(force=False):
    """ローカルの DB と設定をリモートへ送る。内容が同じファイルは飛ばす。"""
    if not enabled():
        _STATE["enabled"] = False
        return {"ok": False, "why": "disabled"}
    with _LOCK:
        now = time.time()
        if not force and now - _STATE["last_push"] < 20:
            return {"ok": False, "why": "間隔が短い"}
        _STATE["last_push"] = now

    c = cfg()
    ensure_branch()

    meta_obj, old = None, {}
    try:
        meta_obj = _head(c["dir"] + "/meta.json")
        if meta_obj:
            old = json.loads(_raw(c["dir"] + "/meta.json").decode("utf-8"))
    except Exception:
        meta_obj, old = None, {}
    old_files = (old.get("files") or {})

    files, sent, skipped = {}, 0, 0
    for p in _paths():
        if not os.path.exists(p):
            continue
        if p.endswith(".db"):
            _checkpoint(p)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception:
            continue
        h = _sha(data)
        rpath = _remote(p)
        files[rpath] = {"path": p, "sha": h}
        if not force and old_files.get(rpath, {}).get("sha") == h:
            skipped += 1
            continue
        prev = _head(rpath)
        try:
            _put(rpath, data, (prev or {}).get("sha"), f"backup {os.path.basename(p)}")
            sent += 1
        except Exception as e:
            _STATE["err"] = repr(e)

    meta = json.dumps({"ts": time.time(), "files": files}, ensure_ascii=False).encode()
    try:
        _put(c["dir"] + "/meta.json", meta, (meta_obj or {}).get("sha"), "backup meta")
    except Exception as e:
        _STATE["err"] = repr(e)

    _STATE["ok"] = True
    _STATE["files"] = len(files)
    return {"ok": True, "sent": sent, "skipped": skipped, "total": len(files)}


def _loop():
    every = cfg()["every"] or 300
    while True:
        time.sleep(every)
        try:
            push()
        except Exception as e:
            _STATE["err"] = repr(e)


def start():
    global _STARTED
    if _STARTED or not enabled():
        return
    _STARTED = True
    ensure_branch()
    if cfg()["every"] > 0:
        threading.Thread(target=_loop, daemon=True).start()
        print(f"[backup] 定期バックアップ開始（{cfg()['every']}秒間隔）")