"""テナント分離。ユーザーごとに DB / 設定 / IGセッション / メディアを完全に分ける。"""
import os, re, threading, contextvars
from .database import DB

_current = contextvars.ContextVar("igt_tenant", default=None)

_lock = threading.RLock()
_dbs = {}

ROOT = os.getenv("TENANT_ROOT", "data/tenants")
_BAD = re.compile(r"[^a-z0-9_.-]")


def safe_name(user: str) -> str:
    u = (user or "").strip().lower()
    u = _BAD.sub("_", u)[:40]
    return u or "_"


def tenant_dir(user: str) -> str:
    d = os.path.join(ROOT, safe_name(user))
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "media"), exist_ok=True)
    return d


def db_for(user: str) -> DB:
    key = safe_name(user)
    with _lock:
        inst = _dbs.get(key)
        if inst is None:
            inst = DB(os.path.join(tenant_dir(key), "uraaka.db"))
            _dbs[key] = inst
        return inst


def set_current(user):
    _current.set(safe_name(user) if user else None)


def get_current():
    return _current.get()


class _DBProxy:
    """既存の db.q() / db.targets() ... を無改造で使えるようにする代理。"""

    def __getattr__(self, name):
        u = _current.get()
        if u is None:
            raise RuntimeError("tenant context is not set")
        return getattr(db_for(u), name)


db = _DBProxy()


def run_in_thread(user, fn, *args, **kwargs):
    """テナント文脈を引き継いだバックグラウンドスレッド。"""
    u = safe_name(user) if user else None

    def _run():
        _current.set(u)
        try:
            fn(*args, **kwargs)
        except Exception as e:
            try:
                db_for(u).log("system", "bg_error",
                              {"fn": getattr(fn, "__name__", "?"), "error": repr(e)})
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t