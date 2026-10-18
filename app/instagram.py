"""instagrapi ラッパ。プロフィール/投稿/ストーリー/関係/DM を全部取ってDBに書く。"""
import os, json, time, datetime as dt
import requests
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

from .config import get as get_cfg
from .database import now

_cl = None

def client():
    global _cl
    if _cl:
        return _cl
    cfg = get_cfg()
    cl = Client()
    cl.delay_range = [1, 3]
    sf = cfg["instagram"]["session_file"]
    if os.path.exists(sf):
        try:
            cl.load_settings(sf)
            cl.login(cfg["instagram"]["username"], cfg["instagram"]["password"])
            cl.get_timeline_feed()
            _cl = cl
            return cl
        except Exception:
            pass
    cl.login(cfg["instagram"]["username"], cfg["instagram"]["password"])
    cl.dump_settings(sf)
    _cl = cl
    return cl


def phash_from_url(url):
    from io import BytesIO
    import imagehash
    from PIL import Image
    try:
        r = requests.get(url, timeout=15)
        return str(imagehash.phash(Image.open(BytesIO(r.content)).convert("RGB")))
    except Exception:
        return None


def profile_dict(cl, uid):
    i = cl.user_info(uid)
    return {
        "user_id": str(i.pk), "username": i.username, "full_name": i.full_name,
        "bio": i.biography, "external_url": i.external_url,
        "follower_count": i.follower_count, "following_count": i.following_count,
        "media_count": i.media_count, "is_private": i.is_private,
        "is_verified": getattr(i, "is_verified", False),
        "business_category": getattr(i, "business_category", None),
        "profile_pic_url": str(i.profile_pic_url) if i.profile_pic_url else None,
        "profile_pic_phash": phash_from_url(str(i.profile_pic_url)) if i.profile_pic_url else None,
    }


def _dl(url, path, budget):
    if not url or budget["mb"] <= 0:
        return None
    try:
        r = requests.get(url, timeout=30, stream=True)
        size = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk); size += len(chunk)
        budget["mb"] -= size / 1e6
        return path
    except Exception:
        return None


# ---------- 各アーカイブ ----------

def save_profile(db, uid):
    cl = client()
    p = profile_dict(cl, uid)
    db.upsert_profile(p)
    db.snapshot_profile(p)
    db.log(uid, "profile_snapshot", {"followers": p["follower_count"],
                                     "following": p["following_count"]})
    return p


def save_posts(db, uid, max_posts=500):
    cl = client()
    medias = cl.user_medias(uid, amount=max_posts)
    new = 0
    with db.tx() as c:
        for m in medias:
            exists = c.execute("SELECT 1 FROM posts WHERE media_id=?", (str(m.pk),)).fetchone()
            if not exists:
                new += 1
            c.execute("""INSERT OR REPLACE INTO posts(media_id,user_id,code,taken_at,
                media_type,caption,location_name,location_id,like_count,comment_count,
                play_count,view_count,is_video,url,archived_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(m.pk), uid, m.code,
                 m.taken_at.isoformat() if m.taken_at else None, int(m.media_type),
                 m.caption_text,
                 getattr(m.location, "name", None) if m.location else None,
                 str(getattr(m.location, "pk", "")) if m.location else None,
                 m.like_count, m.comment_count, m.play_count,
                 getattr(m, "view_count", None), int(bool(m.video_url)),
                 m.video_url or (str(m.thumbnail_url) if m.thumbnail_url else ""), now()))
            c.execute("""INSERT INTO post_metrics(media_id,observed_at,like_count,
                comment_count) VALUES(?,?,?,?)""",
                (str(m.pk), now(), m.like_count, m.comment_count))
    db.log(uid, "posts_synced", {"total": len(medias), "new": new})
    return new


def save_stories(db, uid):
    cl = client()
    try:
        stories = cl.user_stories(uid)
    except Exception:
        return 0
    new = 0
    with db.tx() as c:
        for s in stories:
            if not c.execute("SELECT 1 FROM stories WHERE pk=?", (str(s.pk),)).fetchone():
                new += 1
            c.execute("""INSERT OR REPLACE INTO stories(pk,user_id,taken_at,expiring_at,
                media_type,caption,url,archived_at) VALUES(?,?,?,?,?,?,?,?)""",
                (str(s.pk), uid,
                 s.taken_at.isoformat() if s.taken_at else None,
                 s.expiring_at.isoformat() if s.expiring_at else None,
                 int(s.media_type), getattr(s, "caption_text", None),
                 str(s.thumbnail_url) if s.thumbnail_url else "", now()))
    if new:
        db.log(uid, "new_stories", {"count": new})
    return new


def save_highlights(db, uid):
    cl = client()
    try:
        hs = cl.user_highlights(uid)
    except Exception:
        return 0
    with db.tx() as c:
        for h in hs:
            c.execute("""INSERT OR REPLACE INTO highlights(pk,user_id,title,cover_url,
                item_count,archived_at) VALUES(?,?,?,?,?,?)""",
                (str(h.pk), uid, h.title,
                 str(h.cover_media.thumbnail_url) if getattr(h, "cover_media", None) else "",
                 getattr(h, "item_count", None), now()))
    db.log(uid, "highlights_synced", {"count": len(hs)})
    return len(hs)


def save_comments(db, uid, max_posts=50):
    cl = client()
    rows = db.q("SELECT media_id FROM posts WHERE user_id=? ORDER BY taken_at DESC LIMIT ?",
                (uid, max_posts))
    total = 0
    for r in rows:
        try:
            cs = cl.media_comments(r["media_id"], amount=100)
        except Exception:
            continue
        with db.tx() as c:
            for cm in cs:
                c.execute("""INSERT OR REPLACE INTO comments(pk,media_id,user_id,username,
                    text,created_at,like_count,archived_at) VALUES(?,?,?,?,?,?,?,?)""",
                    (str(cm.pk), r["media_id"], str(cm.user_id),
                     getattr(cm, "user", None) and cm.user.username or "",
                     cm.text, cm.created_at.isoformat() if cm.created_at else None,
                     getattr(cm, "like_count", 0), now()))
                total += 1
    db.log(uid, "comments_synced", {"count": total})
    return total


def save_relations(db, uid, max_follow=10000):
    cl = client()
    out = {}
    for direction, fn in (("following", cl.user_following), ("follower", cl.user_followers)):
        try:
            cur = fn(uid, amount=max_follow)
        except Exception:
            out[direction] = 0; continue
        cur_ids = {str(k): v.username for k, v in cur.items()}
        prev = {r["to_user_id"] for r in
                db.q("SELECT to_user_id FROM relationships WHERE from_user_id=? AND direction=?",
                     (uid, direction))}
        added = set(cur_ids) - prev
        removed = prev - set(cur_ids)
        with db.tx() as c:
            for tid in added:
                c.execute("""INSERT OR REPLACE INTO relationships
                    (from_user_id,to_user_id,to_username,direction,observed_at)
                    VALUES(?,?,?,?,?)""", (uid, tid, cur_ids[tid], direction, now()))
                c.execute("""INSERT INTO relationship_events(from_user_id,to_user_id,
                    to_username,event_type,observed_at) VALUES(?,?,?,?,?)""",
                    (uid, tid, cur_ids[tid], f"{direction}_add", now()))
            for tid in removed:
                c.execute("""INSERT INTO relationship_events(from_user_id,to_user_id,
                    to_username,event_type,observed_at) VALUES(?,?,?,?,?)""",
                    (uid, tid, None, f"{direction}_remove", now()))
        for tid in added:
            db.log(uid, f"{direction}_add", {"to": cur_ids[tid], "to_id": tid})
        for tid in removed:
            db.log(uid, f"{direction}_remove", {"to_id": tid})
        out[direction] = len(added)
    return out


def save_dms(db, max_threads=300):
    cl = client()
    try:
        threads = cl.direct_threads(amount=max_threads)
    except Exception:
        return 0
    total = 0
    for th in threads:
        with db.tx() as c:
            c.execute("""INSERT OR REPLACE INTO dm_threads(thread_id,title,participants,
                last_activity_at,updated_at) VALUES(?,?,?,?,?)""",
                (th.id, th.thread_title,
                 json.dumps([{"pk": str(u.pk), "username": u.username} for u in th.users],
                            ensure_ascii=False),
                 th.last_activity_at.isoformat() if th.last_activity_at else None, now()))
        try:
            msgs = cl.direct_messages(th.id, amount=100)
        except Exception:
            continue
        with db.tx() as c:
            for m in msgs:
                if not c.execute("SELECT 1 FROM dm_messages WHERE message_id=?",
                                 (m.id,)).fetchone():
                    db.log(str(m.user_id), "new_dm",
                           {"thread": th.thread_title, "text": m.text})
                c.execute("""INSERT OR REPLACE INTO dm_messages(message_id,thread_id,
                    sender_id,sender_username,timestamp,item_type,text,media_url,archived_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (m.id, th.id, str(m.user_id), getattr(m, "username", None),
                     m.timestamp.isoformat() if m.timestamp else None,
                     m.item_type, m.text, getattr(m, "media_url", None) or "", now()))
                total += 1
    db.log("me", "dms_synced", {"messages": total})
    return total


def full_archive(db, uid, cfg=None):
    cfg = cfg or get_cfg()
    a = cfg["archive"]
    save_profile(db, uid)
    save_posts(db, uid, a["max_posts"])
    save_stories(db, uid)
    save_highlights(db, uid)
    save_relations(db, uid, a["max_follow"])
    save_comments(db, uid, min(a["max_posts"], 50))
    save_dms(db, a["max_threads"])