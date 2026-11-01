"""逆探知（IP インテリジェンス）エンジン。

IP から機械的に取れる情報を「全部」取り、GPS と突き合わせて矛盾を検出する。
取得できる項目は docs/IP_INTEL.md と画面に全列挙してある。

v1:
  ・複数プロバイダのラダー（ip-api → ipwho.is → ipapi.co → freeipapi → ipinfo）
  ・RDAP（ARIN/RIPE/APNIC/…）で CIDR・ネットワーク名・登録組織・ abuse 窓口
  ・逆引き PTR、共通ポートの開閉、TLS 証明書、Tor 出口判定
  ・IP 種別（v4/v6・private・CGNAT・bogon・loopback・multicast）
  ・GPS との距離・タイムゾーン矛盾・言語矛盾・回線とUAの矛盾・時計ズレ
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
import threading
import time
from urllib.parse import quote

import requests

TTL = int(os.getenv("REVERSE_TTL", "900"))
TIMEOUT = float(os.getenv("REVERSE_TIMEOUT", "6"))
RDAP_ON = os.getenv("REVERSE_RDAP", "1") != "0"
PORT_ON = os.getenv("REVERSE_PORTS", "1") != "0"

_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.RLock()

# 逆探知で機械的に取れる項目（画面表示用の定義。ここが仕様）
FIELDS = [
    ("ip", "対象IP"),
    ("ip_version", "IPバージョン"),
    ("ip_type", "IP種別（グローバル/私設/CGNAT/予約）"),
    ("reverse_dns", "逆引きホスト名(PTR)"),
    ("continent", "大陸コード"),
    ("country", "国"),
    ("country_code", "国コード"),
    ("region", "地域（都道府県相当）"),
    ("region_code", "地域コード"),
    ("city", "市区町村"),
    ("district", "区・地区"),
    ("postal", "郵便番号"),
    ("lat", "緯度"),
    ("lon", "経度"),
    ("accuracy_km", "IP位置の推定半径"),
    ("timezone", "タイムゾーン"),
    ("utc_offset", "UTCオフセット"),
    ("currency", "通貨"),
    ("calling_code", "国際電話コード"),
    ("languages", "公用語"),
    ("isp", "ISP名"),
    ("org", "組織名"),
    ("asn", "AS番号"),
    ("as_name", "AS名"),
    ("cidr", "割当CIDR"),
    ("registry", "RIR（登録管理機関）"),
    ("netname", "ネットワーク名"),
    ("abuse_mail", "abuse 連絡先"),
    ("allocated", "割当年月日"),
    ("is_mobile", "モバイル回線"),
    ("is_proxy", "プロキシ"),
    ("is_vpn", "VPN"),
    ("is_tor", "Tor出口"),
    ("is_hosting", "データセンター/クラウド"),
    ("is_anycast", "Anycast"),
    ("is_relay", "中継事業者"),
    ("open_ports", "開放ポート"),
    ("tls_cn", "TLS証明書 CN"),
    ("tls_issuer", "TLS発行者"),
    ("tls_not_after", "TLS有効期限"),
    ("http_server", "HTTP Serverヘッダ"),
    ("provider_count", "一致した情報源の数"),
    ("confidence", "信頼度"),
]

TOR_LIST = "https://check.torproject.org/torbulkexitlist"
_tor_cache: tuple[float, set] = (0.0, set())

# 主要 VPN / クラウド / 中継事業者の ASN・名前の手がかり
VPN_KW = ("vpn", "nordvpn", "expressvpn", "surfshark", "cyberghost", "private internet",
          "protonvpn", "mullvad", "ipvanish", "pia", "windscribe", "hide.me",
          "tunnelbear", "hotspot shield", "zenmate", "purevpn", "ivacy", "airvpn")
HOST_KW = ("amazon", "aws", "google", "microsoft", "azure", "digitalocean", "linode",
           "vultr", "hetzner", "ovh", "contabo", "oracle", "alibaba", "tencent",
           "cloudflare", "fastly", "akamai", "leaseweb", "scaleway", "upcloud",
           "colocation", "datacenter", "data center", "server", "hosting", "cloud")
RELAY_KW = ("relay", "transit", "backbone", "peer", "exchange")

PORTS = [(80, "http"), (443, "https"), (22, "ssh"), (8080, "http-alt"),
         (8443, "https-alt"), (3128, "proxy"), (1080, "socks"), (3389, "rdp"),
         (5060, "sip"), (7547, "tr-069")]

PROVIDERS = [
    ("ip-api.com", "http://ip-api.com/json/{ip}", {
        "country": "country", "country_code": "countryCode", "region": "regionName",
        "region_code": "region", "city": "city", "district": "district",
        "postal": "zip", "lat": "lat", "lon": "lon", "timezone": "timezone",
        "isp": "isp", "org": "org", "asn": "as", "reverse_dns": "reverse",
        "is_mobile": "mobile", "is_proxy": "proxy", "is_hosting": "hosting",
    }, {"fields": "status,message,continent,continentCode,country,countryCode,region,"
                  "regionName,city,district,zip,lat,lon,timezone,offset,currency,"
                  "isp,org,as,asname,reverse,mobile,proxy,hosting,query"}),
    ("ipwho.is", "https://ipwho.is/{ip}", {
        "continent": "continent", "country": "country", "country_code": "country_code",
        "region": "region", "city": "city", "postal": "postal", "lat": "latitude",
        "lon": "longitude", "is_proxy": "security.proxy", "is_vpn": "security.vpn",
        "is_tor": "security.tor", "is_hosting": "security.hosting",
        "isp": "connection.isp", "org": "connection.org", "asn": "connection.asn",
    }, None),
    ("ipapi.co", "https://ipapi.co/{ip}/json/", {
        "country": "country_name", "country_code": "country_code", "region": "region",
        "city": "city", "postal": "postal", "lat": "latitude", "lon": "longitude",
        "timezone": "timezone", "currency": "currency", "org": "org", "asn": "asn",
        "languages": "languages", "calling_code": "country_calling_code",
    }, None),
    ("freeipapi.com", "https://freeipapi.com/api/json/{ip}", {
        "country": "countryName", "country_code": "countryCode", "region": "regionName",
        "city": "cityName", "lat": "latitude", "lon": "longitude",
        "timezone": "timeZone", "is_proxy": "isProxy",
    }, None),
]


# ---------- 基本判定 ----------

def valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address((ip or "").strip())
        return True
    except ValueError:
        return False


def ip_kind(ip: str) -> tuple[str, str, int]:
    """(version, 種別, グローバルか)"""
    try:
        a = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return ("-", "不正", 0)
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.is_loopback:
        return (f"v{a.version}", "ループバック", 0)
    if a.is_link_local:
        return (f"v{a.version}", "リンクライト", 0)
    if a.is_multicast:
        return (f"v{a.version}", "マルチキャスト", 0)
    if a.is_private:
        return (f"v{a.version}", "私設アドレス", 0)
    if a.is_reserved or a.is_unspecified:
        return (f"v{a.version}", "予約", 0)
    if a.version == 4 and a in ipaddress.ip_network("100.64.0.0/10"):
        return ("v4", "CGNAT（キャリアNAT）", 0)
    return (f"v{a.version}", "グローバル", 1)


def rdns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _get(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _fetch(provider: tuple) -> dict:
    name, tmpl, map_, params = provider
    try:
        r = requests.get(tmpl.format(ip=quote(ip_target := _fetch.ip, safe="")),
                         params=params, timeout=TIMEOUT,
                         headers={"User-Agent": "igtracker-reverse/1"})
        d = r.json()
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    if d.get("success") is False or d.get("error") or d.get("status") == "fail":
        return {}
    out = {}
    for dst, src in map_.items():
        v = _get(d, src)
        if v not in (None, "", False):
            out[dst] = v
    return out


def _rdap(ip: str) -> dict:
    if not RDAP_ON:
        return {}
    try:
        r = requests.get(f"https://rdap.org/ip/{ip}", timeout=TIMEOUT,
                         headers={"Accept": "application/rdap+json"})
        d = r.json()
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    if d.get("handle"):
        out["netname"] = str(d["handle"])[:80]
    if d.get("name"):
        out["netname"] = str(d["name"])[:80]
    if d.get("country"):
        out["registry_country"] = d["country"]
    try:
        out["registry"] = str(d["port43"] or "")
    except Exception:
        pass
    for ev in d.get("events") or []:
        if ev.get("eventAction") == "registration":
            out["allocated"] = str(ev.get("eventDate") or "")[:10]
    for ent in d.get("entities") or []:
        roles = ent.get("roles") or []
        if "abuse" in roles:
            v = ent.get("vcardArray")
            try:
                for item in v[1]:
                    if item[0] == "email":
                        out["abuse_mail"] = item[3]
            except Exception:
                pass
    for c in d.get("cidr0_cidrs") or []:
        out.setdefault("cidr", f"{c.get('v4prefix') or c.get('v6prefix')}/{c.get('length')}")
    if not out.get("registry"):
        for link in d.get("links") or []:
            if link.get("rel") == "self":
                out["registry"] = link.get("href", "")[:120]
    return out


def _tor(ip: str) -> int:
    global _tor_cache
    now = time.time()
    with _LOCK:
        if now - _tor_cache[0] < 3600 and _tor_cache[1]:
            return int(ip in _tor_cache[1])
    try:
        r = requests.get(TOR_LIST, timeout=TIMEOUT)
        s = {l.strip() for l in r.text.splitlines() if l.strip()}
        with _LOCK:
            _tor_cache = (now, s)
        return int(ip in s)
    except Exception:
        return 0


def _ports(ip: str) -> list[str]:
    if not PORT_ON:
        return []
    out = []
    for port, label in PORTS:
        s = socket.socket(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                          socket.SOCK_STREAM)
        s.settimeout(1.2)
        try:
            if s.connect_ex((ip, port)) == 0:
                out.append(f"{port}/{label}")
        finally:
            s.close()
    return out


def _tls(ip: str) -> dict:
    out = {}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for port in (443, 8443):
        try:
            with socket.create_connection((ip, port), timeout=2.5) as raw:
                with ctx.wrap_socket(raw, server_hostname=ip) as s:
                    c = s.getpeercert() or {}
                    sub = dict(x[0] for x in c.get("subject", ()))
                    iss = dict(x[0] for x in c.get("issuer", ()))
                    out = {"tls_cn": sub.get("commonName", "")[:120],
                           "tls_issuer": iss.get("organizationName", "")[:120],
                           "tls_not_after": c.get("notAfter", "")[:40]}
                    return out
        except Exception:
            continue
    return out


def _http_server(ip: str) -> str:
    for scheme, port in (("http", 80), ("https", 443)):
        try:
            r = requests.get(f"{scheme}://{ip}:{port}/", timeout=3, verify=False,
                             headers={"User-Agent": "igtracker-reverse/1"})
            v = r.headers.get("server")
            if v:
                return v[:80]
        except Exception:
            continue
    return ""


# ---------- 矛盾検出（GPS との突き合わせ） ----------

def _haversine(a, b, c, d):
    import math
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def contradictions(data: dict, gps_lat=None, gps_lon=None, client: dict | None = None) -> list[dict]:
    out = []
    client = client or {}
    if gps_lat is not None and data.get("lat") is not None:
        d = _haversine(float(gps_lat), float(gps_lon), float(data["lat"]), float(data["lon"]))
        out.append({
            "level": "warn" if d > 50000 else "info",
            "key": "gps_gap",
            "text": f"GPS と IP 推定位置の距離 {d/1000:.1f}km"
                    + ("（回線推定のみで説明できる範囲）" if d < 50000
                       else "（VPN/中継の可能性）"),
        })
    if data.get("timezone") and client.get("tz"):
        if str(data["timezone"]).lower() != str(client["tz"]).lower():
            out.append({"level": "warn", "key": "tz_mismatch",
                        "text": f"回線のタイムゾーン {data['timezone']} と端末 {client['tz']} が不一致"})
    if client.get("lang") and data.get("country_code"):
        first = str(client["lang"]).split(",")[0].split("-")[0].lower()
        cc = str(data["country_code"]).lower()
        if first and cc and first not in (cc, "en") and len(first) == 2:
            out.append({"level": "info", "key": "lang_mismatch",
                        "text": f"端末言語 {first} と回線国 {cc} が不一致"})
    if data.get("is_mobile") and client.get("platform"):
        p = str(client["platform"]).lower()
        if any(k in p for k in ("win", "mac", "linux")) and "android" not in p:
            out.append({"level": "info", "key": "mobile_pc",
                        "text": "モバイル回線なのに PC 系プラットフォーム（テザリング/ルータ経由の可能性）"})
    if data.get("is_hosting"):
        out.append({"level": "warn", "key": "hosting",
                    "text": "データセンター経由。素の回線位置ではない可能性が高い"})
    if data.get("is_vpn") or data.get("is_proxy"):
        out.append({"level": "warn", "key": "vpn",
                    "text": "VPN/プロキシ検出。位置は出口サーバのもの"})
    if data.get("is_tor"):
        out.append({"level": "warn", "key": "tor", "text": "Tor 出口ノード"})
    if client.get("clock_skew") is not None:
        try:
            sk = float(client["clock_skew"])
            if abs(sk) > 120:
                out.append({"level": "info", "key": "clock",
                            "text": f"端末時計がサーバと {sk:+.0f} 秒ずれている"})
        except Exception:
            pass
    if client.get("lan_ip"):
        out.append({"level": "info", "key": "lan",
                    "text": f"LAN 内 IP が漏れている: {client['lan_ip']}"})
    return out


def _verdict(data: dict) -> tuple[int, str]:
    score = 100
    if data.get("is_hosting"):
        score -= 30
    if data.get("is_vpn") or data.get("is_proxy"):
        score -= 30
    if data.get("is_tor"):
        score -= 40
    if data.get("is_mobile"):
        score -= 20
    if not data.get("country"):
        score -= 20
    score = max(0, min(100, score))
    if score >= 80:
        return score, "固定回線。位置は比較的信用できる"
    if score >= 55:
        return score, "モバイル回線。市区町村レベルまで"
    if score >= 30:
        return score, "VPN/DC 経由。国・地域レベル"
    return score, "匿名化経由。ほぼ当てにならない"


# ---------- 本体 ----------

def intel(ip: str, use_cache: bool = True) -> dict:
    """IP 1 件の逆探知。結果は TTL キャッシュする。"""
    ip = (ip or "").strip()
    if not valid_ip(ip):
        return {"ip": ip, "error": "IPとして不正"}
    now = time.time()
    if use_cache:
        with _LOCK:
            hit = _CACHE.get(ip)
            if hit and now - hit[0] < TTL:
                return hit[1]

    version, kind, glob = ip_kind(ip)
    data: dict = {"ip": ip, "ip_version": version, "ip_type": kind, "is_global": glob}

    if not glob:
        data.update({"reverse_dns": rdns(ip) if version == "v4" else "",
                     "provider_count": 0, "confidence": 100,
                     "verdict": "私設/CGNAT。回線事業者の内側"})
        with _LOCK:
            _CACHE[ip] = (now, data)
        return data

    merged: dict = {}
    hits = 0
    for p in PROVIDERS:
        _fetch.ip = ip
        got = _fetch(p)
        if got:
            hits += 1
            for k, v in got.items():
                merged.setdefault(k, v)
    merged.update({k: v for k, v in _rdap(ip).items() if v})
    if not merged.get("reverse_dns"):
        r = rdns(ip)
        if r:
            merged["reverse_dns"] = r

    blob = " ".join(str(merged.get(k, "")) for k in
                    ("isp", "org", "asn", "as_name", "netname", "reverse_dns")).lower()
    if any(k in blob for k in VPN_KW):
        merged["is_vpn"] = 1
    if any(k in blob for k in HOST_KW):
        merged["is_hosting"] = 1
    if any(k in blob for k in RELAY_KW):
        merged["is_relay"] = 1
    if "anycast" in blob:
        merged["is_anycast"] = 1
    merged["is_tor"] = _tor(ip)

    ports = _ports(ip)
    if ports:
        merged["open_ports"] = ports
    merged.update({k: v for k, v in _tls(ip).items() if v})
    srv = _http_server(ip)
    if srv:
        merged["http_server"] = srv

    for k, v in merged.items():
        if v not in (None, "", [], 0) or k.startswith("is_"):
            data[k] = v
    if data.get("lat") is not None and data.get("lon") is not None:
        data["accuracy_km"] = 25 if data.get("is_mobile") else 5
    data["provider_count"] = hits
    data["sources"] = hits
    data["confidence"], data["verdict"] = _verdict(data)
    data["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    if hits == 0:
        data.setdefault("verdict", "どの情報源も応答せず（レート制限の可能性）")

    with _LOCK:
        _CACHE[ip] = (now, data)
    return data


def summarize_ips(ips: list[str], limit: int = 12) -> list[dict]:
    """複数 IP をまとめて逆探知（重複除去・上限あり）。"""
    seen, out = set(), []
    for ip in ips:
        ip = (ip or "").strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        if len(out) >= limit:
            break
        out.append(intel(ip))
    return out


def rows_for(code: str, limit: int = 12) -> list[dict]:
    """コードに紐づく実ヒット IP を逆探知する。"""
    from .tenancy import db
    ips = [r["ip"] for r in db.q(
        "SELECT ip, COUNT(*) n FROM link_hits WHERE code=? AND is_bot=0 "
        "GROUP BY ip ORDER BY n DESC LIMIT ?", (code, limit))]
    return summarize_ips(ips, limit=limit)


# ---------- ルーター ----------

def _m():
    from . import main
    return main


async def _auth(request):
    return await _m().auth(request)


def make_router():
    from fastapi import APIRouter, Depends, HTTPException, Request
    from fastapi.responses import HTMLResponse

    router = APIRouter()

    def _owner(code):
        from . import users, tenancy
        o = users.owner_of_link(code)
        if o:
            tenancy.set_current(o)
        return o

    @router.get("/link/{code}/reverse", response_class=HTMLResponse)
    def reverse_page(code: str, request: Request, ip: str = "", u=Depends(_auth)):
        from .tenancy import db
        from . import linktrack
        if not _owner(code):
            raise HTTPException(404)
        link = db.link_get(code)
        if not link:
            raise HTTPException(404)
        rows = rows_for(code)
        gps = db.q1("SELECT gps_lat, gps_lon FROM link_hits WHERE code=? "
                    "AND gps_lat IS NOT NULL ORDER BY ts DESC LIMIT 1", (code,))
        for r in rows:
            r["issues"] = contradictions(
                r, gps["gps_lat"] if gps else None,
                gps["gps_lon"] if gps else None,
                {"tz": r.get("timezone")})
        single = intel(ip) if ip else None
        if single:
            single["issues"] = contradictions(single)
        return _m().render("link_reverse.html", request, link=link, rows=rows,
                           single=single, ip=ip, fields=FIELDS,
                           base=_m()._base(request))

    @router.get("/api/reverse/{code}")
    def api_reverse(code: str, u=Depends(_auth)):
        from .tenancy import db
        if not _owner(code):
            raise HTTPException(404)
        return {"ok": True, "rows": rows_for(code)}

    @router.get("/api/reverse/ip/{ip}")
    def api_reverse_ip(ip: str, u=Depends(_auth)):
        return {"ok": True, "data": intel(ip)}

    @router.get("/reverse", response_class=HTMLResponse)
    def reverse_any(request: Request, ip: str = "", u=Depends(_auth)):
        single = intel(ip) if ip else None
        if single:
            single["issues"] = contradictions(single)
        return _m().render("link_reverse.html", request, link=None, rows=[],
                           single=single, ip=ip, fields=FIELDS,
                           base=_m()._base(request))

    return router