"""通信の痕跡を全部抜く。IP・DNS・レスポンスヘッダ・端末指紋を記録。"""
import socket, json, platform, datetime as dt
import requests

from .database import now


def egress_ip(db=None):
    """自分の出口IP（Instagramにどう見えているか）"""
    for url in ("https://api.ipify.org?format=json",
                "https://ifconfig.me/all.json"):
        try:
            r = requests.get(url, timeout=8)
            data = r.json()
            ip = data.get("ip") or data.get("ip_addr")
            if ip:
                if db:
                    db.forensic("egress_ip", {"ip": ip, "source": url})
                return ip
        except Exception:
            continue
    return None


def resolve_hosts(db=None):
    """Instagram関連ホストのIPを引く"""
    hosts = ["i.instagram.com", "www.instagram.com", "graph.instagram.com",
             "instagram.com", "scontent.cdninstagram.com"]
    out = {}
    for h in hosts:
        try:
            infos = socket.getaddrinfo(h, 443, proto=socket.IPPROTO_TCP)
            ips = sorted({i[4][0] for i in infos})
            out[h] = ips
        except Exception as e:
            out[h] = [f"error: {e}"]
    if db:
        db.forensic("dns_resolve", out)
    return out


def capture_headers(db, cl, tag):
    """instagrapi の最後のレスポンスヘッダを保存（x-ig-* 等の内部情報）"""
    try:
        resp = getattr(cl, "last_response", None)
        if resp is None:
            return None
        h = dict(resp.headers)
        keep = {k: v for k, v in h.items()
                if k.lower().startswith(("x-ig", "x-fb", "ig-", "x-"))}
        payload = {"tag": tag, "status": resp.status_code,
                   "url": getattr(resp, "url", ""), "headers": keep}
        db.forensic("response_headers", payload)
        return payload
    except Exception:
        return None


def device_fingerprint(db, cl):
    """instagrapi が使っている端末フィンガープリントを保存"""
    try:
        s = cl.get_settings()
        payload = {
            "device_settings": s.get("device_settings", {}),
            "user_agent": s.get("user_agent"),
            "uuid": s.get("uuid"),
            "phone_id": s.get("phone_id"),
            "country": s.get("country"),
            "locale": s.get("locale"),
            "timezone_offset": s.get("timezone_offset"),
            "app_version": s.get("app_version"),
            "client_ip": egress_ip(),
            "host": platform.node(),
        }
        db.forensic("device_fingerprint", payload)
        return payload
    except Exception:
        return None


def snapshot_all(db, cl):
    """まとめて記録"""
    egress_ip(db)
    resolve_hosts(db)
    device_fingerprint(db, cl)
    capture_headers(db, cl, "forensics_snapshot")