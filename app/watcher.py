"""バックグラウンド監視。APSchedulerで差分を定期取得し続ける。"""
import threading
from apscheduler.schedulers.background import BackgroundScheduler

from . import instagram as ig
from . import forensics
from .config import get as get_cfg

_sched = None


def _job(name, fn, uid, db):
    try:
        fn(db, uid)
    except Exception as e:
        db.log(uid, "job_error", {"job": name, "error": str(e)})


def start(db):
    global _sched
    if _sched:
        return _sched
    cfg = get_cfg()
    m = cfg["monitor"]
    sched = BackgroundScheduler(timezone="UTC")

    def run_all(fn_name, fn):
        for t in db.targets(only_monitored=True):
            _job(fn_name, fn, t["user_id"], db)

    sched.add_job(lambda: run_all("relations", ig.save_relations), "interval",
                  seconds=m["relations_interval_sec"], id="relations", max_instances=1)
    sched.add_job(lambda: run_all("posts", ig.save_posts), "interval",
                  seconds=m["posts_interval_sec"], id="posts", max_instances=1)
    sched.add_job(lambda: run_all("stories", ig.save_stories), "interval",
                  seconds=m["stories_interval_sec"], id="stories", max_instances=1)
    sched.add_job(lambda: run_all("profile", ig.save_profile), "interval",
                  seconds=m["profile_interval_sec"], id="profile", max_instances=1)

    def dms_job():
        try:
            ig.save_dms(db)
        except Exception as e:
            db.log("me", "job_error", {"job": "dms", "error": str(e)})

    def forensic_job():
        try:
            forensics.snapshot_all(db, ig.client())
        except Exception as e:
            db.log("me", "job_error", {"job": "forensics", "error": str(e)})

    if m.get("watch_dms", True):
        sched.add_job(dms_job, "interval", seconds=m["dms_interval_sec"],
                      id="dms", max_instances=1)
    sched.add_job(forensic_job, "interval", seconds=m["forensics_interval_sec"],
                  id="forensics", max_instances=1)

    sched.start()
    _sched = sched
    return sched


def run_bg(fn, *args, **kwargs):
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()