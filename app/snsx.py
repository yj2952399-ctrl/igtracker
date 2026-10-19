"""マルチSNSプロフィール監視。Instagram以外のSNSにも同じ追跡を広げる。

- 認証は main.auth を遅延importして流用（循環import回避）
- 保存はテナントディレクトリ内のJSON（DBスキーマ変更なし）
- 対応SNSは platforms.py のレジストリに集約

有効化するには main.py に2行:
    from . import snsx
    app.include_router(snsx.router)
"""
from __future__ import annotations

import html
import json
import os
import secrets
import threading
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import platforms

router = APIRouter(prefix="/snsx")

WATCH = "snsx.json"
HIST = "snsx_history.json"
MAX_HIST = 500
AUTO_MIN = 30 * 60          # これより古い項目はページ表示時に裏で更新
_LOCK = threading.RLock()
_RUNNING = set()


# ---------- 認証 / 保存 ----------

async def _auth(request: Request):
    from . import main
    return await main.auth(request)


def _dir(user):
    from . import tenancy
    return tenancy.tenant_dir(user)


def _load(user, name, default):
    try:
        with open(os.path.join(_dir(user), name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(user, name, data):
    p = os.path.join(_dir(user), name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _items(user):
    v = _load(user, WATCH, [])
    return v if isinstance(v, list) else []


def _history(user):
    v = _load(user, HIST, {})
    return v if isinstance(v, dict) else {}


# ---------- 取得 ----------

def _snap(res):
    return {"ts": time.time(), "exists": bool(res.get("exists")),
            "followers": res.get("followers"), "following": res.get("following"),
            "posts": res.get("posts"), "full_name": res.get("full_name"),
            "bio": res.get("bio"), "avatar": res.get("avatar"),
            "url": res.get("url")}


def _fetch_into(user, item):
    try:
        res = platforms.fetch(item["platform"], item["handle"])
        snap = _snap(res)
        with _LOCK:
            h = _history(user)
            lst = h.setdefault(item["id"], [])
            lst.append(snap)
            del lst[:-MAX_HIST]
            _save(user, HIST, h)
        item["last_ts"] = snap["ts"]
        return snap, None
    except Exception as e:
        return None, repr(e)


def _refresh_all(user, only_stale=False):
    items = _items(user)
    changed = False
    for it in items:
        if only_stale and it.get("last_ts") and time.time() - it["last_ts"] < AUTO_MIN:
            continue
        _fetch_into(user, it)
        changed = True
    if changed:
        _save(user, WATCH, items)
    return changed


def _spawn_refresh(user):
    with _LOCK:
        if user in _RUNNING:
            return
        _RUNNING.add(user)

    def run():
        try:
            _refresh_all(user, only_stale=True)
        finally:
            with _LOCK:
                _RUNNING.discard(user)

    threading.Thread(target=run, daemon=True).start()


# ---------- 描画 ----------

CSS = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 system-ui,-apple-system,"Hiragino Sans",sans-serif;color:#111;background:#fff}
@media(prefers-color-scheme:dark){body{color:#eaeaea;background:#141414}}
header{display:flex;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid #8884}
header a{color:inherit;opacity:.7;text-decoration:none}
header a:hover{opacity:1}
main{padding:16px;max-width:980px;margin:0 auto}
h1{font-size:18px;margin:0 0 14px}
form.add{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
select,input,button{font:inherit;padding:7px 9px;border:1px solid #8886;border-radius:7px;background:transparent;color:inherit}
button{cursor:pointer}
button:hover{background:#8882}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #8883;vertical-align:middle}
th{font-weight:500;opacity:.65}
.num{font-variant-numeric:tabular-nums}
.up{color:#2a8}.down{color:#d55}
.muted{opacity:.6}
.msg{padding:8px 10px;border-radius:7px;background:#8882;margin-bottom:12px}
a.p{color:inherit}
svg{display:block}
"""


def esc(s):
    return html.escape("" if s is None else str(s))


def _page(title, body, msg=""):
    m = '<div class="msg">' + esc(msg) + '</div>' if msg else ""
    return HTMLResponse(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>' + esc(title) + '</title><style>' + CSS + '</style></head><body>'
        '<header><a href="/">← ダッシュボード</a>'
        '<span class="muted">' + esc(title) + '</span></header>'
        '<main>' + m + body + '</main></body></html>')


def _delta(cur, prev):
    if cur is None or prev is None:
        return ""
    d = cur - prev
    if d == 0:
        return ' <span class="muted">±0</span>'
    cls = "up" if d > 0 else "down"
    return ' <span class="%s">%s%d</span>' % (cls, "+" if d > 0 else "", d)


def _spark(vals, w=90, h=22):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if len(vals) < 2:
        return '<span class="muted">—</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = []
    for i, v in enumerate(vals):
        x = round(i * (w - 2) / (len(vals) - 1), 1) + 1
        y = round(h - 2 - (v - lo) * (h - 4) / rng, 1) + 1
        pts.append("%s,%s" % (x, y))
    p = " ".join(pts)
    return ('<svg width="%d" height="%d"><polyline fill="none" stroke="currentColor" '
            'stroke-width="1.5" points="%s"/></svg>' % (w, h, p))


def _select(name="platform"):
    o = "".join('<option value="%s">%s</option>' % (esc(p), esc(platforms.LABELS[p]))
                for p in platforms.PLATFORMS)
    return '<select name="%s">%s</select>' % (name, o)


# ---------- ルート ----------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, u=Depends(_auth), msg: str = "", err: str = ""):
    _spawn_refresh(u)
    items = _items(u)
    hist = _history(u)
    rows = []
    for it in items:
        lst = hist.get(it["id"], [])
        cur = lst[-1] if lst else None
        prev = lst[-2] if len(lst) > 1 else None
        vals = [s.get("followers") for s in lst if s.get("followers") is not None]
        if cur is None:
            stat = '<span class="muted">未取得</span>'
        else:
            f = cur.get("followers")
            stat = '<span class="num">%s</span>%s' % (
                f if f is not None else "-", _delta(f, (prev or {}).get("followers")))
        url = it.get("url") or platforms.profile_url(it["platform"], it["handle"])
        note = '<div class="muted">%s</div>' % esc(it.get("note")) if it.get("note") else ""
        rows.append(
            "<tr>"
            "<td>%s</td>" % esc(platforms.LABELS.get(it["platform"], it["platform"])) +
            '<td><a class="p" href="%s" target="_blank" rel="noopener">%s</a>%s</td>'
            % (esc(url), esc(it["handle"]), note) +
            "<td>%s</td>" % stat +
            '<td class="num">%s</td>' % (esc(cur.get("posts")) if cur else "-") +
            "<td>%s</td>" % _spark(vals) +
            '<td><a href="/snsx/%s">詳細</a></td>' % esc(it["id"]) +
            '<td><form method="post" action="/snsx/%s/refresh" style="display:inline">'
            "<button>更新</button></form> "
            '<form method="post" action="/snsx/%s/delete" style="display:inline">'
            "<button>削除</button></form></td>" % (esc(it["id"]), esc(it["id"])) +
            "</tr>")
    table = ("<table><thead><tr><th>SNS</th><th>アカウント</th><th>フォロワー</th>"
             "<th>投稿</th><th>推移</th><th></th><th></th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>") if rows else \
            '<p class="muted">まだ登録がありません。下のフォームから追加してください。</p>'
    body = ("<h1>マルチSNS 監視</h1>"
            '<form class="add" method="post" action="/snsx/add">' + _select() +
            '<input name="handle" placeholder="ユーザー名 / user@instance" required>'
            '<input name="note" placeholder="メモ（任意）">'
            "<button>追加</button></form>"
            '<form method="post" action="/snsx/refresh" style="margin-bottom:16px">'
            "<button>全部更新</button></form>" + table)
    return _page("マルチSNS", body, msg or err)


@router.get("/api", response_class=JSONResponse)
async def api(u=Depends(_auth)):
    hist = _history(u)
    out = []
    for it in _items(u):
        lst = hist.get(it["id"], [])
        out.append({"platform": it["platform"], "handle": it["handle"],
                    "note": it.get("note"), "latest": lst[-1] if lst else None,
                    "points": len(lst)})
    return JSONResponse({"items": out})


@router.post("/add")
async def add(u=Depends(_auth), platform: str = Form(""), handle: str = Form(""),
              note: str = Form("")):
    platform = platform.strip()
    handle = handle.strip().lstrip("@")
    if platform not in platforms.REGISTRY:
        return RedirectResponse("/snsx?err=" + _q("SNSを選んでください"), 303)
    if not handle:
        return RedirectResponse("/snsx?err=" + _q("ユーザー名を入れてください"), 303)
    items = _items(u)
    if any(i["platform"] == platform and i["handle"].lower() == handle.lower() for i in items):
        return RedirectResponse("/snsx?err=" + _q("すでに登録済みです"), 303)
    item = {"id": secrets.token_hex(4), "platform": platform, "handle": handle,
            "note": note.strip(), "created_at": time.time()}
    _fetch_into(u, item)
    items.append(item)
    _save(u, WATCH, items)
    return RedirectResponse("/snsx?msg=" + _q("追加しました"), 303)


@router.post("/refresh")
async def refresh(u=Depends(_auth)):
    _refresh_all(u)
    return RedirectResponse("/snsx?msg=" + _q("更新しました"), 303)


@router.get("/{wid}", response_class=HTMLResponse)
async def detail(wid: str, u=Depends(_auth)):
    items = _items(u)
    item = next((i for i in items if i["id"] == wid), None)
    if not item:
        return RedirectResponse("/snsx?err=" + _q("見つかりません"), 303)
    lst = _history(u).get(wid, [])
    rows = []
    for s in reversed(lst[-50:]):
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["ts"]))
        rows.append("<tr><td>%s</td><td class=\"num\">%s</td><td class=\"num\">%s</td>"
                    "<td class=\"num\">%s</td></tr>"
                    % (esc(ts), esc(s.get("followers")), esc(s.get("following")),
                       esc(s.get("posts"))))
    vals = [s.get("followers") for s in lst if s.get("followers") is not None]
    url = item.get("url") or platforms.profile_url(item["platform"], item["handle"])
    body = ("<h1>%s / %s</h1>" % (esc(platforms.LABELS.get(item["platform"], item["platform"])),
                                  esc(item["handle"])) +
            '<p><a href="%s" target="_blank" rel="noopener">プロフィールを開く</a></p>' % esc(url) +
            "<p>%s</p>" % _spark(vals, 300, 60) +
            "<table><thead><tr><th>日時</th><th>フォロワー</th><th>フォロー</th><th>投稿</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>" +
            '<p><a href="/snsx">← 一覧</a></p>')
    return _page("%s / %s" % (item["platform"], item["handle"]), body)


@router.post("/{wid}/refresh")
async def refresh_one(wid: str, u=Depends(_auth)):
    items = _items(u)
    item = next((i for i in items if i["id"] == wid), None)
    if item:
        _fetch_into(u, item)
        _save(u, WATCH, items)
    return RedirectResponse("/snsx?msg=" + _q("更新しました"), 303)


@router.post("/{wid}/delete")
async def delete(wid: str, u=Depends(_auth)):
    items = [i for i in _items(u) if i["id"] != wid]
    _save(u, WATCH, items)
    return RedirectResponse("/snsx?msg=" + _q("削除しました"), 303)


def _q(s):
    from urllib.parse import quote
    return quote(s)