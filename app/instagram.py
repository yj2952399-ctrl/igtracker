"""instagrapi ラッパ。取れるものは全部取ってDBに書く。"""
import os, json, datetime as dt
from io import BytesIO

import requests
import imagehash
from PIL import Image
from instagrapi import Client

from .config import get as get_cfg
from .database import now
from . import forensics

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


def avatar_features(url):
    """アイコンのpHashと色ヒストグラムを抽出"""
    if not url:
        return "", []
    try:
        r = requests.get(url, timeout=15)
        img = Image.open(BytesIO(r.content)).convert("RGB")
        ph = str(imagehash.phash(img))
        small = img.resize((64, 64))
        hues = [0] * 36
        for px in small.getdata():
            rr, gg, bb = [v / 255.0 for v in px]
            mx, mn = max(rr, gg, bb), min(rr, gg, bb)
            if mx == mn:
                continue
            d = mx - mn
            if mx == rr:
                h = ((gg - bb) / d) % 6
            elif mx == gg:
                h = (bb - rr) / d + 2
            else:
                h = (rr - gg) / d + 4
            hues[int(h * 6) % 36] += 1
        return ph, hues
    except Exception:
        return "", []


def raw_profile(cl, uid):
    """取得できる全フィールドを辞書化"""
    i = cl.user_info(uid)
    ph, hist = avatar_features(str(i.profile_pic_url) if i.profile_pic_url else None)
    forensics.capture_headers(cl._db if hasattr(cl, "_db") else None, cl, f"user_info:{uid}")
    return {
        "user_id": str(i.pk),
        "username": i.username,
        "full_name": i.full_name,
        "bio": i.biography,
        "external_url": i.external_url,
        "follower_count": i.follower_count,
        "following_count": i.following_count,
        "media_count": i.media_count,
        "is_private": bool(i.is_private),
        "is_verified": bool(getattr(i, "is_verified", False)),
        "is_business": bool(getattr(i, "is_business", False)),
        "business_category": getattr(i, "category_name", None) or getattr(i, "business_category_name", None),
        "public_email": getattr(i, "public_email", None),
        "contact_phone": getattr(i, "contact_phone_number", None),
        "business_email": getattr(i, "business_email", None),
        "business_phone": getattr(i, "business_phone_number", None),
        "city": getattr(i, "city_name", None),
        "address": getattr(i, "address_street", None),
        "zipcode": getattr(i, "zip", None),
        "latitude": getattr(i, "latitude", None),
        "longitude": getattr(i, "longitude", None),
        "profile_pic_url": str(i.profile_pic_url) if i.profile_pic_url else None,
        "profile_pic_phash": ph,
        "_avatar_hist": hist,
    }


# ---------- 保存系 ----------

def save_profile(db, uid):
    p = raw_profile(client(), uid)
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
            if not c.execute("SELECT 1 FROM posts WHERE media_id=?", (str(m.pk),)).fetchone():
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


def save_relations(db, uid, max_follow=10000):
    cl = client()
    out = {}
    for direction, fn in (("following", cl.user_following), ("follower", cl.user_followers)):
        try:
            cur = fn(uid, amount=max_follow)
        except Exception:
            out[direction] = 0
            continue
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
                uid_c = str(cm.user_id)
                uname = getattr(cm, "user", None) and cm.user.username or ""
                c.execute("""INSERT OR REPLACE INTO comments(pk,media_id,user_id,username,
                    text,created_at,like_count,archived_at) VALUES(?,?,?,?,?,?,?,?)""",
                    (str(cm.pk), r["media_id"], uid_c, uname, cm.text,
                     cm.created_at.isoformat() if cm.created_at else None,
                     getattr(cm, "like_count", 0), now()))
                c.execute("""INSERT OR REPLACE INTO media_commenters
                    (media_id,user_id,username,archived_at) VALUES(?,?,?,?)""",
                    (r["media_id"], uid_c, uname, now()))
                total += 1
    db.log(uid, "comments_synced", {"count": total})
    return total


def save_likers(db, uid, max_posts=12, per_post=200):
    cl = client()
    rows = db.q("SELECT media_id FROM posts WHERE user_id=? ORDER BY taken_at DESC LIMIT ?",
                (uid, max_posts))
    total = 0
    for r in rows:
        try:
            likers = cl.media_likers(r["media_id"])
        except Exception:
            continue
        with db.tx() as c:
            for u in likers[:per_post]:
                c.execute("""INSERT OR REPLACE INTO media_likers
                    (media_id,user_id,username,archived_at) VALUES(?,?,?,?)""",
                    (r["media_id"], str(u.pk), u.username, now()))
                total += 1
    db.log(uid, "likers_synced", {"count": total})
    return total


def save_related(db, uid):
    cl = client()
    if not hasattr(cl, "user_related_profiles"):
        return 0
    try:
        rels = cl.user_related_profiles(uid)
    except Exception:
        return 0
    with db.tx() as c:
        for u in rels:
            c.execute("""INSERT OR REPLACE INTO related_profiles
                (user_id,related_id,related_username,archived_at) VALUES(?,?,?,?)""",
                (uid, str(u.pk), u.username, now()))
    db.log(uid, "related_synced", {"count": len(rels)})
    return len(rels)


def save_tagged(db, uid, max_items=200):
    cl = client()
    try:
        medias = cl.user_tagged_medias(uid, amount=max_items)
    except Exception:
        return 0
    with db.tx() as c:
        for m in medias:
            c.execute("""INSERT OR REPLACE INTO tagged_media
                (media_id,user_id,owner_id,code,taken_at,archived_at)
                VALUES(?,?,?,?,?,?)""",
                (str(m.pk), uid, str(m.user.pk) if getattr(m, "user", None) else "",
                 m.code, m.taken_at.isoformat() if m.taken_at else None, now()))
    db.log(uid, "tagged_synced", {"count": len(medias)})
    return len(medias)


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


def archive_account(db, uid, max_posts=200, max_follow=2000):
    """削除対策：あとで削除されても照合できるようDBに残す。"""
    for fn, args in ((save_profile, (db, uid)),
                     (save_posts, (db, uid, max_posts)),
                     (save_relations, (db, uid, max_follow)),
                     (save_likers, (db, uid, 12, 200)),
                     (save_tagged, (db, uid, 200)),
                     (save_related, (db, uid)),
                     (save_comments, (db, uid, 20))):
        try:
            fn(*args)
        except Exception as e:
            db.log(uid, "archive_partial", {"fn": fn.__name__, "error": str(e)})
    db.log(uid, "account_archived", {})


def full_archive(db, uid, cfg=None):
    cfg = cfg or get_cfg()
    a = cfg["archive"]
    save_profile(db, uid)
    save_posts(db, uid, a["max_posts"])
    save_stories(db, uid)
    save_highlights(db, uid)
    save_relations(db, uid, a["max_follow"])
    save_comments(db, uid, min(a["max_posts"], 50))
    save_likers(db, uid)
    save_related(db, uid)
    save_tagged(db, uid)
    save_dms(db, a["max_threads"])
    forensics.snapshot_all(db, client())