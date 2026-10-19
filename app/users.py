"""ユーザー台帳・セッション・監査。パスワードは scrypt ハッシュのみ保存。

設計:
  - パスワードは平文を一切残さない（scrypt + 定数時間比較）
  - セッションはランダムトークン。DB には SHA-256 のみ保存
  - realm='user' と realm='admin' を分離（管理者は別パスワード・別Cookie）
  - pw_epoch / admin_epoch をパスワード変更でインクリメント → 全端末即無効
  - env は「初回ブートストラップ」と「ブレークグラス」専用
"""
import os, re, hmac, base64, hashlib, secrets, sqlite3, threading, time, json
import datetime as dt

from .database import now

ROOT_DB = os.getenv("ROOT_DB", "data/root.db")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))

USER_RE = re.compile(r"^[a-z0-9]([a-z0-9_.-]{0,38}[a-z0-9])?$")

RESERVED = {
    "admin", "root", "system", "me", "api", "app", "www", "null", "undefined",
    "static", "assets", "media", "data", "tenant", "tenants", "setup",
    "login", "logout", "signup", "account", "settings", "password", "reset",
    "invite", "link", "links", "l", "docs", "favicon.ico", "healthz",
    "export.json", "import", "test", "demo", "guest", "user",
}

_lock = threading.RLock()
_conn = None
_fails = {}
_touch_at = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    pwd_salt TEXT, pwd_hash TEXT, pw_epoch INTEGER DEFAULT 1,
    role TEXT DEFAULT 'user',
    admin_salt TEXT, admin_hash TEXT, admin_epoch INTEGER DEFAULT 1,
    disabled INTEGER DEFAULT 0, must_change INTEGER DEFAULT 0,
    created_at TEXT, last_login TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    sid TEXT PRIMARY KEY, username TEXT, realm TEXT DEFAULT 'user',
    epoch INTEGER DEFAULT 0, created_at TEXT, last_seen TEXT, expires_at TEXT,
    ip TEXT, ua TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, actor TEXT, action TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS link_index (
    code TEXT PRIMARY KEY, owner TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(username, realm);
"""


def _c():
    global _conn
    if _conn is None:
        d = os.path.dirname(ROOT_DB)
        if d:
            os.makedirs(d, exist_ok=True)
        _conn = sqlite3.connect(ROOT_DB, check_same_thread=False, timeout=30)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=10000")
        _conn.executescript(SCHEMA)
        _conn.commit()
        _migrate(_conn)
    return _conn


def _migrate(c):
    def cols(t):
        return {r["name"] for r in c.execute(f"PRAGMA table_info({t})").fetchall()}
    add = {
        "users": [("pw_epoch", "INTEGER DEFAULT 1"), ("admin_salt", "TEXT"),
                  ("admin_hash", "TEXT"), ("admin_epoch", "INTEGER DEFAULT 1"),
                  ("must_change", "INTEGER DEFAULT 0"), ("note", "TEXT")],
    }
    for table, defs in add.items():
        have = cols(table)
        for name, ddl in defs:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    c.commit()


def init():
    with _lock:
        _c()


# ---------- 基本 ----------

def norm(u):
    return (u or "").strip().lower()


def valid(u):
    u = norm(u)
    return bool(USER_RE.match(u)) and u not in RESERVED


def _hash(pw, salt: bytes) -> str:
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1,
                        dklen=32, maxmem=64 * 1024 * 1024)
    return base64.b64encode(dk).decode()


def _now():
    return dt.datetime.now(dt.timezone.utc)


def env_admin():
    u = os.getenv("ADMIN_USER") or os.getenv("WEB_USER") or ""
    p = os.getenv("ADMIN_PASS") or os.getenv("WEB_PASS") or ""
    return (norm(u), p) if u and p else ("", "")


def env_breakglass():
    return os.getenv("ADMIN_BREAKGLASS") or ""


# ---------- 参照 ----------

def get(u):
    with _lock:
        return _c().execute("SELECT * FROM users WHERE username=?", (norm(u),)).fetchone()


def exists(u):
    return get(u) is not None


def list_users():
    with _lock:
        return _c().execute(
            "SELECT username,role,disabled,must_change,created_at,last_login,note "
            "FROM users ORDER BY role DESC, username").fetchall()


def list_usernames(include_disabled=False):
    sql = "SELECT username FROM users"
    if not include_disabled:
        sql += " WHERE disabled=0"
    with _lock:
        return [r["username"] for r in _c().execute(sql + " ORDER BY username").fetchall()]


def count():
    with _lock:
        return _c().execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def count_admins():
    with _lock:
        return _c().execute(
            "SELECT COUNT(*) c FROM users WHERE role='admin'").fetchone()["c"]


def role_of(u):
    u = norm(u)
    eu, _ = env_admin()
    if eu and u == eu:
        return "admin"
    r = get(u)
    return r["role"] if r else "user"


def is_admin(u):
    return role_of(u) == "admin"


# ---------- 作成・更新 ----------

def create(u, pw, role="user", note="", must_change=0):
    u = norm(u)
    if not valid(u):
        if u in RESERVED:
            raise ValueError("その名前は予約されています")
        raise ValueError("ユーザー名は英小文字/数字/._- の2〜40文字（先頭末尾は英数字）")
    if len(pw or "") < 8:
        raise ValueError("パスワードは8文字以上にしてください")
    salt = secrets.token_bytes(16)
    with _lock:
        c = _c()
        c.execute("""INSERT INTO users(username,pwd_salt,pwd_hash,pw_epoch,role,
            disabled,must_change,created_at,note) VALUES(?,?,?,1,?,0,?,?,?)
            ON CONFLICT(username) DO UPDATE SET pwd_salt=excluded.pwd_salt,
            pwd_hash=excluded.pwd_hash, pw_epoch=users.pw_epoch+1,
            role=excluded.role, disabled=0, must_change=excluded.must_change,
            note=excluded.note""",
            (u, base64.b64encode(salt).decode(), _hash(pw, salt),
             "admin" if role == "admin" else "user", int(bool(must_change)), now(), note))
        c.execute("DELETE FROM sessions WHERE username=? AND realm='user'", (u,))
        c.commit()
    audit(u, "create", {"role": role})
    return u


def set_password(u, pw, must_change=0):
    u = norm(u)
    if len(pw or "") < 8:
        raise ValueError("パスワードは8文字以上にしてください")
    salt = secrets.token_bytes(16)
    with _lock:
        c = _c()
        c.execute("""UPDATE users SET pwd_salt=?, pwd_hash=?, pw_epoch=pw_epoch+1,
            must_change=? WHERE username=?""",
            (base64.b64encode(salt).decode(), _hash(pw, salt), int(bool(must_change)), u))
        c.execute("DELETE FROM sessions WHERE username=? AND realm='user'", (u,))
        c.commit()
    audit(u, "set_password", {})


def set_admin_password(u, pw):
    u = norm(u)
    if len(pw or "") < 8:
        raise ValueError("管理者パスワードは8文字以上にしてください")
    salt = secrets.token_bytes(16)
    with _lock:
        c = _c()
        c.execute("""UPDATE users SET admin_salt=?, admin_hash=?, admin_epoch=admin_epoch+1
            WHERE username=?""",
            (base64.b64encode(salt).decode(), _hash(pw, salt), u))
        c.execute("DELETE FROM sessions WHERE username=? AND realm='admin'", (u,))
        c.commit()
    audit(u, "set_admin_password", {})


def set_role(u, role):
    with _lock:
        c = _c()
        c.execute("UPDATE users SET role=? WHERE username=?", (role, norm(u)))
        if role != "admin":
            c.execute("DELETE FROM sessions WHERE username=? AND realm='admin'", (norm(u),))
        c.commit()
    audit(u, "set_role", {"role": role})


def set_disabled(u, flag):
    with _lock:
        c = _c()
        c.execute("UPDATE users SET disabled=? WHERE username=?", (int(bool(flag)), norm(u)))
        if flag:
            c.execute("DELETE FROM sessions WHERE username=?", (norm(u),))
        c.commit()
    audit(u, "set_disabled", {"disabled": bool(flag)})


def delete(u):
    with _lock:
        c = _c()
        c.execute("DELETE FROM users WHERE username=?", (norm(u),))
        c.execute("DELETE FROM sessions WHERE username=?", (norm(u),))
        c.commit()
    audit(u, "delete", {})


# ---------- 認証 ----------

def check_password(u, pw):
    r = get(u)
    if not r or r["disabled"]:
        return False
    try:
        salt = base64.b64decode(r["pwd_salt"])
        return hmac.compare_digest(_hash(pw or "", salt), r["pwd_hash"])
    except Exception:
        return False


def verify_user(username, password):
    u = norm(username)
    row = get(u)
    if not row or row["disabled"]:
        return None
    try:
        salt = base64.b64decode(row["pwd_salt"])
        if not hmac.compare_digest(_hash(password or "", salt), row["pwd_hash"]):
            return None
    except Exception:
        return None
    _touch_login(u)
    return {"username": u, "role": row["role"], "must_change": bool(row["must_change"])}


def verify_admin(username, password):
    """管理者パスワード。env のブレークグラスが設定されていれば常に通す。"""
    u = norm(username)
    bg = env_breakglass()
    row = get(u)
    if not row or row["disabled"] or row["role"] != "admin":
        eu, _ = env_admin()
        if eu and bg and u == eu and hmac.compare_digest(password or "", bg):
            return True
        return False
    if bg and hmac.compare_digest(password or "", bg):
        _touch_login(u)
        return True
    if not row["admin_hash"]:
        return False
    try:
        salt = base64.b64decode(row["admin_salt"])
        if not hmac.compare_digest(_hash(password or "", salt), row["admin_hash"]):
            return False
    except Exception:
        return False
    _touch_login(u)
    return True


def _touch_login(u):
    t = time.time()
    if t - _touch_at.get(u, 0) < 60:
        return
    _touch_at[u] = t
    try:
        with _lock:
            c = _c()
            c.execute("UPDATE users SET last_login=? WHERE username=?", (now(), u))
            c.commit()
    except Exception:
        pass


# ---------- セッション ----------

def _sid(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def new_session(username, realm="user", ip="", ua=""):
    u = norm(username)
    row = get(u)
    if not row:
        return ""
    epoch = int(row["pw_epoch"] if realm == "user" else row["admin_epoch"])
    token = secrets.token_urlsafe(32)
    with _lock:
        c = _c()
        c.execute("""INSERT INTO sessions(sid,username,realm,epoch,created_at,
            last_seen,expires_at,ip,ua) VALUES(?,?,?,?,?,?,?,?,?)""",
            (_sid(token), u, realm, epoch, now(), now(),
             (_now() + dt.timedelta(days=SESSION_DAYS)).isoformat(),
             (ip or "")[:64], (ua or "")[:300]))
        c.commit()
    return token


def resolve_session(token, realm="user"):
    if not token:
        return None
    sid = _sid(token)
    with _lock:
        r = _c().execute("SELECT * FROM sessions WHERE sid=?", (sid,)).fetchone()
    if not r or r["realm"] != realm:
        return None
    if r["expires_at"] and r["expires_at"] < now():
        delete_session(token)
        return None
    u = get(r["username"])
    if not u or u["disabled"]:
        return None
    if realm == "admin" and u["role"] != "admin":
        return None
    cur = int(u["pw_epoch"] if realm == "user" else u["admin_epoch"])
    if int(r["epoch"] or 0) != cur:
        delete_session(token)
        return None
    _touch_session(sid)
    return u


def _touch_session(sid):
    t = time.time()
    if t - _touch_at.get("s:" + sid, 0) < 120:
        return
    _touch_at["s:" + sid] = t
    try:
        with _lock:
            c = _c()
            c.execute("UPDATE sessions SET last_seen=? WHERE sid=?", (now(), sid))
            c.commit()
    except Exception:
        pass


def delete_session(token):
    if not token:
        return
    with _lock:
        c = _c()
        c.execute("DELETE FROM sessions WHERE sid=?", (_sid(token),))
        c.commit()


def delete_sessions(username, realm=None):
    with _lock:
        c = _c()
        if realm:
            c.execute("DELETE FROM sessions WHERE username=? AND realm=?",
                      (norm(username), realm))
        else:
            c.execute("DELETE FROM sessions WHERE username=?", (norm(username),))
        c.commit()


def list_sessions(username, realm="user"):
    with _lock:
        return _c().execute(
            "SELECT * FROM sessions WHERE username=? AND realm=? "
            "ORDER BY last_seen DESC", (norm(username), realm)).fetchall()


def sid_of(token):
    return _sid(token)


def purge_expired():
    with _lock:
        c = _c()
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        c.commit()


# ---------- レート制限 ----------

def bump_fail(key):
    n, t0 = _fails.get(key, (0, time.time()))
    if time.time() - t0 > 600:
        n, t0 = 0, time.time()
    _fails[key] = (n + 1, t0)


def clear_fail(key):
    _fails.pop(key, None)


def is_throttled(key, limit=15, window=600):
    n, t0 = _fails.get(key, (0, 0))
    return n >= limit and (time.time() - t0) <= window


# ---------- 監査 ----------

def audit(actor, action, detail=None):
    try:
        with _lock:
            c = _c()
            c.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)",
                      (now(), norm(actor), action,
                       json.dumps(detail or {}, ensure_ascii=False, default=str)))
            c.commit()
    except Exception:
        pass


def list_audit(limit=300):
    with _lock:
        return _c().execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ---------- ブートストラップ ----------

def bootstrap_admin():
    """起動時に呼ぶ。管理者が居なければ env から1回だけ作る。"""
    eu, ep = env_admin()
    if not eu or not ep:
        if count_admins() == 0 and count() == 0:
            pw = secrets.token_urlsafe(12)
            create("admin", pw, role="admin", note="auto generated")
            set_admin_password("admin", pw)
            print(f"[users] 初期管理者を作成: admin / {pw}")
            print("[users] 環境変数 ADMIN_USER / ADMIN_PASS の設定を推奨します")
            return "admin"
        return ""
    row = get(eu)
    if row is None:
        create(eu, ep, role="admin", note="env bootstrap")
        set_admin_password(eu, ep)
        print(f"[users] 管理者 {eu} を環境変数から作成しました")
    else:
        if row["role"] != "admin":
            set_role(eu, "admin")
        if not row["admin_hash"]:
            set_admin_password(eu, ep)
    if env_breakglass():
        print("[users] ADMIN_BREAKGLASS が有効です（常に /管理者ログイン で通ります）")
    return eu


# ---------- リンクのオーナー索引 ----------

def register_link(code, owner):
    with _lock:
        c = _c()
        c.execute("INSERT OR REPLACE INTO link_index(code,owner,created_at) VALUES(?,?,?)",
                  (code, norm(owner), now()))
        c.commit()


def owner_of_link(code):
    with _lock:
        r = _c().execute("SELECT owner FROM link_index WHERE code=?", (code,)).fetchone()
    return r["owner"] if r else None


def unregister_link(code):
    with _lock:
        c = _c()
        c.execute("DELETE FROM link_index WHERE code=?", (code,))
        c.commit()