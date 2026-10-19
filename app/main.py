"""FastAPI アプリ本体。Cookieセッション認証 + マルチテナント完全分離版。"""
import os, secrets, random, string, base64, json as _json, traceback, shutil
from urllib.parse import quote

from fastapi import FastAPI, APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, tenancy, users
from .config import get as get_cfg
from . import instagram as ig
from . import identity, watcher, forensics, linktrack, together

config.load()
users.init()
db = tenancy.db

app = FastAPI(title="Uraaka Tracker", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = _json.loads

COOKIE_USER = "igt_sid"
COOKIE_ADMIN = "igt_admin"
SECURE_COOKIE = os.getenv("COOKIE_SECURE", "1") != "0"
ADMIN_PATH = "/" + (os.getenv("ADMIN_PATH", "admin").strip("/") or "admin")
EDITABLE = ["identity", "monitor", "archive"]
SIGNUP_OPEN = os.getenv("SIGNUP_OPEN", "1") != "0"

admin = APIRouter(prefix=ADMIN_PATH)


# ---------- 共通 ----------

def render(name, request, **ctx):
    ctx["request"] = request
    ctx["me"] = getattr(request.state, "user_name", None)
    ctx["real_user"] = getattr(request.state, "real_user", None)
    ctx["is_admin"] = getattr(request.state, "is_admin", False)
    ctx["admin_realm"] = getattr(request.state, "admin_ok", False)
    ctx["must_change"] = getattr(request.state, "must_change", False)
    ctx["impersonating"] = bool(ctx["me"] and ctx["real_user"] and ctx["me"] != ctx["real_user"])
    ctx["admin_path"] = ADMIN_PATH
    ctx["signup_open"] = SIGNUP_OPEN
    return templates.TemplateResponse(name, ctx)


def _wants_json(request):
    p = request.url.path
    if p.startswith("/api/") or p in ("/export.json", "/import"):
        return True
    acc = request.headers.get("accept", "")
    return "application/json" in acc and "text/html" not in acc


def _safe_next(n, default="/"):
    if not n or not n.startswith("/") or n.startswith("//"):
        return default
    return n


def _ip(request):
    return linktrack.client_ip(request)


def _ua(request):
    return request.headers.get("user-agent", "")


def _set_cookie(resp, name, token):
    resp.set_cookie(name, token, max_age=users.SESSION_DAYS * 86400, httponly=True,
                    secure=SECURE_COOKIE, samesite="lax", path="/")


def _activate(request, row, admin_ok=False):
    real = row["username"]
    is_admin = row["role"] == "admin"
    effective = real
    if is_admin:
        want = users.norm(request.cookies.get("view_as") or "")
        r2 = users.get(want) if want else None
        if r2 and not r2["disabled"]:
            effective = want
    tenancy.set_current(effective)
    request.state.user_name = effective
    request.state.real_user = real
    request.state.is_admin = is_admin
    request.state.admin_ok = admin_ok
    request.state.must_change = bool(row["must_change"]) and effective == real
    return effective


@app.middleware("http")
async def harden(request: Request, call_next):
    resp = await call_next(request)
    if not request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "private, no-store, must-revalidate"
        resp.headers["Vary"] = "Cookie"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        if not request.url.path.startswith("/l/"):
            resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(Exception)
async def _debug_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    try:
        if tenancy.get_current():
            db.log("system", "unhandled_error",
                   {"path": str(request.url.path), "error": repr(exc)})
    except Exception:
        pass
    return PlainTextResponse(f"PATH: {request.url.path}\n\n{tb}", status_code=500)


# ---------- 認証依存 ----------

async def auth(request: Request) -> str:
    tok = request.cookies.get(COOKIE_USER)
    row = users.resolve_session(tok, "user")
    if row:
        return _activate(request, row)

    hdr = request.headers.get("authorization", "")
    if hdr.lower().startswith("basic "):
        try:
            raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8")
            un, _, pw = raw.partition(":")
        except Exception:
            un = pw = ""
        if users.verify_user(un, pw):
            return _activate(request, users.get(un))

    if _wants_json(request):
        raise HTTPException(401, "unauthorized")
    raise HTTPException(303, headers={
        "Location": "/login?next=" + quote(str(request.url.path))})


async def admin_auth(request: Request) -> str:
    tok = request.cookies.get(COOKIE_ADMIN)
    row = users.resolve_session(tok, "admin")
    if not row:
        if _wants_json(request):
            raise HTTPException(401, "admin login required")
        raise HTTPException(303, headers={
            "Location": f"{ADMIN_PATH}/login?next=" + quote(str(request.url.path))})
    return _activate(request, row, admin_ok=True)


# ---------- ログイン / 登録 / ログアウト ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "", msg: str = "", err: str = ""):
    return render("login.html", request, next=_safe_next(next), msg=msg, err=err)


@app.post("/login")
def login_post(request: Request, username: str = Form(""), password: str = Form(""),
               next: str = Form("/")):
    ip = _ip(request)
    key = "u:" + ip
    if users.is_throttled(key):
        return RedirectResponse("/login?err=" + quote("試行回数が多すぎます。少し待ってください"), 303)
    info = users.verify_user(username, password)
    if not info:
        users.bump_fail(key)
        users.audit(username, "login_fail", {"ip": ip})
        return RedirectResponse("/login?next=" + quote(_safe_next(next)) +
                                "&err=" + quote("ユーザー名かパスワードが違います"), 303)
    users.clear_fail(key)
    users.audit(info["username"], "login_ok", {"ip": ip, "ua": _ua(request)[:120]})
    tok = users.new_session(info["username"], "user", ip, _ua(request))
    r = RedirectResponse(_safe_next(next), 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, msg: str = "", err: str = ""):
    return render("signup.html", request, msg=msg, err=err)


@app.post("/signup")
def signup_post(request: Request, username: str = Form(""), password: str = Form(""),
                password2: str = Form("")):
    if not SIGNUP_OPEN:
        return RedirectResponse("/signup?err=" + quote("現在、新規登録は停止しています"), 303)
    ip = _ip(request)
    key = "s:" + ip
    if users.is_throttled(key, limit=10):
        return RedirectResponse("/signup?err=" + quote("試行回数が多すぎます"), 303)
    if password != password2:
        return RedirectResponse("/signup?err=" + quote("パスワードが一致しません"), 303)
    try:
        users.create(username, password, role="user", note="self signup")
    except ValueError as e:
        users.bump_fail(key)
        return RedirectResponse("/signup?err=" + quote(str(e)), 303)
    u = users.norm(username)
    users.audit(u, "signup", {"ip": ip})
    tok = users.new_session(u, "user", ip, _ua(request))
    r = RedirectResponse("/", 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


@app.post("/logout")
def logout_post(request: Request):
    users.delete_session(request.cookies.get(COOKIE_USER))
    r = RedirectResponse("/login?msg=" + quote("ログアウトしました"), 303)
    r.delete_cookie(COOKIE_USER, path="/")
    return r


@app.get("/logout")
def logout_get(request: Request):
    return logout_post(request)


@app.on_event("startup")
def _startup():
    users.bootstrap_admin()
    users.purge_expired()
    for t in users.list_usernames():
        tenancy.set_current(t)
        cfg = get_cfg()
        if not cfg["instagram"].get("username"):
            continue
        for h in cfg.get("targets", []):
            try:
                uid = ig.client().user_id_from_username(h)
            except Exception as e:
                print(f"[startup] {t} target解決失敗:", h, e)
                uid = h
            try:
                db.add_target(uid, h)
                db.add_known(str(uid), h, source="target")
            except Exception:
                pass
    if os.getenv("RUN_SCHEDULER", "1") == "1":
        watcher.start()


# ---------- 自分のアカウント ----------

@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    real = request.state.real_user
    toks = request.cookies.get(COOKIE_USER) or ""
    cur = users.sid_of(toks)
    sess = [dict(s) | {"short": s["sid"][:8],
                       "current": s["sid"] == cur,
                       "admin_short": None} for s in users.list_sessions(real, "user")]
    adms = [dict(s) | {"short": s["sid"][:8]} for s in users.list_sessions(real, "admin")]
    return render("account.html", request, msg=msg, err=err,
                  role=users.role_of(real),
                  env_admin=bool(users.env_admin()[0] == real),
                  breakglass=bool(users.env_breakglass()),
                  sessions=sess, admin_sessions=adms,
                  session_days=users.SESSION_DAYS)


@app.post("/account/password")
def account_password(request: Request, cur: str = Form(""), new: str = Form(""),
                     new2: str = Form(""), u=Depends(auth)):
    real = request.state.real_user
    if new != new2:
        return RedirectResponse("/account?err=" + quote("新しいパスワードが一致しません"), 303)
    if not users.check_password(real, cur):
        return RedirectResponse("/account?err=" + quote("現在のパスワードが違います"), 303)
    try:
        users.set_password(real, new, must_change=0)
    except ValueError as e:
        return RedirectResponse("/account?err=" + quote(str(e)), 303)
    tok = users.new_session(real, "user", _ip(request), _ua(request))
    users.audit(real, "password_changed", {})
    r = RedirectResponse("/account?msg=" + quote(
        "パスワードを変更し、他の全端末からログアウトしました"), 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


@app.post("/account/sessions/delete")
def account_session_delete(request: Request, sid: str = Form(...), u=Depends(auth)):
    real = request.state.real_user
    cur = users.sid_of(request.cookies.get(COOKIE_USER) or "")
    for s in users.list_sessions(real, "user"):
        if s["sid"].startswith(sid):
            if s["sid"] == cur:
                return RedirectResponse("/account?err=" + quote(
                    "使用中のセッションは「全端末ログアウト」で消してください"), 303)
            users.delete_session_by_sid(s["sid"])
            break
    return RedirectResponse("/account?msg=" + quote("セッションを削除しました"), 303)


@app.post("/account/logout-all")
def account_logout_all(request: Request, u=Depends(auth)):
    real = request.state.real_user
    users.delete_sessions(real, "user")
    tok = users.new_session(real, "user", _ip(request), _ua(request))
    users.audit(real, "logout_all", {})
    r = RedirectResponse("/account?msg=" + quote("全端末からログアウトしました"), 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


# ---------- 管理（別パス・別Cookie） ----------

@admin.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request, next: str = "", msg: str = "", err: str = ""):
    return render("admin_login.html", request, next=_safe_next(next, ADMIN_PATH + "/"),
                  msg=msg, err=err)


@admin.post("/login")
def admin_login_post(request: Request, username: str = Form(""), password: str = Form(""),
                     next: str = Form("")):
    ip = _ip(request)
    key = "a:" + ip
    if users.is_throttled(key, limit=10):
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" +
                                quote("試行回数が多すぎます"), 303)
    if not users.verify_admin(username, password):
        users.bump_fail(key)
        users.audit(username, "admin_login_fail", {"ip": ip})
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" +
                                quote("管理者として認証できません"), 303)
    users.clear_fail(key)
    u = users.norm(username)
    users.audit(u, "admin_login_ok", {"ip": ip})
    tok = users.new_session(u, "admin", ip, _ua(request))
    r = RedirectResponse(_safe_next(next, ADMIN_PATH + "/"), 303)
    _set_cookie(r, COOKIE_ADMIN, tok)
    return r


@admin.post("/logout")
def admin_logout(request: Request):
    users.delete_session(request.cookies.get(COOKIE_ADMIN))
    r = RedirectResponse(f"{ADMIN_PATH}/login?msg=" + quote("管理者ログアウトしました"), 303)
    r.delete_cookie(COOKIE_ADMIN, path="/")
    return r


def _tenant_size(t):
    p = os.path.join(tenancy.ROOT, t)
    tot = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                tot += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return tot


@admin.get("", response_class=HTMLResponse)
@admin.get("/", response_class=HTMLResponse)
def admin_page(request: Request, msg: str = "", err: str = "", u=Depends(admin_auth)):
    rows = []
    for r in users.list_users():
        d = dict(r)
        t = tenancy.safe_name(r["username"])
        try:
            tdb = tenancy.db_for(t)
            d["targets"] = tdb.q1("SELECT COUNT(*) c FROM targets")["c"]
            d["known"] = tdb.q1("SELECT COUNT(*) c FROM known_accounts")["c"]
            d["links"] = tdb.q1("SELECT COUNT(*) c FROM links")["c"]
            d["hits"] = tdb.q1("SELECT COUNT(*) c FROM link_hits")["c"]
            d["visitors"] = tdb.q1("SELECT COUNT(*) c FROM visitors")["c"]
        except Exception:
            d["targets"] = d["known"] = d["links"] = d["hits"] = d["visitors"] = "-"
        d["ig_user"] = config.load(t).get("instagram", {}).get("username") or ""
        d["size_mb"] = round(_tenant_size(t) / 1048576, 2)
        d["sessions"] = len(users.list_sessions(r["username"], "user"))
        rows.append(d)
    return render("admin.html", request, rows=rows, msg=msg, err=err,
                  env_user=users.env_admin()[0],
                  breakglass=bool(users.env_breakglass()),
                  tenant_root=tenancy.ROOT,
                  audits=users.list_audit(200),
                  me=request.state.real_user)


@admin.get("/audit", response_class=HTMLResponse)
def admin_audit(request: Request, u=Depends(admin_auth)):
    return render("admin_audit.html", request, rows=users.list_audit(1000),
                  tenant_root=tenancy.ROOT)


@admin.post("/password")
def admin_password(request: Request, cur: str = Form(""), new: str = Form(""),
                   new2: str = Form(""), u=Depends(admin_auth)):
    real = request.state.real_user
    if new != new2:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("一致しません"), 303)
    bg = users.env_breakglass()
    ok = users.verify_admin(real, cur) or (bg and cur == bg)
    if not ok:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("現在の管理者パスワードが違います"), 303)
    try:
        users.set_admin_password(real, new)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)
    tok = users.new_session(real, "admin", _ip(request), _ua(request))
    users.audit(real, "admin_password_changed", {})
    r = RedirectResponse(ADMIN_PATH + "/?msg=" + quote(
        "管理者パスワードを変更し、他の管理者セッションを無効化しました"), 303)
    _set_cookie(r, COOKIE_ADMIN, tok)
    return r


@admin.post("/users/create")
def admin_create(username: str = Form(...), password: str = Form(...),
                 role: str = Form("user"), note: str = Form(""),
                 must_change: str = Form(""), u=Depends(admin_auth)):
    try:
        users.create(username, password, role="admin" if role == "admin" else "user",
                     note=note, must_change=bool(must_change))
        users.audit(request_actor(u), "admin_create", {"username": username, "role": role})
        return RedirectResponse(ADMIN_PATH + "/?msg=" + quote(f"{username} を作成しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/password")
def admin_setpw(target: str, password: str = Form(...), u=Depends(admin_auth)):
    try:
        users.set_password(target, password, must_change=1)
        users.audit(u, "admin_setpw", {"username": target})
        return RedirectResponse(ADMIN_PATH + "/?msg=" +
                                quote(f"{target} のパスワードを再設定しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/adminpw")
def admin_set_adminpw(target: str, password: str = Form(...), u=Depends(admin_auth)):
    try:
        users.set_admin_password(target, password)
        users.audit(u, "admin_set_adminpw", {"username": target})
        return RedirectResponse(ADMIN_PATH + "/?msg=" +
                                quote(f"{target} の管理者パスワードを設定しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/role")
def admin_role(target: str, role: str = Form(...), u=Depends(admin_auth)):
    users.set_role(target, "admin" if role == "admin" else "user")
    users.audit(u, "admin_role", {"username": target, "role": role})
    return RedirectResponse(ADMIN_PATH + "/", 303)


@admin.post("/users/{target}/toggle")
def admin_toggle(target: str, u=Depends(admin_auth)):
    row = users.get(target)
    if row:
        users.set_disabled(target, not row["disabled"])
        users.audit(u, "admin_toggle", {"username": target, "disabled": bool(not row["disabled"])})
    return RedirectResponse(ADMIN_PATH + "/", 303)


@admin.post("/users/{target}/delete")
def admin_delete(target: str, purge: str = Form(""), u=Depends(admin_auth)):
    if users.norm(target) == users.norm(u):
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("自分自身は削除できません"), 303)
    users.delete(target)
    if purge:
        shutil.rmtree(os.path.join(tenancy.ROOT, tenancy.safe_name(target)),
                      ignore_errors=True)
        with tenancy._lock:
            tenancy._dbs.pop(tenancy.safe_name(target), None)
    users.audit(u, "admin_delete", {"username": target, "purge": bool(purge)})
    return RedirectResponse(ADMIN_PATH + "/?msg=" + quote(f"{target} を削除しました"), 303)


@admin.get("/switch")
def admin_switch(request: Request, to: str = "", back: str = "/", u=Depends(admin_auth)):
    r = RedirectResponse(_safe_next(back, ADMIN_PATH + "/"), 303)
    if to and users.get(to):
        r.set_cookie("view_as", users.norm(to), httponly=True, samesite="lax",
                     secure=SECURE_COOKIE, max_age=8 * 3600, path="/")
    else:
        r.delete_cookie("view_as", path="/")
    return r


def request_actor(_):
    return tenancy.get_current() or ""


app.include_router(admin)


# ---------- ダッシュボード ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, u=Depends(auth)):
    targets = []
    for t in db.targets():
        p = db.q1("SELECT * FROM profiles WHERE user_id=?", (t["user_id"],))
        snap = db.q("""SELECT * FROM profile_snapshots WHERE user_id=?
            ORDER BY taken_at DESC LIMIT 30""", (t["user_id"],))
        best = db.q1("""SELECT * FROM identity_scores WHERE uraaka_user_id=?
            ORDER BY computed_at DESC, score DESC LIMIT 1""", (t["user_id"],))
        targets.append({"t": t, "p": p, "snap": [dict(s) for s in snap], "best": best})
    events = db.q("SELECT * FROM events ORDER BY ts DESC LIMIT 40")
    return render("dashboard.html", request, targets=targets, events=events)


# ---------- 特定 ----------

@app.get("/identity", response_class=HTMLResponse)
def identity_page(request: Request, u=Depends(auth)):
    runs = db.q("SELECT * FROM identity_runs ORDER BY id DESC LIMIT 20")
    pairs = db.pairs(200)
    return render("identity.html", request, runs=runs, pairs=pairs,
                  candidates=get_cfg().get("candidates", []))


@app.post("/identity/run")
def identity_run(target: str = Form(...), candidates: str = Form(""),
                 auto: str = Form(""), archive: str = Form(""),
                 note: str = Form(""), u=Depends(auth)):
    toks = [t.strip().lstrip("@") for t in (candidates or "").replace(",", "\n").split()
            if t.strip()]
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
def pair_run(pid: int = Form(...), u=Depends(auth)):
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
def pair_delete(pid: int, u=Depends(auth)):
    db.del_pair(pid)
    return RedirectResponse("/identity", 303)


# ---------- 履歴 ----------

@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, u=Depends(auth)):
    return render("runs.html", request,
                  runs=db.q("SELECT * FROM identity_runs ORDER BY id DESC LIMIT 300"))


@app.get("/runs/{rid}", response_class=HTMLResponse)
def run_detail(rid: int, request: Request, u=Depends(auth)):
    run = db.q1("SELECT * FROM identity_runs WHERE id=?", (rid,))
    if not run:
        raise HTTPException(404)
    scores = db.q("SELECT * FROM identity_scores WHERE run_id=? ORDER BY score DESC", (rid,))
    tp = db.q1("SELECT * FROM profiles WHERE user_id=?", (run["target_uid"],))
    return render("run_detail.html", request, run=run, scores=scores, tp=tp)


@app.post("/runs/{rid}/delete")
def run_delete(rid: int, u=Depends(auth)):
    db.delete_run(rid)
    return RedirectResponse("/runs", 303)


# ---------- アカウント台帳 ----------

@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request, u=Depends(auth)):
    return render("accounts.html", request, rows=db.known(1000))


@app.post("/accounts/add")
def accounts_add(token: str = Form(...), note: str = Form(""),
                 deleted: str = Form(""), u=Depends(auth)):
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
def accounts_archive(uid: str, u=Depends(auth)):
    def job():
        try:
            ig.archive_account(db, uid)
        except Exception as e:
            db.log(uid, "archive_error", {"error": repr(e)})
    watcher.run_bg(job)
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/deleted")
def accounts_deleted(uid: str, u=Depends(auth)):
    row = db.known_get(uid)
    db.set_known_deleted(uid, not (row and row["deleted"]))
    return RedirectResponse("/accounts", 303)


@app.post("/accounts/{uid}/delete")
def accounts_delete(uid: str, u=Depends(auth)):
    db.del_known(uid)
    return RedirectResponse("/accounts", 303)


# ---------- ターゲット ----------

@app.get("/target/{uid}", response_class=HTMLResponse)
def target_detail(uid: str, request: Request, u=Depends(auth)):
    p = db.q1("SELECT * FROM profiles WHERE user_id=?", (uid,))
    posts = db.q("SELECT * FROM posts WHERE user_id=? ORDER BY taken_at DESC LIMIT 60", (uid,))
    rel = db.q("""SELECT * FROM relationship_events WHERE from_user_id=?
        ORDER BY observed_at DESC LIMIT 100""", (uid,))
    snap = db.q("""SELECT * FROM profile_snapshots WHERE user_id=?
        ORDER BY taken_at DESC LIMIT 100""", (uid,))
    return render("target.html", request, uid=uid, p=p, posts=posts, rel=rel, snap=snap)


@app.get("/forensics", response_class=HTMLResponse)
def forensics_page(request: Request, u=Depends(auth)):
    rows = db.q("SELECT * FROM forensics ORDER BY ts DESC LIMIT 300")
    return render("activity.html", request, events=rows, kind="forensics")


@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request, kind: str = "", u=Depends(auth)):
    if kind:
        rows = db.q("SELECT * FROM events WHERE kind LIKE ? ORDER BY ts DESC LIMIT 500",
                    (f"%{kind}%",))
    else:
        rows = db.q("SELECT * FROM events ORDER BY ts DESC LIMIT 500")
    return render("activity.html", request, events=rows, kind=kind)


@app.get("/dms", response_class=HTMLResponse)
def dms(request: Request, thread: str = "", u=Depends(auth)):
    threads = db.q("SELECT * FROM dm_threads ORDER BY last_activity_at DESC LIMIT 200")
    msgs = []
    if thread:
        msgs = db.q("""SELECT * FROM dm_messages WHERE thread_id=?
            ORDER BY timestamp ASC LIMIT 500""", (thread,))
    return render("dms.html", request, threads=threads, msgs=msgs, thread=thread)


@app.get("/targets", response_class=HTMLResponse)
def targets_page(request: Request, u=Depends(auth)):
    return render("targets.html", request, targets=db.targets(),
                  candidates=get_cfg().get("candidates", []))


@app.post("/targets/add")
def targets_add(handle: str = Form(...), u=Depends(auth)):
    h = handle.strip().lstrip("@")
    try:
        uid = identity.resolve_uid(ig.client(), db, h)
    except Exception:
        uid = h
    db.add_target(uid, h)
    db.add_known(uid, h, source="target")
    return RedirectResponse("/targets", 303)


@app.post("/target/{uid}/archive")
def target_archive(uid: str, u=Depends(auth)):
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
def target_monitor(uid: str, u=Depends(auth)):
    row = db.q1("SELECT monitor FROM targets WHERE user_id=?", (uid,))
    newv = 0 if row and row["monitor"] else 1
    with db.tx() as c:
        c.execute("UPDATE targets SET monitor=? WHERE user_id=?", (newv, uid))
    return RedirectResponse("/targets", 303)


@app.post("/candidates/add")
def candidates_add(handle: str = Form(...), u=Depends(auth)):
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
def settings_page(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    cfg = get_cfg()
    sections = {s: {k: v for k, v in cfg.get(s, {}).items() if not k.startswith("_")}
                for s in EDITABLE if isinstance(cfg.get(s), dict)}
    return render("settings.html", request, sections=sections, ig=cfg["instagram"],
                  tenant_dir=tenancy.tenant_dir(u),
                  env_user=os.getenv("IG_USER") or "",
                  targets="\n".join(cfg.get("targets", [])),
                  candidates="\n".join(cfg.get("candidates", [])),
                  msg=msg, err=err)


@app.post("/settings")
async def settings_save(request: Request, u=Depends(auth)):
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


@app.post("/ig/test")
def ig_test(u=Depends(auth)):
    try:
        me = ig.client().account_info()
        return RedirectResponse("/settings?msg=" + quote(f"接続OK: @{me.username}"), 303)
    except Exception as e:
        return RedirectResponse("/settings?err=" + quote(repr(e)), 303)


@app.post("/ig/login")
def ig_login(user: str = Form(""), password: str = Form(""), u=Depends(auth)):
    cfg = get_cfg()
    un = (user or "").strip() or cfg["instagram"].get("username") or ""
    pw = password or cfg["instagram"].get("password") or ""
    sf = cfg["instagram"]["session_file"]
    try:
        ig.reset_client()
        ig.login_now(un, pw, sf)
        with open(sf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        config.save_sections({"instagram": {"username": un, "password": pw, "session_b64": b64}})
        ig.reset_client()
        return RedirectResponse("/settings?msg=" + quote("ログイン成功・セッションを保存しました"), 303)
    except Exception as e:
        return RedirectResponse("/settings?err=" + quote(repr(e)), 303)


@app.post("/ig/logout")
def ig_logout(u=Depends(auth)):
    sf = get_cfg()["instagram"]["session_file"]
    try:
        if os.path.exists(sf):
            os.remove(sf)
    except Exception:
        pass
    config.save_sections({"instagram": {"session_b64": ""}})
    ig.reset_client()
    return RedirectResponse("/settings?msg=" + quote("ログアウトしました"), 303)


# ---------- リンク追跡（公開ルート） ----------

def _record_hit(request: Request, code: str):
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
        "nonce": secrets.token_hex(16),
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


def _bind_owner(code):
    owner = users.owner_of_link(code)
    if owner:
        tenancy.set_current(owner)
    return owner


@app.get("/l/{code}")
def link_hit(code: str, request: Request):
    if not _bind_owner(code):
        return PlainTextResponse("リンクが無効です", status_code=404)
    link = db.link_get(code)
    if not link or not link["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    hid = _record_hit(request, code)
    hrow = db.q1("SELECT nonce FROM link_hits WHERE id=?", (hid,))
    nonce = (hrow["nonce"] if hrow else "") or ""

    if link["mode"] == "redirect" and link["dest"]:
        return RedirectResponse(link["dest"], 302)

    if link["mode"] == "quiz" and db.questions(code):
        qs = [{"id": r["id"], "qtype": r["qtype"], "prompt": r["prompt"],
               "options": _json.loads(r["options"] or "[]")} for r in db.questions(code)]
        return render("link_quiz.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce,
                      questions_json=_json.dumps(qs, ensure_ascii=False))

    if link["mode"] == "identify":
        ip = linktrack.client_ip(request)
        return render("link_identify.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce, ip=ip,
                      p=linktrack.parse_ua(request.headers.get("user-agent", "")),
                      g=linktrack.geo(ip))

    return render("link_land.html", request, code=code, hit_id=hid, link=link,
                  dest=link["dest"] or "", nonce=nonce)


@app.post("/l/{code}/x")
async def link_extra(code: str, request: Request):
    if not _bind_owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
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
        f["fp_json"] = _json.dumps(body["fp_json"], ensure_ascii=False)[:8000]
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
    return {"ok": True, "vid": vid}


@app.post("/l/{code}/a")
async def link_answer(code: str, request: Request):
    if not _bind_owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    q = db.q1("SELECT * FROM link_questions WHERE id=? AND code=?",
              (int(body.get("qid") or 0), code))
    if not q:
        return {"ok": False}
    ans = body.get("answer")
    if isinstance(ans, list):
        ans = ",".join(str(x) for x in ans)
    ans = str(ans or "")[:2000]
    ok = None
    if (q["answer_key"] or "") != "":
        ok = int(str(q["answer_key"]).strip() == ans.strip())
    db.add_answer({"code": code, "hit_id": int(body.get("hit_id") or 0),
                   "qid": q["id"], "ord": q["ord"], "qtype": q["qtype"],
                   "answer": ans, "is_correct": ok,
                   "ms": int(body.get("ms") or 0),
                   "ip": linktrack.client_ip(request), "ts": now_iso()})

    reveal = ""
    if q["qtype"] in ("choice", "multi"):
        opts = _json.loads(q["options"] or "[]")
        idxs = [int(x) for x in ans.split(",") if x.strip().isdigit()]
        reveal = " / ".join(o.get("reveal", "") for i, o in enumerate(opts)
                            if i in idxs and o.get("reveal"))
    else:
        reveal = q["reveal"] or ""
    return {"ok": True, "correct": ok, "reveal": reveal}


@app.post("/l/{code}/done")
async def link_done(code: str, request: Request):
    if not _bind_owner(code):
        return {"ok": False}
    try:
        body = await request.json()
    except Exception:
        body = {}
    hid = int(body.get("hit_id") or 0)
    if hid:
        db.update_hit(hid, quiz_done=1, quiz_score=float(body.get("score") or 0),
                      quiz_total=int(body.get("total") or 0),
                      quiz_ms=int(body.get("ms") or 0))
        db.log("link", "quiz_done", {"code": code, "hit_id": hid,
                                     "score": body.get("score"),
                                     "total": body.get("total")})
    return {"ok": True}


@app.get("/l/{code}/go")
def link_go(code: str):
    if not _bind_owner(code):
        raise HTTPException(404)
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    return RedirectResponse(link["dest"] or "/", 302)


@app.get("/link/me", response_class=HTMLResponse)
def link_me(request: Request):
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    return render("link_me.html", request, ip=ip, ua=ua,
                  p=linktrack.parse_ua(ua), g=linktrack.geo(ip))


# ---------- リンク管理 ----------

def _new_code(n=8):
    for _ in range(50):
        c = "".join(random.choices(string.ascii_lowercase + string.digits, k=n))
        if not users.owner_of_link(c):
            return c
    return secrets.token_urlsafe(8)


@app.get("/links", response_class=HTMLResponse)
def links_page(request: Request, u=Depends(auth)):
    return render("links.html", request, links=db.links(500),
                  base=str(request.base_url).rstrip("/"))


@app.post("/links/add")
def links_add(name: str = Form(""), dest: str = Form(""), note: str = Form(""),
              mode: str = Form("page"), u=Depends(auth)):
    code = _new_code()
    users.register_link(code, u)
    db.add_link(code, name or code, dest.strip(), note,
                mode if mode in ("page", "geo", "redirect", "quiz", "identify") else "page")
    return RedirectResponse(f"/link/{code}", 303)


@app.get("/link/{code}", response_class=HTMLResponse)
def link_detail(code: str, request: Request, bots: str = "", u=Depends(auth)):
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
    return render("link_detail.html", request, link=link, hits=hits, stats=stats,
                  points_json=_json.dumps(points, ensure_ascii=False),
                  base=str(request.base_url).rstrip("/"), bots=bots,
                  net={h["id"]: linktrack.network_label(h) for h in hits},
                  answers_by_hit={h["id"]: [dict(a) for a in db.answers_for(h["id"])]
                                  for h in hits},
                  qs=db.questions(code),
                  vlabels={v["vid"]: (v["label"] or "") for v in db.visitors(500)})


@app.post("/link/{code}/toggle")
def link_toggle(code: str, u=Depends(auth)):
    l = db.link_get(code)
    if l:
        db.set_link_active(code, not l["active"])
    return RedirectResponse(f"/link/{code}", 303)


@app.post("/link/{code}/delete")
def link_delete(code: str, u=Depends(auth)):
    db.del_link(code)
    users.unregister_link(code)
    return RedirectResponse("/links", 303)


@app.post("/link/{code}/hits/clear")
def link_clear(code: str, u=Depends(auth)):
    db.del_hits(code)
    return RedirectResponse(f"/link/{code}", 303)


@app.post("/link/{code}/hit/{hid}/bot")
def link_hit_bot(code: str, hid: int, u=Depends(auth)):
    row = db.q1("SELECT is_bot FROM link_hits WHERE id=?", (hid,))
    if row:
        db.update_hit(hid, is_bot=0 if row["is_bot"] else 1)
    return RedirectResponse(f"/link/{code}?bots=1", 303)


# ---------- クイズ編集 / 訪問者 / 一緒解析 ----------

@app.get("/link/{code}/questions", response_class=HTMLResponse)
def link_questions(code: str, request: Request, u=Depends(auth)):
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    return render("link_questions.html", request, link=link, qs=db.questions(code),
                  base=str(request.base_url).rstrip("/"))


@app.post("/link/{code}/questions/add")
def link_questions_add(code: str, prompt: str = Form(...), qtype: str = Form("choice"),
                       options: str = Form(""), answer_key: str = Form(""),
                       reveal: str = Form(""), u=Depends(auth)):
    rows = []
    for line in (options or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        rows.append({"label": parts[0],
                     "key": parts[1] if len(parts) > 1 else str(len(rows)),
                     "reveal": parts[2] if len(parts) > 2 else ""})
    db.add_question(code, prompt, qtype if qtype in ("choice", "multi", "text") else "choice",
                    rows, answer_key, reveal)
    return RedirectResponse(f"/link/{code}/questions", 303)


@app.post("/link/{code}/questions/{qid}/delete")
def link_questions_del(code: str, qid: int, u=Depends(auth)):
    db.del_question(qid)
    return RedirectResponse(f"/link/{code}/questions", 303)


@app.get("/visitors", response_class=HTMLResponse)
def visitors_page(request: Request, u=Depends(auth)):
    return render("visitors.html", request, rows=db.visitors(500))


@app.get("/visitor/{vid}", response_class=HTMLResponse)
def visitor_detail(vid: str, request: Request, u=Depends(auth)):
    v = db.visitor(vid)
    if not v:
        raise HTTPException(404)
    return render("visitor.html", request, v=v, hits=db.hits_by_vid(vid),
                  near=together.for_visitor(db, vid))


@app.post("/visitor/{vid}/label")
def visitor_label(vid: str, label: str = Form(""), note: str = Form(""), u=Depends(auth)):
    db.set_visitor_label(vid, label, note)
    return RedirectResponse(f"/visitor/{vid}", 303)


@app.get("/together", response_class=HTMLResponse)
def together_page(request: Request, code: str = "", window: int = 6,
                  minscore: float = 0.35, u=Depends(auth)):
    res = together.analyze(db, code=code or None,
                           window_h=max(1, min(int(window), 72)),
                           min_score=max(0.0, min(float(minscore), 1.0)))
    return render("together.html", request, res=res, code=code,
                  window=window, minscore=minscore, links=db.links(500))


# ---------- API / エクスポート ----------

@app.get("/api/summary")
def api_summary(u=Depends(auth)):
    return {
        "tenant": u,
        "targets": len(db.targets()),
        "known": db.q1("SELECT COUNT(*) c FROM known_accounts")["c"],
        "runs": db.q1("SELECT COUNT(*) c FROM identity_runs")["c"],
        "links": db.q1("SELECT COUNT(*) c FROM links")["c"],
        "visitors": db.q1("SELECT COUNT(*) c FROM visitors")["c"],
        "events": db.q1("SELECT COUNT(*) c FROM events")["c"],
    }


@app.get("/api/events")
def api_events(limit: int = 500, u=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]


@app.get("/api/together")
def api_together(code: str = "", window: int = 6, minscore: float = 0.35, u=Depends(auth)):
    return together.analyze(db, code=code or None,
                            window_h=max(1, min(int(window), 72)),
                            min_score=max(0.0, min(float(minscore), 1.0)))


@app.get("/export.json")
def export_json(u=Depends(auth)):
    return {
        "tenant": u,
        "known_accounts": [dict(r) for r in db.q("SELECT * FROM known_accounts")],
        "saved_pairs": [dict(r) for r in db.q("SELECT * FROM saved_pairs")],
        "profiles": [dict(r) for r in db.q("SELECT * FROM profiles")],
        "runs": [dict(r) for r in db.q("SELECT * FROM identity_runs")],
        "scores": [dict(r) for r in db.q("SELECT * FROM identity_scores")],
    }


@app.post("/import")
async def import_json(request: Request, u=Depends(auth)):
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