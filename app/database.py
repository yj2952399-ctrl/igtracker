"""SQLite スキーマとアクセス層。特定エンジン用テーブルを大幅追加。"""
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
    is_private INTEGER, is_verified INTEGER, is_business INTEGER,
    business_category TEXT, public_email TEXT, contact_phone TEXT,
    business_email TEXT, business_phone TEXT,
    city TEXT, address TEXT, zipcode TEXT, latitude REAL, longitude REAL,
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
CREATE TABLE IF NOT EXISTS media_likers (
    media_id TEXT, user_id TEXT, username TEXT, archived_at TEXT,
    PRIMARY KEY (media_id, user_id)
);
CREATE TABLE IF NOT EXISTS media_commenters (
    media_id TEXT, user_id TEXT, username TEXT, archived_at TEXT,
    PRIMARY KEY (media_id, user_id)
);
CREATE TABLE IF NOT EXISTS tagged_media (
    media_id TEXT, user_id TEXT, owner_id TEXT, code TEXT, taken_at TEXT,
    archived_at TEXT, PRIMARY KEY (media_id, user_id)
);
CREATE TABLE IF NOT EXISTS related_profiles (
    user_id TEXT, related_id TEXT, related_username TEXT, archived_at TEXT,
    PRIMARY KEY (user_id, related_id)
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
    run_id INTEGER, uraaka_user_id TEXT, candidate_user_id TEXT,
    candidate_username TEXT, score REAL, verdict TEXT, evidence TEXT,
    computed_at TEXT
);
CREATE TABLE IF NOT EXISTS identity_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_uid TEXT, target_username TEXT, status TEXT,
    progress INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
    started_at TEXT, finished_at TEXT, log TEXT
);
CREATE TABLE IF NOT EXISTS forensics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, kind TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, user_id TEXT, kind TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, status TEXT, started_at TEXT, finished_at TEXT, log TEXT
);
CREATE TABLE IF NOT EXISTS known_accounts (
    user_id TEXT PRIMARY KEY, username TEXT, full_name TEXT,
    note TEXT, source TEXT, deleted INTEGER DEFAULT 0,
    added_at TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS saved_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_uid TEXT, target_username TEXT,
    candidate_uid TEXT, candidate_username TEXT,
    note TEXT, added_at TEXT,
    UNIQUE(target_uid, candidate_uid)
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_dm_msg ON dm_messages(thread_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snap ON profile_snapshots(user_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_scores_run ON identity_scores(run_id, score);
CREATE INDEX IF NOT EXISTS idx_forensics_ts ON forensics(ts);
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
        self._migrate()

    def _migrate(self):
        def cols(t):
            return {r["name"] for r in self.q(f"PRAGMA table_info({t})")}
        add = {
            "identity_runs": [("candidates_raw", "TEXT"), ("note", "TEXT"),
                              ("target_deleted", "INTEGER DEFAULT 0")],
            "identity_scores": [("candidate_display", "TEXT"), ("flags", "TEXT")],
        }
        for table, defs in add.items():
            have = cols(table)
            for name, ddl in defs:
                if name not in have:
                    with self.tx() as c:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def q(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def q1(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def log(self, user_id, kind, payload):
        with self.tx() as c:
            c.execute("INSERT INTO events(ts,user_id,kind,payload) VALUES(?,?,?,?)",
                      (now(), user_id, kind,
                       json.dumps(payload, ensure_ascii=False, default=str)))

    def forensic(self, kind, payload):
        with self.tx() as c:
            c.execute("INSERT INTO forensics(ts,kind,payload) VALUES(?,?,?)",
                      (now(), kind, json.dumps(payload, ensure_ascii=False, default=str)))

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
                follower_count,following_count,media_count,is_private,is_verified,is_business,
                business_category,public_email,contact_phone,business_email,business_phone,
                city,address,zipcode,latitude,longitude,profile_pic_url,profile_pic_phash,
                first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username, full_name=excluded.full_name,
                    bio=excluded.bio, external_url=excluded.external_url,
                    follower_count=excluded.follower_count,
                    following_count=excluded.following_count,
                    media_count=excluded.media_count,
                    is_private=excluded.is_private, is_verified=excluded.is_verified,
                    is_business=excluded.is_business,
                    business_category=excluded.business_category,
                    public_email=excluded.public_email,
                    contact_phone=excluded.contact_phone,
                    business_email=excluded.business_email,
                    business_phone=excluded.business_phone,
                    city=excluded.city, address=excluded.address,
                    zipcode=excluded.zipcode, latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    profile_pic_url=excluded.profile_pic_url,
                    profile_pic_phash=excluded.profile_pic_phash,
                    last_seen=excluded.last_seen""",
                (str(u["user_id"]), u.get("username"), u.get("full_name"),
                 u.get("bio"), u.get("external_url"), u.get("follower_count"),
                 u.get("following_count"), u.get("media_count"),
                 int(bool(u.get("is_private"))), int(bool(u.get("is_verified"))),
                 int(bool(u.get("is_business"))), u.get("business_category"),
                 u.get("public_email"), u.get("contact_phone"),
                 u.get("business_email"), u.get("business_phone"),
                 u.get("city"), u.get("address"), u.get("zipcode"),
                 u.get("latitude"), u.get("longitude"),
                 u.get("profile_pic_url"), u.get("profile_pic_phash"), now(), now()))

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

    # ---- 特定ラン ----
    def start_run(self, target_uid, target_username):
        with self.tx() as c:
            cur = c.execute("""INSERT INTO identity_runs(target_uid,target_username,
                status,started_at) VALUES(?,?,?,?)""",
                (target_uid, target_username, "running", now()))
            return cur.lastrowid

    def update_run(self, run_id, progress=None, total=None, status=None, log=None):
        sets, args = [], []
        if progress is not None:
            sets.append("progress=?"); args.append(progress)
        if total is not None:
            sets.append("total=?"); args.append(total)
        if status is not None:
            sets.append("status=?"); args.append(status)
        if log is not None:
            sets.append("log=?"); args.append(log[:20000])
        if status in ("ok", "error"):
            sets.append("finished_at=?"); args.append(now())
        args.append(run_id)
        with self.tx() as c:
            c.execute(f"UPDATE identity_runs SET {','.join(sets)} WHERE id=?", args)