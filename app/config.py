import os, yaml

_CFG = None

def load(path="config.yaml"):
    global _CFG
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    # 環境変数で上書き（AWSではSecrets的に使う）
    cfg.setdefault("instagram", {})
    cfg["instagram"]["username"] = os.getenv("IG_USER", cfg["instagram"].get("username"))
    cfg["instagram"]["password"] = os.getenv("IG_PASS", cfg["instagram"].get("password"))
    cfg.setdefault("web", {})
    cfg["web"]["user"] = os.getenv("WEB_USER", cfg["web"].get("user", "admin"))
    cfg["web"]["password"] = os.getenv("WEB_PASS", cfg["web"].get("password", "change_me"))
    _CFG = cfg
    return cfg

def get():
    return _CFG or load()