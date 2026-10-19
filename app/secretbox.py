"""IGパスワードを settings.json に平文で置かないための簡易ラッパ。
SECRET_KEY 未設定 or cryptography 未導入ならそのまま素通し。"""
import os, base64, hashlib

try:
    from cryptography.fernet import Fernet
    _HAVE = True
except Exception:
    _HAVE = False

_PREFIX = "enc:"


def _key():
    s = os.getenv("SECRET_KEY")
    if not s:
        return None
    return base64.urlsafe_b64encode(hashlib.sha256(s.encode()).digest())


def enc(v):
    k = _key()
    if not (k and _HAVE and v and not str(v).startswith(_PREFIX)):
        return v
    return _PREFIX + Fernet(k).encrypt(str(v).encode()).decode()


def dec(v):
    if not (isinstance(v, str) and v.startswith(_PREFIX)):
        return v
    k = _key()
    if not (k and _HAVE):
        return v
    try:
        return Fernet(k).decrypt(v[len(_PREFIX):].encode()).decode()
    except Exception:
        return v