"""1人1リンクを配って踏ませ、誰が踏んだかを突き合わせる。

DMは相手ごとに違うURLを送るので、どのリンクが踏まれたか＝誰が踏んだかが確定する。
ついでに一斉フォロー / いいね / コメント / アーカイブも持つ。
"""
from __future__ import annotations

import random
import secrets
import string
import time

from . import instagram as ig
from .database import now


def _new_code(owner, n=7):
    from . import users
    for _ in range(60):
        c = "".join(random.choices(string.ascii_lowercase + string.digits, k=n))
        if not users.owner_of_link(c):
            return c
    return secrets.token_urlsafe(7)


def create(db, owner, name, handles, message="", mode="page", dest="", note=""):
    """キャンペーンを作り、対象ごとに固有リンクを発行する。"""
    from . import users
    with db.tx() as c:
        cur = c.execute("""INSERT INTO campaigns(name,note,mode,message,created_at,status)
            VALUES(?,?,?,?,?,?)""", (name, note, mode, message, now(), "draft"))
        cid = cur.lastrowid

    seen, n = set(), 0
    for h in handles:
        h = (h or "").strip().lstrip("@")
        if not h or h.lower() in seen:
            continue
        seen.add(h.lower())
        code = _new_code(owner)
        users.register_link(code, owner)
        db.add_link(code, f"{name} → @{h}", dest, f"campaign:{cid}", mode)
        with db.tx() as c:
            c.execute("""INSERT INTO campaign_targets(campaign_id,username,code,state)
                VALUES(?,?,?,?)""", (cid, h, code, "pending"))
        n += 1
    with db.tx() as c:
        c.execute("UPDATE campaigns SET total=? WHERE id=?", (n, cid))
    return cid


def send(db, cid, base, delay=8.0, limit=0, dry=False):
    """未送信の対象へDMを送る。{link} と {name} を差し込む。"""
    camp = db.q1("SELECT * FROM campaigns WHERE id=?", (cid,))
    if not camp:
        return 0, 0
    rows = db.q("SELECT * FROM campaign_targets WHERE campaign_id=? AND state='pending' "
                "ORDER BY id", (cid,))
    if limit:
        rows = rows[:limit]

    cl = None if dry else ig.client()
    ok = ng = 0
    for r in rows:
        url = f"{base}/l/{r['code']}"
        msg = (camp["message"] or "").replace("{link}", url).replace(
            "{name}", "@" + r["username"])
        try:
            if dry:
                print(f"[dry] @{r['username']} <- {msg}")
                ok += 1
                continue
            uid = cl.user_id_from_username(r["username"])
            cl.direct_send(msg, user_ids=[uid])
            with db.tx() as c:
                c.execute("""UPDATE campaign_targets SET state='sent',user_id=?,sent_at=?
                    WHERE id=?""", (str(uid), now(), r["id"]))
            ok += 1
        except Exception as e:
            with db.tx() as c:
                c.execute("UPDATE campaign_targets SET state='error',error=? WHERE id=?",
                          (repr(e)[:400], r["id"]))
            ng += 1
        time.sleep(delay + random.random() * 3)
    with db.tx() as c:
        c.execute("""UPDATE campaigns SET sent=sent+?, failed=failed+?,
            status=CASE WHEN status='draft' THEN 'sent' ELSE status END WHERE id=?""",
            (ok, ng, cid))
    return ok, ng


def match(db, cid):
    """誰が踏んだかを突き合わせる。"""
    rows = db.q("""SELECT t.id, t.username, t.code, t.state, t.sent_at,
        (SELECT COUNT(*) FROM link_hits h WHERE h.code=t.code AND h.is_bot=0) hits,
        (SELECT MIN(h.ts) FROM link_hits h WHERE h.code=t.code) first_hit,
        (SELECT h.vid FROM link_hits h WHERE h.code=t.code ORDER BY h.ts LIMIT 1) vid,
        (SELECT h.device FROM link_hits h WHERE h.code=t.code ORDER BY h.ts LIMIT 1) device,
        (SELECT h.country||' '||COALESCE(h.city,'') FROM link_hits h
            WHERE h.code=t.code ORDER BY h.ts LIMIT 1) geo
        FROM campaign_targets t WHERE t.campaign_id=? ORDER BY
        (hits IS NULL), t.id""", (cid,))
    return [dict(r) for r in rows]


# ---------- 一斉操作 ----------

def bulk_follow(handles, delay=6.0, unfollow=False, limit=0):
    cl = ig.client()
    ok = ng = 0
    items = [h.strip().lstrip("@") for h in handles if h.strip()]
    if limit:
        items = items[:limit]
    for h in items:
        try:
            uid = cl.user_id_from_username(h)
            if unfollow:
                cl.user_unfollow(uid)
            else:
                cl.user_follow(uid)
            ok += 1
        except Exception:
            ng += 1
        time.sleep(delay + random.random() * 3)
    return ok, ng


def bulk_like(username, amount=12, delay=5.0):
    cl = ig.client()
    uid = cl.user_id_from_username(username.strip().lstrip("@"))
    medias = cl.user_medias(uid, amount=amount)
    ok = ng = 0
    for m in medias:
        try:
            cl.media_like(m.id)
            ok += 1
        except Exception:
            ng += 1
        time.sleep(delay + random.random() * 2)
    return ok, ng


def bulk_comment(target, text, amount=1, delay=6.0):
    """target はURLかcode。amount件に同じコメントを付ける。"""
    cl = ig.client()
    t = target.strip()
    pk = cl.media_pk_from_url(t) if t.startswith("http") else cl.media_pk_from_code(t)
    media = cl.media_info(pk)
    ok = ng = 0
    for m in [media][:amount]:
        try:
            cl.media_comment(m.id, text)
            ok += 1
        except Exception:
            ng += 1
        time.sleep(delay)
    return ok, ng


def bulk_archive(db, handles, delay=4.0):
    ok = ng = 0
    for h in handles:
        h = h.strip().lstrip("@")
        if not h:
            continue
        try:
            uid = ig.client().user_id_from_username(h)
            ig.archive_account(db, uid)
            ok += 1
        except Exception:
            ng += 1
        time.sleep(delay)
    return ok, ng