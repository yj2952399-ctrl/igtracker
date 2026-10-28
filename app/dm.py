"""app/dm.py — ユーザー同士のDM（1:1）とグループチャット。

機能:
  ・DM      : ユーザー一覧／検索から相手を選んで開始（自分以外）
  ・グループ: 作成（名前＋メンバー選択）／参加コードで途中参加／脱退
  ・通知    : スレッドごとに ON/OFF（既定ON）。未読バッジ＋ブラウザ通知
  ・検索    : 名前の部分一致でユーザーを絞り込み

保存先は DM_DB（既定 data/dm.db）。全ユーザー共有の1ファイルなので
persist が自動でバックアップする（persist._shared_paths に DM_DB を追加済み）。

main.py への追記は2行:
    from . import dm
    app.include_router(dm.router)

権限キー feature.dm（roles.FEATURES に追加済み）。
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import secrets
import string
import datetime as dt

from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()
from .chat_media import save_upload, MEDIA_DIR

DB = os.getenv("DM_DB", "data/dm.db")
MAX_LEN = int(os.getenv("DM_MAX_LEN", "2000"))
NAME_MAX = 60
GROUP_MAX = int(os.getenv("DM_GROUP_MAX", "100"))
MIN_GAP = float(os.getenv("DM_MIN_GAP", "0.35"))     # 連投間隔（秒）
BURST_N = int(os.getenv("DM_BURST_N", "25"))         # 窓内の上限通数
BURST_WIN = float(os.getenv("DM_BURST_WIN", "30"))   # 窓（秒）
KEEP = int(os.getenv("DM_KEEP", "4000"))             # 1スレッドの保持行数
FETCH = int(os.getenv("DM_FETCH", "300"))
ALL_CODE = "all"                                     # 全体連絡の固定コード

_lock = threading.RLock()
_conn = None
_rate = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_threads(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT DEFAULT 'dm',
  name TEXT DEFAULT '',
  owner TEXT DEFAULT '',
  code TEXT,
  open INTEGER DEFAULT 1,
  created_at TEXT, last_at TEXT, last_text TEXT, last_user TEXT);
CREATE TABLE IF NOT EXISTS dm_members(
  thread_id INTEGER, user TEXT, joined_at TEXT,
  notify INTEGER DEFAULT 1, last_read INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0,
  PRIMARY KEY(thread_id, user));
CREATE TABLE IF NOT EXISTS dm_msgs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id INTEGER, ts TEXT, user TEXT, text TEXT,
  kind TEXT DEFAULT 'msg', deleted INTEGER DEFAULT 0, media_url TEXT DEFAULT '', media_type TEXT DEFAULT '', media_name TEXT DEFAULT '', media_size INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS dm_msgs_t ON dm_msgs(thread_id, id);
CREATE INDEX IF NOT EXISTS dm_mem_u ON dm_members(user);
CREATE INDEX IF NOT EXISTS dm_thr_code ON dm_threads(code);
"""


def _c():
    global _conn
    if _conn is None:
        d = os.path.dirname(DB)
        if d:
            os.makedirs(d, exist_ok=True)
        _conn = sqlite3.connect(DB, check_same_thread=False, timeout=20)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=8000")
        _conn.executescript(SCHEMA)
        cols = {r["name"] for r in _conn.execute("PRAGMA table_info(dm_msgs)")}
        for name, typ in (("media_url", "TEXT DEFAULT ''"), ("media_type", "TEXT DEFAULT ''"),
                          ("media_name", "TEXT DEFAULT ''"), ("media_size", "INTEGER DEFAULT 0")):
            if name not in cols:
                _conn.execute(f"ALTER TABLE dm_msgs ADD COLUMN {name} {typ}")
        _conn.commit()
    return _conn


def close():
    """バックアップ復元の前に接続を閉じる。"""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _m():
    from . import main
    return main


def _u():
    from . import users
    return users


def _r():
    from . import roles
    return roles


async def _auth(request: Request):
    return await _m().auth(request)


def _ok(request: Request):
    """feature.dm 権限チェック（ルートは素通り）。"""
    return _m()._perm(request, "feature.dm")


async def _body(request: Request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _new_code(n=6):
    with _lock:
        for _ in range(60):
            c = "".join(secrets.choice(string.ascii_lowercase + string.digits)
                        for _ in range(n))
            if c == ALL_CODE:
                continue
            r = _c().execute("SELECT 1 FROM dm_threads WHERE code=?", (c,)).fetchone()
            if not r:
                return c
    return secrets.token_urlsafe(6)


# ---------------- スレッド／メンバー ----------------

def _thread(tid):
    with _lock:
        return _c().execute("SELECT * FROM dm_threads WHERE id=?", (tid,)).fetchone()


def _member(tid, user):
    with _lock:
        return _c().execute("SELECT * FROM dm_members WHERE thread_id=? AND user=?",
                            (tid, user)).fetchone()


def _need(tid, user):
    t = _thread(tid)
    if not t or not _member(tid, user):
        raise HTTPException(404, "スレッドが見つかりません")
    return t


def _members(tid):
    with _lock:
        return [r["user"] for r in _c().execute(
            "SELECT user FROM dm_members WHERE thread_id=? ORDER BY joined_at, user",
            (tid,)).fetchall()]


def _add_member(tid, user):
    with _lock:
        c = _c()
        c.execute("""INSERT INTO dm_members(thread_id,user,joined_at,notify,last_read)
            VALUES(?,?,?,1,0) ON CONFLICT(thread_id,user)
            DO UPDATE SET hidden=0""", (tid, user, _now()))
        c.commit()


def _decorate(rows, me):
    """行にタイトル・参加者を足す（N+1回避のためまとめて引く）。"""
    ids = [r["id"] for r in rows]
    mem = {}
    if ids:
        q = ",".join("?" * len(ids))
        with _lock:
            for r in _c().execute(
                    f"SELECT thread_id,user FROM dm_members WHERE thread_id IN ({q})",
                    ids).fetchall():
                mem.setdefault(r["thread_id"], []).append(r["user"])
    out = []
    for r in rows:
        d = dict(r)
        m = sorted(mem.get(r["id"], []))
        d["members"] = m
        d["n"] = len(m)
        if d["kind"] == "group":
            d["title"] = d["name"] or "グループ"
            d["other"] = ""
        else:
            other = next((x for x in m if x != me), me)
            d["title"] = _u().display_name(other)
            d["other"] = other
            prof = _u().get_profile(other)
            d["avatar"] = ("/profile/avatar/" + other) if prof.get("avatar_data") else ""
        if d.get("last_user"):
            d["last_user_display"] = _u().display_name(d["last_user"])
        out.append(d)
    return out


def _list_threads(user):
    u = _u().norm(user)
    with _lock:
        rows = _c().execute("""
            SELECT t.*, m.notify, m.last_read,
              (SELECT COUNT(*) FROM dm_msgs x WHERE x.thread_id=t.id
                 AND x.id>m.last_read AND x.user<>? AND x.deleted=0) AS unread
            FROM dm_threads t JOIN dm_members m ON m.thread_id=t.id
            WHERE m.user=? AND m.hidden=0
            ORDER BY COALESCE(t.last_at, t.created_at) DESC LIMIT 300""",
            (u, u)).fetchall()
    return _decorate([dict(r) for r in rows], u)


def ensure_all(user):
    """全員参加の「全体連絡」を保証して自分を入れる。"""
    u = _u().norm(user)
    with _lock:
        c = _c()
        r = c.execute("SELECT id FROM dm_threads WHERE kind='group' AND code=?",
                      (ALL_CODE,)).fetchone()
        if r:
            tid = r["id"]
        else:
            cur = c.execute("""INSERT INTO dm_threads(kind,name,owner,code,open,
                created_at,last_at) VALUES('group',?,?,?,1,?,?)""",
                ("全体連絡", _u().norm(_u().root_admin() or u), ALL_CODE,
                 _now(), _now()))
            tid = cur.lastrowid
            c.commit()
        c.execute("""INSERT INTO dm_members(thread_id,user,joined_at,notify,last_read)
            VALUES(?,?,?,1,0) ON CONFLICT(thread_id,user) DO UPDATE SET hidden=0""",
            (tid, u, _now()))
        c.commit()
    return tid


def open_dm(a, b):
    """1:1スレッドを取得（無ければ作成）。"""
    a, b = _u().norm(a), _u().norm(b)
    with _lock:
        c = _c()
        row = c.execute("""SELECT t.id FROM dm_threads t
            JOIN dm_members x ON x.thread_id=t.id AND x.user=?
            JOIN dm_members y ON y.thread_id=t.id AND y.user=?
            WHERE t.kind='dm' LIMIT 1""", (a, b)).fetchone()
        if row:
            tid = row["id"]
        else:
            cur = c.execute("""INSERT INTO dm_threads(kind,name,owner,created_at,last_at)
                VALUES('dm','',?,?,?)""", (a, _now(), _now()))
            tid = cur.lastrowid
            for m in sorted({a, b}):
                c.execute("""INSERT OR IGNORE INTO dm_members
                    (thread_id,user,joined_at,notify,last_read) VALUES(?,?,?,1,0)""",
                    (tid, m, _now()))
        c.execute("UPDATE dm_members SET hidden=0 WHERE thread_id=? AND user=?", (tid, a))
        c.commit()
    return tid


def create_group(owner, name, members):
    owner = _u().norm(owner)
    ms = []
    for x in members or []:
        n = _u().norm(x)
        if n and _u().get(n) and n not in ms:
            ms.append(n)
    ms = ms[:GROUP_MAX]
    if owner not in ms:
        ms.insert(0, owner)
    nm = (name or "").strip()[:NAME_MAX] or "グループ"
    code = _new_code()
    with _lock:
        c = _c()
        cur = c.execute("""INSERT INTO dm_threads(kind,name,owner,code,open,
            created_at,last_at) VALUES('group',?,?,?,1,?,?)""",
            (nm, owner, code, _now(), _now()))
        tid = cur.lastrowid
        for m in ms:
            c.execute("""INSERT OR IGNORE INTO dm_members
                (thread_id,user,joined_at,notify,last_read) VALUES(?,?,?,1,0)""",
                (tid, m, _now()))
        c.execute("""INSERT INTO dm_msgs(thread_id,ts,user,text,kind)
            VALUES(?,?,?,?,?)""", (tid, _now(), owner, f"グループ「{nm}」を作成しました", "sys"))
        c.execute("UPDATE dm_threads SET last_at=?, last_text=?, last_user=? WHERE id=?",
                  (_now(), "グループを作成しました", owner, tid))
        c.commit()
    return tid


def _join(code, user):
    code = (code or "").strip().lower()
    u = _u().norm(user)
    with _lock:
        r = _c().execute("SELECT * FROM dm_threads WHERE code=? AND kind='group'",
                         (code,)).fetchone()
    if not r:
        return None
    if r["open"] or _member(r["id"], u):
        _add_member(r["id"], u)
        return r["id"]
    return None


def _post(tid, user, text, kind="msg", media=None):
    with _lock:
        c = _c()
        media = media or {}
        cur = c.execute("""INSERT INTO dm_msgs(thread_id,ts,user,text,kind,media_url,media_type,media_name,media_size)
            VALUES(?,?,?,?,?,?,?,?,?)""", (tid, _now(), user, text, kind, media.get("url", ""), media.get("type", ""), media.get("name", ""), media.get("size", 0)))
        mid = cur.lastrowid
        c.execute("UPDATE dm_threads SET last_at=?, last_text=?, last_user=? WHERE id=?",
                  (_now(), text[:140], user, tid))
        c.execute("DELETE FROM dm_msgs WHERE thread_id=? AND id<=?", (tid, mid - KEEP))
        c.execute("UPDATE dm_members SET last_read=? WHERE thread_id=? AND user=?",
                  (mid, tid, user))
        c.commit()
    return mid


def _mark_read(tid, user):
    with _lock:
        c = _c()
        r = c.execute("SELECT MAX(id) m FROM dm_msgs WHERE thread_id=?", (tid,)).fetchone()
        mx = int((r["m"] if r and r["m"] else 0) or 0)
        c.execute("UPDATE dm_members SET last_read=? WHERE thread_id=? AND user=?",
                  (mx, tid, user))
        c.commit()
    return mx


def _rate_ok(user):
    now = time.time()
    with _lock:
        last, cnt, win = _rate.get(user, (0.0, 0, now))
        if now - last < MIN_GAP:
            return False, "連投しすぎ（少し待って）"
        if now - win > BURST_WIN:
            cnt, win = 0, now
        if cnt >= BURST_N:
            return False, f"{int(BURST_WIN)}秒で{BURST_N}通まで"
        _rate[user] = (now, cnt + 1, win)
    return True, ""


def _msgs(tid, since=0, limit=FETCH):
    with _lock:
        c = _c()
        if since > 0:
            rows = c.execute("SELECT * FROM dm_msgs WHERE thread_id=? AND id>? "
                             "ORDER BY id LIMIT ?", (tid, since, limit)).fetchall()
        else:
            rows = list(reversed(c.execute(
                "SELECT * FROM dm_msgs WHERE thread_id=? ORDER BY id DESC LIMIT ?",
                (tid, limit)).fetchall()))
    return [dict(r) for r in rows]


def _out(rows, me):
    out = []
    for r in rows:
        d = dict(r)
        d["mine"] = (d["user"] == me)
        d["deleted"] = bool(d["deleted"])
        try:
            profile = _u().get_profile(d["user"])
            d["display_name"] = (profile.get("display_name") or "").strip() or d["user"]
            d["avatar"] = ("/profile/avatar/" + d["user"]) if profile.get("avatar_data") else ""
        except Exception:
            d["display_name"], d["avatar"] = d["user"], ""
        out.append(d)
    return out


def _title_of(tid, me):
    t = _thread(tid)
    if not t:
        return "?"
    if t["kind"] == "group":
        return t["name"] or "グループ"
    ms = _members(tid)
    other = next((x for x in ms if x != me), me)
    return _u().display_name(other)


# ---------------- 画面 ----------------

@router.get("/dm", response_class=HTMLResponse)
def page(request: Request, q: str = "", u=Depends(_auth)):
    _ok(request)
    ensure_all(u)
    rows = _list_threads(u)
    return _m().render("dm.html", request, threads=rows, q=q,
                       max_len=MAX_LEN, group_max=GROUP_MAX)


@router.get("/dm/t/{tid}", response_class=HTMLResponse)
def thread_page(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    _mark_read(tid, u)
    mem = _members(tid)
    labels = _r().LABELS
    members = [{"name": n, "display_name": _u().display_name(n),
                "avatar": ("/profile/avatar/" + n) if _u().get_profile(n).get("avatar_data") else "",
                "label": labels.get(_u().role_of(n), ""),
                "root": _u().is_root(n)} for n in mem]
    my = _member(tid, u)
    return _m().render("dm_thread.html", request,
                       t=dict(t), title=_title_of(tid, u), msgs=_out(_msgs(tid), u),
                       members=members, notify=bool(my["notify"]) if my else True,
                       owner=(t["owner"] == _u().norm(u)),
                       code=t["code"] or "", is_group=(t["kind"] == "group"),
                       max_len=MAX_LEN)


@router.get("/dm/join/{code}", response_class=HTMLResponse)
def join_page(code: str, request: Request, msg: str = "", err: str = "",
              u=Depends(_auth)):
    _ok(request)
    with _lock:
        t = _c().execute("SELECT * FROM dm_threads WHERE code=? AND kind='group'",
                         ((code or "").strip().lower(),)).fetchone()
    if not t:
        raise HTTPException(404, "参加コードが無効です")
    mem = _members(t["id"])
    return _m().render("dm_join.html", request, t=dict(t), code=t["code"],
                       members=mem, already=bool(_member(t["id"], u)),
                       msg=msg, err=err)


# ---------------- API ----------------

@router.get("/dm/api/list")
def api_list(request: Request, u=Depends(_auth)):
    _ok(request)
    return {"ok": True, "threads": _list_threads(u)}


@router.get("/dm/search")
def api_search(request: Request, q: str = "", limit: int = 60, u=Depends(_auth)):
    _ok(request)
    q = (q or "").strip().lower()
    me = _u().norm(u)
    rows = []
    for name in _u().list_usernames():
        if name == me:
            continue
        profile = _u().get_profile(name)
        shown = (profile.get("display_name") or "").strip()
        if q and q not in name and q not in shown.lower():
            continue
        rows.append({"name": name,
                     "display_name": (profile.get("display_name") or "").strip() or name,
                     "avatar": ("/profile/avatar/" + name) if profile.get("avatar_data") else "",
                     "label": _r().LABELS.get(_u().role_of(name), ""),
                     "lvl": _r().level(_u().role_of(name))})
    rows.sort(key=lambda r: (-r["lvl"], r["name"]))
    for r in rows:
        r.pop("lvl", None)
    return {"ok": True, "users": rows[:max(1, min(limit, 200))]}


@router.get("/dm/api/t/{tid}")
def api_msgs(tid: int, request: Request, since: int = 0, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    _mark_read(tid, u)
    return {"ok": True, "msgs": _out(_msgs(tid, since), u),
            "title": _title_of(tid, u), "now": _now(),
            "members": _members(t["id"])}


@router.post("/dm/api/start")
async def api_start(request: Request, u=Depends(_auth)):
    _ok(request)
    b = await _body(request)
    other = _u().norm(str(b.get("user") or ""))
    if not _u().get(other):
        return JSONResponse({"ok": False, "why": "そのユーザーは居ません"}, status_code=404)
    return {"ok": True, "id": open_dm(u, other)}


@router.post("/dm/api/group")
async def api_group(request: Request, u=Depends(_auth)):
    _ok(request)
    b = await _body(request)
    mem = b.get("members") or []
    if isinstance(mem, str):
        mem = [x.strip() for x in mem.replace(",", "\n").split() if x.strip()]
    tid = create_group(u, str(b.get("name") or ""), mem)
    return {"ok": True, "id": tid}


@router.post("/dm/api/join")
async def api_join(request: Request, u=Depends(_auth)):
    _ok(request)
    b = await _body(request)
    tid = _join(str(b.get("code") or ""), u)
    if not tid:
        return JSONResponse({"ok": False, "why": "参加コードが無効／閉じています"},
                            status_code=404)
    return {"ok": True, "id": tid}


@router.post("/dm/api/t/{tid}/send")
async def api_send(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    b = await _body(request)
    text = str(b.get("text") or "").strip()[:MAX_LEN]
    if not text:
        return JSONResponse({"ok": False, "why": "空です"}, status_code=400)
    ok, why = _rate_ok(_u().norm(u))
    if not ok:
        return JSONResponse({"ok": False, "why": why}, status_code=429)
    return {"ok": True, "id": _post(tid, _u().norm(u), text)}


@router.post("/dm/api/t/{tid}/upload")
async def api_upload(tid: int, request: Request, file: UploadFile = File(...), caption: str = Form(""), u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    saved = await save_upload(file)
    caption = (caption or "").strip()[:MAX_LEN]
    ok, why = _rate_ok(_u().norm(u))
    if not ok:
        try: (MEDIA_DIR / saved["filename"]).unlink(missing_ok=True)
        except Exception: pass
        return JSONResponse({"ok": False, "why": why}, status_code=429)
    mid = _post(tid, _u().norm(u), caption, media=saved)
    return {"ok": True, "id": mid}


@router.post("/dm/t/{tid}/send")
def form_send(tid: int, request: Request, text: str = Form(""), u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    t = (text or "").strip()[:MAX_LEN]
    if t:
        _post(tid, _u().norm(u), t)
    return RedirectResponse(f"/dm/t/{tid}", 303)


@router.post("/dm/api/t/{tid}/read")
def api_read(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    return {"ok": True, "read": _mark_read(tid, u)}


@router.post("/dm/api/t/{tid}/notify")
async def api_notify(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    b = await _body(request)
    on = 1 if str(b.get("on", "1")) not in ("0", "", "false", "False") else 0
    with _lock:
        c = _c()
        c.execute("UPDATE dm_members SET notify=? WHERE thread_id=? AND user=?",
                  (on, tid, _u().norm(u)))
        c.commit()
    return {"ok": True, "notify": bool(on)}


@router.post("/dm/api/t/{tid}/invite")
async def api_invite(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    if t["kind"] != "group":
        return {"ok": False, "why": "グループではありません"}
    b = await _body(request)
    names = b.get("users") or ([b.get("user")] if b.get("user") else [])
    if isinstance(names, str):
        names = [x.strip() for x in names.replace(",", "\n").split() if x.strip()]
    added = []
    for n in names:
        n = _u().norm(n)
        if n and _u().get(n) and not _member(tid, n):
            _add_member(tid, n)
            added.append(n)
    if added:
        _post(tid, _u().norm(u), "＋ " + ", ".join(added) + " を追加", "sys")
    return {"ok": True, "added": added}


@router.post("/dm/api/t/{tid}/rename")
async def api_rename(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    if t["kind"] != "group":
        return {"ok": False, "why": "グループではありません"}
    if t["owner"] != _u().norm(u) and not _u().is_root(u):
        return JSONResponse({"ok": False, "why": "作成者のみ"}, status_code=403)
    b = await _body(request)
    nm = (str(b.get("name") or "").strip()[:NAME_MAX]) or "グループ"
    with _lock:
        c = _c()
        c.execute("UPDATE dm_threads SET name=? WHERE id=?", (nm, tid))
        c.commit()
    _post(tid, _u().norm(u), f"名前を「{nm}」に変更", "sys")
    return {"ok": True, "name": nm}


@router.post("/dm/api/t/{tid}/code")
def api_code(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    if t["kind"] != "group":
        return {"ok": False}
    if t["owner"] != _u().norm(u) and not _u().is_root(u):
        raise HTTPException(403, "作成者のみ")
    code = _new_code()
    with _lock:
        c = _c()
        c.execute("UPDATE dm_threads SET code=? WHERE id=?", (code, tid))
        c.commit()
    return {"ok": True, "code": code}


@router.post("/dm/api/t/{tid}/del")
async def api_del(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    b = await _body(request)
    mid = int(b.get("id") or 0)
    me = _u().norm(u)
    with _lock:
        c = _c()
        r = c.execute("SELECT user FROM dm_msgs WHERE id=? AND thread_id=?",
                      (mid, tid)).fetchone()
        if not r:
            return {"ok": False}
        if r["user"] != me and not _u().is_root(u):
            return JSONResponse({"ok": False, "why": "他人の発言です"}, status_code=403)
        c.execute("UPDATE dm_msgs SET deleted=1 WHERE id=?", (mid,))
        c.commit()
    return {"ok": True}


@router.post("/dm/api/t/{tid}/leave")
def api_leave(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    t = _need(tid, u)
    me = _u().norm(u)
    with _lock:
        c = _c()
        if t["kind"] == "dm":
            c.execute("UPDATE dm_members SET hidden=1 WHERE thread_id=? AND user=?",
                      (tid, me))
        else:
            if t["code"] == ALL_CODE:
                c.execute("UPDATE dm_members SET hidden=1 WHERE thread_id=? AND user=?",
                          (tid, me))
            else:
                c.execute("DELETE FROM dm_members WHERE thread_id=? AND user=?", (tid, me))
            rest = [r["user"] for r in c.execute(
                "SELECT user FROM dm_members WHERE thread_id=? ORDER BY joined_at",
                (tid,)).fetchall()]
            if rest and t["owner"] == me:
                c.execute("UPDATE dm_threads SET owner=? WHERE id=?", (rest[0], tid))
        c.commit()
    if t["kind"] == "group":
        _post(tid, me, "（脱退しました）", "sys")
    return {"ok": True}


@router.post("/dm/api/t/{tid}/hide")
def api_hide(tid: int, request: Request, u=Depends(_auth)):
    _ok(request)
    _need(tid, u)
    with _lock:
        c = _c()
        c.execute("UPDATE dm_members SET hidden=1 WHERE thread_id=? AND user=?",
                  (tid, _u().norm(u)))
        c.commit()
    return {"ok": True}


@router.get("/dm/api/ping")
def api_ping(request: Request, since: int = 0, u=Depends(_auth)):
    """ナビのバッジ＋ブラウザ通知用。since より新しい発言を返す。"""
    _ok(request)
    me = _u().norm(u)
    items, mx = [], since
    with _lock:
        c = _c()
        rows = c.execute("""
            SELECT t.id, t.kind, t.name, m.notify, m.last_read,
              (SELECT COUNT(*) FROM dm_msgs x WHERE x.thread_id=t.id
                 AND x.id>m.last_read AND x.user<>? AND x.deleted=0) AS unread
            FROM dm_threads t JOIN dm_members m ON m.thread_id=t.id
            WHERE m.user=? AND m.hidden=0""", (me, me)).fetchall()
        total = sum(int(r["unread"] or 0) for r in rows)
        if since > 0:
            for r in rows:
                if not r["notify"]:
                    continue
                for m in c.execute("""SELECT id,user,text,ts FROM dm_msgs
                        WHERE thread_id=? AND id>? AND user<>? AND deleted=0
                        ORDER BY id LIMIT 20""", (r["id"], since, me)).fetchall():
                    items.append({"thread": r["id"], "from": m["user"], "text": m["text"],
                                  "ts": m["ts"], "group": r["kind"] == "group",
                                  "name": r["name"]})
                    mx = max(mx, int(m["id"]))
        else:
            for r in rows:
                x = c.execute("SELECT MAX(id) m FROM dm_msgs WHERE thread_id=?",
                              (r["id"],)).fetchone()
                if x and x["m"]:
                    mx = max(mx, int(x["m"]))
    if items:
        ids = sorted({it["thread"] for it in items})
        q = ",".join("?" * len(ids))
        mem = {}
        with _lock:
            for r in _c().execute(
                    f"SELECT thread_id,user FROM dm_members WHERE thread_id IN ({q})",
                    ids).fetchall():
                mem.setdefault(r["thread_id"], []).append(r["user"])
        for it in items:
            if it["group"]:
                it["title"] = it["name"] or "グループ"
            else:
                ms = mem.get(it["thread"], [])
                it["title"] = next((x for x in ms if x != me), "DM")
    return {"ok": True, "unread": total, "max": mx, "items": items[:12]}