"""複数SNSの公開プロフィール取得アダプタ（認証不要の範囲で）。

    from . import platforms
    platforms.PLATFORMS                  # UIの <select> 用
    platforms.check("github", "torvalds")   # 存在確認 -> bool
    platforms.fetch("github", "torvalds")   # プロフィール -> dict

fetch() の戻り値は全SNS共通:
    {"platform","handle","url","exists","user_id","full_name","bio",
     "avatar","followers","following","posts","verified","extra"}
取得失敗は例外、存在しない場合は exists=False。
"""
from __future__ import annotations

import re
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

LABELS = {
    "instagram": "Instagram",
    "threads":   "Threads",
    "x":         "X (Twitter)",
    "tiktok":    "TikTok",
    "youtube":   "YouTube",
    "bluesky":   "Bluesky",
    "mastodon":  "Mastodon",
    "github":    "GitHub",
}
PLATFORMS = list(LABELS)


def _h(extra=None):
    h = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"}
    if extra:
        h.update(extra)
    return h


def _get(url, params=None, headers=None, timeout=20):
    r = requests.get(url, params=params, headers=_h(headers), timeout=timeout)
    r.raise_for_status()
    return r


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.match(r"^([\d.]+)\s*([KMB])?", str(v).replace(",", "").strip(), re.I)
    if not m:
        return None
    mult = {"K": 10**3, "M": 10**6, "B": 10**9}.get((m.group(2) or "").upper(), 1)
    return int(float(m.group(1)) * mult)


def _blank(platform, handle, url):
    return {"platform": platform, "handle": handle, "url": url, "exists": False,
            "user_id": None, "full_name": None, "bio": None, "avatar": None,
            "followers": None, "following": None, "posts": None,
            "verified": None, "extra": {}}


def instagram(handle):
    u = handle.lstrip("@")
    url = f"https://www.instagram.com/{u}/"
    try:
        d = (_get("https://www.instagram.com/api/v1/users/web_profile_info/",
                  params={"username": u},
                  headers={"x-ig-app-id": "936619743392459"}).json().get("data") or {}).get("user")
    except Exception:
        d = None
    if not d:
        return _blank("instagram", u, url)
    return {"platform": "instagram", "handle": u, "url": url, "exists": True,
            "user_id": str(d.get("id") or ""), "full_name": d.get("full_name"),
            "bio": d.get("biography"),
            "avatar": d.get("profile_pic_url_hd") or d.get("profile_pic_url"),
            "followers": (d.get("edge_followed_by") or {}).get("count"),
            "following": (d.get("edge_follow") or {}).get("count"),
            "posts": (d.get("edge_owner_to_timeline_media") or {}).get("count"),
            "verified": d.get("is_verified"), "extra": {"private": d.get("is_private")}}


def threads(handle):
    u = handle.lstrip("@")
    url = f"https://www.threads.net/@{u}"
    try:
        html = _get(url).text
    except Exception:
        return _blank("threads", u, url)
    m = re.search(r'"follower_count"\s*:\s*(\d+)', html)
    if not m and "not found" in html.lower():
        return _blank("threads", u, url)
    return {"platform": "threads", "handle": u, "url": url, "exists": bool(m),
            "user_id": None, "full_name": None, "bio": None, "avatar": None,
            "followers": _num(m.group(1)) if m else None,
            "following": None, "posts": None, "verified": None, "extra": {}}


def x(handle):
    u = handle.lstrip("@")
    url = f"https://x.com/{u}"
    try:
        arr = _get("https://cdn.syndication.twimg.com/widgets/followbutton/info.json",
                   params={"screen_names": u}).json()
    except Exception:
        return _blank("x", u, url)
    if not arr:
        return _blank("x", u, url)
    d = arr[0]
    return {"platform": "x", "handle": u, "url": url, "exists": True,
            "user_id": str(d.get("id") or ""), "full_name": d.get("name"),
            "bio": None, "avatar": d.get("profile_image_url_https"),
            "followers": d.get("followers_count"), "following": None, "posts": None,
            "verified": d.get("verified"), "extra": {}}


def tiktok(handle):
    u = handle.lstrip("@")
    url = f"https://www.tiktok.com/@{u}"
    try:
        html = _get(url).text
    except Exception:
        return _blank("tiktok", u, url)
    m = re.search(r'"followerCount"\s*:\s*(\d+)', html)
    return {"platform": "tiktok", "handle": u, "url": url, "exists": bool(m),
            "user_id": None, "full_name": None, "bio": None, "avatar": None,
            "followers": _num(m.group(1)) if m else None,
            "following": None, "posts": None, "verified": None, "extra": {}}


def youtube(handle):
    u = handle.lstrip("@")
    url = f"https://www.youtube.com/@{u}"
    try:
        html = _get(url).text
    except Exception:
        return _blank("youtube", u, url)
    m = re.search(r'"subscriberCountText":\{[^}]*?"simpleText":"([^"]+)"', html)
    return {"platform": "youtube", "handle": u, "url": url, "exists": bool(m),
            "user_id": None, "full_name": None, "bio": None, "avatar": None,
            "followers": _num(m.group(1).split(" ")[0]) if m else None,
            "following": None, "posts": None, "verified": None, "extra": {}}


def bluesky(handle):
    u = handle.lstrip("@")
    url = f"https://bsky.app/profile/{u}"
    try:
        d = _get("https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
                 params={"actor": u}).json()
    except Exception:
        return _blank("bluesky", u, url)
    if not d or not d.get("did"):
        return _blank("bluesky", u, url)
    return {"platform": "bluesky", "handle": u, "url": url, "exists": True,
            "user_id": d.get("did"), "full_name": d.get("displayName"),
            "bio": d.get("description"), "avatar": d.get("avatar"),
            "followers": d.get("followersCount"), "following": d.get("followsCount"),
            "posts": d.get("postsCount"), "verified": None, "extra": {}}


def mastodon(handle):
    u = handle.lstrip("@")
    if "@" not in u:
        raise ValueError("Mastodon は user@instance 形式で指定してください")
    user, host = u.split("@", 1)
    url = f"https://{host}/@{user}"
    try:
        d = _get(f"https://{host}/api/v1/accounts/lookup", params={"acct": user}).json()
    except Exception:
        return _blank("mastodon", u, url)
    if not d or not d.get("id"):
        return _blank("mastodon", u, url)
    return {"platform": "mastodon", "handle": u, "url": url, "exists": True,
            "user_id": str(d.get("id")), "full_name": d.get("display_name"),
            "bio": d.get("note"), "avatar": d.get("avatar"),
            "followers": d.get("followers_count"), "following": d.get("following_count"),
            "posts": d.get("statuses_count"), "verified": d.get("locked") is False,
            "extra": {"instance": host}}


def github(handle):
    u = handle.lstrip("@")
    url = f"https://github.com/{u}"
    try:
        r = _get(f"https://api.github.com/users/{u}")
        if r.status_code == 404:
            return _blank("github", u, url)
        d = r.json()
    except Exception:
        return _blank("github", u, url)
    return {"platform": "github", "handle": u, "url": url, "exists": True,
            "user_id": str(d.get("id") or ""), "full_name": d.get("name"),
            "bio": d.get("bio"), "avatar": d.get("avatar_url"),
            "followers": d.get("followers"), "following": d.get("following"),
            "posts": d.get("public_repos"), "verified": None, "extra": {}}


REGISTRY = {
    "instagram": instagram, "threads": threads, "x": x, "tiktok": tiktok,
    "youtube": youtube, "bluesky": bluesky, "mastodon": mastodon, "github": github,
}


def fetch(platform: str, handle: str) -> dict:
    fn = REGISTRY.get(platform)
    if not fn:
        raise ValueError(f"未対応のSNS: {platform}")
    return fn(handle)


def check(platform: str, handle: str) -> bool:
    try:
        return bool(fetch(platform, handle).get("exists"))
    except Exception:
        return False