"""個人単位でデータを GitHub リポジトリへ退避し、ログイン時に自動復元する。

Render の無料枠はファイルシステムが揮発で、スリープ復帰や再デプロイのたびに
data/ 配下が消える。GitHub を外部ストレージ代わりにして回避する。

テナントごとに backup/users/<ユーザー>/ 配下へ分けて保存するので、
他のユーザーのデータと混ざらない。共有ファイル（root.db 等）は
backup/ 直下に別途退避する。

必須の環境変数:
  BACKUP_REPO   "owner/repo"           （private推奨）
  BACKUP_TOKEN  contents:write の Personal Access Token
任意:
  BACKUP_BRANCH   既定 main
  BACKUP_DIR      既定 backup
  BACKUP_EVERY    既定 300（秒）。自動バックアップの間隔
  BACKUP_RESTORE  0 で自動復元を無効化
  BACKUP_PER_USER 0 で個人単位バックアップを無効化
  BACKUP_MEDIA    0 で media 配下を除外
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import threading
import time

import requests

API = "https://api.github.com"
_BOOT = time.time()
_LOCK = threading.RLock()
_TLOCK = threading.RLock()
_STARTED = False
_PULLED = set()
_LAST = {}

_STATE = {"enabled": False, "last_push": 0.0, "last_pull": 0.0,
          "ok": None, "err": "", "files": 0, "restored": 0, "users": {}}


def cfg():
    return {
        "repo": (os.getenv("BACKUP_REPO") or "").strip(),
        "token": (os.getenv("BACKUP_TOKEN") or "").strip(),
        "branch": (os.getenv("BACKUP_BRANCH") or "main").strip() or "main",
        "dir": (os.getenv("BACKUP_DIR") or "backup").strip().strip("/") or "backup",
        "every": int(os.getenv("BACKUP_EVERY", "300") or 0),
        "restore": (os.getenv("BACKUP_RESTORE", "1") or "1") != "0",
        "per_user": (os.getenv("BACKUP_PER_USER", "1") or "1") != "0",
        "media": (os.getenv("BACKUP_MEDIA", "1") or "1") != "0",
    }


def enabled():
    c = cfg()
    return bool(c["repo"] and c["token"])


def state():
    with _LOCK:
        d = dict(_STATE)
        d["users"] = {k: dict(v) for k, v in _STATE["users"].items()}
    return d


def user_state(user):
    with _LOCK:
        return dict(_STATE["users"].get(_safe(user), {}))


def _us(user):
    with _LOCK:
        return _STATE["users"].setdefault(
            _safe(user), {"last_push": 0.0, "last_pull": 0.0, "restored": 0, "err": ""})


def _h(raw=False):
    return {"Authorization": "Bearer " + cfg()["token"],
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "User-Agent": "igtracker-backup",
            "X-GitHub-Api-Version": "2022-11-28"}


def _safe(u):
    return re.sub(r"[^a-z0-9._-]", "_", (u or "").lower()) or "user"


def _tenant_root():
    return os.getenv("TENANT_ROOT") or "data/tenants"


def user_dir(user):
    try:
        from . import tenancy
        d = tenancy.tenant_dir(user)
        if d:
            return d
    except Exception:
        pass
    return os.path.join(_tenant_root(), _safe(user))


def user_files(user):
    """そのユーザーに属するファイル。"""
    out, seen = [], set()
    base = user_dir(user)
    if not os.path.isdir(base):
        return out
    want_media = cfg()["media"]
    for root, _dirs, files in os.walk(base):
        for f in files:
            p = os.path.join(root, f)
            ap = os.path.abspath(p)
            if ap in seen:
                continue
            if f.endswith(".db") or f.endswith(".json"):
                seen.add(ap)
                out.append(ap)
            elif want_media:
                seen.add(ap)
                out.append(ap)
    return out


def _shared_paths():
    out, seen = [], set()

    def add(p):
        ap = os.path.abspath(p)
        if ap not in seen and os.path.exists(ap):
            seen.add(ap)
            out.append(ap)

    for env in ("ROOT_DB", "SETTINGS_FILE", "SESSION_FILE"):
        v = os.getenv(env)
        if v:
            add(v)
    for p in ("data/root.db", "data/settings.json", "data/session.json"):
        add(p)
    return out


def _paths():
    """共有ファイル + 全テナント（起動時の一括復元用）。"""
    out = list(_shared_paths())
    root = _tenant_root()
    if os.path.isdir(root):
        for t in sorted(os.listdir(root)):
            out += user_files(t)
    return out


def _remote(ap, prefix=None):
    c = cfg()
    name = ap.lstrip("/").replace("/", "__") + ".b64"
    return f"{c['dir']}/{prefix}/{name}" if prefix else f"{c['dir']}/{name}"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _checkpoint(path):
    try:
        c = sqlite3.connect(path, timeout=10)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except Exception:
        pass


def _drop_tenant(user):
    """キャッシュされたDB接続を捨てて、次のアクセスで開き直させる。"""
    try:
        from . import tenancy
        with tenancy._lock:
            tenancy._dbs.pop(tenancy.safe_name(user), None)
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


# ---------- リンク索引の持ち出し ----------

def _user_links(user):
    try:
        from . import users as U
        with U._lock:
            rows = U._c().execute(
                "SELECT code, created_at FROM link_index WHERE owner=?",
                (U.norm(user),)).fetchall()
        return [{"code": r["code"], "created_at": r["created_at"]} for r in rows]
    except Exception:
        return []


def _restore_links(user, links):
    if not links:
        return 0
    try:
        from . import users as U
    except Exception:
        return 0
    n = 0
    for l in links:
        try:
            U.register_link(l["code"], user)
            n += 1
        except Exception:
            pass
    return n


# ---------- 個人単位 ----------

def push_user(user, force=True):
    """そのユーザーのデータだけを退避する。"""
    if not enabled() or not cfg()["per_user"] or not user:
        return {"ok": False, "why": "disabled"}
    st = _us(user)
    with _TLOCK:
        now = time.time()
        if not force and now - st["last_push"] < 20:
            return {"ok": False, "why": "間隔が短い"}
        st["last_push"] = now

    ensure_branch()
    prefix = f"users/{_safe(user)}"
    meta_obj, old = None, {}
    try:
        meta_obj = _head(f"{cfg()['dir']}/{prefix}/meta.json")
        if meta_obj:
            old = json.loads(_raw(f"{cfg()['dir']}/{prefix}/meta.json").decode("utf-8"))
    except Exception:
        meta_obj, old = None, {}
    old_files = (old.get("files") or {})

    files, sent, skipped = {}, 0, 0
    for p in user_files(user):
        if p.endswith(".db"):
            _checkpoint(p)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception:
            continue
        h = _sha(data)
        rpath = _remote(p, prefix)
        files[rpath] = {"path": p, "sha": h}
        if not force and old_files.get(rpath, {}).get("sha") == h:
            skipped += 1
            continue
        prev = _head(rpath)
        try:
            _put(rpath, data, (prev or {}).get("sha"), f"backup {_safe(user)}/{os.path.basename(p)}")
            sent += 1
        except Exception as e:
            st["err"] = repr(e)

    links = _user_links(user)
    meta = json.dumps({"ts": time.time(), "user": user, "files": files, "links": links},
                      ensure_ascii=False).encode()
    try:
        _put(f"{cfg()['dir']}/{prefix}/meta.json", meta,
             (meta_obj or {}).get("sha"), f"backup meta {_safe(user)}")
    except Exception as e:
        st["err"] = repr(e)

    st["files"] = len(files)
    st["ok"] = True
    return {"ok": True, "user": user, "sent": sent, "skipped": skipped, "total": len(files)}


def pull_user(user, force=False):
    """そのユーザーのデータを復元する。ローカルの方が新しければ触らない。"""
    if not enabled() or not user:
        return {"ok": False, "why": "disabled"}
    if not force and not cfg()["restore"]:
        return {"ok": False, "why": "restore無効"}
    st = _us(user)
    prefix = f"users/{_safe(user)}"
    try:
        if not _head(f"{cfg()['dir']}/{prefix}/meta.json"):
            return {"ok": False, "why": "未作成"}
        doc = json.loads(_raw(f"{cfg()['dir']}/{prefix}/meta.json").decode("utf-8"))
    except Exception as e:
        st["err"] = repr(e)
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
            st["err"] = repr(e)

    n = _restore_links(user, doc.get("links"))
    if restored:
        _drop_tenant(user)
    st["last_pull"] = time.time()
    st["restored"] = len(restored)
    if restored or n:
        print(f"[backup] 復元 {user}: {len(restored)}ファイル / {n}リンク")
    return {"ok": True, "user": user, "restored": restored, "links": n, "skipped": skipped}


def touch(user, force=False, sync_first=True):
    """ログイン中やリンク所有者アクセスのたびに呼ぶ。初回は復元、以降は間隔を空けて退避。"""
    if not enabled() or not user:
        return
    key = _safe(user)
    first = False
    with _TLOCK:
        if key not in _PULLED:
            _PULLED.add(key)
            first = True

    if first:
        if sync_first:
            try:
                pull_user(user)
            except Exception as e:
                _us(user)["err"] = repr(e)
        else:
            threading.Thread(target=pull_user, args=(user,), daemon=True).start()
        threading.Thread(target=push_user, kwargs={"force": True}, daemon=True).start()
        return

    now = time.time()
    every = max(30, cfg()["every"] or 300)
    with _TLOCK:
        if not force and now - _LAST.get(key, 0) < every:
            return
        _LAST[key] = now
    threading.Thread(target=push_user, args=(user,), daemon=True).start()


def push_all(force=True):
    out = {}
    try:
        from . import users as U
        names = U.list_usernames(include_disabled=True)
    except Exception:
        names = []
    for n in names:
        try:
            out[n] = push_user(n, force=force)
        except Exception as e:
            out[n] = {"ok": False, "why": repr(e)}
    return out


# ---------- 共有ファイル（起動時の一括復元用） ----------

def pull(force=False):
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
    """共有ファイル（root.db など）だけを退避する。"""
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
    for p in _shared_paths():
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
        except Exception:
            pass


def start():
    global _STARTED
    if _STARTED or not enabled():
        return
    _STARTED = True
    ensure_branch()
    if cfg()["every"] > 0:
        threading.Thread(target=_loop, daemon=True).start()
        print(f"[backup] 定期バックアップ開始（{cfg()['every']}秒間隔 / 個人単位）")