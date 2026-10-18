"""SQLite スキーマとアクセス層。全データはここに集約される。"""
import sqlite3, json, datetime as dt, os
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    user_id TEXT PRIMARY KEY,
    username TEXT, added_at TEXT, monitor INTEGER DEFAULT 1, note TEXT
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT, full_name TEXT, bio TEXT, external_url TEXT,
    follower_count INTEGER, following_count INTEGER, media_count INTEGER,
    is_private INTEGER, is_verified INTEGER, business_category TEXT,
    profile_pic_url TEXT, profile_pic_phash TEXT,
    first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS profile_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT, taken_at TEXT,
    follower_count INTEGER, following_count INTEGER, media_count INTEGER,
    bio TEXT, full_name TEXT, profile_pic_phash TEXT, external_url TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    media_id TEXT PRIMARY KEY,
    user_id TEXT, code TEXT, taken_at TEXT, media_type INTEGER,
    caption TEXT, location_name TEXT, location_id TEXT,
    like_count INTEGER, comment_count INTEGER, play_count INTEGER,
    view_count INTEGER, is_video INTEGER, url TEXT, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS post_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id TEXT, observed_at TEXT, like_count INTEGER, comment_count INTEGER
);
CREATE TABLE IF NOT EXISTS stories (
    pk TEXT PRIMARY KEY, user_id TEXT, taken_at TEXT, expiring_at TEXT,
    media_type INTEGER, caption TEXT, url TEXT, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS highlights (
    pk TEXT PRIMARY KEY, user_id TEXT, title TEXT, cover_url TEXT,
    item_count INTEGER, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS relationships (
    from_user_id TEXT, to_user_id TEXT, to_username TEXT, direction TEXT,
    observed_at TEXT,
    PRIMARY KEY (from_user_id, to_user_id, direction, observed_at)
);
CREATE TABLE IF NOT EXISTS relationship_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id TEXT, to_user_id TEXT, to_username TEXT,
    event_type TEXT, observed_at TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    pk TEXT PRIMARY KEY, media_id TEXT, user_id TEXT, username TEXT,
    text TEXT, created_at TEXT, like_count INTEGER, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS dm_threads (
    thread_id TEXT PRIMARY KEY, title TEXT, participants TEXT,
    last_activity_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS dm_messages (
    message_id TEXT PRIMARY KEY, thread_id TEXT, sender_id TEXT,
    sender_username TEXT, timestamp TEXT, item_type TEXT, text TEXT,
    media_url TEXT, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS identity_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uraaka_user_id TEXT, candidate_user_id TEXT, candidate_username TEXT,
    score REAL, evidence TEXT, computed_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, user_id TEXT, kind TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, status TEXT, started_at TEXT, finished_at TEXT, log TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_dm_msg ON dm_messages(thread_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snap ON profile_snapshots(user_id, taken_at);
"""

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---- 汎用 ----
    def q(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def q1(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def log(self, user_id, kind, payload):
        with self.tx() as c:
            c.execute("INSERT INTO events(ts,user_id,kind,payload) VALUES(?,?,?,?)",
                      (now(), user_id, kind, json.dumps(payload, ensure_ascii=False, default=str)))

    # ---- ターゲット ----
    def add_target(self, user_id, username, note=""):
        with self.tx() as c:
            c.execute("""INSERT INTO targets(user_id,username,added_at,monitor,note)
                VALUES(?,?,?,1,?)
                ON CONFLICT(user_id) DO UPDATE SET username=excluded.username""",
                (str(user_id), username, now(), note))

    def targets(self, only_monitored=False):
        sql = "SELECT * FROM targets"
        if only_monitored:
            sql += " WHERE monitor=1"
        return self.q(sql + " ORDER BY added_at")

    # ---- プロフィール ----
    def upsert_profile(self, u):
        with self.tx() as c:
            c.execute("""INSERT INTO profiles(user_id,username,full_name,bio,external_url,
                follower_count,following_count,media_count,is_private,is_verified,
                business_category,profile_pic_url,profile_pic_phash,first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username, full_name=excluded.full_name,
                    bio=excluded.bio, external_url=excluded.external_url,
                    follower_count=excluded.follower_count,
                    following_count=excluded.following_count,
                    media_count=excluded.media_count,
                    is_private=excluded.is_private, is_verified=excluded.is_verified,
                    business_category=excluded.business_category,
                    profile_pic_url=excluded.profile_pic_url,
                    profile_pic_phash=excluded.profile_pic_phash,
                    last_seen=excluded.last_seen""",
                (str(u["user_id"]), u.get("username"), u.get("full_name"),
                 u.get("bio"), u.get("external_url"), u.get("follower_count"),
                 u.get("following_count"), u.get("media_count"),
                 int(bool(u.get("is_private"))), int(bool(u.get("is_verified"))),
                 u.get("business_category"), u.get("profile_pic_url"),
                 u.get("profile_pic_phash"), now(), now()))

    def snapshot_profile(self, u):
        with self.tx() as c:
            c.execute("""INSERT INTO profile_snapshots(user_id,taken_at,follower_count,
                following_count,media_count,bio,full_name,profile_pic_phash,external_url)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (str(u["user_id"]), now(), u.get("follower_count"),
                 u.get("following_count"), u.get("media_count"), u.get("bio"),
                 u.get("full_name"), u.get("profile_pic_phash"), u.get("external_url")))

    # ---- ジョブ ----
    def start_job(self, name):
        with self.tx() as c:
            cur = c.execute("INSERT INTO jobs(name,status,started_at) VALUES(?,?,?)",
                            (name, "running", now()))
            return cur.lastrowid

    def finish_job(self, job_id, status, log=""):
        with self.tx() as c:
            c.execute("UPDATE jobs SET status=?,finished_at=?,log=? WHERE id=?",
                      (status, now(), log[:20000], job_id))