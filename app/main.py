"""FastAPI アプリ本体。設定・記録はすべてWebで完結。"""
import os, secrets, json as _json
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config
from .config import load, get as get_cfg
from .database import DB
from . import instagram as ig
from . import identity, watcher, forensics

load()
db = DB(get_cfg()["storage"]["db_path"])

app = FastAPI(title="Uraaka Tracker")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = _json.loads
security = HTTPBasic()

EDITABLE = ["web", "instagram", "identity", "monitor", "archive", "storage"]


def auth(cred: HTTPBasicCredentials = Depends(security)):
    cfg = get_cfg()
    if not (secrets.compare_digest(cred.username, cfg["web"]["user"]) and
            secrets.compare_digest(cred.password, cfg["web"]["password"])):
        raise HTTPException(401, "unauthorized", {"WWW-Authenticate": "Basic"})
    return cred.username


def _tokens(raw):
    return [t.strip().lstrip("@") for t in (raw or "").replace(",", "\n").split() if t.strip()]


@app.on_event("startup")
def _startup():
    for h in get_cfg().get("targets", []):
        try:
            uid = ig.client().user_id_from_username(h)
            db.add_target(uid, h)
            db.add_known(str(uid), h, source="target")
        except Exception:
            pass
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


# ---------- 特定（メイン） ----------

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
    cl = ig.client()
    toks = _tokens(candidates)
    t_uid = identity.resolve_uid(cl, db, target)
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
            db.update_run(rid, status="error", log=str(e))
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
            db.update_run(rid, status="error", log=str(e))
    watcher.run_bg(job)
    return RedirectResponse(f"/runs/{rid}", 303)


@app.post("/pairs/{pid}/delete")
def pair_delete(pid: int, _=Depends(auth)):
    db.del_pair(pid)
    return RedirectResponse("/identity", 303)


# ---------- 履歴（記録） ----------

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


# ---------- アカウント台帳（ID控え） ----------

@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request, _=Depends(auth)):
    return templates.TemplateResponse("accounts.html",
        {"request": request, "rows": db.known(1000)})


@app.post("/accounts/add")
def accounts_add(token: str = Form(...), note: str = Form(""),
                 deleted: str = Form(""), _=Depends(auth)):
    cl = ig.client()
    t = token.strip().lstrip("@")
    try:
        uid = identity.resolve_uid(cl, db, t)
    except Exception:
        if t.isdigit():
            uid = t
        else:
            raise HTTPException(400, "IDでもユーザー名でも解決できません")
    name = identity.name_of(db, uid, t if not t.isdigit() else "")
    db.add_known(uid, name, note=note, source="manual",
                 deleted=bool(deleted) or identity.is_deleted(db, uid))
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/archive")
def accounts_archive(uid: str, _=Depends(auth)):
    def job():
        ig.archive_account(db, uid)
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
    cl = ig.client()
    uid = identity.resolve_uid(cl, db, handle)
    db.add_target(uid, handle.lstrip("@"))
    db.add_known(uid, handle.lstrip("@"), source="target")
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
def settings_page(request: Request, _=Depends(auth)):
    cfg = get_cfg()
    sections = {s: cfg.get(s, {}) for s in EDITABLE if isinstance(cfg.get(s), dict)}
    return templates.TemplateResponse("settings.html",
        {"request": request, "sections": sections,
         "targets": "\n".join(cfg.get("targets", [])),
         "candidates": "\n".join(cfg.get("candidates", [])),
         "settings_file": config._settings_path()})


@app.post("/settings")
async def settings_save(request: Request, _=Depends(auth)):
    form = await request.form()
    base = get_cfg()
    over = {}
    for key, val in form.items():
        if key.startswith("__"):
            continue
        parts = key.split(".")
        node, cur = base, over
        for p in parts[:-1]:
            node = node.get(p, {}) or {}
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = _coerce(node.get(parts[-1]), val)
    over["targets"] = [l.strip().lstrip("@")
                       for l in form.get("__targets", "").splitlines() if l.strip()]
    over["candidates"] = [l.strip().lstrip("@")
                          for l in form.get("__candidates", "").splitlines() if l.strip()]
    config.save_sections(over)
    return RedirectResponse("/settings", 303)


# ---------- API / エクスポート ----------

@app.get("/api/summary")
def api_summary(_=Depends(auth)):
    return {
        "targets": len(db.targets()),
        "known": db.q1("SELECT COUNT(*) c FROM known_accounts")["c"],
        "runs": db.q1("SELECT COUNT(*) c FROM identity_runs")["c"],
        "posts": db.q1("SELECT COUNT(*) c FROM posts")["c"],
        "events": db.q1("SELECT COUNT(*) c FROM events")["c"],
    }


@app.get("/api/events")
def api_events(limit: int = 500, _=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]


@app.get("/api/forensics")
def api_forensics(limit: int = 500, _=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM forensics ORDER BY ts DESC LIMIT ?", (limit,))]


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