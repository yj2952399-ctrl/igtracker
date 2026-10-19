"""
裏垢特定エンジン v2。
31シグナル総動員 + 候補の自動収集で総当たりスコアリング。

シグナルの種類:
  [名前系]  username / username_root / fullname
  [文面系]  bio / bio_token / caption_style
  [リンク系] external_url_exact / external_url_domain
  [画像系]  avatar_phash / avatar_color
  [関係系]  follower_overlap / following_overlap / *_idf / follower_order
  [連絡先系] business_email / business_phone / public_email / contact_phone / city / address
  [時系列系] posting_hour / posting_weekday / co_activity
  [内容系]  shared_hashtags / shared_locations / shared_mentions / tagged_overlap
  [波及系]  related_overlap / liker_overlap / commenter_overlap
  [ID系]    user_id_proximity
"""
from __future__ import annotations
import json, math, datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .instagram import client, raw_profile
from .database import now

# ---------- 正規化 ----------

_SUFFIXES = ["_uraaka", "_ura", "uraaka", "ura", "_sub", "sub", "_subaccount",
             "_real", "real", "_main", "main", "_official", "official",
             "_back", "back", "_bek", "_bak", "_2nd", "2nd", "_2", "2",
             "_private", "private", "_hidden", "hidden", "0"]


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _strip(u):
    u = (u or "").lower()
    for s in _SUFFIXES:
        if u.endswith(s) and len(u) > len(s):
            u = u[: -len(s)]
    return _norm(u)


def username_sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.75 + 0.25 * min(len(a), len(b)) / max(len(a), len(b))
    return SequenceMatcher(None, a, b).ratio()


def root_sim(a, b):
    a, b = _strip(a), _strip(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def text_sim(a, b):
    a, b = (a or "").lower(), (b or "").lower()
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def jaccard(xs, ys):
    xs, ys = set(xs), set(ys)
    return len(xs & ys) / len(xs | ys) if xs and ys else 0.0


def cosine(va, vb):
    if not va or not vb or len(va) != len(vb):
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    return dot / (na * nb) if na and nb else 0.0


def phash_sim(h1, h2):
    if not h1 or not h2:
        return 0.0
    try:
        import imagehash
        return max(0.0, 1.0 - (imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)) / 32.0)
    except Exception:
        return 0.0


def norm_str(s):
    return _norm(s)


def spearman(pairs):
    """pairs: [(rankA, rankB), ...] -> 順位相関"""
    n = len(pairs)
    if n < 5:
        return 0.0
    ra = [p[0] for p in pairs]
    rb = [p[1] for p in pairs]
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in pairs)
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((y - mb) ** 2 for y in rb))
    if not da or not db:
        return 0.0
    rho = num / (da * db)
    return max(0.0, rho)


def hour_hist(times):
    h = [0] * 24
    for t in times:
        try:
            h[dt.datetime.fromisoformat(t.replace("Z", "+00:00")).hour] += 1
        except Exception:
            pass
    return h


def weekday_hist(times):
    h = [0] * 7
    for t in times:
        try:
            h[dt.datetime.fromisoformat(t.replace("Z", "+00:00")).weekday()] += 1
        except Exception:
            pass
    return h


def style_vector(captions):
    """文体ベクトル: 平均長 / 絵文字比率 / 改行 / 感嘆符 / ハッシュタグ"""
    if not captions:
        return []
    n = len(captions)
    lens = sum(len(c or "") for c in captions) / n
    emo = sum(sum(1 for ch in (c or "") if ord(ch) > 0x2190) for c in captions) / n
    nl = sum((c or "").count("\n") for c in captions) / n
    excl = sum((c or "").count("!") + (c or "").count("！") for c in captions) / n
    tags = sum((c or "").count("#") for c in captions) / n
    return [min(lens / 200, 1), min(emo / 20, 1), min(nl / 5, 1),
            min(excl / 5, 1), min(tags / 10, 1)]


def mentions_of(captions):
    out = set()
    for c in captions:
        for tok in (c or "").split():
            if tok.startswith("@") and len(tok) > 1:
                out.add(tok[1:].strip(".,!?:;").lower())
    return out


def hashtags_of(captions):
    out = set()
    for c in captions:
        for tok in (c or "").split():
            if tok.startswith("#") and len(tok) > 1:
                out.add(tok[1:].strip(".,!?:;").lower())
    return out


def domain_of(url):
    if not url:
        return ""
    u = url.lower().replace("https://", "").replace("http://", "").strip("/")
    return u.split("/")[0].replace("www.", "")


def idf_weight(shared, freq, total_docs):
    """希少な共通フォロワーほど高く評価"""
    if not shared or not freq or total_docs <= 1:
        return 0.0
    score = 0.0
    for node in shared:
        df = freq.get(node, 1)
        score += math.log((total_docs + 1) / (df + 0.5))
    mx = len(shared) * math.log(total_docs + 1)
    return min(score / mx, 1.0) if mx else 0.0


# ---------- 収集 ----------

@dataclass
class Acct:
    uid: str
    username: str = ""
    full_name: str = ""
    bio: str = ""
    external_url: str = ""
    business_email: str = ""
    business_phone: str = ""
    public_email: str = ""
    contact_phone: str = ""
    city: str = ""
    address: str = ""
    follower_count: int = 0
    following_count: int = 0
    media_count: int = 0
    is_private: bool = False
    is_business: bool = False
    avatar_phash: str = ""
    avatar_hist: list = field(default_factory=list)
    followers: dict = field(default_factory=dict)
    following: dict = field(default_factory=dict)
    posts: list = field(default_factory=list)
    tagged_ids: set = field(default_factory=set)
    related_ids: set = field(default_factory=set)
    liker_ids: set = field(default_factory=set)
    commenter_ids: set = field(default_factory=set)
    # --- 追加 ---
    deleted: bool = False      # user_info が取れない＝削除/凍結の疑い
    cached: bool = False       # DBキャッシュから復元した
    partial: bool = False      # 一部のシグナルが欠けている

    @property
    def captions(self):
        return [p.get("caption", "") for p in self.posts]

    @property
    def times(self):
        return [p["taken_at"] for p in self.posts if p.get("taken_at")]


liker_ids: set = field(default_factory=set)
    commenter_ids: set = field(default_factory=set)
    # --- 追加 ---
    deleted: bool = False      # user_info が取れない＝削除/凍結の疑い
    cached: bool = False       # DBキャッシュから復元した
    partial: bool = False      # 一部のシグナルが欠けている


# ---------- 比較 ----------

def compare(a: Acct, b: Acct, w, freq, total_docs):
    sig = []

    def add(name, score, detail=None):
        sig.append({"name": name, "score": round(float(score), 4),
                    "weight": w.get(name, 0), "detail": detail or {}})

    add("username", username_sim(a.username, b.username),
        {"a": a.username, "b": b.username})
    add("username_root", root_sim(a.username, b.username),
        {"a": _strip(a.username), "b": _strip(b.username)})
    add("fullname", text_sim(a.full_name, b.full_name))
    add("bio", text_sim(a.bio, b.bio))
    add("bio_token", jaccard(norm_str(a.bio).split(), norm_str(b.bio).split())
        if a.bio and b.bio else
        jaccard({_norm(t) for t in a.bio.split()}, {_norm(t) for t in b.bio.split()}))
    add("external_url_exact", 1.0 if a.external_url and
        a.external_url.rstrip("/") == b.external_url.rstrip("/") else 0.0)
    add("external_url_domain", 1.0 if domain_of(a.external_url) and
        domain_of(a.external_url) == domain_of(b.external_url) else 0.0)
    add("avatar_phash", phash_sim(a.avatar_phash, b.avatar_phash))
    add("avatar_color", cosine(a.avatar_hist, b.avatar_hist))

    sh_fol = set(a.followers) & set(b.followers)
    sh_folw = set(a.following) & set(b.following)
    add("follower_overlap", jaccard(a.followers, b.followers), {"common": len(sh_fol)})
    add("following_overlap", jaccard(a.following, b.following), {"common": len(sh_folw)})
    add("follower_overlap_idf", idf_weight(sh_fol, freq, total_docs),
        {"common": len(sh_fol)})
    add("following_overlap_idf", idf_weight(sh_folw, freq, total_docs),
        {"common": len(sh_folw)})

    # フォロワー順序相関（先頭ほど重い）
    pos_a = {k: i for i, k in enumerate(list(a.followers)[:500])}
    pos_b = {k: i for i, k in enumerate(list(b.followers)[:500])}
    pairs = [(pos_a[k], pos_b[k]) for k in set(pos_a) & set(pos_b)]
    add("follower_order", spearman(pairs), {"n": len(pairs)})

    try:
        da = abs(int(a.uid) - int(b.uid))
        add("user_id_proximity", max(0.0, 1 - math.log10(da + 1) / 8), {"delta": da})
    except Exception:
        add("user_id_proximity", 0.0)

    add("business_email", 1.0 if a.business_email and a.business_email == b.business_email else 0.0,
        {"a": a.business_email, "b": b.business_email})
    add("business_phone", 1.0 if a.business_phone and a.business_phone == b.business_phone else 0.0)
    add("public_email", 1.0 if a.public_email and a.public_email == b.public_email else 0.0)
    add("contact_phone", 1.0 if a.contact_phone and a.contact_phone == b.contact_phone else 0.0)
    add("city", 1.0 if a.city and a.city == b.city else 0.0, {"a": a.city, "b": b.city})
    add("address", text_sim(a.address, b.address))

    add("posting_hour", cosine(hour_hist(a.times), hour_hist(b.times)))
    add("posting_weekday", cosine(weekday_hist(a.times), weekday_hist(b.times)))
    add("caption_style", cosine(style_vector(a.captions), style_vector(b.captions)))

    add("shared_hashtags", jaccard(hashtags_of(a.captions), hashtags_of(b.captions)))
    add("shared_mentions", jaccard(mentions_of(a.captions), mentions_of(b.captions)))
    loc_a = {p["location_id"] for p in a.posts if p.get("location_id")}
    loc_b = {p["location_id"] for p in b.posts if p.get("location_id")}
    add("shared_locations", jaccard(loc_a, loc_b), {"common": len(loc_a & loc_b)})

    add("tagged_overlap", jaccard(a.tagged_ids, b.tagged_ids),
        {"common": len(a.tagged_ids & b.tagged_ids)})
    add("related_overlap", jaccard(a.related_ids, b.related_ids),
        {"common": len(a.related_ids & b.related_ids)})
    add("liker_overlap", jaccard(a.liker_ids, b.liker_ids),
        {"common": len(a.liker_ids & b.liker_ids)})
    add("commenter_overlap", jaccard(a.commenter_ids, b.commenter_ids),
        {"common": len(a.commenter_ids & b.commenter_ids)})

    # 同時活動の逆相関（同じ人が2垢を同時に投稿しにくい）
    def co_activity():
        ta = sorted(a.times)
        tb = sorted(b.times)
        if len(ta) < 3 or len(tb) < 3:
            return 0.0
        near = 0
        for t in ta[:40]:
            try:
                d = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:
                continue
            for u in tb[:40]:
                try:
                    e = dt.datetime.fromisoformat(u.replace("Z", "+00:00"))
                except Exception:
                    continue
                if abs((d - e).total_seconds()) < 180:
                    near += 1
        return min(near / 20.0, 1.0)

    add("co_activity", co_activity())

    tw = sum(s["weight"] for s in sig) or 1.0
    total = sum(s["score"] * s["weight"] for s in sig) / tw
    return round(total, 4), sig


def verdict(score, th):
    if score >= th["certain"]:
        return "ほぼ確定"
    if score >= th["strong"]:
        return "濃厚"
    if score >= th["possible"]:
        return "可能性あり"
    if score >= th["weak"]:
        return "弱い"
    return "低い"


# ---------- 実行 ----------

def auto_candidates(a: Acct, limit):
    pool = {}
    for src in (a.following, a.followers):
        pool.update(src)
    for x in list(a.tagged_ids) + list(a.liker_ids) + list(a.commenter_ids):
        pool.setdefault(x, "")
    pool.pop(a.uid, None)
    items = list(pool.items())
    return items[:limit]


def run_identify(db, target_uid, candidate_uids=None, auto_scan=True, run_id=None):
    cfg = __import__("app.config", fromlist=["get"]).get()
    icfg = cfg["identity"]
    w = icfg["weights"]
    g = icfg["gather"]
    th = icfg["thresholds"]
    cl = client()

    target = gather(cl, target_uid, g)
    db.upsert_profile({
        "user_id": target.uid, "username": target.username,
        "full_name": target.full_name, "bio": target.bio,
        "external_url": target.external_url,
        "follower_count": target.follower_count,
        "following_count": target.following_count,
        "media_count": target.media_count,
        "is_private": target.is_private, "is_business": target.is_business,
        "profile_pic_phash": target.avatar_phash,
    })

    pool = []
    if candidate_uids:
        for u in candidate_uids:
            pool.append((str(u), ""))
    if auto_scan:
        pool += auto_candidates(target, icfg["auto_scan_max"])
    # 重複除去
    seen, uniq = set(), []
    for uid, un in pool:
        if uid in seen or uid == target.uid:
            continue
        seen.add(uid)
        uniq.append((uid, un))

    if run_id:
        db.update_run(run_id, total=len(uniq), progress=0, status="running")

    accounts = []
    freq = Counter()
    for i, (uid, un) in enumerate(uniq, 1):
        ac = gather(cl, uid, g)
        if not ac.username:
            ac.username = un
        if ac.username:
            accounts.append(ac)
            for n in set(ac.followers) | set(ac.following):
                freq[n] += 1
        if run_id and i % 5 == 0:
            db.update_run(run_id, progress=i)

    total_docs = max(len(accounts), 1)
    results = []
    for ac in accounts:
        score, ev = compare(target, ac, w, freq, total_docs)
        if score < icfg["min_score_report"]:
            continue
        results.append({"uid": ac.uid, "username": ac.username,
                        "score": score, "verdict": verdict(score, th),
                        "evidence": ev})
    results.sort(key=lambda r: r["score"], reverse=True)

    with db.tx() as c:
        for r in results:
            c.execute("""INSERT INTO identity_scores(run_id,uraaka_user_id,
                candidate_user_id,candidate_username,score,verdict,evidence,computed_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (run_id, target.uid, r["uid"], r["username"], r["score"],
                 r["verdict"], json.dumps(r["evidence"], ensure_ascii=False), now()))

    db.log(target.uid, "identify_done",
           {"candidates": len(accounts), "top": results[0]["username"] if results else None})
    return results