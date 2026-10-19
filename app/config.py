import os, json, copy, base64, yaml

_CFG = None
_PATH = "config.yaml"


def _settings_path():
    return os.getenv("SETTINGS_FILE", "data/settings.json")


def _overlay(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _overlay(base[k], v)
        else:
            base[k] = v
    return base


def _bootstrap_session(path):
    """IG_SESSION_B64 から session.json を復元（エフェメラル対策）"""
    b64 = os.getenv("IG_SESSION_B64")
    if b64 and not os.path.exists(path):
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            print("[config] session.json を環境変数から復元")
        except Exception as e:
            print("[config] session復元失敗:", e)


def raw(path=_PATH):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _env_list(name):
    v = os.getenv(name)
    if not v:
        return None
    return [x.strip().lstrip("@") for x in v.replace(",", "\n").split() if x.strip()]


def load(path=_PATH):
    """config.yaml -> data/settings.json -> 環境変数 の順で上書きして返す。"""
    global _CFG
    if _CFG is not None:
        return _CFG
    cfg = copy.deepcopy(raw(path))

    sf = _settings_path()
    if os.path.exists(sf):
        try:
            with open(sf, encoding="utf-8") as f:
                _overlay(cfg, json.load(f) or {})
        except Exception as e:
            print("[config] settings.json 読込失敗:", e)

    cfg.setdefault("instagram", {})
    cfg["instagram"]["username"] = os.getenv("IG_USER", cfg["instagram"].get("username"))
    cfg["instagram"]["password"] = os.getenv("IG_PASS", cfg["instagram"].get("password"))
    cfg["instagram"]["session_file"] = os.getenv(
        "SESSION_FILE", cfg["instagram"].get("session_file", "session.json"))

    cfg.setdefault("web", {})
    cfg["web"]["user"] = os.getenv("WEB_USER", cfg["web"].get("user", "admin"))
    cfg["web"]["password"] = os.getenv("WEB_PASS", cfg["web"].get("password", "change_me"))
    cfg["web"]["host"] = os.getenv("HOST", cfg["web"].get("host", "0.0.0.0"))
    cfg["web"]["port"] = int(os.getenv("PORT", cfg["web"].get("port", 8000)))

    cfg.setdefault("storage", {})
    cfg["storage"]["db_path"] = os.getenv("DB_PATH", cfg["storage"].get("db_path", "data/uraaka.db"))
    cfg["storage"]["media_dir"] = os.getenv("MEDIA_DIR", cfg["storage"].get("media_dir", "data/media"))

    t = _env_list("IG_TARGETS")
    if t is not None:
        cfg["targets"] = t
    c = _env_list("IG_CANDIDATES")
    if c is not None:
        cfg["candidates"] = c

    for p in (cfg["storage"]["db_path"], cfg["storage"]["media_dir"],
              cfg["instagram"]["session_file"]):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)

    _bootstrap_session(cfg["instagram"]["session_file"])
    _CFG = cfg
    return cfg


def save_sections(data):
    """Webの設定画面から呼ぶ。data/settings.json に上書き保存（リポジトリは汚さない）。"""
    global _CFG
    sf = _settings_path()
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
    _overlay(cur, data)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    _CFG = None
    return cur


def get():
    return load()