"""app/siege.py — 指定サイト攻城。段階実行・保存・PIIエクスポート・画面。"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import threading

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from . import persist, siege_ops as ops, tenancy, users
from .tenancy import db

router = APIRouter()
READY = False

DDL = """
CREATE TABLE IF NOT EXISTS siege (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT,
  name TEXT, owner TEXT, ts TEXT, grade TEXT DEFAULT '', pwned INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS siege_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, sid INTEGER,
  stage TEXT, status TEXT, ts TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS siege_findings (id INTEGER PRIMARY KEY AUTOINCREMENT, sid INTEGER,
  stage TEXT, k TEXT, sev TEXT, title TEXT, detail TEXT, evidence TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS siege_loot (id INTEGER PRIMARY KEY AUTOINCREMENT, sid INTEGER,
  col TEXT, val TEXT, extra TEXT);
CREATE INDEX IF NOT EXISTS idx_sj ON siege_jobs(sid, id);
"""

STAGES = [("recon", "① 偵察"), ("vuln", "② 脆弱性"), ("exploit", "③ 悪用"),
          ("escalate", "④ 権限昇格"), ("loot", "⑤ 全PII窃取"), ("down", "⑥ 停止")]


def _ensure():
    global READY
    if READY:
        return
    with db.tx() as c:
        c.executescript(DDL)
    READY = True


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


async def auth(request: Request):
    from . import main
    return await main.auth(request)


@router.get("/siege", response_class=HTMLResponse)
def home(request: Request, u=Depends(auth)):
    _ensure()
    rows = db.q("SELECT * FROM siege WHERE owner=? ORDER BY id DESC LIMIT 100", (u,))
    return HTMLResponse(_page(rows=rows))


@router.post("/siege")
def create(url: str = Form(""), name: str = Form(""), u=Depends(auth)):
    _ensure()
    url = (url or "").strip()
    if not url:
        return RedirectResponse("/siege", 303)
    with db.tx() as c:
        cur = c.execute("INSERT INTO siege(url,name,owner,ts) VALUES(?,?,?,?)",
                        (url, (name or url)[:80], u, _now()))
        sid = int(cur.lastrowid)
    persist.push_user(u, force=True)
    return RedirectResponse(f"/siege/{sid}", 303)


@router.get("/siege/{sid}", response_class=HTMLResponse)
def detail(sid: int, request: Request, u=Depends(auth)):
    _ensure()
    t = db.q1("SELECT * FROM siege WHERE id=?", (sid,))
    if not t:
        raise HTTPException(404)
    fl = [dict(r) for r in db.q(
        "SELECT * FROM siege_findings WHERE sid=? ORDER BY id DESC LIMIT 400", (sid,))]
    jobs = [dict(r) for r in db.q(
        "SELECT * FROM siege_jobs WHERE sid=? ORDER BY id DESC LIMIT 40", (sid,))]
    loot = db.q1("SELECT COUNT(*) c FROM siege_loot WHERE sid=?", (sid,))
    return HTMLResponse(_page(t=t, fl=fl, jobs=jobs, loot=loot["c"], sid=sid))


@router.post("/siege/{sid}/run")
def run(sid: int, stage: str = Form("recon"), u=Depends(auth)):
    _ensure()
    t = db.q1("SELECT * FROM siege WHERE id=?", (sid,))
    if not t:
        raise HTTPException(404)
    with db.tx() as c:
        cur = c.execute("INSERT INTO siege_jobs(sid,stage,status,ts) VALUES(?,?,'running',?)",
                        (sid, stage, _now()))
        jid = int(cur.lastrowid)
    threading.Thread(target=_worker, args=(sid, jid, stage, t["url"], t["owner"]),
                     daemon=True).start()
    return RedirectResponse(f"/siege/{sid}", 303)


def _worker(sid, jid, stage, url, owner):
    tenancy.set_current(owner)
    try:
        vf = _last(sid, "vuln")
        ef = _last(sid, "exploit")
        if stage == "recon":
            res = ops.recon(url)
        elif stage == "vuln":
            res = ops.vuln(url, _last(sid, "recon"))
        elif stage == "exploit":
            res = ops.exploit(url, vf)
        elif stage == "escalate":
            res = ops.escalate(url, vf, ef)
        elif stage == "loot":
            res = ops.loot(url, ef)
        elif stage == "down":
            res = ops.down(url)
        else:
            res = {"findings": []}
        fl = res.get("findings") or []
        with db.tx() as c:
            for x in fl:
                c.execute("INSERT INTO siege_findings(sid,stage,k,sev,title,detail,evidence,url)"
                          " VALUES(?,?,?,?,?,?,?,?)",
                          (sid, stage, x.get("k", ""), x.get("sev", "info"),
                           x.get("title", ""), x.get("detail", ""),
                           x.get("evidence", ""), x.get("url", "")))
            if stage == "loot":
                for r in res.get("data") or []:
                    if not isinstance(r, dict):
                        continue
                    if "val" in r:
                        c.execute("INSERT INTO siege_loot(sid,col,val,extra) VALUES(?,?,?,?)",
                                  (sid, str(r.get("col", ""))[:60],
                                   str(r.get("val", ""))[:400], str(r.get("from", ""))[:200]))
                    else:
                        for k, v in r.items():
                            if isinstance(v, (str, int, float)):
                                c.execute("INSERT INTO siege_loot(sid,col,val,extra)"
                                          " VALUES(?,?,?,?)",
                                          (sid, str(k)[:60], str(v)[:400], ""))
            _s, g = ops.score(fl)
            pwn = 1 if (stage == "escalate" and res.get("pwned")) else 0
            if stage == "exploit" and res.get("admin"):
                pwn = 1
            c.execute("UPDATE siege SET grade=?, pwned=MAX(pwned,?) WHERE id=?", (g, pwn, sid))
            c.execute("UPDATE siege_jobs SET status='ok', result=? WHERE id=?",
                      (json.dumps({k: v for k, v in res.items() if k != "data"},
                                  ensure_ascii=False)[:60000], jid))
    except Exception as e:
        with db.tx() as c:
            c.execute("UPDATE siege_jobs SET status='error', result=? WHERE id=?",
                      (repr(e)[:400], jid))
    try:
        persist.push_user(owner, force=True)
    except Exception:
        pass


def _last(sid, stage):
    r = db.q1("SELECT result FROM siege_jobs WHERE sid=? AND stage=? AND status='ok'"
              " ORDER BY id DESC LIMIT 1", (sid, stage))
    if not r:
        return {}
    try:
        return json.loads(r["result"] or "{}")
    except Exception:
        return {}


@router.get("/siege/{sid}/loot.csv")
def loot_csv(sid: int, u=Depends(auth)):
    _ensure()
    rows = db.q("SELECT col,val,extra FROM siege_loot WHERE sid=? ORDER BY id", (sid,))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["col", "value", "from"])
    for r in rows:
        w.writerow([r["col"], r["val"], r["extra"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="siege-{sid}.csv"'})


@router.get("/siege/{sid}/job/{jid}")
def job(sid: int, jid: int, u=Depends(auth)):
    r = db.q1("SELECT * FROM siege_jobs WHERE id=? AND sid=?", (jid, sid))
    if not r:
        raise HTTPException(404)
    return JSONResponse(dict(r))


@router.post("/siege/{sid}/delete")
def delete(sid: int, u=Depends(auth)):
    _ensure()
    with db.tx() as c:
        c.execute("DELETE FROM siege WHERE id=?", (sid,))
        for t in ("siege_jobs", "siege_findings", "siege_loot"):
            c.execute(f"DELETE FROM {t} WHERE sid=?", (sid,))
    persist.push_user(u, force=True)
    return RedirectResponse("/siege", 303)


def _page(rows=None, t=None, fl=None, jobs=None, loot=0, sid=None):
    if t:
        head = (f"<h1>{t['name']}</h1><div class=dim>{t['url']} / 評価 {t['grade'] or '-'}"
                f"{' / <b class=bad>昇格済</b>' if t['pwned'] else ''} / loot {loot}件</div>")
        bar = "<div class=bar>" + "".join(
            f"<form method=post action='/siege/{sid}/run'>"
            f"<input type=hidden name=stage value='{k}'><button>{n}</button></form>"
            for k, n in STAGES) + f"<a href='/siege/{sid}/loot.csv'>CSV</a></div>"
        his = "<h3>履歴</h3>" + "".join(
            f"<div class=card>{j['ts'][:19]} {j['stage']} <b>{j['status']}</b></div>"
            for j in (jobs or []))
        det = "<h3>検出</h3>" + "".join(
            f"<div class=card><span class=sev-{x['sev']}>[{x['sev']}]</span> {x['title']}"
            f" <code>{(x['evidence'] or '')[:90]}</code>"
            f"<div class=dim>{x['detail']}</div></div>" for x in (fl or []))
        return _wrap(head + bar + his + det)
    body = ("<h1>攻城</h1><form method=post action='/siege' class=card>"
            "<input name=url placeholder='https://target.example' style='width:60%'>"
            "<input name=name placeholder='名前'><button>追加</button></form>")
    for r in rows or []:
        body += (f"<div class=card><a href='/siege/{r['id']}'>{r['name']}</a>"
                 f" <span class=dim>{r['url']} / {r['grade'] or '-'}"
                 f"{' / 昇格済' if r['pwned'] else ''}</span></div>")
    return _wrap(body)


def _wrap(body):
    return f"""<!doctype html><meta charset=utf-8><title>攻城</title><style>
body{{background:#0b0e14;color:#e6e9ef;font:14px/1.7 system-ui,sans-serif;padding:20px;
max-width:900px;margin:auto}}a{{color:#7fb3ff}}.dim{{color:#8b93a7;font-size:12px}}
.card{{background:#151922;border:1px solid #232936;border-radius:8px;padding:10px;margin:8px 0}}
button{{background:#4c8dff;color:#fff;border:0;border-radius:6px;padding:6px 12px;cursor:pointer}}
input{{background:#0f1218;color:#e6e9ef;border:1px solid #232936;border-radius:6px;padding:6px}}
.bar{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}}.bad{{color:#ff6b6b}}
code{{color:#9fe0a0}}.sev-critical{{color:#ff5c5c}}.sev-high{{color:#ffa04c}}
.sev-medium{{color:#ffd84c}}.sev-low{{color:#8b93a7}}
</style>{body}"""