"""クイズ作成・編集ルーター。作成直後に編集画面へ着地させる。

main.py より先に include するので /links/add はこちらが優先される。

v2:
  ・Request を starlette から明示 import（文字列注釈の解決を確実にする）
  ・links_add から未使用の request 引数を削除（422 の温床）
  ・yesno / scale の選択肢自動生成
"""
from __future__ import annotations

import json
from urllib.parse import quote

from starlette.requests import Request
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from .tenancy import db

router = APIRouter()

QTYPES = ("choice", "multi", "text", "long", "yesno", "scale", "number", "date")
QTYPE_LABEL = {
    "choice": "単一選択", "multi": "複数選択", "text": "自由記述（1行）",
    "long": "自由記述（長文）", "yesno": "はい / いいえ",
    "scale": "5段階評価", "number": "数値", "date": "日付",
}
KEYED = ("choice", "multi", "yesno", "scale")


def _m():
    from . import main
    return main


async def _auth(request: Request):
    return await _m().auth(request)


def _parse_options(raw: str):
    """`ラベル|キー|回答後に出す文` を1行1件で解釈。"""
    rows = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        rows.append({"label": parts[0][:120],
                     "key": (parts[1] if len(parts) > 1 and parts[1] else str(len(rows))),
                     "reveal": (parts[2] if len(parts) > 2 else "")[:300]})
    return rows[:30]


def _opts_text(rows) -> str:
    try:
        return "\n".join(f"{o.get('label', '')}|{o.get('key', '')}|{o.get('reveal', '')}"
                         for o in json.loads(rows or "[]"))
    except Exception:
        return ""


def _link(code: str):
    link = db.link_get(code)
    if not link:
        raise HTTPException(404)
    return link


def _fill(qtype: str, rows):
    """yesno / scale の選択肢を自動生成。"""
    if qtype == "yesno" and not rows:
        return [{"label": "はい", "key": "1", "reveal": ""},
                {"label": "いいえ", "key": "0", "reveal": ""}]
    if qtype == "scale" and not rows:
        return [{"label": str(i), "key": str(i), "reveal": ""} for i in range(1, 6)]
    return rows


# ---------- 作成（quiz は編集画面へ直行） ----------

@router.post("/links/add")
def links_add(name: str = Form(""), dest: str = Form(""), note: str = Form(""),
              mode: str = Form("page"), u=Depends(_auth)):
    code, m = _m()._create_link(name, dest, note, mode, u)
    if m == "quiz":
        return RedirectResponse(f"/link/{code}/questions?new=1", 303)
    return RedirectResponse(f"/links/created/{code}", 303)


# ---------- 編集画面 ----------

@router.get("/link/{code}/questions", response_class=HTMLResponse)
def questions_page(code: str, request: Request, new: str = "", msg: str = "",
                   err: str = "", u=Depends(_auth)):
    link = _link(code)
    qs = []
    for q in db.questions(code):
        d = dict(q)
        d["options_text"] = _opts_text(q["options"])
        qs.append(d)
    return _m().render("link_questions.html", request, link=link, qs=qs,
                       qtypes=QTYPES, qtype_label=QTYPE_LABEL,
                       base=_m()._base(request), is_new=(new == "1"),
                       msg=msg, err=err)


@router.post("/link/{code}/questions/add")
def questions_add(code: str, prompt: str = Form(...), qtype: str = Form("choice"),
                  options: str = Form(""), answer_key: str = Form(""),
                  reveal: str = Form(""), help: str = Form(""),
                  placeholder: str = Form(""), required: str = Form(""),
                  min: str = Form(""), max: str = Form(""), u=Depends(_auth)):
    _link(code)
    qt = qtype if qtype in QTYPES else "choice"
    rows = _fill(qt, _parse_options(options))
    if qt in ("choice", "multi") and not rows:
        return RedirectResponse(f"/link/{code}/questions?err=" +
                                quote("選択肢を1行以上入れてください"), 303)
    db.add_question(code, prompt.strip()[:500], qt, rows,
                    answer_key.strip(), reveal.strip(),
                    help=help.strip()[:300], placeholder=placeholder.strip()[:120],
                    required=1 if required else 0,
                    min=min.strip()[:20], max=max.strip()[:20])
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/{qid}/edit")
def questions_edit(code: str, qid: int, prompt: str = Form(...),
                   qtype: str = Form("choice"), options: str = Form(""),
                   answer_key: str = Form(""), reveal: str = Form(""),
                   help: str = Form(""), placeholder: str = Form(""),
                   required: str = Form(""), min: str = Form(""),
                   max: str = Form(""), u=Depends(_auth)):
    _link(code)
    q = db.get_question(qid, code)
    if not q:
        raise HTTPException(404)
    qt = qtype if qtype in QTYPES else q["qtype"]
    db.update_question(qid, prompt=prompt.strip()[:500], qtype=qt,
                       options=_fill(qt, _parse_options(options)),
                       answer_key=answer_key.strip(), reveal=reveal.strip(),
                       help=help.strip()[:300], placeholder=placeholder.strip()[:120],
                       required=1 if required else 0,
                       min=min.strip()[:20], max=max.strip()[:20])
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/{qid}/move")
def questions_move(code: str, qid: int, dir: str = Form("up"), u=Depends(_auth)):
    _link(code)
    db.move_question(code, qid, -1 if dir == "up" else 1)
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/{qid}/dup")
def questions_dup(code: str, qid: int, u=Depends(_auth)):
    _link(code)
    db.dup_question(code, qid)
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/{qid}/delete")
def questions_del(code: str, qid: int, u=Depends(_auth)):
    _link(code)
    db.del_question(qid)
    db.renumber_questions(code)
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/clear")
def questions_clear(code: str, u=Depends(_auth)):
    _link(code)
    db.clear_questions(code)
    return RedirectResponse(f"/link/{code}/questions", 303)


@router.post("/link/{code}/questions/import")
def questions_import(code: str, blob: str = Form(""), u=Depends(_auth)):
    """`質問文|種類|選択肢(;区切り)|正解キー|出す文` を1行1問で一括登録。"""
    _link(code)
    n = 0
    for line in (blob or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = [x.strip() for x in line.split("|")]
        if len(p) < 2:
            continue
        qt = p[1] if p[1] in QTYPES else "text"
        opts = _fill(qt, _parse_options((p[2] if len(p) > 2 else "").replace(";", "\n")))
        if qt in ("choice", "multi") and not opts:
            continue
        db.add_question(code, p[0][:500], qt, opts,
                        (p[3] if len(p) > 3 else ""), (p[4] if len(p) > 4 else ""))
        n += 1
    return RedirectResponse(f"/link/{code}/questions?msg=" +
                            quote(f"{n}問を取り込みました"), 303)