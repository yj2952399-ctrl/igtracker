"""バックグラウンド監視。全テナントを1分tickで回し、各自の設定間隔で実行する。"""
import os, time
from apscheduler.schedulers.background import BackgroundScheduler

from . import instagram as ig, tenancy, users, forensics
from .config import get as get_cfg

_sched = None
_last = {}


def run_bg(fn, *args, **kwargs):
    """呼び出し元スレッドのテナント文脈を引き継いでバックグラウンド実行。"""
    return tenancy.run_in_thread(tenancy.get_current(), fn, *args, **kwargs)


def _due(tenant, job, interval):
    k = (tenant, job)
    t = time.time()
    if t - _last.get(k, 0) < max(int(interval), 30):
        return False
    _last[k] = t
    return True


def _safe(fn, *args, label=""):
    try:
        return fn(*args)
    except Exception as e:
        try:
            tenancy.db.log("system", "job_error", {"job": label, "error": repr(e)})
        except Exception:
            pass


def _tick_tenant(u):
    tenancy.set_current(u)
    cfg = get_cfg()
    if not cfg["instagram"].get("username"):
        return
    m = cfg.get("monitor") or {}
    db = tenancy.db

    target_jobs = [
        ("relations", m.get("relations_interval_sec", 600), ig.save_relations),
        ("posts", m.get("posts_interval_sec", 600), ig.save_posts),
        ("stories", m.get("stories_interval_sec", 300), ig.save_stories),
        ("profile", m.get("profile_interval_sec", 900), ig.save_profile),
    ]
    for name, interval, fn in target_jobs:
        if not _due(u, name, interval):
            continue
        for t in db.targets(only_monitored=True):
            _safe(fn, db, t["user_id"], label=name)

    if m.get("watch_dms", True) and _due(u, "dms", m.get("dms_interval_sec", 180)):
        _safe(lambda: ig.save_dms(db), label="dms")

    if _due(u, "forensics", m.get("forensics_interval_sec", 3600)):
        _safe(lambda: forensics.snapshot_all(db, ig.client()), label="forensics")


def _tick():
    for u in users.list_usernames():
        try:
            _tick_tenant(u)
        except Exception as e:
            print(f"[scheduler] {u} tick失敗:", e)


def start():
    global _sched
    if _sched:
        return _sched
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_tick, "interval",
                  seconds=int(os.getenv("SCHED_TICK_SEC", "60")),
                  id="tick", max_instances=1, coalesce=True)
    sched.start()
    _sched = sched
    return sched