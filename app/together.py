"""取得したIPから「誰と誰が一緒か」を解析する。

考え方:
  同じ出口IPから複数の訪問者が来ていれば、その人たちは同じ家・同じ職場・
  同じWi-Fiなど、物理的に近い場所にいる可能性が高い。
  さらに同じIPで時刻が近ければ「同時に同じ場所にいた」と言える。
  端末キー(pubkey)やフィンガープリントが一致すれば同一人物の複数端末。

  モバイル回線は CGNAT で他人とIPを共有するため、時刻の近さを必須にする。

  さらに端末単位の解析も行う。同じ端末で複数回来ていれば「同一端末の再訪」、
  同じ端末なのに訪問者IDが別なら「同一端末・別訪問者」として検出する。
"""
from __future__ import annotations

import ipaddress
import math
import datetime as dt
from collections import defaultdict
from itertools import combinations

# 信号の重み。noisy-or で合成するので「単独でどれだけ確からしいか」を表す。
W_PUBKEY = 0.97      # 同一端末キー = ほぼ同一人物
W_FP = 0.88          # 同一フィンガープリント = 同一端末
W_IP = 0.60          # 同じ固定回線IP = 同じ家/職場
W_IP_MOBILE = 0.35   # 同じモバイルIP（CGNATなので弱い）
W_IP_TIME = 0.45     # 同じIPで時刻が近い = 同時に同じ場所
W_SUBNET = 0.18      # 同じ/24 = 同一ISPの近隣
W_ASN_CITY = 0.12    # 同じASN・同じ市区町村

TH = [(0.90, "同一人物の可能性が高い"),
      (0.80, "同一端末の可能性が高い"),
      (0.70, "同居・同一世帯の可能性が高い"),
      (0.55, "同じ回線（同じ家・職場の可能性）"),
      (0.35, "近い関係の可能性")]

GROUP_TH = 0.50


def _t(s):
    try:
        return dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _sub24(ip):
    try:
        return str(ipaddress.ip_network(ip + "/24", strict=False))
    except Exception:
        return ""


def verdict(score):
    for th, label in TH:
        if score >= th:
            return label
    return "弱い"


class V:
    __slots__ = ("vid", "label", "ips", "times", "ip_mobile", "fps", "keys",
                 "asns", "cities", "mobile", "hosting", "isp", "hits", "last", "pseudo")

    def __init__(self, vid):
        self.vid = vid
        self.label = ""
        self.ips = set()
        self.times = defaultdict(list)
        self.ip_mobile = defaultdict(int)
        self.fps = set()
        self.keys = set()
        self.asns = set()
        self.cities = set()
        self.mobile = 0
        self.hosting = 0
        self.isp = ""
        self.hits = 0
        self.last = ""
        self.pseudo = vid.startswith("ip:")


def label_of(v):
    if v.label:
        return v.label
    if v.pseudo:
        return "IP " + v.vid[3:]
    return "訪問者 " + v.vid[:8]


def _hits(db, code=None, limit=20000):
    sql = "SELECT * FROM link_hits WHERE is_bot=0"
    args = []
    if code:
        sql += " AND code=?"
        args.append(code)
    sql += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in db.q(sql, tuple(args))]


def load(db, code=None, limit=20000):
    vs = {}
    for h in _hits(db, code, limit):
        ip = h.get("ip") or ""
        vid = h.get("vid") or ("ip:" + (ip or "?"))
        v = vs.get(vid)
        if v is None:
            v = V(vid)
            vs[vid] = v
        v.hits += 1
        ts = h.get("ts") or ""
        if ts > v.last:
            v.last = ts
        if ip:
            v.ips.add(ip)
            t = _t(ts)
            if t:
                v.times[ip].append(t)
            if h.get("is_mobile"):
                v.ip_mobile[ip] += 1
        if h.get("fingerprint"):
            v.fps.add(h["fingerprint"])
        if h.get("pubkey"):
            v.keys.add(h["pubkey"])
        if h.get("asn"):
            v.asns.add(h["asn"])
        if h.get("city"):
            v.cities.add(h["city"])
        if h.get("is_mobile"):
            v.mobile += 1
        if h.get("is_hosting"):
            v.hosting += 1
        if not v.isp and h.get("isp"):
            v.isp = h["isp"]

    try:
        for row in db.visitors(2000):
            v = vs.get(row["vid"])
            if v:
                v.label = row["label"] or ""
    except Exception:
        pass
    return vs


def _pair(a, b, window_h):
    sig = {}

    if a.keys & b.keys:
        sig["同一端末キー"] = W_PUBKEY
    if a.fps & b.fps:
        sig["同一フィンガープリント"] = W_FP

    shared = a.ips & b.ips
    fixed = [ip for ip in shared if not a.ip_mobile.get(ip) and not b.ip_mobile.get(ip)]
    mob = [ip for ip in shared if ip not in fixed]
    if fixed:
        sig["同じ固定回線IP"] = W_IP
    if mob:
        sig["同じモバイルIP"] = W_IP_MOBILE

    win = dt.timedelta(hours=window_h).total_seconds()
    near = 0
    for ip in shared:
        for ta in a.times.get(ip, []):
            for tb in b.times.get(ip, []):
                if abs((ta - tb).total_seconds()) <= win:
                    near += 1
    if near:
        sig["同じIPで時間的に近い"] = W_IP_TIME * min(1.0, near / 2.0)

    a24 = {_sub24(ip) for ip in a.ips} - {""}
    b24 = {_sub24(ip) for ip in b.ips} - {""}
    if a24 & b24:
        sig["同じ/24サブネット"] = W_SUBNET

    if (a.asns & b.asns) and (a.cities & b.cities):
        sig["同じASN・同じ市区町村"] = W_ASN_CITY

    s = 1.0
    for w in sig.values():
        s *= (1.0 - w)
    return round(1.0 - s, 4), sig, sorted(shared), near


def _layout(members, vs, pairs):
    n = len(members)
    w, h = 660, 300
    cx, cy = w / 2, h / 2
    r = min(115, 42 + n * 13)
    nodes = []
    for i, m in enumerate(members):
        ang = -math.pi / 2 + 2 * math.pi * i / max(n, 1)
        nodes.append({"vid": m, "label": label_of(vs[m]),
                      "x": round(cx + r * math.cos(ang), 1),
                      "y": round(cy + r * math.sin(ang), 1)})
    pos = {nd["vid"]: nd for nd in nodes}
    edges = []
    for p in pairs:
        A, B = pos.get(p["a"]), pos.get(p["b"])
        if not A or not B:
            continue
        edges.append({"x1": A["x"], "y1": A["y"], "x2": B["x"], "y2": B["y"],
                      "w": round(1 + p["score"] * 5, 1),
                      "op": round(0.25 + p["score"] * 0.75, 2)})
    return {"gw": w, "gh": h, "cx": cx, "cy": cy, "nodes": nodes, "edges": edges}


# ---------- 端末単位の解析 ----------

def device_groups(db, code=None, limit=20000):
    """フィンガープリント/端末キー単位でまとめる。

    同じ端末の再訪、同じ端末で訪問者IDが変わった相手を検出する。
    """
    dev = {}
    for h in _hits(db, code, limit):
        key = h.get("pubkey") or h.get("fingerprint") or ""
        if not key:
            continue
        d = dev.get(key)
        if d is None:
            d = {"key": key, "short": key[:12], "pubkey": h.get("pubkey") or "",
                 "fp": h.get("fingerprint") or "", "vids": set(), "hits": 0,
                 "ips": set(), "codes": set(), "first": "", "last": "",
                 "device": h.get("device"), "os": h.get("os"),
                 "browser": h.get("browser"), "inapp": h.get("inapp")}
            dev[key] = d
        d["hits"] += 1
        if h.get("vid"):
            d["vids"].add(h["vid"])
        if h.get("ip"):
            d["ips"].add(h["ip"])
        if h.get("code"):
            d["codes"].add(h["code"])
        ts = h.get("ts") or ""
        if not d["first"] or ts < d["first"]:
            d["first"] = ts
        if ts > d["last"]:
            d["last"] = ts

    out = []
    for d in dev.values():
        if d["hits"] < 2 and len(d["vids"]) < 2:
            continue
        d["vids"] = sorted(d["vids"])
        d["ips"] = sorted(d["ips"])
        d["codes"] = sorted(d["codes"])
        d["revisit"] = d["hits"] >= 2
        d["multi_vid"] = len(d["vids"]) >= 2
        d["verdict"] = ("同一端末・別訪問者" if d["multi_vid"]
                        else "同一端末の再訪")
        out.append(d)
    out.sort(key=lambda d: (not d["multi_vid"], -d["hits"], d["last"]))
    return out


def self_visits(vs):
    """同じ訪問者が何度も来ている場合の一覧。"""
    out = []
    for v in vs.values():
        if v.hits >= 2:
            out.append({"vid": v.vid, "label": label_of(v), "hits": v.hits,
                        "ips": sorted(v.ips), "last": v.last,
                        "verdict": "同一端末の再訪"})
    out.sort(key=lambda d: -d["hits"])
    return out


def analyze(db, code=None, window_h=6, min_score=0.35, group_th=GROUP_TH, limit=20000):
    vs = load(db, code, limit)
    vids = sorted(vs)

    pairs = []
    for a, b in combinations(vids, 2):
        score, sig, shared, near = _pair(vs[a], vs[b], window_h)
        if score < min_score:
            continue
        pairs.append({
            "a": a, "b": b,
            "alabel": label_of(vs[a]), "blabel": label_of(vs[b]),
            "score": score, "verdict": verdict(score),
            "signals": sorted(sig.keys()),
            "shared_ips": shared, "near": near,
        })
    pairs.sort(key=lambda p: -p["score"])

    parent = {v: v for v in vids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for p in pairs:
        if p["score"] >= group_th:
            union(p["a"], p["b"])

    buckets = defaultdict(list)
    for v in vids:
        buckets[find(v)].append(v)

    groups = []
    for _root, members in buckets.items():
        if len(members) < 2:
            continue
        sub = [p for p in pairs if p["a"] in members and p["b"] in members]
        if not sub:
            continue
        top = sub[0]["score"]
        g = {
            "members": [{"vid": m, "label": label_of(vs[m]),
                         "ips": sorted(vs[m].ips), "hits": vs[m].hits} for m in members],
            "score": top, "verdict": verdict(top),
            "shared_ips": sorted({ip for p in sub for ip in p["shared_ips"]}),
            "signals": sorted({s for p in sub for s in p["signals"]}),
            "pairs": sub,
            "pseudo": any(vs[m].pseudo for m in members),
        }
        g.update(_layout(members, vs, sub))
        groups.append(g)
    groups.sort(key=lambda g: (-g["score"], -len(g["members"])))

    devs = device_groups(db, code, limit)
    selfv = self_visits(vs)

    summary = {
        "visitors": len(vids),
        "hits": sum(v.hits for v in vs.values()),
        "pairs": len(pairs),
        "groups": len(groups),
        "same_device": sum(1 for p in pairs if "同一端末キー" in p["signals"]
                           or "同一フィンガープリント" in p["signals"]),
        "same_ip": sum(1 for p in pairs if any("IP" in s for s in p["signals"])),
        "devices": len(devs),
        "multi_vid_devices": sum(1 for d in devs if d["multi_vid"]),
        "revisits": len(selfv),
    }
    return {"pairs": pairs, "groups": groups, "summary": summary,
            "window": window_h, "devices": devs, "self": selfv}


def for_visitor(db, vid, window_h=6, min_score=0.30):
    res = analyze(db, window_h=window_h, min_score=min_score)
    return {"pairs": [p for p in res["pairs"] if vid in (p["a"], p["b"])],
            "window": window_h,
            "devices": [d for d in res["devices"] if vid in d["vids"]]}


def same_device_vids(db, vid, limit=200):
    """同じ端末（フィンガープリント）を使っている別の訪問者。"""
    fps = [r["fingerprint"] for r in db.q(
        "SELECT DISTINCT fingerprint FROM link_hits WHERE vid=? "
        "AND fingerprint IS NOT NULL AND fingerprint<>''", (vid,))]
    if not fps:
        return [], None
    ph = ",".join("?" * len(fps))
    args = tuple(fps)
    stat = db.q1(f"SELECT COUNT(*) c, MIN(ts) f, MAX(ts) l, COUNT(DISTINCT code) k "
                 f"FROM link_hits WHERE fingerprint IN ({ph}) AND is_bot=0", args)
    rows = db.q(f"SELECT DISTINCT vid, device, os, browser, inapp FROM link_hits "
                f"WHERE fingerprint IN ({ph}) AND vid<>? AND vid IS NOT NULL "
                f"AND is_bot=0", args + (vid,))
    return [dict(r) for r in rows], stat