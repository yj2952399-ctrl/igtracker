import os, json, copy, base64, threading, yaml
from . import tenancy, secretbox

_CFG = {}
_LOCK = threading.RLock()
_PATH = "config.yaml"


def _settings_path(user=None):
    if user:
        return os.path.join(tenancy.tenant_dir(user), "settings.json")
    return os.getenv("SETTINGS_FILE", "data/settings.json")


def _key(user):
    return tenancy.safe_name(user) if user else "__base__"


def _overlay(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _overlay(base[k], v)
        else:
            base[k] = v
    return base


def _env_fill(cfg, sec, key, env):
    v = os.getenv(env)
    if not v:
        return
    cfg.setdefault(sec, {})
    if not cfg[sec].get(key):
        cfg[sec][key] = v


def _env_list(name):
    v = os.getenv(name)
    if not v:
        return None
    return [x.strip().lstrip("@") for x in v.replace(",", "\n").split() if x.strip()]


def write_session_file(b64, path):
    if not b64:
        return False
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return True
    except Exception as e:
        print("[config] session書込失敗:", e)
        return False


def raw(path=_PATH):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load(user=None):
    """優先順位: config.yaml < 環境変数(空欄補完) < <tenant>/settings.json"""
    key = _key(user)
    with _LOCK:
        if key in _CFG:
            return _CFG[key]

    cfg = copy.deepcopy(raw(_PATH))
    tdir = tenancy.tenant_dir(user) if user else None

    sf = _settings_path(user)
    if os.path.exists(sf):
        try:
            with open(sf, encoding="utf-8") as f:
                _overlay(cfg, json.load(f) or {})
        except Exception as e:
            print("[config] settings.json 読込失敗:", e)

    _env_fill(cfg, "instagram", "username", "IG_USER")
    _env_fill(cfg, "instagram", "password", "IG_PASS")
    _env_fill(cfg, "instagram", "session_b64", "IG_SESSION_B64")
    _env_fill(cfg, "instagram", "session_file", "SESSION_FILE")

    cfg.setdefault("instagram", {})
    cfg["instagram"].setdefault("session_file", "session.json")
    cfg["instagram"].setdefault("session_b64", "")
    cfg["instagram"].setdefault("request_timeout", 30)
    cfg["instagram"].setdefault("max_retries", 3)
    cfg["instagram"]["password"] = secretbox.dec(cfg["instagram"].get("password") or "")

    cfg.setdefault("storage", {})
    cfg["storage"].setdefault("db_path", "data/uraaka.db")
    cfg["storage"].setdefault("media_dir", "data/media")

    cfg.setdefault("web", {})
    cfg["web"].setdefault("host", "0.0.0.0")
    cfg["web"].setdefault("port", 8000)

    if tdir:
        cfg["storage"]["db_path"] = os.path.join(tdir, "uraaka.db")
        cfg["storage"]["media_dir"] = os.path.join(tdir, "media")
        cfg["instagram"]["session_file"] = os.path.join(tdir, "session.json")

    t = _env_list("IG_TARGETS")
    if t and not cfg.get("targets"):
        cfg["targets"] = t
    c = _env_list("IG_CANDIDATES")
    if c and not cfg.get("candidates"):
        cfg["candidates"] = c
    cfg.setdefault("targets", [])
    cfg.setdefault("candidates", [])

    cfg["web"]["host"] = os.getenv("HOST", cfg["web"]["host"])
    cfg["web"]["port"] = int(os.getenv("PORT", cfg["web"]["port"]))

    for p in (cfg["storage"]["db_path"], cfg["storage"]["media_dir"],
              cfg["instagram"]["session_file"]):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)

    if cfg["instagram"]["session_b64"] and not os.path.exists(cfg["instagram"]["session_file"]):
        if write_session_file(cfg["instagram"]["session_b64"], cfg["instagram"]["session_file"]):
            print(f"[config] {key}: session.json を復元")

    with _LOCK:
        _CFG[key] = cfg
    return cfg


def save_sections(data, user=None):
    user = user if user is not None else tenancy.get_current()
    sf = _settings_path(user)
    d = os.path.dirname(sf)
    if d:
        os.makedirs(d, exist_ok=True)
    cur = {}
    if os.path.exists(sf):
        try:
            with open(sf, encoding="utf-8") as f:
                cur = json.load(f) or {}
        except Exception:
            cur = {}
    data = copy.deepcopy(data)
    ig = data.get("instagram")
    if isinstance(ig, dict) and "password" in ig:
        ig["password"] = secretbox.enc(ig.get("password") or "")
    _overlay(cur, data)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    with _LOCK:
        _CFG.pop(_key(user), None)
    return cur


def get():
    return load(tenancy.get_current())