"""裏垢特定エンジン。複数シグナルの重み付き合成でスコアリングする。"""
from difflib import SequenceMatcher
from collections import Counter
from io import BytesIO
import datetime as dt
import imagehash, requests
from PIL import Image

from .instagram import client, profile_dict

def _norm(s): return "".join(ch for ch in (s or "").lower() if ch.isalnum())

def username_sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    if a in b or b in a:
        return 0.75 + 0.25 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()

def jaccard(xs, ys):
    xs, ys = set(xs), set(ys)
    return len(xs & ys) / len(xs | ys) if xs and ys else 0.0

def phash_sim(h1, h2):
    if not h1 or not h2: return 0.0
    return max(0.0, 1.0 - (imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)) / 32.0)

def text_sim(a, b):
    a, b = (a or "").lower(), (b or "").lower()
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0

def time_sim(ta, tb):
    def hist(ts):
        h = Counter()
        for t in ts:
            try: h[dt.datetime.fromisoformat(t.replace("Z", "+00:00")).hour] += 1
            except Exception: pass
        return h
    ha, hb = hist(ta), hist(tb)
    if not ha or not hb: return 0.0
    keys = set(ha) | set(hb)
    va = [ha.get(k, 0) for k in keys]; vb = [hb.get(k, 0) for k in keys]
    sa, sb = sum(va) or 1, sum(vb) or 1
    va = [v / sa for v in va]; vb = [v / sb for v in vb]
    dot = sum(x * y for x, y in zip(va, vb))
    na = sum(x * x for x in va) ** .5; nb = sum(y * y for y in vb) ** .5
    return dot / (na * nb) if na and nb else 0.0


def gather(uid):
    cl = client()
    return {
        "profile": profile_dict(cl, uid),
        "follows": set(cl.user_following(uid, amount=3000).keys()),
        "followers": set(cl.user_followers(uid, amount=3000).keys()),
        "posts": [{"taken_at": m.taken_at.isoformat(),
                   "hashtags": [w for w in (m.caption_text or "").split() if w.startswith("#")],
                   "location_id": str(getattr(m.location, "pk", "")) if m.location else None}
                  for m in cl.user_medias(uid, amount=60) if m.taken_at],
    }


def score_pair(ura, cand, w):
    pu, pc = ura["profile"], cand["profile"]
    sig = [
        ("username", username_sim(pu.get("username",""), pc.get("username","")), w["username"]),
        ("fullname", text_sim(pu.get("full_name",""), pc.get("full_name","")), w["fullname"]),
        ("bio", text_sim(pu.get("bio",""), pc.get("bio","")), w["bio"]),
        ("avatar_phash", phash_sim(pu.get("profile_pic_phash"), pc.get("profile_pic_phash")), w["avatar_phash"]),
        ("following_overlap", jaccard(ura["follows"], cand["follows"]), w["following_overlap"]),
        ("follower_overlap", jaccard(ura["followers"], cand["followers"]), w["follower_overlap"]),
        ("posting_time", time_sim([p["taken_at"] for p in ura["posts"]],
                                  [p["taken_at"] for p in cand["posts"]]), w["posting_time"]),
    ]
    # タグ/ハッシュタグ/位置の重複
    hs_u = set().union(*[set(p["hashtags"]) for p in ura["posts"]]) if ura["posts"] else set()
    hs_c = set().union(*[set(p["hashtags"]) for p in cand["posts"]]) if cand["posts"] else set()
    sig.append(("shared_hashtags", jaccard(hs_u, hs_c), w["shared_hashtags"]))
    lo_u = {p["location_id"] for p in ura["posts"] if p["location_id"]}
    lo_c = {p["location_id"] for p in cand["posts"] if p["location_id"]}
    sig.append(("shared_locations", jaccard(lo_u, lo_c), w["shared_locations"]))
    sig.append(("tagged_overlap", 0.0, w["tagged_overlap"]))

    tw = sum(s[2] for s in sig) or 1.0
    total = sum(s[1] * s[2] for s in sig) / tw
    return round(total, 4), [{"name": n, "score": round(s, 3), "weight": wt} for n, s, wt in sig]


def run_identify(db, target_uid, candidate_uids, weights):
    cl = client()
    ura = gather(target_uid)
    db.upsert_profile(ura["profile"])
    results = []
    for cuid in candidate_uids:
        cand = gather(cuid)
        db.upsert_profile(cand["profile"])
        total, ev = score_pair(ura, cand, weights)
        results.append({"candidate_id": cuid,
                        "candidate": cand["profile"].get("username"),
                        "score": total, "evidence": ev})
    results.sort(key=lambda r: r["score"], reverse=True)
    from .database import now
    with db.tx() as c:
        for r in results:
            c.execute("""INSERT INTO identity_scores(uraaka_user_id,candidate_user_id,
                candidate_username,score,evidence,computed_at) VALUES(?,?,?,?,?,?)""",
                (target_uid, r["candidate_id"], r["candidate"], r["score"],
                 __import__("json").dumps(r["evidence"], ensure_ascii=False), now()))
    db.log(target_uid, "identify_done", {"best": results[0]["candidate"] if results else None})
    return results