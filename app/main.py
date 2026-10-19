"""FastAPI アプリ本体。設定・記録はすべてWebで完結。リンク追跡つき。"""
import os, secrets, random, string, base64, json as _json, traceback
from urllib.parse import quote

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config
from .config import load, get as get_cfg
from .database import DB
from . import instagram as ig
from . import identity, watcher, forensics, linktrack

load()
db = DB(get_cfg()["storage"]["db_path"])

app = FastAPI(title="Uraaka Tracker")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = _json.loads
security = HTTPBasic()

EDITABLE = ["web", "identity", "monitor", "archive", "storage"]


@app.exception_handler(Exception)
async def _debug_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    try:
        db.log("system", "unhandled_error",
               {"path": str(request.url.path), "error": repr(exc)})
    except Exception:
        pass
    return PlainTextResponse(f"PATH: {request.url.path}\n\n{tb}", status_code=500)


def auth(cred: HTTPBasicCredentials = Depends(security)):
    cfg = get_cfg()
    cands = [(cfg["web"]["user"], cfg["web"]["password"])]
    if cfg["web"].get("_env_user"):
        cands.append((cfg["web"]["_env_user"], cfg["web"].get("_env_pass", "")))
    for u, p in cands:
        if secrets.compare_digest(cred.username, u) and secrets.compare_digest(cred.password, p):
            return cred.username
    raise HTTPException(401, "unauthorized", {"WWW-Authenticate": "Basic"})


def _tokens(raw):
    return [t.strip().lstrip("@") for t in (raw or "").replace(",", "\n").split() if t.strip()]


def _new_code(n=6):
    while True:
        c = "".join(random.choices(string.ascii_lowercase + string.digits, k=n))
        if not db.link_get(c):
            return c


@app.on_event("startup")
def _startup():
    for h in get_cfg().get("targets", []):
        try:
            uid = ig.client().user_id_from_username(h)
            db.add_target(uid, h)
            db.add_known(str(uid), h, source="target")
        except Exception as e:
            print("[startup] target解決失敗:", h, e)
    if os.getenv("RUN_SCHEDULER", "1") == "1":
        watcher.start(db)


# ---------- ダッシュボード ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _=Depends(auth)):
    targets = []
    for t in db.targets():
        p = db.q1("SELECT * FROM profiles WHERE user_id=?", (t["user_id"],))
        snap = db.q("""SELECT * FROM profile_snapshots WHERE user_id=?
            ORDER BY taken_at DESC LIMIT 30""", (t["user_id"],))
        best = db.q1("""SELECT * FROM identity_scores WHERE uraaka_user_id=?
            ORDER BY computed_at DESC, score DESC LIMIT 1""", (t["user_id"],))
        targets.append({"t": t, "p": p, "snap": [dict(s) for s in snap], "best": best})
    events = db.q("SELECT * FROM events ORDER BY ts DESC LIMIT 40")
    return templates.TemplateResponse("dashboard.html",
        {"request": request, "targets": targets, "events": events})


# ---------- 特定 ----------

@app.get("/identity", response_class=HTMLResponse)
def identity_page(request: Request, _=Depends(auth)):
    runs = db.q("SELECT * FROM identity_runs ORDER BY id DESC LIMIT 20")
    pairs = db.pairs(200)
    return templates.TemplateResponse("identity.html",
        {"request": request, "runs": runs, "pairs": pairs,
         "candidates": get_cfg().get("candidates", [])})


@app.post("/identity/run")
def identity_run(target: str = Form(...), candidates: str = Form(""),
                 auto: str = Form(""), archive: str = Form(""),
                 note: str = Form(""), _=Depends(auth)):
    toks = _tokens(candidates)

    try:
        cl = ig.client()
    except Exception as e:
        rid = db.start_run("0", target.strip().lstrip("@"), note=note)
        db.update_run(rid, status="error",
                      log="Instagramログイン失敗: " + repr(e) + "\n\n" + traceback.format_exc())
        return RedirectResponse(f"/runs/{rid}", 303)

    try:
        t_uid = identity.resolve_uid(cl, db, target)
    except Exception as e:
        rid = db.start_run("0", target.strip().lstrip("@"), note=note)
        db.update_run(rid, status="error",
                      log="ID解決失敗: " + repr(e) + "\n\n" + traceback.format_exc())
        return RedirectResponse(f"/runs/{rid}", 303)

    t_name = identity.name_of(db, t_uid, target.strip().lstrip("@"))
    db.add_known(t_uid, t_name, source="target")
    for tok in toks:
        try:
            uid = identity.resolve_uid(cl, db, tok)
            db.add_known(uid, identity.name_of(db, uid, tok), source="candidate")
        except Exception:
            pass
    rid = db.start_run(t_uid, t_name, candidates_raw=",".join(toks), note=note)

    def job():
        try:
            identity.run_identify(db, target, toks, auto_scan=bool(auto),
                                  run_id=rid, archive_candidates=bool(archive))
            db.update_run(rid, status="ok")
        except Exception as e:
            db.update_run(rid, status="error", log=repr(e) + "\n\n" + traceback.format_exc())
    watcher.run_bg(job)
    return RedirectResponse(f"/runs/{rid}", 303)


@app.post("/pair/run")
def pair_run(pid: int = Form(...), _=Depends(auth)):
    p = db.q1("SELECT * FROM saved_pairs WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404)
    rid = db.start_run(p["target_uid"], p["target_username"] or "",
                       candidates_raw=p["candidate_uid"], note="保存ペア")

    def job():
        try:
            identity.run_identify(db, p["target_uid"], [p["candidate_uid"]], run_id=rid)
            db.update_run(rid, status="ok")
        except Exception as e:
            db.update_run(rid, status="error", log=repr(e) + "\n\n" + traceback.format_exc())
    watcher.run_bg(job)
    return RedirectResponse(f"/runs/{rid}", 303)


@app.post("/pairs/{pid}/delete")
def pair_delete(pid: int, _=Depends(auth)):
    db.del_pair(pid)
    return RedirectResponse("/identity", 303)


# ---------- 履歴 ----------

@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, _=Depends(auth)):
    runs = db.q("SELECT * FROM identity_runs ORDER BY id DESC LIMIT 300")
    return templates.TemplateResponse("runs.html", {"request": request, "runs": runs})


@app.get("/runs/{rid}", response_class=HTMLResponse)
def run_detail(rid: int, request: Request, _=Depends(auth)):
    run = db.q1("SELECT * FROM identity_runs WHERE id=?", (rid,))
    if not run:
        raise HTTPException(404)
    scores = db.q("SELECT * FROM identity_scores WHERE run_id=? ORDER BY score DESC", (rid,))
    tp = db.q1("SELECT * FROM profiles WHERE user_id=?", (run["target_uid"],))
    return templates.TemplateResponse("run_detail.html",
        {"request": request, "run": run, "scores": scores, "tp": tp})


@app.post("/runs/{rid}/delete")
def run_delete(rid: int, _=Depends(auth)):
    db.delete_run(rid)
    return RedirectResponse("/runs", 303)


# ---------- アカウント台帳 ----------

@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request, _=Depends(auth)):
    return templates.TemplateResponse("accounts.html",
        {"request": request, "rows": db.known(1000)})


@app.post("/accounts/add")
def accounts_add(token: str = Form(...), note: str = Form(""),
                 deleted: str = Form(""), _=Depends(auth)):
    t = token.strip().lstrip("@")
    try:
        uid = identity.resolve_uid(ig.client(), db, t)
    except Exception:
        uid = t
    name = identity.name_of(db, uid, "" if t.isdigit() else t)
    db.add_known(uid, name, note=note, source="manual",
                 deleted=bool(deleted) or identity.is_deleted(db, uid))
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/archive")
def accounts_archive(uid: str, _=Depends(auth)):
    def job():
        try:
            ig.archive_account(db, uid)
        except Exception as e:
            db.log(uid, "archive_error", {"error": repr(e)})
    watcher.run_bg(job)
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/deleted")
def accounts_deleted(uid: str, _=Depends(auth)):
    row = db.known_get(uid)
    db.set_known_deleted(uid, not (row and row["deleted"]))
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/delete")
def accounts_delete(uid: str, _=Depends(auth)):
    db.del_known(uid)
    return RedirectResponse("/accounts", 303)


# ---------- ターゲット ----------

@app.get("/target/{uid}", response_class=HTMLResponse)
def target_detail(uid: str, request: Request, _=Depends(auth)):
    p = db.q1("SELECT * FROM profiles WHERE user_id=?", (uid,))
    posts = db.q("SELECT * FROM posts WHERE user_id=? ORDER BY taken_at DESC LIMIT 60", (uid,))
    rel = db.q("""SELECT * FROM relationship_events WHERE from_user_id=?
        ORDER BY observed_at DESC LIMIT 100""", (uid,))
    snap = db.q("""SELECT * FROM profile_snapshots WHERE user_id=?
        ORDER BY taken_at DESC LIMIT 100""", (uid,))
    return templates.TemplateResponse("target.html",
        {"request": request, "uid": uid, "p": p, "posts": posts, "rel": rel, "snap": snap})


@app.get("/forensics", response_class=HTMLResponse)
def forensics_page(request: Request, _=Depends(auth)):
    rows = db.q("SELECT * FROM forensics ORDER BY ts DESC LIMIT 300")
    return templates.TemplateResponse("activity.html",
        {"request": request, "events": rows, "kind": "forensics"})


@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request, kind: str = "", _=Depends(auth)):
    if kind:
        rows = db.q("SELECT * FROM events WHERE kind LIKE ? ORDER BY ts DESC LIMIT 500",
                    (f"%{kind}%",))
    else:
        rows = db.q("SELECT * FROM events ORDER BY ts DESC LIMIT 500")
    return templates.TemplateResponse("activity.html",
        {"request": request, "events": rows, "kind": kind})


@app.get("/dms", response_class=HTMLResponse)
def dms(request: Request, thread: str = "", _=Depends(auth)):
    threads = db.q("SELECT * FROM dm_threads ORDER BY last_activity_at DESC LIMIT 200")
    msgs = []
    if thread:
        msgs = db.q("""SELECT * FROM dm_messages WHERE thread_id=?
            ORDER BY timestamp ASC LIMIT 500""", (thread,))
    return templates.TemplateResponse("dms.html",
        {"request": request, "threads": threads, "msgs": msgs, "thread": thread})


@app.get("/targets", response_class=HTMLResponse)
def targets_page(request: Request, _=Depends(auth)):
    return templates.TemplateResponse("targets.html",
        {"request": request, "targets": db.targets(),
         "candidates": get_cfg().get("candidates", [])})


@app.post("/targets/add")
def targets_add(handle: str = Form(...), _=Depends(auth)):
    h = handle.strip().lstrip("@")
    try:
        uid = identity.resolve_uid(ig.client(), db, h)
    except Exception:
        uid = h
    db.add_target(uid, h)
    db.add_known(uid, h, source="target")
    return RedirectResponse("/targets", 303)


@app.post("/target/{uid}/archive")
def target_archive(uid: str, _=Depends(auth)):
    def job():
        jid = db.start_job(f"archive:{uid}")
        try:
            ig.full_archive(db, uid)
            db.finish_job(jid, "ok")
        except Exception as e:
            db.finish_job(jid, "error", repr(e) + "\n\n" + traceback.format_exc())
    watcher.run_bg(job)
    return RedirectResponse(f"/target/{uid}", 303)


@app.post("/target/{uid}/monitor")
def target_monitor(uid: str, _=Depends(auth)):
    row = db.q1("SELECT monitor FROM targets WHERE user_id=?", (uid,))
    newv = 0 if row and row["monitor"] else 1
    with db.tx() as c:
        c.execute("UPDATE targets SET monitor=? WHERE user_id=?", (newv, uid))
    return RedirectResponse("/targets", 303)


@app.post("/candidates/add")
def candidates_add(handle: str = Form(...), _=Depends(auth)):
    h = handle.strip().lstrip("@")
    cur = get_cfg().get("candidates", [])
    if h and h not in cur:
        config.save_sections({"candidates": cur + [h]})
    return RedirectResponse("/targets", 303)


# ---------- 設定 ----------

def _coerce(old, new):
    if isinstance(old, bool):
        return new in ("on", "1", "true", "True")
    if isinstance(old, int):
        try:
            return int(float(new))
        except Exception:
            return old
    if isinstance(old, float):
        try:
            return float(new)
        except Exception:
            return old
    return new


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, msg: str = "", err: str = "", _=Depends(auth)):
    cfg = get_cfg()
    sections = {s: {k: v for k, v in cfg.get(s, {}).items() if not k.startswith("_")}
                for s in EDITABLE if isinstance(cfg.get(s), dict)}
    return templates.TemplateResponse("settings.html",
        {"request": request, "sections": sections, "ig": cfg["instagram"],
         "env_user": cfg["web"].get("_env_user", ""),
         "targets": "\n".join(cfg.get("targets", [])),
         "candidates": "\n".join(cfg.get("candidates", [])),
         "settings_file": config._settings_path(), "msg": msg, "err": err})


@app.post("/settings")
async def settings_save(request: Request, _=Depends(auth)):
    form = await request.form()
    base = get_cfg()
    over = {}
    for key, val in form.items():
        if key.startswith("__") or key.startswith("ig_"):
            continue
        parts = key.split(".")
        node, cur = base, over
        for p in parts[:-1]:
            node = node.get(p, {}) or {}
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = _coerce(node.get(parts[-1]), val)

    igd = {}
    for f_key, c_key in (("ig_user", "username"), ("ig_pass", "password"),
                         ("ig_session_b64", "session_b64")):
        if f_key in form:
            igd[c_key] = (form.get(f_key) or "").strip()
    over["instagram"] = igd
    over["targets"] = [l.strip().lstrip("@")
                       for l in form.get("__targets", "").splitlines() if l.strip()]
    over["candidates"] = [l.strip().lstrip("@")
                          for l in form.get("__candidates", "").splitlines() if l.strip()]
    config.save_sections(over)

    if igd.get("session_b64"):
        config.write_session_file(igd["session_b64"], get_cfg()["instagram"]["session_file"])
    ig.reset_client()
    return RedirectResponse("/settings?msg=" + quote("設定を保存しました"), 303)


# ---------- Instagram 接続 ----------

@app.post("/ig/test")
def ig_test(_=Depends(auth)):
    try:
        cl = ig.client()
        me = cl.account_info()
        return RedirectResponse("/settings?msg=" + quote(f"接続OK: @{me.username}"), 303)
    except Exception as e:
        return RedirectResponse("/settings?err=" + quote(repr(e)), 303)


@app.post("/ig/login")
def ig_login(user: str = Form(""), password: str = Form(""), _=Depends(auth)):
    cfg = get_cfg()
    u = (user or "").strip() or cfg["instagram"].get("username") or ""
    p = password or cfg["instagram"].get("password") or ""
    sf = cfg["instagram"]["session_file"]
    try:
        ig.reset_client()
        ig.login_now(u, p, sf)
        with open(sf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        config.save_sections({"instagram": {"username": u, "password": p, "session_b64": b64}})
        ig.reset_client()
        return RedirectResponse("/settings?msg=" + quote("ログイン成功・セッションを保存しました"), 303)
    except Exception as e:
        return RedirectResponse("/settings?err=" + quote(repr(e)), 303)


@app.post("/ig/logout")
def ig_logout(_=Depends(auth)):
    cfg = get_cfg()
    sf = cfg["instagram"]["session_file"]
    try:
        if os.path.exists(sf):
            os.remove(sf)
    except Exception:
        pass
    config.save_sections({"instagram": {"session_b64": ""}})
    ig.reset_client()
    return RedirectResponse("/settings?msg=" + quote("ログアウトしました（envのB64があると再復元されます）"), 303)


# ---------- リンク追跡（公開ルート） ----------

def _record_hit(request: Request, code: str, link):
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    p = linktrack.parse_ua(ua)
    g = linktrack.geo(ip)
    hdrs = {k.lower(): v for k, v in request.headers.items()
            if k.lower() in ("accept", "accept-language", "referer", "sec-ch-ua",
                             "sec-ch-ua-mobile", "sec-ch-ua-platform", "dnt",
                             "accept-encoding", "pragma", "cache-control",
                             "x-requested-with", "sec-fetch-site", "sec-fetch-mode")}
    hid = db.add_hit({
        "code": code, "ts": now_iso(), "ip": ip, "ua": ua,
        "lang": request.headers.get("accept-language", ""),
        "referer": request.headers.get("referer", ""),
        "accept": request.headers.get("accept", ""),
        "headers": _json.dumps(hdrs, ensure_ascii=False),
        "query": str(request.url.query)[:500],
        "country": g.get("country"), "country_code": g.get("country_code"),
        "region": g.get("region"), "city": g.get("city"), "zip": g.get("zip"),
        "isp": g.get("isp"), "org": g.get("org"), "asn": g.get("asn"),
        "tz": g.get("tz"), "lat": g.get("lat"), "lon": g.get("lon"),
        "device": p["device"], "os": p["os"], "browser": p["browser"],
        "inapp": p["inapp"], "is_bot": p["is_bot"], "is_mobile": p["is_mobile"],
        "is_proxy": g.get("is_proxy"), "is_hosting": g.get("is_hosting"),
    })
    db.bump_link(code)
    return hid


def now_iso():
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


@app.get("/l/{code}")
def link_hit(code: str, request: Request):
    link = db.link_get(code)
    if not link or not link["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    hid = _record_hit(request, code, link)
    if link["mode"] == "redirect" and link["dest"]:
        return RedirectResponse(link["dest"], 302)
    return templates.TemplateResponse("link_land.html",
        {"request": request, "code": code, "hit_id": hid, "link": link,
         "dest": link["dest"] or ""})


@app.post("/l/{code}/x")
async def link_extra(code: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    hid = body.get("hit_id")
    if not hid:
        return {"ok": False}
    f = {}
    for k in ("screen", "tz", "platform", "cores", "mem", "touch"):
        if body.get(k) not in (None, ""):
            f[k] = body[k]
    if body.get("gps_lat") is not None:
        f["gps_lat"] = body.get("gps_lat")
        f["gps_lon"] = body.get("gps_lon")
        f["gps_acc"] = body.get("gps_acc")
    if f:
        db.update_hit(int(hid), **f)
    return {"ok": True}


@app.get("/l/{code}/go")
def link_go(code: str):
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    return RedirectResponse(link["dest"] or "/", 302)


@app.get("/link/me", response_class=HTMLResponse)
def link_me(request: Request):
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    p = linktrack.parse_ua(ua)
    g = linktrack.geo(ip)
    return templates.TemplateResponse("link_me.html",
        {"request": request, "ip": ip, "ua": ua, "p": p, "g": g})


# ---------- リンク管理 ----------

@app.get("/links", response_class=HTMLResponse)
def links_page(request: Request, _=Depends(auth)):
    return templates.TemplateResponse("links.html",
        {"request": request, "links": db.links(500), "base": str(request.base_url).rstrip("/")})


@app.post("/links/add")
def links_add(name: str = Form(""), dest: str = Form(""), note: str = Form(""),
              mode: str = Form("page"), _=Depends(auth)):
    code = _new_code()
    db.add_link(code, name or code, dest.strip(), note, mode if mode in ("page", "geo", "redirect") else "page")
    return RedirectResponse(f"/link/{code}", 303)


@app.get("/link/{code}", response_class=HTMLResponse)
def link_detail(code: str, request: Request, bots: str = "", _=Depends(auth)):
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    rows = db.hits(code, include_bots=bool(bots), limit=500)
    hits = [dict(r) for r in rows]
    stats = linktrack.summarize(hits)
    points = [{"lat": h["lat"], "lon": h["lon"], "city": h["city"],
               "ts": h["ts"], "ip": h["ip"], "gps": False}
              for h in hits if h.get("lat") is not None]
    points += [{"lat": h["gps_lat"], "lon": h["gps_lon"], "city": h["city"],
                "ts": h["ts"], "ip": h["ip"], "gps": True}
               for h in hits if h.get("gps_lat") is not None]
    return templates.TemplateResponse("link_detail.html",
        {"request": request, "link": link, "hits": hits, "stats": stats,
         "points_json": _json.dumps(points, ensure_ascii=False),
         "base": str(request.base_url).rstrip("/"), "bots": bots,
         "net": {h["id"]: linktrack.network_label(h) for h in hits}})


@app.post("/link/{code}/toggle")
def link_toggle(code: str, _=Depends(auth)):
    l = db.link_get(code)
    if l:
        db.set_link_active(code, not l["active"])
    return RedirectResponse(f"/link/{code}", 303)


@app.post("/link/{code}/delete")
def link_delete(code: str, _=Depends(auth)):
    db.del_link(code)
    return RedirectResponse("/links", 303)


@app.post("/link/{code}/hits/clear")
def link_clear(code: str, _=Depends(auth)):
    db.del_hits(code)
    return RedirectResponse(f"/link/{code}", 303)


@app.post("/link/{code}/hit/{hid}/bot")
def link_hit_bot(code: str, hid: int, _=Depends(auth)):
    row = db.q1("SELECT is_bot FROM link_hits WHERE id=?", (hid,))
    if row:
        db.update_hit(hid, is_bot=0 if row["is_bot"] else 1)
    return RedirectResponse(f"/link/{code}?bots=1", 303)


# ---------- API / エクスポート ----------

@app.get("/api/summary")
def api_summary(_=Depends(auth)):
    return {
        "targets": len(db.targets()),
        "known": db.q1("SELECT COUNT(*) c FROM known_accounts")["c"],
        "runs": db.q1("SELECT COUNT(*) c FROM identity_runs")["c"],
        "links": db.q1("SELECT COUNT(*) c FROM links")["c"],
        "events": db.q1("SELECT COUNT(*) c FROM events")["c"],
    }


@app.get("/api/events")
def api_events(limit: int = 500, _=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]


@app.get("/export.json")
def export_json(_=Depends(auth)):
    return {
        "known_accounts": [dict(r) for r in db.q("SELECT * FROM known_accounts")],
        "saved_pairs": [dict(r) for r in db.q("SELECT * FROM saved_pairs")],
        "profiles": [dict(r) for r in db.q("SELECT * FROM profiles")],
        "runs": [dict(r) for r in db.q("SELECT * FROM identity_runs")],
        "scores": [dict(r) for r in db.q("SELECT * FROM identity_scores")],
    }


@app.post("/import")
async def import_json(request: Request, _=Depends(auth)):
    form = await request.form()
    try:
        doc = _json.loads(form.get("payload") or "{}")
    except Exception:
        doc = {}
    for k in doc.get("known_accounts", []):
        db.add_known(k["user_id"], k.get("username") or "", k.get("note") or "",
                     k.get("source") or "import", k.get("deleted"))
    for p in doc.get("saved_pairs", []):
        db.save_pair(p["target_uid"], p.get("target_username") or "",
                     p["candidate_uid"], p.get("candidate_username") or "",
                     p.get("note") or "")
    for p in doc.get("profiles", []):
        db.upsert_profile(p)
    return RedirectResponse("/accounts", 303)


@app.get("/healthz")
def healthz():
    return {"ok": True}