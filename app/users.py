"""ユーザー台帳（ルートDB）。パスワードは scrypt ハッシュのみ保存。"""
import os, re, hmac, base64, hashlib, secrets, sqlite3, threading, time
from .database import now

ROOT_DB = os.getenv("ROOT_DB", "data/root.db")
USER_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,38}$")

_lock = threading.RLock()
_conn = None
_fails = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    pwd_salt TEXT, pwd_hash TEXT,
    role TEXT DEFAULT 'user',
    disabled INTEGER DEFAULT 0,
    must_change INTEGER DEFAULT 0,
    created_at TEXT, last_login TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS link_index (
    code TEXT PRIMARY KEY, owner TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, actor TEXT, action TEXT, detail TEXT
);
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
    return _conn


def init():
    with _lock:
        _c()


def norm(u):
    return (u or "").strip().lower()


def valid(u):
    return bool(USER_RE.match(norm(u)))


def _hash(pw, salt: bytes) -> str:
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1,
                        dklen=32, maxmem=64 * 1024 * 1024)
    return base64.b64encode(dk).decode()


# ---- 参照 ----

def get(u):
    with _lock:
        return _c().execute("SELECT * FROM users WHERE username=?", (norm(u),)).fetchone()


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


def env_admin():
    u = os.getenv("ADMIN_USER") or os.getenv("WEB_USER") or ""
    p = os.getenv("ADMIN_PASS") or os.getenv("WEB_PASS") or ""
    return (norm(u), p) if u and p else ("", "")


def role_of(u):
    u = norm(u)
    eu, _ = env_admin()
    if eu and u == eu:
        return "admin"
    r = get(u)
    return r["role"] if r else "user"


def is_admin(u):
    return role_of(u) == "admin"


def check_password(u, pw):
    r = get(u)
    if not r or r["disabled"]:
        return False
    try:
        salt = base64.b64decode(r["pwd_salt"])
        return hmac.compare_digest(_hash(pw or "", salt), r["pwd_hash"])
    except Exception:
        return False


# ---- 更新 ----

def create(u, pw, role="user", note="", must_change=0):
    u = norm(u)
    if not valid(u):
        raise ValueError("ユーザー名は英小文字/数字/._- の1〜39文字にしてください")
    if len(pw or "") < 8:
        raise ValueError("パスワードは8文字以上にしてください")
    salt = secrets.token_bytes(16)
    with _lock:
        c = _c()
        c.execute("""INSERT INTO users(username,pwd_salt,pwd_hash,role,disabled,
            must_change,created_at,note) VALUES(?,?,?,?,0,?,?,?)
            ON CONFLICT(username) DO UPDATE SET pwd_salt=excluded.pwd_salt,
            pwd_hash=excluded.pwd_hash, role=excluded.role, disabled=0,
            must_change=excluded.must_change, note=excluded.note""",
            (u, base64.b64encode(salt).decode(), _hash(pw, salt), role,
             int(bool(must_change)), now(), note))
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
        c.execute("UPDATE users SET pwd_salt=?,pwd_hash=?,must_change=? WHERE username=?",
                  (base64.b64encode(salt).decode(), _hash(pw, salt),
                   int(bool(must_change)), u))
        c.commit()
    audit(u, "set_password", {})


def set_role(u, role):
    with _lock:
        c = _c()
        c.execute("UPDATE users SET role=? WHERE username=?", (role, norm(u)))
        c.commit()
    audit(u, "set_role", {"role": role})


def set_disabled(u, flag):
    with _lock:
        c = _c()
        c.execute("UPDATE users SET disabled=? WHERE username=?", (int(bool(flag)), norm(u)))
        c.commit()
    audit(u, "set_disabled", {"disabled": bool(flag)})


def delete(u):
    with _lock:
        c = _c()
        c.execute("DELETE FROM users WHERE username=?", (norm(u),))
        c.commit()
    audit(u, "delete", {})


def _touch(u):
    now_t = time.time()
    if now_t - _last.get(u, 0) < 60:
        return
    _last[u] = now_t
    try:
        with _lock:
            c = _c()
            c.execute("UPDATE users SET last_login=? WHERE username=?", (now(), u))
            c.commit()
    except Exception:
        pass


_last = {}


# ---- 認証 ----

def _bump_fail(ip):
    if not ip:
        return
    n, t0 = _fails.get(ip, (0, time.time()))
    if time.time() - t0 > 600:
        n, t0 = 0, time.time()
    _fails[ip] = (n + 1, t0)


def is_throttled(ip):
    n, t0 = _fails.get(ip, (0, 0))
    return n >= 20 and (time.time() - t0) <= 600


def verify(username, password, ip=None):
    u = norm(username)
    row = get(u)
    ok = False
    role = "user"
    must = 0
    if row and not row["disabled"]:
        try:
            salt = base64.b64decode(row["pwd_salt"])
            ok = hmac.compare_digest(_hash(password or "", salt), row["pwd_hash"])
        except Exception:
            ok = False
        role, must = row["role"], row["must_change"]
    if not ok:
        eu, ep = env_admin()
        if eu and hmac.compare_digest(u, eu) and hmac.compare_digest(password or "", ep):
            ok, role, must = True, "admin", 0
    if not ok:
        _bump_fail(ip)
        return None
    _fails.pop(ip, None)
    _touch(u)
    return {"username": u, "role": role, "must_change": bool(must)}


def bootstrap_env_admin():
    """起動時に必ず呼ぶ。DBが消えても管理者で入れるようにする保険。"""
    eu, ep = env_admin()
    if eu and ep:
        row = get(eu)
        if row is None:
            create(eu, ep, role="admin", note="env bootstrap")
        elif row["role"] != "admin" or row["disabled"]:
            set_role(eu, "admin")
            set_disabled(eu, 0)
        return eu
    if count() == 0:
        pw = secrets.token_urlsafe(12)
        create("admin", pw, role="admin", note="auto generated")
        print(f"[users] 初期管理者を作成: admin / {pw}  "
              f"(環境変数 ADMIN_USER / ADMIN_PASS を推奨)")
        return "admin"
    return ""


# ---- リンクのオーナー索引 ----

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


def audit(actor, action, detail=None):
    try:
        import json
        with _lock:
            c = _c()
            c.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)",
                      (now(), norm(actor), action, json.dumps(detail or {}, ensure_ascii=False)))
            c.commit()
    except Exception:
        pass