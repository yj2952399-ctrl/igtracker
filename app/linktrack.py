"""リンク踏み解析。IP・位置・端末・回線を判定して集計する。"""
import os, re, json, time
from collections import Counter
from urllib.parse import quote

import requests
from fastapi.responses import HTMLResponse

_geo_cache = {}
_geo_ts = {}

BOT_KW = [
    "bot", "crawler", "spider", "facebookexternalhit", "facebot", "whatsapp",
    "telegrambot", "twitterbot", "linkedinbot", "applebot", "bingbot", "yandexbot",
    "duckduckbot", "slackbot", "discordbot", "embedly", "quora link preview",
    "outbrain", "pinterest", "skypeuripreview", "w3c_validator", "googleimageproxy",
    "google-inspectiontool", "semrush", "ahrefs", "screaming frog", "lighthouse",
    "pingdom", "uptimerobot", "better uptime", "python-requests", "curl", "wget",
    "go-http-client", "headlesschrome", "line-poker", "kakaotalk-scrap",
    "facebookcatalog", "vercel", "render-", "expanse", "statuscake",
]

INAPP = [
    ("instagram", "Instagram"), ("fban", "Facebook"), ("fbav", "Facebook"),
    ("line/", "LINE"), ("twitter", "X (Twitter)"), ("micromessenger", "WeChat"),
    ("kakaotalk", "KakaoTalk"), ("naver", "Naver"),
]

# モバイル回線（4G/5G）っぽいISP/ASNの手がかり
MOBILE_KW = (
    "mobile", "cellular", "lte", "5g", "4g", "wimax", "umts", "gsm",
    "docomo", "kddi", "softbank", "rakuten", "au one", "au-net",
    "t-mobile", "vodafone", "orange", "telekom", "telefonica", "movistar",
    "verizon wireless", "at&t", "cricket", "metro pcs", "boost mobile",
    "china mobile", "chinamobile", "china unicom", "china telecom",
    "airtel", "jio", "vodacom", "globe telecom", "smart communications",
    "telstra", "optus", "singtel", "starhub", "true move", "ais ", "dtac",
    "viettel", "mobifone", "vinaphone", "celcom", "digi tele", "maxis",
    "ooredoo", "etisalat", "zain", "mtn ", "safaricom", "claro", "tim ",
    "turkcell", "megafon", "mts ", "beeline", "kyivstar", "plus ",
)

# 精度の注意書き
IP_WARN = ("一部または全部がIP推定の位置です。4G/5G回線では数km〜数十kmの誤差が出ます"
           "（GPSを許可していれば精度が上がります）")


# 生成側：宛先は必ずエンコード
def share_url(code, dest):
    """共有リンク（/l/{code}?to=...）を作る。宛先は必ずエンコードする。"""
    return f"/l/{code}?to={quote(dest, safe='')}"

# 受ける側：スキーム補完
def _abs(d):
    d = (d or "").strip()
    if not d:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", d):
        d = "https://" + d
    return d
# ---------- アプリ内ブラウザ（埋め込み）の検出と脱出 ----------

INAPP_HINT = [
    ("instagram", "Instagram"), ("fban", "Facebook"), ("fbav", "Facebook"),
    ("fb_iab", "Facebook"), ("line/", "LINE"), ("micromessenger", "WeChat"),
    ("twitter", "X (Twitter)"), ("kakaotalk", "KakaoTalk"), ("naver", "Naver"),
    ("snapchat", "Snapchat"), ("pinterest", "Pinterest"), ("linkedinapp", "LinkedIn"),
    ("gsa/", "GoogleApp"), ("musical_ly", "TikTok"), ("barca", "TikTok"),
    ("threads", "Threads"), ("youtube", "YouTube"), ("discord", "Discord"),
    ("slack", "Slack"), ("mercury", "Facebook"),
]

# 子ウィンドウ・iframe は脱出させない（開き直すと増殖が止まる）
BREAKOUT_SKIP_U = ("win", "ifr", "inj", "os", "sw", "usb", "share")


def inapp_label(ua):
    """アプリ内ブラウザ（埋め込み）ならアプリ名、違えば ''。"""
    low = (ua or "").lower()
    if not low or any(k in low for k in BOT_KW):
        return ""
    for k, label in INAPP_HINT:
        if k in low:
            return label
    if "android" in low and "wv)" in low and "version/" in low:
        return "Android WebView"
    return ""


BREAKOUT_HTML = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#05070a">
<title>外部ブラウザで開きます…</title>
<style>
html,body{margin:0;height:100%%;background:#05070a;color:#e6e9ef;
  font-family:system-ui,-apple-system,"Hiragino Sans",sans-serif}
body{display:flex;align-items:center;justify-content:center;padding:22px;text-align:center}
.w{max-width:430px;width:100%%}
.ic{font-size:44px;line-height:1;margin-bottom:10px}
h1{margin:0 0 10px;font-size:17px;color:#7ee08a;letter-spacing:.5px}
p{margin:0 0 20px;font-size:13px;line-height:1.9;color:#9fb4cc}
a.b{display:block;margin:9px 0;padding:15px 18px;border-radius:12px;text-decoration:none;
  font-weight:800;font-size:14.5px;background:#4c8dff;color:#fff}
a.b.g{background:#1a2130;color:#c9d3e4;border:1px solid #2b3346}
.n{margin-top:16px;font-size:11.5px;color:#5f7d99;font-family:ui-monospace,Menlo,monospace}
</style></head><body>
<div class="w">
  <div class="ic">↗</div>
  <h1>アプリ内ブラウザを検出しました</h1>
  <p>%(label)s の中ではなく<b>外部ブラウザ</b>で開き直します。<br>
     埋め込みブラウザではタブ増殖・常駐・ポップアップが制限されるためです。</p>
  <a class="b" id="s1" href="#">開く</a>
  <a class="b" id="s2" href="#">別の方法で開く</a>
  <a class="b g" href="%(target_attr)s">このまま開く</a>
  <div class="n" id="n">自動で切り替えています…</div>
</div>
<script>
var U = %(target_json)s;
var IOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
var AND = /Android/i.test(navigator.userAgent);
var S1 = document.getElementById("s1"), S2 = document.getElementById("s2");
function intent(u, pkg) {
  var t = u.replace(/^https?:\\/\\//, "");
  var p = "#Intent;scheme=" + (u.indexOf("https:") === 0 ? "https" : "http") + ";";
  if (pkg) p += "package=" + pkg + ";";
  p += "S.browser_fallback_url=" + encodeURIComponent(u) + ";end";
  return "intent://" + t + p;
}
function leave(u) { try { location.href = u; } catch (e) {} }
if (IOS) {
  S1.textContent = "Safari で開く";
  S1.href = "x-safari-" + U;
  S2.textContent = "Chrome で開く";
  S2.href = U.replace(/^https:/, "googlechromes:").replace(/^http:/, "googlechrome:");
  leave(S1.href);
} else if (AND) {
  S1.textContent = "Chrome で開く";
  S1.href = intent(U, "com.android.chrome");
  S2.textContent = "ブラウザを選ぶ";
  S2.href = intent(U, "");
  leave(S1.href);
} else {
  S1.style.display = "none"; S2.style.display = "none";
  leave(U);
}
setTimeout(function () {
  if (document.visibilityState === "hidden") return;
  document.getElementById("n").textContent = "切り替わらない時は上のボタンをタップ";
}, 1400);
</script>
</body></html>
"""


def breakout(request):
    """アプリ内ブラウザなら外部ブラウザへ飛ばす HTML を返す（不要なら None）。"""
    if os.getenv("BREAKOUT", "1") == "0":
        return None
    label = inapp_label(request.headers.get("user-agent", ""))
    if not label:
        return None
    q = request.query_params
    if q.get("x") in ("1", "0"):        # 脱出済み / 意図的に埋め込みのまま
        return None
    if (q.get("w") or "").strip():      # 子ウィンドウ
        return None
    if (q.get("u") or "").strip().lower() in BREAKOUT_SKIP_U:
        return None
    base = (os.getenv("PUBLIC_BASE") or str(request.base_url)).rstrip("/")
    qs = "&".join([f"{k}={quote(v, safe='')}" for k, v in q.multi_items()]
                  + ["x=1", "ib=" + quote(label, safe="")])
    target = base + request.url.path + "?" + qs
    return HTMLResponse(BREAKOUT_HTML % {
        "target_json": json.dumps(target),
        "target_attr": target.replace("&", "&amp;"),
        "label": label,
    }, status_code=200)
    
def client_ip(request):
    for h in ("cf-connecting-ip", "true-client-ip", "x-real-ip",
              "x-forwarded-for", "x-client-ip", "forwarded"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].split(";")[0].replace("for=", "").strip().strip('"')
    return request.client.host if request.client else ""


def parse_ua(ua):
    ua = ua or ""
    low = ua.lower()
    r = {"device": "不明", "os": "不明", "browser": "不明", "inapp": "",
         "is_bot": 0, "is_mobile": 0}

    if any(k in low for k in BOT_KW):
        r["is_bot"] = 1
    if "line/" in low and "applewebkit" not in low:
        r["is_bot"] = 1

    for k, label in INAPP:
        if k in low:
            r["inapp"] = label
            break

    if "iphone" in low or "ipod" in low:
        r["os"] = "iOS"; r["is_mobile"] = 1; r["device"] = "iPhone"
    elif "ipad" in low:
        r["os"] = "iPadOS"; r["is_mobile"] = 1; r["device"] = "iPad"
    elif "android" in low:
        m = re.search(r"android[\s/]?([\d.]+)?", low)
        r["os"] = ("Android " + (m.group(1) or "")).strip()
        r["is_mobile"] = 1
        r["device"] = "Androidタブレット" if "tablet" in low else "Android端末"
    elif "windows nt 10" in low:
        r["os"] = "Windows 10/11"; r["device"] = "PC"
    elif "windows" in low:
        r["os"] = "Windows"; r["device"] = "PC"
    elif "mac os x" in low or "macintosh" in low:
        r["os"] = "macOS"; r["device"] = "Mac"
    elif "cros" in low:
        r["os"] = "ChromeOS"; r["device"] = "PC"
    elif "linux" in low:
        r["os"] = "Linux"; r["device"] = "PC"
    if "mobile" in low and not r["is_mobile"]:
        r["is_mobile"] = 1

    if r["inapp"]:
        r["browser"] = r["inapp"] + "内ブラウザ"
    elif "edg/" in low or "edga" in low or "edgios" in low:
        r["browser"] = "Edge"
    elif "opr/" in low or "opera" in low:
        r["browser"] = "Opera"
    elif "samsungbrowser" in low:
        r["browser"] = "Samsung Internet"
    elif "crios" in low:
        r["browser"] = "Chrome (iOS)"
    elif "fxios" in low:
        r["browser"] = "Firefox (iOS)"
    elif "chrome/" in low and "chromium" not in low:
        r["browser"] = "Chrome"
    elif "firefox/" in low:
        r["browser"] = "Firefox"
    elif "safari/" in low:
        r["browser"] = "Safari"
    elif "wv)" in low:
        r["browser"] = "Android WebView"
    return r


def _is_private(ip):
    if not ip:
        return True
    if ip in ("::1",) or ip.startswith(("10.", "127.", "192.168.", "169.254.")):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except Exception:
            return False
    if ip.startswith("fc") or ip.startswith("fd") or ip.startswith("fe80"):
        return True
    return False


def mobile_guess(isp="", org="", asn="", is_mobile=0):
    """4G/5G（モバイル回線）っぽいかどうか。"""
    if is_mobile:
        return True
    s = f"{isp or ''} {org or ''} {asn or ''}".lower()
    return any(k in s for k in MOBILE_KW)


def geo(ip):
    """IPから国・地域・市区町村・ISP・ASN・VPN判定を引く。"""
    if _is_private(ip):
        return {"src": "private"}
    now = time.time()
    if ip in _geo_cache and now - _geo_ts.get(ip, 0) < 3600:
        return _geo_cache[ip]

    out = {}
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,message,country,countryCode,regionName,city,zip,"
                              "lat,lon,timezone,isp,org,as,asname,mobile,proxy,hosting,query"},
            timeout=6)
        d = r.json()
        if d.get("status") == "success":
            out = {
                "country": d.get("country"), "country_code": d.get("countryCode"),
                "region": d.get("regionName"), "city": d.get("city"), "zip": d.get("zip"),
                "lat": d.get("lat"), "lon": d.get("lon"), "tz": d.get("timezone"),
                "isp": d.get("isp"), "org": d.get("org"), "asn": d.get("as"),
                "is_mobile": int(bool(d.get("mobile"))),
                "is_proxy": int(bool(d.get("proxy"))),
                "is_hosting": int(bool(d.get("hosting"))),
                "src": "ip-api.com",
            }
    except Exception:
        pass

    if not out:
        try:
            d = requests.get(f"https://ipwho.is/{ip}", timeout=6).json()
            if d.get("success"):
                c = d.get("connection") or {}
                sec = d.get("security") or {}
                out = {
                    "country": d.get("country"), "country_code": d.get("country_code"),
                    "region": d.get("region"), "city": d.get("city"),
                    "lat": d.get("latitude"), "lon": d.get("longitude"),
                    "tz": (d.get("timezone") or {}).get("id"),
                    "isp": c.get("isp"), "org": c.get("org"), "asn": c.get("asn"),
                    "is_proxy": int(bool(sec.get("proxy"))),
                    "is_hosting": int(bool(sec.get("hosting"))),
                    "src": "ipwho.is",
                }
        except Exception:
            pass

    if not out:
        try:
            d = requests.get(f"https://ipapi.co/{ip}/json/", timeout=6).json()
            if not d.get("error"):
                out = {
                    "country": d.get("country_name"), "country_code": d.get("country_code"),
                    "region": d.get("region"), "city": d.get("city"),
                    "lat": d.get("latitude"), "lon": d.get("longitude"),
                    "tz": d.get("timezone"), "isp": d.get("org"), "org": d.get("org"),
                    "asn": d.get("asn"), "src": "ipapi.co",
                }
        except Exception:
            pass

    if out and "is_mobile" not in out:
        out["is_mobile"] = 1 if mobile_guess(out.get("isp"), out.get("org"),
                                             out.get("asn")) else 0

    _geo_cache[ip] = out
    _geo_ts[ip] = now
    return out


def network_label(h):
    if h.get("is_hosting"):
        return "データセンター"
    if h.get("is_proxy"):
        return "VPN/プロキシ"
    if h.get("is_mobile"):
        return "モバイル回線（4G/5G）"
    if h.get("isp"):
        return "固定回線の可能性"
    return "不明"


def accuracy_label(src, is_mobile=0):
    """その点の位置がどれくらい信用できるか。"""
    if src == "gps":
        return "GPS（高精度）"
    if is_mobile:
        return "IP推定・モバイル回線（誤差 数km〜数十km）"
    if src == "ip":
        return "IP推定（誤差 数百m〜数km）"
    return "不明"


def _top(rows, key):
    c = Counter((r[key] or "").strip() for r in rows if (r[key] or "").strip())
    return c.most_common(1)[0][0] if c else "-"


def _counts(rows, key, n=8):
    return Counter((r[key] or "不明") for r in rows).most_common(n)


def summarize(hits):
    real = [h for h in hits if not h["is_bot"]]
    bots = [h for h in hits if h["is_bot"]]
    ips = Counter(h["ip"] for h in real if h["ip"])
    ip_mobile = sum(1 for h in real if h.get("is_mobile"))
    ip_only = sum(1 for h in real if h.get("gps_lat") is None)
    warn = ""
    if real and ip_only:
        warn = IP_WARN
        if ip_mobile:
            warn += f"（今回モバイル回線: {ip_mobile}件）"
    return {
        "total": len(hits),
        "real": len(real),
        "bots": len(bots),
        "uniq_ip": len(ips),
        "repeat_ip": [(ip, n) for ip, n in ips.most_common() if n > 1][:10],
        "country": _top(real, "country"),
        "region": _top(real, "region"),
        "city": _top(real, "city"),
        "tz": _top(real, "tz"),
        "isp": _top(real, "isp"),
        "asn": _top(real, "asn"),
        "mobile": ip_mobile,
        "ip_only": ip_only,
        "warn": warn,
        "proxy": sum(1 for h in real if h["is_proxy"]),
        "hosting": sum(1 for h in real if h["is_hosting"]),
        "gps": sum(1 for h in real if h["gps_lat"] is not None),
        "inapps": _counts(real, "inapp"),
        "devices": _counts(real, "device"),
        "oses": _counts(real, "os"),
        "browsers": _counts(real, "browser"),
        "langs": _counts(real, "lang"),
        "first": min((h["ts"] for h in hits), default=None),
        "last": max((h["ts"] for h in hits), default=None),
    }


# ---------- 端末キー署名の検証 ----------

def _b64d(s):
    import base64
    s = (s or "").replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _raw_to_der(sig: bytes) -> bytes:
    """WebCrypto の ECDSA 署名(生 r||s) を DER に変換する。"""
    n = len(sig) // 2
    r = int.from_bytes(sig[:n], "big")
    s = int.from_bytes(sig[n:], "big")

    def enc(x):
        b = x.to_bytes((x.bit_length() + 7) // 8 or 1, "big")
        if b[0] & 0x80:
            b = b"\x00" + b
        return b"\x02" + bytes([len(b)]) + b

    body = enc(r) + enc(s)
    return b"\x30" + bytes([len(body)]) + body


def verify_sig(pubkey_b64, sig_b64, message):
    """ブラウザの端末キーが nonce に正しく署名したかを検証する。"""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        pub = load_der_public_key(_b64d(pubkey_b64))
        pub.verify(_raw_to_der(_b64d(sig_b64)), (message or "").encode(),
                   ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False