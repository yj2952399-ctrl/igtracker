"""app/roles.py — 役職（ロール）と権限の定義・判定・保存。

役職の上下（強い順）:
    admin(管理者) > deputy(副官) > upper(上層幹部) > mid(中層幹部)
    > lower(下層幹部) > user(ユーザー)

- 「ルート管理者」= 環境変数 ADMIN_USER のアカウント（未設定なら最古の管理者）。
  ルートは権限チェックを常に素通りし、下位の役職からは
  削除・降格・停止・PW再設定ができない。
- 権限の既定は DEFAULT。roles.json の差分で上書きされ、
  管理コンソール（/console/roles）から変更できる。
- 循環 import を避けるため、このモジュールは app 内の他モジュールに依存しない。
- _GRANT_IF_ABSENT: 後から足した権限キーは、保存済み roles.json に
  一度も出てこない間だけ既定に追従させる（新機能が全員に配られる）。
  管理者が権限マトリクスを保存すると固定される。
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional, Set

ROLES: List[str] = ["admin", "deputy", "upper", "mid", "lower", "user"]

LABELS: Dict[str, str] = {
    "admin": "管理者",
    "deputy": "副官",
    "upper": "上層幹部",
    "mid": "中層幹部",
    "lower": "下層幹部",
    "user": "ユーザー",
}

LEVEL: Dict[str, int] = {
    "admin": 60, "deputy": 50, "upper": 40, "mid": 30, "lower": 20, "user": 10,
}

# (key, 表示名, 説明)
PERMS: List[Dict[str, str]] = [
    {"key": "console.view", "label": "コンソールを見る",
     "desc": "役職コンソール／管理コンソールにログインできる"},
    {"key": "users.view", "label": "ユーザー一覧を見る",
     "desc": "登録者・状態・容量・最終ログインの一覧"},
    {"key": "users.create", "label": "ユーザーを作る",
     "desc": "自分より下の役職を新規作成"},
    {"key": "users.setpw", "label": "利用者PWを再設定",
     "desc": "対象のログインパスワードを入れ替える"},
    {"key": "users.setadminpw", "label": "コンソールPWを設定",
     "desc": "対象の管理コンソール用パスワードを設定"},
    {"key": "users.disable", "label": "停止・再開",
     "desc": "対象のログインを止める／戻す"},
    {"key": "users.delete", "label": "ユーザー削除",
     "desc": "アカウントを消す（データは残す）"},
    {"key": "users.purge", "label": "データごと削除",
     "desc": "テナント実体フォルダも一緒に消す"},
    {"key": "users.role", "label": "役職変更",
     "desc": "自分より下の役職へ昇格・降格"},
    {"key": "view_as", "label": "中を見る（なりすまし）",
     "desc": "他ユーザーの画面をそのまま覗く"},
    {"key": "audit.view", "label": "監査ログ",
     "desc": "操作履歴の閲覧"},
    {"key": "lockdown", "label": "封鎖パネル",
     "desc": "ログイン／新規登録の一時封鎖"},
    {"key": "backup.all", "label": "全ユーザー退避",
     "desc": "全テナントのバックアップ操作"},
    {"key": "tenants.view", "label": "容量・統計",
     "desc": "テナントの容量や件数の表示"},
    {"key": "roles.edit", "label": "権限マトリクス編集",
     "desc": "この表そのものを書き換える"},
]

FEATURES: List[str] = [
    "feature.dash", "feature.identity", "feature.sns", "feature.avatars",
    "feature.gravatar", "feature.links", "feature.hijack", "feature.virus",
    "feature.usb", "feature.gps", "feature.tracks", "feature.visitors",
    "feature.together", "feature.campaigns", "feature.tools", "feature.targets",
    "feature.runs", "feature.accounts", "feature.activity", "feature.dms",
    "feature.dm", "feature.chat", "feature.settings", "feature.snsx",
]

PERMS += [{"key": k, "label": "機能: " + k.split(".", 1)[1],
           "desc": "ナビの該当メニューを出す"} for k in FEATURES]

_BASE: List[str] = ["console.view"] + FEATURES

# 後から足したキー。保存済み roles.json に現れない間だけ既定に追従させる。
_GRANT_IF_ABSENT: List[str] = ["feature.dm"]

# 既定の権限（役職 → 許可キー）
DEFAULT: Dict[str, List[str]] = {
    "user": sorted(set(_BASE)),
    "lower": sorted(set(_BASE + ["users.view"])),
    "mid": sorted(set(_BASE + ["users.view", "audit.view", "view_as"])),
    "upper": sorted(set(_BASE + ["users.view", "audit.view", "view_as",
                                 "users.create", "users.setpw", "users.disable",
                                 "lockdown", "backup.all"])),
    "deputy": sorted(set(_BASE + ["users.view", "audit.view", "view_as",
                                  "users.create", "users.setpw", "users.disable",
                                  "lockdown", "backup.all", "users.role",
                                  "users.setadminpw", "users.delete",
                                  "tenants.view"])),
    "admin": sorted({p["key"] for p in PERMS}),
}

_lock = threading.RLock()
_PATH: Optional[str] = None
_cache: Dict[str, Any] = {"mtime": -2, "data": None}


# ---------------- 保存先 ----------------

def _path() -> str:
    global _PATH
    if _PATH:
        return _PATH
    base = None
    try:
        from . import tenancy
        base = getattr(tenancy, "ROOT", None)
    except Exception:
        base = None
    if not base:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    base = os.path.abspath(base)
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = os.path.abspath(os.path.dirname(__file__))
    _PATH = os.path.join(base, "roles.json")
    return _PATH


def _bust() -> None:
    with _lock:
        _cache["mtime"] = -2
        _cache["data"] = None


# ---------------- 読み書き ----------------

def load() -> Dict[str, Set[str]]:
    """役職 → 許可キー集合（既定に roles.json の差分を重ねたもの）。"""
    p = _path()
    try:
        mt = os.path.getmtime(p)
    except OSError:
        mt = -1
    with _lock:
        if _cache["data"] is not None and _cache["mtime"] == mt:
            return _cache["data"]

    out: Dict[str, Set[str]] = {r: set(DEFAULT.get(r, [])) for r in ROLES}
    raw_seen: Set[str] = set()
    if mt != -1:
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            over = (raw or {}).get("perms") or {}
            if isinstance(over, dict):
                for r, keys in over.items():
                    if r in out and isinstance(keys, list):
                        out[r] = {str(k) for k in keys if str(k)}
                        raw_seen |= out[r]
        except Exception:
            pass

    # 後から足したキーは、保存ファイルに一度も出てこない間だけ既定に追従
    for k in _GRANT_IF_ABSENT:
        if k in raw_seen:
            continue
        for r in ROLES:
            if k in DEFAULT.get(r, []):
                out[r].add(k)

    with _lock:
        _cache["mtime"] = mt
        _cache["data"] = out
    return out


def save_perms(mapping: Dict[str, List[str]]) -> None:
    p = _path()
    doc = {"perms": {r: sorted({str(k) for k in mapping.get(r, []) if str(k)})
                     for r in ROLES}}
    try:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass
    _bust()


def reset() -> None:
    """roles.json を消して既定に戻す。"""
    try:
        os.remove(_path())
    except Exception:
        pass
    _bust()


# ---------------- 判定 ----------------

def is_known(role: str) -> bool:
    return role in ROLES


def label(key: str) -> str:
    if key in LABELS:
        return LABELS[key]
    for p in PERMS:
        if p["key"] == key:
            return p["label"]
    return key


def level(role: str) -> int:
    return LEVEL.get(role or "", 0)


def has(role: str, perm: str) -> bool:
    if not role:
        return False
    return perm in load().get(role, set())


def perms_of(role: Optional[str]) -> Dict[str, bool]:
    """テンプレート用（全キー → bool）。role が None なら全部 False。"""
    allow = load().get(role or "", set()) if role else set()
    return {p["key"]: (p["key"] in allow) for p in PERMS}


def can_act(actor_role: str, target_role: str, actor_is_root: bool = False,
            target_is_root: bool = False, same: bool = False) -> bool:
    """actor が target を操作（削除・降格・停止・PW変更）できるか。"""
    if actor_is_root:
        return True
    if target_is_root:
        return False
    if same:
        return True
    return level(actor_role) > level(target_role)


def assignable(actor_role: str, actor_is_root: bool = False) -> List[str]:
    """actor が付与できる役職（強い順）。自分と同格は付与できない。"""
    if actor_is_root:
        return list(ROLES)
    if actor_role == "admin":
        return [r for r in ROLES if r != "admin"]
    lv = level(actor_role)
    return [r for r in ROLES if level(r) < lv]


def can_assign(actor_role: str, new_role: str, actor_is_root: bool = False) -> bool:
    return new_role in assignable(actor_role, actor_is_root)