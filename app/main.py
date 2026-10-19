"""FastAPI アプリ本体。"""
import os
import secrets
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import load, get as get_cfg
from .database import DB
from . import instagram as ig
from . import identity, watcher, forensics

load()
cfg = get_cfg()
db = DB(cfg["storage"]["db_path"])

app = FastAPI(title="Uraaka Tracker")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
import json as _json
templates.env.filters["fromjson"] = _json.loads
security = HTTPBasic()


def auth(cred: HTTPBasicCredentials = Depends(security)):
    ok_u = secrets.compare_digest(cred.username, cfg["web"]["user"])
    ok_p = secrets.compare_digest(cred.password, cfg["web"]["password"])
    if not (ok_u and ok_p):
        raise HTTPException(401, "unauthorized", {"WWW-Authenticate": "Basic"})
    return cred.username


@app.on_event("startup")
def _startup():
    for h in cfg.get("targets", []):
        try:
            uid = ig.client().user_id_from_username(h)
            db.add_target(uid, h)
        except Exception:
            pass
    if os.getenv("RUN_SCHEDULER", "1") == "1":
        watcher.start(db)


# ---------- 画面 ----------

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


@app.get("/identity", response_class=HTMLResponse)
def identity_page(request: Request, _=Depends(auth)):
    runs = db.q("SELECT * FROM identity_runs ORDER BY id DESC LIMIT 10")
    latest = db.q1("SELECT MAX(id) m FROM identity_runs")
    scores = []
    if latest and latest["m"]:
        scores = db.q("""SELECT * FROM identity_scores WHERE run_id=?
            ORDER BY score DESC LIMIT 50""", (latest["m"],))
    else:
        scores = db.q("""SELECT * FROM identity_scores ORDER BY computed_at DESC, score DESC LIMIT 50""")
    return templates.TemplateResponse("identity.html",
        {"request": request, "scores": scores, "runs": runs,
         "cands": cfg.get("candidates", []), "targets": db.targets()})


@app.post("/identity/run")
def identity_run(target: str = Form(...), candidates: str = Form(""),
                 auto: str = Form(""), _=Depends(auth)):
    cl = ig.client()
    t = target.strip().lstrip("@")
    tuid = str(cl.user_id_from_username(t) if not t.isdigit() else t)
    cands = [c.strip().lstrip("@") for c in candidates.replace(",", "\n").split() if c.strip()]
    cids = [str(cl.user_id_from_username(c) if not c.isdigit() else c) for c in cands]
    auto_scan = bool(auto) or cfg["identity"].get("auto_scan", True)

    def job():
        rid = db.start_run(tuid, t)
        try:
            identity.run_identify(db, tuid, cids, auto_scan=auto_scan, run_id=rid)
            db.update_run(rid, status="ok")
        except Exception as e:
            db.update_run(rid, status="error", log=str(e))

    watcher.run_bg(job)
    return RedirectResponse("/identity", 303)


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
        {"request": request, "targets": db.targets(), "candidates": cfg.get("candidates", [])})


@app.post("/targets/add")
def targets_add(handle: str = Form(...), _=Depends(auth)):
    uid = ig.client().user_id_from_username(handle.lstrip("@"))
    db.add_target(str(uid), handle.lstrip("@"))
    return RedirectResponse("/targets", 303)


@app.post("/target/{uid}/archive")
def target_archive(uid: str, _=Depends(auth)):
    def job():
        jid = db.start_job(f"archive:{uid}")
        try:
            ig.full_archive(db, uid)
            db.finish_job(jid, "ok")
        except Exception as e:
            db.finish_job(jid, "error", str(e))
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
    h = handle.lstrip("@")
    if h and h not in cfg.get("candidates", []):
        cfg.setdefault("candidates", []).append(h)
    return RedirectResponse("/targets", 303)


# ---------- API ----------

@app.get("/api/summary")
def api_summary(_=Depends(auth)):
    return {
        "targets": len(db.targets()),
        "posts": db.q1("SELECT COUNT(*) c FROM posts")["c"],
        "events": db.q1("SELECT COUNT(*) c FROM events")["c"],
        "dm_messages": db.q1("SELECT COUNT(*) c FROM dm_messages")["c"],
        "forensics": db.q1("SELECT COUNT(*) c FROM forensics")["c"],
    }
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/events")
def api_events(limit: int = 500, _=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]


@app.get("/api/forensics")
def api_forensics(limit: int = 500, _=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM forensics ORDER BY ts DESC LIMIT ?", (limit,))]