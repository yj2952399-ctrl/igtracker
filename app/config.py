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


def _env_fill(cfg, sec, key, env):
    """環境変数は「Web設定が空のときだけ」補完する"""
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


def load(path=_PATH):
    """優先順位: config.yaml < 環境変数(空欄補完) < data/settings.json(Web設定)

    ただし PORT / HOST だけは Render が渡す値が絶対。"""
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

    # 環境変数は「Web設定が空のときだけ」補完
    _env_fill(cfg, "instagram", "username", "IG_USER")
    _env_fill(cfg, "instagram", "password", "IG_PASS")
    _env_fill(cfg, "instagram", "session_b64", "IG_SESSION_B64")
    _env_fill(cfg, "instagram", "session_file", "SESSION_FILE")
    _env_fill(cfg, "web", "user", "WEB_USER")
    _env_fill(cfg, "web", "password", "WEB_PASS")
    _env_fill(cfg, "storage", "db_path", "DB_PATH")
    _env_fill(cfg, "storage", "media_dir", "MEDIA_DIR")

    cfg.setdefault("instagram", {})
    cfg["instagram"].setdefault("session_file", "session.json")
    cfg["instagram"].setdefault("session_b64", "")
    cfg["instagram"].setdefault("request_timeout", 30)
    cfg["instagram"].setdefault("max_retries", 3)

    cfg.setdefault("web", {})
    cfg["web"].setdefault("user", "admin")
    cfg["web"].setdefault("password", "change_me")

    cfg.setdefault("storage", {})
    cfg["storage"].setdefault("db_path", "data/uraaka.db")
    cfg["storage"].setdefault("media_dir", "data/media")

    # ロックアウト保険用に環境変数の値も保持（Web設定とどちらでも通す）
    cfg["web"]["_env_user"] = os.getenv("WEB_USER") or ""
    cfg["web"]["_env_pass"] = os.getenv("WEB_PASS") or ""

    t = _env_list("IG_TARGETS")
    if t and not cfg.get("targets"):
        cfg["targets"] = t
    c = _env_list("IG_CANDIDATES")
    if c and not cfg.get("candidates"):
        cfg["candidates"] = c
    cfg.setdefault("targets", [])
    cfg.setdefault("candidates", [])

    # 実行時は環境変数が絶対（Renderがポートを渡すため）
    cfg["web"]["host"] = os.getenv("HOST", cfg["web"].get("host", "0.0.0.0"))
    cfg["web"]["port"] = int(os.getenv("PORT", cfg["web"].get("port", 8000)))

    for p in (cfg["storage"]["db_path"], cfg["storage"]["media_dir"],
              cfg["instagram"]["session_file"]):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)

    # session.json が無く、b64 があれば復元（エフェメラル対策）
    if cfg["instagram"]["session_b64"] and not os.path.exists(cfg["instagram"]["session_file"]):
        if write_session_file(cfg["instagram"]["session_b64"], cfg["instagram"]["session_file"]):
            print("[config] session.json を復元")

    _CFG = cfg
    return cfg


def save_sections(data):
    """Webの設定画面から呼ぶ。data/settings.json に上書き保存。"""
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