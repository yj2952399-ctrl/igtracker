import os, yaml, base64

_CFG = None


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


def load(path="config.yaml"):
    global _CFG
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

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

    for p in (cfg["storage"]["db_path"], cfg["storage"]["media_dir"],
              cfg["instagram"]["session_file"]):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)

    _bootstrap_session(cfg["instagram"]["session_file"])
    _CFG = cfg
    return cfg


def get():
    return _CFG or load()