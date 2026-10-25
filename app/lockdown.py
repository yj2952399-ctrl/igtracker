"""app/lockdown.py — 管理者以外の「新規登録」「ログイン」を一時封鎖する

main.py への追記は3か所だけ:
    from . import lockdown
    app.include_router(lockdown.router)
    @app.middleware("http")
    async def lockdown_gate(request: Request, call_next):
        return await lockdown.gate(request, call_next)

状態は lockdown.json に保存（DB不要）。管理者は /lock/panel から操作。
"""
from __future__ import annotations

import json
import os
import datetime as dt
from typing import Any, Dict, List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

router = APIRouter()

DEFAULT: Dict[str, Any] = {
    "on": 0,
    "block_signup": 1,
    "block_login": 1,
    "admins": ["admin"],
    "title": "ただいま準備中です",
    "msg_signup": "新規登録を一時停止しています。少しお待ちください。",
    "msg_login": "ただいまログインを一時停止しています（管理者のみ入れます）。",
    "note": "",
    "until": "",
    "by": "",
    "at": "",
    "hits": 0,
}

_LOGIN_PATHS = ("/login", "/login/", "/signin", "/signin/", "/auth", "/auth/")
_SIGNUP_PATHS = ("/signup", "/signup/", "/register", "/register/", "/join", "/join/")
_IDENT_KEYS = ("name", "user", "username", "login", "email", "id", "account",
               "userid", "user_name", "mail", "ident", "handle")


# ---------------- 保存 ----------------

def _path() -> str:
    base = None
    try:
        from . import tenancy
        base = getattr(tenancy, "ROOT", None)
    except Exception:
        base = None
    if not base:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    base = os.path.abspath(base)
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, "lockdown.json")


def load() -> Dict[str, Any]:
    st = dict(DEFAULT)
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            st.update(raw)
    except Exception:
        pass
    if not isinstance(st.get("admins"), list):
        st["admins"] = ["admin"]
    st["admins"] = [str(x).strip().lower() for x in st["admins"] if str(x).strip()]
    if not st["admins"]:
        st["admins"] = ["admin"]
    st["on"] = 1 if str(st.get("on") or "0") not in ("0", "", "false", "False") else 0
    if st.get("until"):
        try:
            if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(str(st["until"])):
                if st["on"]:
                    st["on"] = 0
                    save(st)
        except Exception:
            pass
    return st


def save(st: Dict[str, Any]) -> None:
    try:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
    except Exception:
        pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---------------- 判定 ----------------

def is_admin_ident(ident: str) -> bool:
    st = load()
    s = (ident or "").strip().lower()
    if not s:
        return False
    for a in st["admins"]:
        if s == a or s.endswith("@" + a) or s.startswith(a + "@") or a in s:
            return True
    return False


def blocked(kind: str) -> bool:
    """kind = 'signup' | 'login'"""
    st = load()
    if not st["on"]:
        return False
    return bool(st.get("block_" + kind))


async def _body_form(request: Request) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        ct = (request.headers.get("content-type") or "").lower()
        body = await request.body()
        if not body:
            return out
        if "json" in ct:
            try:
                d = json.loads(body.decode("utf-8", "ignore"))
                if isinstance(d, dict):
                    out = {str(k): str(v) for k, v in d.items()}
            except Exception:
                pass
        else:
            from urllib.parse import parse_qs
            for k, v in parse_qs(body.decode("utf-8", "ignore")).items():
                out[str(k)] = (v[0] if v else "")
    except Exception:
        pass
    return out


def _ident(form: Dict[str, str]) -> str:
    low = {k.lower(): v for k, v in form.items()}
    for k in _IDENT_KEYS:
        if low.get(k):
            return str(low[k])
    for k, v in low.items():
        if v and "pass" not in k and len(v) < 120:
            return str(v)
    return ""


def _admin(request: Request) -> bool:
    try:
        if bool(getattr(request.state, "is_admin", False)):
            return True
    except Exception:
        pass
    try:
        u = getattr(request.state, "user_name", None)
        if u and is_admin_ident(str(u)):
            return True
    except Exception:
        pass
    return False


# ---------------- 表示 ----------------

def _page(title: str, msg: str, note: str, back: str = "/") -> HTMLResponse:
    note_html = f'<div class="note">{note}</div>' if note else ""
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
html,body{{margin:0;height:100%;background:#0b0e14;color:#e6e9ef;
  font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif}}
body{{display:grid;place-items:center;padding:24px}}
.box{{max-width:460px;text-align:center}}
.ic{{font-size:52px;line-height:1;margin-bottom:14px}}
h1{{font-size:20px;margin:0 0 12px;color:#ffd21e}}
p{{font-size:14px;line-height:1.9;color:#c7cddb;margin:0 0 18px;white-space:pre-wrap}}
.note{{font-size:12px;color:#8b93a7;margin-top:14px;white-space:pre-wrap}}
a.btn{{display:inline-block;padding:12px 26px;border-radius:999px;background:#4c8dff;
  color:#fff;text-decoration:none;font-weight:700;font-size:14px}}
</style></head><body><div class="box">
<div class="ic">🔒</div><h1>{title}</h1><p>{msg}</p>
<a class="btn" href="{back}">戻る</a>{note_html}
</div></body></html>"""
    return HTMLResponse(html, status_code=200,
                        headers={"Cache-Control": "no-store"})


def banner_html() -> str:
    st = load()
    if not st["on"]:
        return ""
    t = st.get("title") or DEFAULT["title"]
    m = st.get("msg_login") or DEFAULT["msg_login"]
    s = st.get("msg_signup") or DEFAULT["msg_signup"]
    return (
        '<div id="lockbanner" style="position:fixed;left:0;right:0;top:0;z-index:99999;'
        'background:#3a2a10;border-bottom:1px solid #7a5a1f;color:#ffd98a;'
        'padding:10px 14px;font:13px/1.6 system-ui,-apple-system,sans-serif;text-align:center">'
        f'<b>🔒 {t}</b> ／ 登録: {s} ／ ログイン: {m}'
        '</div>'
        '<script>(function(){var b=document.getElementById("lockbanner");'
        'if(b){var h=b.offsetHeight||44;document.documentElement.style.paddingTop=h+"px";}})();</script>'
    )


# ---------------- ミドルウェア本体 ----------------

async def gate(request: Request, call_next):
    st = load()
    if not st["on"]:
        return await call_next(request)

    p = (request.url.path or "/").rstrip("/") or "/"
    meth = request.method.upper()

    if meth == "POST" and st.get("block_signup") and p in [x.rstrip("/") or "/" for x in _SIGNUP_PATHS]:
        form = await _body_form(request)
        if not is_admin_ident(_ident(form)):
            st["hits"] = int(st.get("hits") or 0) + 1
            save(st)
            return _page(st.get("title") or DEFAULT["title"],
                         st.get("msg_signup") or DEFAULT["msg_signup"],
                         st.get("note") or "", "/signup")

    if meth == "POST" and st.get("block_login") and p in [x.rstrip("/") or "/" for x in _LOGIN_PATHS]:
        form = await _body_form(request)
        ident = _ident(form)
        if not is_admin_ident(ident):
            st["hits"] = int(st.get("hits") or 0) + 1
            save(st)
            return _page(st.get("title") or DEFAULT["title"],
                         st.get("msg_login") or DEFAULT["msg_login"],
                         st.get("note") or "", "/login")

    if meth == "GET" and p in [x.rstrip("/") or "/" for x in (_LOGIN_PATHS + _SIGNUP_PATHS)]:
        resp = await call_next(request)
        try:
            ct = (resp.headers.get("content-type") or "")
            if "text/html" not in ct:
                return resp
            body = b""
            async for chunk in resp.body_iterator:
                body += chunk
            html = body.decode("utf-8", "ignore")
            snip = banner_html()
            if "</body>" in html:
                html = html.replace("</body>", snip + "</body>", 1)
            else:
                html += snip
            h = {k: v for k, v in resp.headers.items()
                 if k.lower() not in ("content-length", "content-encoding")}
            return Response(html, status_code=resp.status_code, headers=h,
                            media_type="text/html; charset=utf-8")
        except Exception:
            return resp

    return await call_next(request)


# ---------------- API / パネル ----------------

def _m():
    from . import main
    return main


async def _auth(request: Request):
    return await _m().auth(request)


def _render(name, request, **ctx):
    return _m().render(name, request, **ctx)


@router.get("/lock")
def api_state():
    st = load()
    return JSONResponse({"ok": 1, "on": st["on"],
                         "block_signup": st.get("block_signup", 1),
                         "block_login": st.get("block_login", 1),
                         "title": st.get("title", ""),
                         "msg_signup": st.get("msg_signup", ""),
                         "msg_login": st.get("msg_login", ""),
                         "note": st.get("note", ""),
                         "admins": st.get("admins", []),
                         "until": st.get("until", ""),
                         "hits": int(st.get("hits") or 0),
                         "at": st.get("at", "")},
                        headers={"Cache-Control": "no-store"})


@router.post("/lock")
async def api_set(request: Request, u=Depends(_auth)):
    if not _admin(request):
        raise HTTPException(403, "管理者のみ")
    try:
        b = await request.json()
        if not isinstance(b, dict):
            b = {}
    except Exception:
        b = {}
    st = load()
    if "on" in b:
        st["on"] = 1 if str(b.get("on")) not in ("0", "", "false", "False") else 0
    for k in ("block_signup", "block_login"):
        if k in b:
            st[k] = 1 if str(b.get(k)) not in ("0", "", "false", "False") else 0
    for k in ("title", "msg_signup", "msg_login", "note", "until"):
        if k in b:
            st[k] = str(b.get(k) or "")[:400]
    if "admins" in b:
        v = b.get("admins")
        if isinstance(v, str):
            v = [x.strip() for x in v.replace("\n", ",").split(",")]
        if isinstance(v, list):
            st["admins"] = [str(x).strip().lower() for x in v if str(x).strip()] or ["admin"]
    if "hits_reset" in b:
        st["hits"] = 0
    st["by"] = str(getattr(request.state, "user_name", "") or u or "")
    st["at"] = _now()
    save(st)
    return JSONResponse({"ok": 1, "state": {k: st[k] for k in st}},
                        headers={"Cache-Control": "no-store"})


@router.post("/lock/toggle")
def api_toggle(u=Depends(_auth)):
    st = load()
    st["on"] = 0 if st["on"] else 1
    st["at"] = _now()
    save(st)
    return RedirectResponse("/lock/panel", status_code=303)


@router.get("/lock/panel", response_class=HTMLResponse)
def panel(request: Request, u=Depends(_auth)):
    if not _admin(request):
        raise HTTPException(403, "管理者のみ（/lock/panel）")
    st = load()
    return _render("lockdown_admin.html", request, st=st,
                   admins=", ".join(st.get("admins") or ["admin"]),
                   on=st["on"], hits=int(st.get("hits") or 0))