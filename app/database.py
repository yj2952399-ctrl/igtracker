"""SQLite スキーマとアクセス層。特定エンジン + リンク追跡 + 横断検索。スレッド安全版。"""
import sqlite3, json, datetime as dt, os, threading
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
    candidate_username TEXT, candidate_display TEXT, score REAL, verdict TEXT,
    evidence TEXT, flags TEXT, computed_at TEXT
);
CREATE TABLE IF NOT EXISTS identity_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_uid TEXT, target_username TEXT, status TEXT,
    progress INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
    candidates_raw TEXT, note TEXT, target_deleted INTEGER DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS links (
    code TEXT PRIMARY KEY, name TEXT, dest TEXT, note TEXT,
    mode TEXT DEFAULT 'page', created_at TEXT,
    hit_count INTEGER DEFAULT 0, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS link_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT, ts TEXT, ip TEXT, ua TEXT, lang TEXT, referer TEXT,
    accept TEXT, headers TEXT, query TEXT,
    country TEXT, country_code TEXT, region TEXT, city TEXT, zip TEXT,
    isp TEXT, org TEXT, asn TEXT, tz TEXT, lat REAL, lon REAL,
    gps_lat REAL, gps_lon REAL, gps_acc REAL,
    device TEXT, os TEXT, browser TEXT, inapp TEXT,
    is_bot INTEGER DEFAULT 0, is_mobile INTEGER, is_proxy INTEGER, is_hosting INTEGER,
    screen TEXT, platform TEXT, cores INTEGER, mem REAL, touch INTEGER,
    extra TEXT, note TEXT,
    vid TEXT, fingerprint TEXT, pubkey TEXT, sig TEXT, sig_ok INTEGER,
    nonce TEXT, fp_json TEXT,
    quiz_done INTEGER DEFAULT 0, quiz_score REAL, quiz_total INTEGER, quiz_ms INTEGER
);
CREATE TABLE IF NOT EXISTS link_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT, ord INTEGER DEFAULT 0, qtype TEXT DEFAULT 'choice',
    prompt TEXT, options TEXT, answer_key TEXT, reveal TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS link_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT, hit_id INTEGER, qid INTEGER, ord INTEGER, qtype TEXT,
    answer TEXT, is_correct INTEGER, ms INTEGER, ip TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS visitors (
    vid TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT, hits INTEGER DEFAULT 0,
    ip TEXT, country TEXT, region TEXT, city TEXT, isp TEXT, asn TEXT,
    device TEXT, os TEXT, browser TEXT, inapp TEXT,
    fingerprint TEXT, pubkey TEXT, label TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS track_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT, link_id INTEGER, person TEXT, sid TEXT,
    ts TEXT, kind TEXT DEFAULT 'pt', src TEXT DEFAULT 'gps',
    lat REAL, lon REAL, acc REAL, spd REAL, hdg REAL,
    ip TEXT, country TEXT, country_code TEXT, region TEXT, city TEXT, isp TEXT, asn TEXT,
    device TEXT, os TEXT, browser TEXT, inapp TEXT,
    battery REAL, charging INTEGER, screen TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS sns_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT, total INTEGER DEFAULT 0, found INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running', started_at TEXT, finished_at TEXT, log TEXT
);
CREATE TABLE IF NOT EXISTS sns_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER, username TEXT, site TEXT, site_name TEXT, cat TEXT,
    url TEXT, state TEXT, code INTEGER, title TEXT, og_image TEXT,
    phash TEXT, seen_at TEXT
);
CREATE TABLE IF NOT EXISTS sns_avatars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, ref TEXT, site TEXT, url TEXT, phash TEXT, seen_at TEXT,
    UNIQUE(source, ref, site)
);
CREATE TABLE IF NOT EXISTS gravatar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT, md5 TEXT, display_name TEXT, profile_url TEXT,
    has_avatar INTEGER, accounts TEXT, urls TEXT, raw TEXT, seen_at TEXT,
    UNIQUE(email)
);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, note TEXT, mode TEXT DEFAULT 'page', message TEXT,
    created_at TEXT, status TEXT DEFAULT 'draft',
    total INTEGER DEFAULT 0, sent INTEGER DEFAULT 0, failed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS campaign_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER, username TEXT, user_id TEXT, code TEXT,
    state TEXT DEFAULT 'pending', sent_at TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_dm_msg ON dm_messages(thread_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_snap ON profile_snapshots(user_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_scores_run ON identity_scores(run_id, score);
CREATE INDEX IF NOT EXISTS idx_forensics_ts ON forensics(ts);
CREATE INDEX IF NOT EXISTS idx_known_seen ON known_accounts(last_seen);
CREATE INDEX IF NOT EXISTS idx_hits_code ON link_hits(code, ts);
CREATE INDEX IF NOT EXISTS idx_q_code ON link_questions(code, ord);
CREATE INDEX IF NOT EXISTS idx_ans_hit ON link_answers(hit_id);
CREATE INDEX IF NOT EXISTS idx_ans_code ON link_answers(code, ts);
CREATE INDEX IF NOT EXISTS idx_visitors_seen ON visitors(last_seen);
CREATE INDEX IF NOT EXISTS idx_sns_scan ON sns_hits(scan_id, state);
CREATE INDEX IF NOT EXISTS idx_sns_u ON sns_hits(username, state);
CREATE INDEX IF NOT EXISTS idx_ct_camp ON campaign_targets(campaign_id, state);
CREATE INDEX IF NOT EXISTS idx_tp_code ON track_points(code, id);
CREATE INDEX IF NOT EXISTS idx_tp_sid ON track_points(code, sid, id);
CREATE INDEX IF NOT EXISTS idx_tp_ts ON track_points(ts);
"""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
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
            "link_hits": [("inapp", "TEXT"), ("platform", "TEXT"), ("cores", "INTEGER"),
                          ("mem", "REAL"), ("touch", "INTEGER"), ("note", "TEXT"),
                          ("vid", "TEXT"), ("fingerprint", "TEXT"), ("pubkey", "TEXT"),
                          ("sig", "TEXT"), ("sig_ok", "INTEGER"), ("nonce", "TEXT"),
                          ("fp_json", "TEXT"), ("quiz_done", "INTEGER DEFAULT 0"),
                          ("quiz_score", "REAL"), ("quiz_total", "INTEGER"),
                          ("quiz_ms", "INTEGER")],
        }
        for table, defs in add.items():
            have = cols(table)
            for name, ddl in defs:
                if name not in have:
                    with self.tx() as c:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def q(self, sql, args=()):
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    def q1(self, sql, args=()):
        with self._lock:
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
    def start_run(self, target_uid, target_username, candidates_raw="", note="",
                  target_deleted=0):
        with self.tx() as c:
            cur = c.execute("""INSERT INTO identity_runs(target_uid,target_username,status,
                candidates_raw,note,target_deleted,started_at) VALUES(?,?,?,?,?,?,?)""",
                (str(target_uid), target_username, "running", candidates_raw, note,
                 int(bool(target_deleted)), now()))
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
        if not sets:
            return
        args.append(run_id)
        with self.tx() as c:
            c.execute(f"UPDATE identity_runs SET {','.join(sets)} WHERE id=?", args)

    def delete_run(self, rid):
        with self.tx() as c:
            c.execute("DELETE FROM identity_scores WHERE run_id=?", (rid,))
            c.execute("DELETE FROM identity_runs WHERE id=?", (rid,))

    # ---- 既知アカウント ----
    def add_known(self, user_id, username="", note="", source="manual", deleted=None):
        uid = str(user_id)
        with self.tx() as c:
            row = c.execute("SELECT deleted FROM known_accounts WHERE user_id=?",
                            (uid,)).fetchone()
            d = int(deleted) if deleted is not None else (row["deleted"] if row else 0)
            c.execute("""INSERT INTO known_accounts(user_id,username,note,source,deleted,
                added_at,last_seen) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=CASE WHEN excluded.username<>'' THEN excluded.username
                                  ELSE known_accounts.username END,
                    note=CASE WHEN excluded.note<>'' THEN excluded.note
                              ELSE known_accounts.note END,
                    source=excluded.source, deleted=excluded.deleted,
                    last_seen=excluded.last_seen""",
                (uid, username, note, source, d, now(), now()))

    def known(self, limit=1000):
        return self.q("SELECT * FROM known_accounts ORDER BY last_seen DESC LIMIT ?", (limit,))

    def known_get(self, uid):
        return self.q1("SELECT * FROM known_accounts WHERE user_id=?", (str(uid),))

    def set_known_deleted(self, uid, flag):
        with self.tx() as c:
            c.execute("UPDATE known_accounts SET deleted=? WHERE user_id=?",
                      (int(bool(flag)), str(uid)))

    def del_known(self, uid):
        with self.tx() as c:
            c.execute("DELETE FROM known_accounts WHERE user_id=?", (str(uid),))

    # ---- 保存ペア ----
    def save_pair(self, tuid, tname, cuid, cname, note=""):
        with self.tx() as c:
            c.execute("""INSERT INTO saved_pairs(target_uid,target_username,candidate_uid,
                candidate_username,note,added_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(target_uid,candidate_uid) DO UPDATE SET
                    target_username=excluded.target_username,
                    candidate_username=excluded.candidate_username,
                    note=CASE WHEN excluded.note<>'' THEN excluded.note
                              ELSE saved_pairs.note END""",
                (str(tuid), tname, str(cuid), cname, note, now()))

    def pairs(self, limit=500):
        return self.q("SELECT * FROM saved_pairs ORDER BY added_at DESC LIMIT ?", (limit,))

    def del_pair(self, pid):
        with self.tx() as c:
            c.execute("DELETE FROM saved_pairs WHERE id=?", (pid,))

    # ---- リンク追跡 ----
    def add_link(self, code, name, dest, note="", mode="page"):
        with self.tx() as c:
            c.execute("""INSERT INTO links(code,name,dest,note,mode,created_at,hit_count,active)
                VALUES(?,?,?,?,?,?,0,1)
                ON CONFLICT(code) DO UPDATE SET name=excluded.name, dest=excluded.dest,
                    note=excluded.note, mode=excluded.mode""",
                (code, name, dest, note, mode, now()))

    def links(self, limit=500):
        return self.q("SELECT * FROM links ORDER BY created_at DESC LIMIT ?", (limit,))

    def link_get(self, code):
        return self.q1("SELECT * FROM links WHERE code=?", (code,))

    def del_link(self, code):
        with self.tx() as c:
            c.execute("DELETE FROM links WHERE code=?", (code,))
            c.execute("DELETE FROM link_hits WHERE code=?", (code,))
            c.execute("DELETE FROM link_questions WHERE code=?", (code,))
            c.execute("DELETE FROM link_answers WHERE code=?", (code,))

    def set_link_active(self, code, flag):
        with self.tx() as c:
            c.execute("UPDATE links SET active=? WHERE code=?", (int(bool(flag)), code))

    def bump_link(self, code):
        with self.tx() as c:
            c.execute("UPDATE links SET hit_count=hit_count+1 WHERE code=?", (code,))

    def add_hit(self, d):
        cols = list(d.keys())
        with self.tx() as c:
            cur = c.execute(
                f"INSERT INTO link_hits({','.join(cols)}) VALUES({','.join(['?'] * len(cols))})",
                [d[k] for k in cols])
            return cur.lastrowid

    def update_hit(self, hid, **f):
        if not f:
            return
        sets = ", ".join(f"{k}=?" for k in f)
        with self.tx() as c:
            c.execute(f"UPDATE link_hits SET {sets} WHERE id=?", list(f.values()) + [hid])

    def hits(self, code, include_bots=True, limit=500):
        sql = "SELECT * FROM link_hits WHERE code=?"
        if not include_bots:
            sql += " AND is_bot=0"
        return self.q(sql + " ORDER BY ts DESC LIMIT ?", (code, limit))

    def del_hits(self, code):
        with self.tx() as c:
            c.execute("DELETE FROM link_hits WHERE code=?", (code,))
            c.execute("DELETE FROM link_answers WHERE code=?", (code,))
            c.execute("UPDATE links SET hit_count=0 WHERE code=?", (code,))

    # ---- クイズ ----
    def add_question(self, code, prompt, qtype="choice", options=None,
                     answer_key="", reveal=""):
        with self.tx() as c:
            o = c.execute("SELECT COALESCE(MAX(ord),-1)+1 n FROM link_questions WHERE code=?",
                          (code,)).fetchone()["n"]
            c.execute("""INSERT INTO link_questions(code,ord,qtype,prompt,options,
                answer_key,reveal,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                (code, o, qtype, prompt, json.dumps(options or [], ensure_ascii=False),
                 answer_key, reveal, now()))

    def questions(self, code):
        return self.q("SELECT * FROM link_questions WHERE code=? ORDER BY ord,id", (code,))

    def del_question(self, qid):
        with self.tx() as c:
            c.execute("DELETE FROM link_questions WHERE id=?", (qid,))

    def add_answer(self, d):
        cols = list(d.keys())
        with self.tx() as c:
            c.execute(f"INSERT INTO link_answers({','.join(cols)}) "
                      f"VALUES({','.join(['?'] * len(cols))})", [d[k] for k in cols])

    def answers(self, code, limit=2000):
        return self.q("SELECT * FROM link_answers WHERE code=? ORDER BY ts DESC LIMIT ?",
                      (code, limit))

    def answers_for(self, hit_id):
        return self.q("SELECT * FROM link_answers WHERE hit_id=? ORDER BY ord", (hit_id,))

    # ---- 訪問者台帳 ----
    def upsert_visitor(self, vid, **f):
        with self.tx() as c:
            c.execute("""INSERT INTO visitors(vid,first_seen,last_seen,hits)
                VALUES(?,?,?,1) ON CONFLICT(vid) DO UPDATE SET
                last_seen=excluded.last_seen, hits=visitors.hits+1""",
                (vid, now(), now()))
            f = {k: v for k, v in f.items() if v not in (None, "")}
            if f:
                sets = ",".join(f"{k}=?" for k in f)
                c.execute(f"UPDATE visitors SET {sets} WHERE vid=?",
                          list(f.values()) + [vid])

    def visitor(self, vid):
        return self.q1("SELECT * FROM visitors WHERE vid=?", (vid,))

    def visitors(self, limit=500):
        return self.q("SELECT * FROM visitors ORDER BY last_seen DESC LIMIT ?", (limit,))

    def set_visitor_label(self, vid, label, note=""):
        with self.tx() as c:
            c.execute("UPDATE visitors SET label=?, note=? WHERE vid=?", (label, note, vid))

    def hits_by_vid(self, vid, limit=200):
        return self.q("SELECT * FROM link_hits WHERE vid=? ORDER BY ts DESC LIMIT ?",
                      (vid, limit))

    # ---- SNS横断検索 ----
    def start_scan(self, username):
        with self.tx() as c:
            cur = c.execute("""INSERT INTO sns_scans(username,status,started_at)
                VALUES(?,?,?)""", (username, "running", now()))
            return cur.lastrowid

    def finish_scan(self, sid, total=0, found=0, status="ok", log=""):
        with self.tx() as c:
            c.execute("""UPDATE sns_scans SET total=?,found=?,status=?,finished_at=?,log=?
                WHERE id=?""", (total, found, status, now(), log[:20000], sid))

    def scans(self, limit=200):
        return self.q("SELECT * FROM sns_scans ORDER BY id DESC LIMIT ?", (limit,))

    def scan(self, sid):
        return self.q1("SELECT * FROM sns_scans WHERE id=?", (sid,))

    def del_scan(self, sid):
        with self.tx() as c:
            c.execute("DELETE FROM sns_hits WHERE scan_id=?", (sid,))
            c.execute("DELETE FROM sns_scans WHERE id=?", (sid,))

    def add_sns_hit(self, d):
        cols = list(d.keys())
        with self.tx() as c:
            c.execute(f"INSERT INTO sns_hits({','.join(cols)}) "
                      f"VALUES({','.join(['?'] * len(cols))})", [d[k] for k in cols])

    def sns_hits(self, sid):
        return self.q("SELECT * FROM sns_hits WHERE scan_id=? ORDER BY "
                      "(state<>'yes'), id", (sid,))

    def sns_by_username(self, username):
        return self.q("SELECT * FROM sns_hits WHERE username=? ORDER BY id DESC",
                      (username,))

    def upsert_avatar(self, source, ref, site, url, phash):
        with self.tx() as c:
            c.execute("""INSERT INTO sns_avatars(source,ref,site,url,phash,seen_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(source,ref,site) DO UPDATE SET
                    url=excluded.url, phash=excluded.phash, seen_at=excluded.seen_at""",
                (source, ref, site, url, phash, now()))

    def avatars(self, limit=2000):
        return self.q("SELECT * FROM sns_avatars ORDER BY id DESC LIMIT ?", (limit,))

    def add_gravatar(self, d):
        with self.tx() as c:
            c.execute("""INSERT INTO gravatar(email,md5,display_name,profile_url,
                has_avatar,accounts,urls,raw,seen_at) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET display_name=excluded.display_name,
                    accounts=excluded.accounts, urls=excluded.urls, raw=excluded.raw,
                    seen_at=excluded.seen_at""",
                (d["email"], d["md5"], d.get("display_name"), d.get("profile"),
                 int(bool(d.get("has_avatar"))),
                 json.dumps(d.get("accounts"), ensure_ascii=False),
                 json.dumps(d.get("urls"), ensure_ascii=False),
                 json.dumps(d.get("raw"), ensure_ascii=False, default=str), now()))

    def gravatars(self, limit=200):
        return self.q("SELECT * FROM gravatar ORDER BY seen_at DESC LIMIT ?", (limit,))

    def del_gravatar(self, gid):
        with self.tx() as c:
            c.execute("DELETE FROM gravatar WHERE id=?", (gid,))

    # ---- キャンペーン ----
    def add_campaign(self, name, note="", mode="page", message=""):
        with self.tx() as c:
            cur = c.execute("""INSERT INTO campaigns(name,note,mode,message,created_at,status)
                VALUES(?,?,?,?,?,?)""", (name, note, mode, message, now(), "draft"))
            return cur.lastrowid

    def campaigns(self, limit=200):
        return self.q("SELECT * FROM campaigns ORDER BY id DESC LIMIT ?", (limit,))

    def campaign(self, cid):
        return self.q1("SELECT * FROM campaigns WHERE id=?", (cid,))

    def del_campaign(self, cid):
        with self.tx() as c:
            c.execute("DELETE FROM campaign_targets WHERE campaign_id=?", (cid,))
            c.execute("DELETE FROM campaigns WHERE id=?", (cid,))

    def set_campaign_status(self, cid, status):
        with self.tx() as c:
            c.execute("UPDATE campaigns SET status=? WHERE id=?", (status, cid))