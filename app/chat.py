"""全員チャット。ログイン中の全ユーザーが同じ1部屋で喋れる。

  GET  /chat                 チャット画面
  GET  /chat/api/messages    差分取得（?since=ID / 0で直近）
  POST /chat/api/send        送信 {"text": "..."}
  GET  /chat/api/online      在室者
  POST /chat/api/delete      発言を削除（自分の分。管理者は全件）
  POST /chat/api/clear       全消去（管理者のみ）

保存先は CHAT_DB（既定 data/chat.db）。共有ファイルなので persist が自動バックアップする。
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import datetime as dt

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

DB = os.getenv("CHAT_DB", "data/chat.db")
MAX_LEN = int(os.getenv("CHAT_MAX_LEN", "1000"))
MIN_GAP = float(os.getenv("CHAT_MIN_GAP", "0.6"))     # 連投間隔（秒）
BURST_N = int(os.getenv("CHAT_BURST_N", "15"))        # 窓内の上限通数
BURST_WIN = float(os.getenv("CHAT_BURST_WIN", "30"))  # 窓（秒）
ONLINE_SEC = float(os.getenv("CHAT_ONLINE_SEC", "50"))
KEEP = int(os.getenv("CHAT_KEEP", "3000"))            # 保持する最大行数
FETCH = int(os.getenv("CHAT_FETCH", "200"))

_lock = threading.RLock()
_conn = None
_rate = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_msgs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, user TEXT, text TEXT, kind TEXT DEFAULT 'msg',
  deleted INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS chat_msgs_id ON chat_msgs(id);
CREATE TABLE IF NOT EXISTS chat_online(
  user TEXT PRIMARY KEY, ts REAL, ua TEXT);
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


async def _auth(request: Request):
    return await _m().auth(request)


def _touch_online(user, ua=""):
    with _lock:
        c = _c()
        c.execute("INSERT INTO chat_online(user,ts,ua) VALUES(?,?,?) "
                  "ON CONFLICT(user) DO UPDATE SET ts=excluded.ts, ua=excluded.ua",
                  (user, time.time(), (ua or "")[:120]))
        c.execute("DELETE FROM chat_online WHERE ts < ?", (time.time() - 86400,))
        c.commit()


def _online(limit=80):
    cut = time.time() - ONLINE_SEC
    with _lock:
        rows = _c().execute("SELECT user FROM chat_online WHERE ts>=? "
                            "ORDER BY ts DESC LIMIT ?", (cut, limit)).fetchall()
    return [r["user"] for r in rows]


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


@router.get("/chat", response_class=HTMLResponse)
def page(request: Request, u=Depends(_auth)):
    _touch_online(u, request.headers.get("user-agent", ""))
    return _m().render("chat.html", request,
                       online=_online(), online_sec=int(ONLINE_SEC),
                       max_len=MAX_LEN, chat_admin=_m().users.is_admin(u))


@router.get("/chat/api/messages")
def messages(request: Request, since: int = 0, u=Depends(_auth)):
    _touch_online(u, request.headers.get("user-agent", ""))
    with _lock:
        c = _c()
        if since > 0:
            rows = c.execute("SELECT * FROM chat_msgs WHERE id>? ORDER BY id LIMIT ?",
                             (since, FETCH)).fetchall()
        else:
            rows = list(reversed(c.execute(
                "SELECT * FROM chat_msgs ORDER BY id DESC LIMIT ?", (FETCH,)).fetchall()))
    out = []
    for r in rows:
        d = dict(r)
        d["mine"] = (d["user"] == u)
        d["deleted"] = bool(d["deleted"])
        d.update(_profile_fields(d["user"]))
        out.append(d)
    online_names = _online()
    online_users = [{"username": n, **_profile_fields(n)} for n in online_names]
    return {"ok": True, "msgs": out, "online": online_names,
            "online_users": online_users, "now": _now()}


@router.get("/chat/api/heartbeat")
def heartbeat(request: Request, u=Depends(_auth)):
    _touch_online(u, request.headers.get("user-agent", ""))
    return {"ok": True, "online": len(_online(limit=10000))}


def _profile_fields(username):
    try:
        p = _m().users.get_profile(username)
        return {"display_name": (p.get("display_name") or "").strip() or username,
                "avatar": ("/profile/avatar/" + username) if p.get("avatar_data") else ""}
    except Exception:
        return {"display_name": username, "avatar": ""}


@router.get("/chat/api/online")
def online(u=Depends(_auth)):
    return {"ok": True, "online": _online()}


@router.post("/chat/api/send")
async def send(request: Request, u=Depends(_auth)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str((body or {}).get("text") or "").strip()[:MAX_LEN]
    if not text:
        return JSONResponse({"ok": False, "why": "空です"}, status_code=400)
    ok, why = _rate_ok(u)
    if not ok:
        return JSONResponse({"ok": False, "why": why}, status_code=429)
    with _lock:
        c = _c()
        cur = c.execute("INSERT INTO chat_msgs(ts,user,text,kind) VALUES(?,?,?,?)",
                        (_now(), u, text, "msg"))
        mid = cur.lastrowid
        c.execute("DELETE FROM chat_msgs WHERE id<=?", (mid - KEEP,))
        c.commit()
    _touch_online(u, request.headers.get("user-agent", ""))
    return {"ok": True, "id": mid}


@router.post("/chat/api/delete")
async def delete(request: Request, u=Depends(_auth)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    mid = int((body or {}).get("id") or 0)
    if not mid:
        return {"ok": False}
    with _lock:
        c = _c()
        r = c.execute("SELECT user FROM chat_msgs WHERE id=?", (mid,)).fetchone()
        if not r:
            return {"ok": False, "why": "無い"}
        if r["user"] != u and not _m().users.is_admin(u):
            return {"ok": False, "why": "他人の発言です"}
        c.execute("UPDATE chat_msgs SET deleted=1 WHERE id=?", (mid,))
        c.commit()
    return {"ok": True}


@router.post("/chat/api/clear")
def clear(u=Depends(_auth)):
    if not _m().users.is_admin(u):
        raise HTTPException(403, "admin only")
    with _lock:
        c = _c()
        c.execute("DELETE FROM chat_msgs")
        c.commit()
    return {"ok": True}