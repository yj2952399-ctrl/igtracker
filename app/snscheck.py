"""ユーザー名・メールから色んなSNSを横断で炙り出す。

判定はHTTPステータスと本文キーワードで行う。JSレンダリングはしないので
SPA系のサイトは best-effort（best_effort=True）として扱う。
"""
from __future__ import annotations

import hashlib
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8",
           "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}

OG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*'
                r'content=["\']([^"\']+)', re.I)
OG2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
                 r'(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# (id, 表示名, カテゴリ, URLテンプレ, 方式, キーワード, 補足)
#   status  : 404/410 で「無し」
#   absent  : 200 でもキーワードが本文にあれば「無し」
#   present : 200 でもキーワードが本文に無ければ「無し」
SITES = [
    # --- 主要SNS ---
    ("instagram", "Instagram", "SNS", "https://www.instagram.com/{u}/", "absent",
     ["Sorry, this page isn't available", "ページが見つかりません"], True),
    ("x", "X (Twitter)", "SNS", "https://x.com/{u}", "absent",
     ["This account doesn’t exist", "This account doesn't exist"], True),
    ("threads", "Threads", "SNS", "https://www.threads.net/@{u}", "absent",
     ["Sorry, this page isn't available"], True),
    ("tiktok", "TikTok", "SNS", "https://www.tiktok.com/@{u}", "absent",
     ["Couldn't find this account", "Couldn’t find this account"], True),
    ("facebook", "Facebook", "SNS", "https://www.facebook.com/{u}", "absent",
     ["content isn't available", "ページを表示できません"], True),
    ("bsky", "Bluesky", "SNS",
     "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={u}.bsky.social",
     "absent", ["ActorNotFound", "Profile not found"], False),
    ("mastodon", "Mastodon (mastodon.social)", "SNS", "https://mastodon.social/@{u}",
     "status", [], False),
    ("misskey", "Misskey (misskey.io)", "SNS", "https://misskey.io/@{u}", "status", [], True),
    ("pinterest", "Pinterest", "SNS", "https://www.pinterest.com/{u}/", "status", [], True),
    ("snapchat", "Snapchat", "SNS", "https://www.snapchat.com/add/{u}", "status", [], True),
    ("telegram", "Telegram", "SNS", "https://t.me/{u}", "present", ["og:title"], False),
    ("line", "LINE", "SNS", "https://line.me/R/ti/p/@{u}", "status", [], True),
    ("keybase", "Keybase", "SNS", "https://keybase.io/{u}", "status", [], False),
    ("reddit", "Reddit", "SNS", "https://www.reddit.com/user/{u}/about.json",
     "status", [], False),
    # --- 動画 / 音楽 ---
    ("youtube", "YouTube", "動画", "https://www.youtube.com/@{u}", "absent",
     ["This page isn't available", "このページはありません"], True),
    ("twitch", "Twitch", "動画", "https://www.twitch.tv/{u}", "status", [], True),
    ("vimeo", "Vimeo", "動画", "https://vimeo.com/{u}", "status", [], False),
    ("dailymotion", "Dailymotion", "動画", "https://www.dailymotion.com/{u}", "status", [], True),
    ("nicovideo", "ニコニコ", "動画", "https://www.nicovideo.jp/user/{u}", "status", [], True),
    ("spotify", "Spotify", "音楽", "https://open.spotify.com/user/{u}", "status", [], True),
    ("soundcloud", "SoundCloud", "音楽", "https://soundcloud.com/{u}", "status", [], True),
    ("bandcamp", "Bandcamp", "音楽", "https://{u}.bandcamp.com", "status", [], False),
    ("lastfm", "Last.fm", "音楽", "https://www.last.fm/user/{u}", "status", [], True),
    # --- 開発 / 技術 ---
    ("github", "GitHub", "開発", "https://github.com/{u}", "status", [], False),
    ("gitlab", "GitLab", "開発", "https://gitlab.com/{u}", "status", [], False),
    ("bitbucket", "Bitbucket", "開発", "https://bitbucket.org/{u}", "status", [], False),
    ("qiita", "Qiita", "開発", "https://qiita.com/{u}", "status", [], False),
    ("zenn", "Zenn", "開発", "https://zenn.dev/{u}", "status", [], False),
    ("note", "note", "開発", "https://note.com/{u}", "status", [], True),
    ("devto", "dev.to", "開発", "https://dev.to/{u}", "status", [], False),
    ("codepen", "CodePen", "開発", "https://codepen.io/{u}", "status", [], False),
    ("kaggle", "Kaggle", "開発", "https://www.kaggle.com/{u}", "status", [], True),
    ("hn", "Hacker News", "開発", "https://news.ycombinator.com/user?id={u}", "absent",
     ["No such user"], False),
    ("hatena", "はてな", "開発", "https://profile.hatena.ne.jp/{u}/", "status", [], True),
    # --- クリエイティブ ---
    ("behance", "Behance", "制作", "https://www.behance.net/{u}", "status", [], True),
    ("dribbble", "Dribbble", "制作", "https://dribbble.com/{u}", "status", [], True),
    ("pixiv", "pixiv", "制作", "https://www.pixiv.net/users/{u}", "status", [], True),
    ("artstation", "ArtStation", "制作", "https://www.artstation.com/{u}", "status", [], True),
    ("flickr", "Flickr", "写真", "https://www.flickr.com/people/{u}", "status", [], True),
    ("500px", "500px", "写真", "https://500px.com/p/{u}", "status", [], True),
    ("unsplash", "Unsplash", "写真", "https://unsplash.com/@{u}", "status", [], True),
    ("medium", "Medium", "記事", "https://medium.com/@{u}", "status", [], True),
    ("substack", "Substack", "記事", "https://{u}.substack.com", "status", [], False),
    ("tumblr", "Tumblr", "記事", "https://{u}.tumblr.com", "status", [], False),
    ("wattpad", "Wattpad", "記事", "https://www.wattpad.com/user/{u}", "status", [], True),
    ("ao3", "AO3", "記事", "https://archiveofourown.org/users/{u}", "status", [], False),
    # --- 趣味 / その他 ---
    ("anilist", "AniList", "趣味", "https://anilist.co/user/{u}", "status", [], True),
    ("mal", "MyAnimeList", "趣味", "https://myanimelist.net/profile/{u}", "status", [], True),
    ("duolingo", "Duolingo", "趣味", "https://www.duolingo.com/profile/{u}", "status", [], True),
    ("steam", "Steam", "ゲーム", "https://steamcommunity.com/id/{u}", "absent",
     ["The specified profile could not be found"], True),
    ("linktree", "Linktree", "リンク", "https://linktr.ee/{u}", "status", [], True),
    ("litlink", "lit.link", "リンク", "https://lit.link/{u}", "status", [], True),
    ("patreon", "Patreon", "支援", "https://www.patreon.com/{u}", "status", [], True),
    ("kofi", "Ko-fi", "支援", "https://ko-fi.com/{u}", "status", [], True),
    ("booth", "BOOTH", "物販", "https://{u}.booth.pm", "status", [], False),
    ("aboutme", "about.me", "リンク", "https://about.me/{u}", "status", [], True),
    ("gravatar", "Gravatar", "リンク", "https://gravatar.com/{u}", "status", [], True),
]

CATS = ["SNS", "動画", "音楽", "開発", "制作", "写真", "記事", "趣味", "ゲーム",
        "リンク", "支援", "物販"]


def _og(body):
    m = OG.search(body) or OG2.search(body)
    return m.group(1) if m else ""


def _title(body):
    m = TITLE.search(body)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:160] if m else ""


def check(site, username, timeout=8):
    sid, name, cat, tpl, kind, kws, best = site
    url = tpl.format(u=username)
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    except Exception as e:
        return {"site": sid, "site_name": name, "cat": cat, "url": url,
                "state": "error", "code": 0, "title": "", "og_image": "",
                "note": repr(e)[:120]}
    code = r.status_code
    body = r.text[:300000]
    low = body.lower()

    if code in (404, 410):
        state = "no"
    elif code == 429:
        state = "rate"
    elif code in (401, 403):
        state = "blocked"
    elif code >= 500:
        state = "error"
    elif code >= 400:
        state = "no"
    else:
        state = "yes"
        if kind == "absent":
            for kw in kws:
                if kw.lower() in low:
                    state = "no"
                    break
        elif kind == "present":
            for kw in kws:
                if kw.lower() not in low:
                    state = "no"
                    break
    return {"site": sid, "site_name": name, "cat": cat, "url": url,
            "state": state, "code": code,
            "title": _title(body) if state == "yes" else "",
            "og_image": _og(body) if state == "yes" else "",
            "note": "best-effort" if best else ""}


def scan(username, cats=None, workers=14, timeout=8, include_best=True):
    """ユーザー名を全サイトで並列チェックする。"""
    u = (username or "").strip().lstrip("@")
    if not u:
        return []
    pool = [s for s in SITES
            if (not cats or s[2] in cats) and (include_best or not s[6])]
    out = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(check, s, u, timeout): s for s in pool}
        for f in as_completed(futs):
            try:
                out.append(f.result())
            except Exception:
                continue
    order = {s[0]: i for i, s in enumerate(SITES)}
    out.sort(key=lambda r: (r["state"] != "yes", order.get(r["site"], 999)))
    return out


# ---------- Gravatar ----------

def gravatar(email):
    """メールアドレスからGravatarプロフィールと紐付きSNSを引く。"""
    e = (email or "").strip().lower()
    if not e:
        return None
    h = hashlib.md5(e.encode()).hexdigest()
    res = {"email": e, "md5": h, "avatar": f"https://www.gravatar.com/avatar/{h}",
           "profile": f"https://gravatar.com/{h}", "display_name": "",
           "accounts": [], "urls": [], "raw": {}}
    try:
        d = requests.get(f"https://gravatar.com/{h}.json", headers=HEADERS,
                         timeout=10).json()
        ent = (d.get("entry") or [{}])[0]
        res["display_name"] = ent.get("displayName") or ""
        res["accounts"] = [{"shortname": a.get("shortname"), "url": a.get("url"),
                            "username": a.get("username")}
                           for a in (ent.get("accounts") or [])]
        res["urls"] = [{"title": x.get("title"), "value": x.get("value")}
                       for x in (ent.get("urls") or [])]
        res["raw"] = ent
    except Exception:
        pass
    try:
        r = requests.get(f"https://www.gravatar.com/avatar/{h}?d=404",
                         headers=HEADERS, timeout=10)
        res["has_avatar"] = r.status_code == 200
    except Exception:
        res["has_avatar"] = None
    return res


# ---------- アイコン照合 ----------

def phash_url(url, timeout=12):
    """画像URLからpHashを計算する。"""
    try:
        import imagehash
        from PIL import Image
    except Exception:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        return str(imagehash.phash(im))
    except Exception:
        return ""


def phash_distance(a, b):
    try:
        import imagehash
        return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)
    except Exception:
        return 99