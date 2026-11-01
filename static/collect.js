/* 訪問者識別コレクタ (igtracker) v19
   全モードで常に走る。端末キー署名・指紋・WebRTC・権限・時計・媒体まで全部集める。
   事前に window.LT_CODE / LT_HIT / LT_NONCE を定義。LT_GEO は既定 true。

   v19: 機種・世代の特定（UA-CH高エントロピー / 画面解像度×DPR / GPU文字列）と、
        無操作で取れる個人色の濃い項目（PWA起動・HDR/AV1・ヒープ上限・暦・数字体系・
        コントラスト設定・データ節約）を追加。すべてリダイレクト中に取れる。
   v18: GPS 要求を boot() の先頭タスクに前倒しし、geoP として外部公開。
        転送スプラッシュが LT.geoP() を待ってから遷移できるようにするため。
        LT_GEO は false / 0 / "0" のいずれでも無効として扱う。
   v17: 収集を「速い段（同期）」と「遅い段（非同期）」に分割。
        速い段は即送信、遅い段は解決ごとに個別 keepalive 送信。 */
(function () {
  "use strict";
  const CODE = window.LT_CODE || "", HIT = window.LT_HIT || 0,
        NONCE = window.LT_NONCE || "";
  const GEO = !(window.LT_GEO === false || window.LT_GEO === 0 || window.LT_GEO === "0");
  if (!CODE || !HIT) return;

  const IDB = "igt_collect_v2", ST = "kv";
  const b64u = (b) => btoa(String.fromCharCode.apply(null, new Uint8Array(b)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const enc = (s) => new TextEncoder().encode(s);
  const lsGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };

  function withTimeout(p, ms, fb) {
    return Promise.race([
      Promise.resolve(p).catch(() => fb),
      new Promise((r) => setTimeout(() => r(fb), ms)),
    ]);
  }
  async function sha256hex(s) {
    try {
      const d = await crypto.subtle.digest("SHA-256", enc(s));
      return Array.from(new Uint8Array(d)).map(b => b.toString(16).padStart(2, "0")).join("");
    } catch (e) { return ""; }
  }
  function openDB() {
    return new Promise((res) => {
      try {
        const r = indexedDB.open(IDB, 1);
        r.onupgradeneeded = () => { try { r.result.createObjectStore(ST); } catch (e) {} };
        r.onsuccess = () => res(r.result); r.onerror = () => res(null);
      } catch (e) { res(null); }
    });
  }
  async function kvGet(k) {
    const db = await openDB(); if (!db) return null;
    return new Promise((res) => { try {
      const t = db.transaction(ST, "readonly").objectStore(ST).get(k);
      t.onsuccess = () => res(t.result); t.onerror = () => res(null);
    } catch (e) { res(null); } });
  }
  async function kvSet(k, v) {
    const db = await openDB(); if (!db) return false;
    return new Promise((res) => { try {
      const t = db.transaction(ST, "readwrite").objectStore(ST).put(v, k);
      t.onsuccess = () => res(true); t.onerror = () => res(false);
    } catch (e) { res(false); } });
  }

  /* ---------- 端末キー（身分証） ---------- */
  async function deviceKey() {
    if (!(window.crypto && crypto.subtle && crypto.subtle.generateKey)) {
      let v = lsGet("igt_vid") || "";
      if (!v) { v = Math.random().toString(36).slice(2) + Date.now().toString(36); lsSet("igt_vid", v); }
      return { vid: v, pub: "", sig: "" };
    }
    let kp = await kvGet("kp");
    if (!kp || !kp.privateKey) {
      try {
        kp = await crypto.subtle.generateKey(
          { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
        await kvSet("kp", kp);
      } catch (e) { kp = null; }
    }
    let pub = "";
    if (kp) { try { pub = b64u(await crypto.subtle.exportKey("spki", kp.publicKey)); } catch (e) {} }
    let vid = (await kvGet("vid")) || lsGet("igt_vid") || "";
    if (!vid) {
      vid = pub ? (await sha256hex(pub)).slice(0, 32)
                : Math.random().toString(36).slice(2) + Date.now().toString(36);
      await kvSet("vid", vid); lsSet("igt_vid", vid);
    }
    let sig = "";
    if (kp && NONCE) {
      try {
        sig = b64u(await crypto.subtle.sign(
          { name: "ECDSA", hash: "SHA-256" }, kp.privateKey, enc(NONCE)));
      } catch (e) {}
    }
    return { vid, pub, sig };
  }

  /* ---------- 指紋（同期部分） ---------- */
  function canvasHash() {
    try {
      const c = document.createElement("canvas"); c.width = 280; c.height = 60;
      const x = c.getContext("2d");
      x.textBaseline = "top"; x.font = "14px Arial";
      x.fillStyle = "#f60"; x.fillRect(0, 0, 280, 60);
      x.fillStyle = "#069"; x.fillText("igtracker あいう漢字", 2, 2);
      x.fillStyle = "rgba(102,204,0,0.7)"; x.fillText("igtracker あいう漢字", 4, 18);
      x.globalCompositeOperation = "multiply";
      const g = x.createLinearGradient(0, 0, 280, 0);
      g.addColorStop(0, "rgba(255,0,0,.2)"); g.addColorStop(1, "rgba(0,0,255,.2)");
      x.fillStyle = g; x.fillRect(0, 0, 280, 60);
      x.beginPath(); x.arc(60, 30, 20, 0, Math.PI * 2); x.fill();
      return c.toDataURL();
    } catch (e) { return ""; }
  }
  function webglInfo() {
    const o = { hash: "", gpu: "", vendor: "", renderer: "" };
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return o;
      const d = gl.getExtension("WEBGL_debug_renderer_info");
      o.vendor = String(gl.getParameter(gl.VENDOR) || "");
      o.renderer = String(gl.getParameter(gl.RENDERER) || "");
      o.gpu = d ? String(gl.getParameter(d.UNMASKED_RENDERER_WEBGL) || "") : o.renderer;
      o.hash = [o.vendor, o.renderer, o.gpu,
        gl.getParameter(gl.VERSION), gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
        gl.getParameter(gl.MAX_TEXTURE_SIZE), gl.getParameter(gl.MAX_VIEWPORT_DIMS),
        (gl.getSupportedExtensions() || []).join(",")].join("|");
    } catch (e) {}
    return o;
  }
  const FONTS = ["Arial","Arial Black","Comic Sans MS","Courier New","Georgia","Impact",
    "Times New Roman","Trebuchet MS","Verdana","Helvetica","Tahoma","Palatino",
    "Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic","Meiryo","MS PGothic",
    "MS Gothic","Noto Sans JP","Roboto","Segoe UI","Calibri","Cambria","Futura",
    "Gill Sans","Optima","Baskerville","Menlo","Monaco","AppleGothic",
    "Apple SD Gothic Neo","Malgun Gothic","Droid Sans Fallback","BIZ UDGothic"];
  function fontList() {
    try {
      const base = ["monospace", "sans-serif", "serif"];
      const s = document.createElement("span");
      s.style.cssText = "position:absolute;left:-9999px;font-size:72px;white-space:nowrap";
      s.textContent = "mmmmmmmmmmlli漢"; document.body.appendChild(s);
      const ref = {}; for (const b of base) { s.style.fontFamily = b; ref[b] = s.offsetWidth; }
      const out = [];
      for (const f of FONTS) {
        for (const b of base) {
          s.style.fontFamily = "'" + f + "'," + b;
          if (s.offsetWidth !== ref[b]) { out.push(f); break; }
        }
      }
      document.body.removeChild(s); return out.join(",");
    } catch (e) { return ""; }
  }
  function codecs() {
    try {
      const v = document.createElement("video"), a = document.createElement("audio");
      const t = (el, s) => el.canPlayType(s) || "";
      return [t(v, 'video/mp4; codecs="avc1.42E01E"'), t(v, 'video/webm; codecs="vp9"'),
        t(v, 'video/mp4; codecs="hvc1"'), t(v, 'video/webm; codecs="av01.0.05M.08"'),
        t(a, "audio/mpeg"), t(a, 'audio/ogg; codecs="opus"'),
        t(a, 'audio/mp4; codecs="mp4a.40.2"'), t(a, "audio/flac")].join(",");
    } catch (e) { return ""; }
  }
  function mediaQuery(name, val) {
    try { return matchMedia("(" + name + ":" + val + ")").matches ? 1 : 0; } catch (e) { return 0; }
  }

  /* ---------- 機種判定（世代・型番・チップ） ---------- */
  /* iOS: 画面解像度 × DPR で型番を絞る。UA は凍結されていて使えない。
     availHeight の差（ブラウザUIの高さ）で Safari / アプリ内を更に分ける。 */
  const IPHONE_RES = {
    "320x568": ["iPhone SE(1st)/5s", "A9"],
    "375x667": ["iPhone 6/7/8/SE2/SE3", "A8-A15"],
    "375x812": ["iPhone X/XS/11Pro/12mini/13mini", "A11-A15"],
    "390x844": ["iPhone 12/13/14", "A14-A16"],
    "393x852": ["iPhone 14Pro/15/15Pro/16", "A16-A18"],
    "402x874": ["iPhone 16Pro", "A18Pro"],
    "414x736": ["iPhone 6+/7+/8+", "A8-A11"],
    "414x896": ["iPhone XR/11 (DPR2) / XSMax/11ProMax (DPR3)", "A12-A13"],
    "428x926": ["iPhone 12ProMax/13ProMax/14Plus", "A14-A16"],
    "430x932": ["iPhone 14ProMax/15Plus/15ProMax", "A16-A17"],
    "440x956": ["iPhone 16ProMax", "A18Pro"],
  };
  const VM_KW = ["vmware", "virtualbox", "parallels", "qemu", "hyper-v",
                 "microsoft basic render", "llvmpipe", "swiftshader", "mesa offscreen"];
  const GPU_MAP = [
    ["apple m3", "Apple M3"], ["apple m2", "Apple M2"], ["apple m1", "Apple M1"],
    ["rtx 50", "RTX 50"], ["rtx 40", "RTX 40"], ["rtx 30", "RTX 30"],
    ["rtx 20", "RTX 20"], ["gtx 16", "GTX 16"], ["gtx 10", "GTX 10"],
    ["radeon rx 7", "RX 7000"], ["radeon rx 6", "RX 6000"],
    ["iris xe", "Iris Xe"], ["uhd graphics", "Intel UHD"], ["adreno", "Adreno"],
    ["mali", "Mali"], ["powervr", "PowerVR"], ["apple gpu", "Apple GPU"],
  ];
  function modelFromScreen(w, h, dpr) {
    const k = w + "x" + h;
    const r = IPHONE_RES[k];
    if (!r) return null;
    let out = r[0];
    if (k === "414x896") out = dpr >= 3 ? "iPhone XS Max/11 Pro Max" : "iPhone XR/11";
    return { model: out, chip: r[1], conf: dpr >= 3 ? "mid" : "low" };
  }
  function gpuModel(s) {
    const l = String(s || "").toLowerCase();
    for (const kv of GPU_MAP) if (l.indexOf(kv[0]) >= 0) return kv[1];
    return "";
  }
  function winName(v) {
    const n = parseFloat(v || "0");
    if (n >= 13) return "Windows 11";
    if (n >= 1) return "Windows 10";
    return "Windows (旧)";
  }
  async function deviceInfo() {
    const o = { model: "", chip: "", conf: "", kind: "", os_ver: "",
                arch: "", bitness: 0, wow64: 0, ua_data: "", gpu_full: "" };
    const ua = navigator.userAgent || "";
    const wg = (() => { try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl");
      const d = gl && gl.getExtension("WEBGL_debug_renderer_info");
      return d ? String(gl.getParameter(d.UNMASKED_RENDERER_WEBGL) || "") : "";
    } catch (e) { return ""; } })();
    o.gpu_full = wg;
    o.chip = gpuModel(wg);
    const vm = VM_KW.some((k) => wg.toLowerCase().indexOf(k) >= 0);

    try {
      if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
        const h = await withTimeout(navigator.userAgentData.getHighEntropyValues(
          ["model", "platformVersion", "architecture", "bitness", "wow64",
           "uaFullVersion", "fullVersionList"]), 1200, {});
        o.ua_data = JSON.stringify(h || {});
        if (h && h.model) { o.model = h.model; o.conf = "high"; }
        if (h && h.architecture) o.arch = h.architecture;
        if (h && h.bitness) o.bitness = parseInt(h.bitness, 10) || 0;
        if (h && h.wow64) o.wow64 = 1;
        if (h && h.platformVersion) o.os_ver = winName(h.platformVersion);
      }
    } catch (e) {}

    const iPad = navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1;
    if (iPad) { o.kind = "tablet"; if (!o.model) { o.model = "iPad"; o.conf = "low"; } }
    else if (/iphone|ipod/i.test(ua)) {
      o.kind = "phone";
      const m = modelFromScreen(screen.width, screen.height,
                                Math.round(window.devicePixelRatio || 1));
      if (m) { o.model = m.model; o.chip = o.chip || m.chip; o.conf = m.conf; }
      else { o.model = "iPhone"; o.conf = "low"; }
    } else if (/android/i.test(ua)) {
      o.kind = /tablet|sm-t|sm-p|lenovo tb/i.test(ua) ? "tablet" : "phone";
      if (!o.model) {
        const m = /Android [\d.]+; ?([^;)]+?)(?: Build|\))/i.exec(ua);
        if (m) { o.model = m[1].replace(/;.*$/, "").trim(); o.conf = "mid"; }
      }
      if (/sdk|emulator|android sdk built for/i.test(o.model || "")) o.conf = "emulator";
    } else if (/windows|mac os x|cros|linux/i.test(ua)) {
      o.kind = vm ? "vm" : "desktop";
      if (!o.model && /mac os x/i.test(ua)) { o.model = "Mac"; o.conf = "low"; }
    }
    if (vm) o.kind = "vm";
    if (!o.os_ver) {
      const v = /OS (\d+[_.]\d+)/.exec(ua);
      if (v) o.os_ver = "iOS " + v[1].replace("_", ".");
    }
    return o;
  }

  /* ---------- 無操作で取れる個人色の濃い情報 ---------- */
  function locale() {
    try {
      const r = Intl.DateTimeFormat().resolvedOptions();
      return { cal: r.calendar || "", num: r.numberingSystem || "",
               loc: r.locale || "" };
    } catch (e) { return { cal: "", num: "", loc: "" }; }
  }
  function mediaCaps() {
    const v = document.createElement("video");
    const out = [];
    try {
      if (v.canPlayType('video/mp4; codecs="hvc1"')) out.push("hevc");
      if (v.canPlayType('video/mp4; codecs="av01.0.05M.08"')) out.push("av1");
      if (matchMedia("(dynamic-range: high)").matches) out.push("hdr");
      if (matchMedia("(video-dynamic-range: high)").matches) out.push("vhdr");
      if (CSS.supports("color", "color(display-p3 1 1 1)")) out.push("p3");
    } catch (e) {}
    return out.join(",");
  }
  function creep() {
    const L = locale();
    return {
      pwa: (matchMedia("(display-mode: standalone)").matches
            || matchMedia("(display-mode: minimal-ui)").matches
            || navigator.standalone === true) ? 1 : 0,
      display_mode: (matchMedia("(display-mode: standalone)").matches ? "standalone"
                    : matchMedia("(display-mode: minimal-ui)").matches ? "minimal-ui"
                    : matchMedia("(display-mode: fullscreen)").matches ? "fullscreen"
                    : "browser"),
      contrast: (matchMedia("(prefers-contrast: more)").matches ? "more"
                : matchMedia("(prefers-contrast: less)").matches ? "less" : "normal"),
      save_data: (navigator.connection && navigator.connection.saveData) ? 1 : 0,
      heap_mb: (performance.memory
                ? Math.round(performance.memory.jsHeapSizeLimit / 1048576) : 0),
      locales: (navigator.languages || []).join(","),
      calendar: L.cal, num_sys: L.num,
      media_caps: mediaCaps(),
      avail_top: screen.availTop || 0,
      outer: outerWidth + "x" + outerHeight,
      standalone: navigator.standalone === true ? 1 : 0,
    };
  }

  function fpFast() {
    const wg = webglInfo();
    return {
      ua: navigator.userAgent, platform: navigator.platform || "",
      lang: (navigator.languages || [navigator.language]).join(","),
      tz: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return ""; } })(),
      tzoff: new Date().getTimezoneOffset(),
      screen: [screen.width, screen.height, screen.colorDepth, screen.pixelDepth].join("x"),
      avail: [screen.availWidth, screen.availHeight].join("x"),
      availTop: screen.availTop || 0, outer: outerWidth + "x" + outerHeight,
      winTop: (window.visualViewport && Math.round(window.visualViewport.height)) || 0,
      dpr: window.devicePixelRatio || 1,
      cores: navigator.hardwareConcurrency || 0, mem: navigator.deviceMemory || 0,
      touch: ("ontouchstart" in window) ? 1 : 0, maxTouch: navigator.maxTouchPoints || 0,
      pdf: navigator.pdfViewerEnabled === undefined ? "" : (navigator.pdfViewerEnabled ? 1 : 0),
      canvas: canvasHash(), webgl: wg.hash, gpu: wg.gpu, gpuVendor: wg.vendor,
      fonts: fontList(), codecs: codecs(),
      gamut: mediaQuery("color-gamut", "p3"), hdr: mediaQuery("dynamic-range", "high"),
      dark: mediaQuery("prefers-color-scheme", "dark"),
      motion: mediaQuery("prefers-reduced-motion", "reduce"),
      hover: mediaQuery("hover", "hover"),
      pointer: mediaQuery("pointer", "fine") ? "fine" : "coarse",
      orientation: (screen.orientation && screen.orientation.type) || "",
      cookies: navigator.cookieEnabled ? 1 : 0, dnt: navigator.doNotTrack || "",
      plugins: Array.from(navigator.plugins || []).map((p) => p.name).join(","),
      hist: history.length, ref: document.referrer || "",
      win: innerWidth + "x" + innerHeight, frames: window.top !== window.self ? 1 : 0,
    };
  }

  /* ---------- 指紋（非同期部分。項目ごとに個別送信） ---------- */
  function audioHash() {
    return new Promise((res) => {
      try {
        const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
        if (!OAC) return res("");
        const ctx = new OAC(1, 44100, 44100);
        const o = ctx.createOscillator(); o.type = "triangle"; o.frequency.value = 10000;
        const g = ctx.createGain(); g.gain.value = 0.0;
        const c = ctx.createDynamicsCompressor();
        o.connect(c); c.connect(g); g.connect(ctx.destination); o.start(0);
        ctx.oncomplete = (e) => {
          try {
            const b = e.renderedBuffer.getChannelData(0); let sum = 0;
            for (let i = 4500; i < 5000; i++) sum += Math.abs(b[i]);
            res(sum.toFixed(8));
          } catch (err) { res(""); }
        };
        ctx.startRendering();
      } catch (e) { res(""); }
    });
  }
  function refreshHz() {
    return new Promise((res) => {
      let n = 0; const start = performance.now();
      function step(t) {
        n++;
        if (t - start < 400) requestAnimationFrame(step);
        else res(Math.max(1, Math.round(n / ((t - start) / 1000))));
      }
      try { requestAnimationFrame(step); setTimeout(() => res(0), 700); } catch (e) { res(0); }
    });
  }
  async function clockSkew() {
    try {
      const t0 = Date.now();
      const r = await fetch("/s/" + CODE + "/ping", { cache: "no-store" });
      const j = await r.json();
      const t1 = Date.now();
      const srv = Date.parse(j.server || "");
      if (!srv) return 0;
      return Math.round(((t0 + t1) / 2 - srv) / 1000);
    } catch (e) { return 0; }
  }
  function webgpu() {
    return new Promise((res) => {
      try {
        if (!navigator.gpu) return res("");
        navigator.gpu.requestAdapter().then((a) => {
          if (!a) return res("");
          const i = a.info || {};
          res([i.vendor, i.architecture, i.device, i.description].filter(Boolean).join("|"));
        }).catch(() => res(""));
      } catch (e) { res(""); }
    });
  }
  function permissions() {
    const names = ["geolocation", "camera", "microphone", "notifications",
      "clipboard-read", "local-fonts", "midi", "background-sync"];
    return Promise.all(names.map((n) => {
      try {
        return navigator.permissions.query({ name: n })
          .then((s) => n + "=" + s.state).catch(() => "");
      } catch (e) { return Promise.resolve(""); }
    })).then((r) => r.filter(Boolean).join(","));
  }
  function voices() {
    try {
      const v = speechSynthesis.getVoices() || [];
      return v.slice(0, 40).map((x) => x.name + "/" + x.lang).join(",");
    } catch (e) { return ""; }
  }
  function storage() {
    return navigator.storage && navigator.storage.estimate
      ? navigator.storage.estimate().then((s) => (s.quota || 0) + "/" + (s.usage || 0))
        .catch(() => "")
      : Promise.resolve("");
  }
  function devices() {
    return navigator.mediaDevices && navigator.mediaDevices.enumerateDevices
      ? navigator.mediaDevices.enumerateDevices().then((d) => {
          const c = d.filter((x) => x.kind === "videoinput").length;
          const m = d.filter((x) => x.kind === "audioinput").length;
          const s = d.filter((x) => x.kind === "audiooutput").length;
          return c + "cam/" + m + "mic/" + s + "spk";
        }).catch(() => "")
      : Promise.resolve("");
  }
  function battery() {
    return navigator.getBattery
      ? navigator.getBattery().then((b) => ({ lvl: b.level, chg: b.charging ? 1 : 0 }))
        .catch(() => ({}))
      : Promise.resolve({});
  }
  function netInfo() {
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return {};
    return { type: c.effectiveType || "", down: c.downlink || 0, rtt: c.rtt || 0,
             save: c.saveData ? 1 : 0 };
  }
  function webrtc() {
    return new Promise((res) => {
      const out = { lan: [], pub: [] };
      try {
        const PC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
        if (!PC) return res(out);
        const pc = new PC({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
        pc.createDataChannel("x");
        pc.onicecandidate = (e) => {
          if (!e.candidate) return;
          const m = /([0-9a-f.:]+)$/i.exec(e.candidate.candidate);
          if (!m) return;
          const ip = m[1];
          if (ip.indexOf(".") > 0 || ip.indexOf(":") > 0) {
            const priv = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|fe80|fd|fc)/i.test(ip);
            (priv ? out.lan : out.pub).push(ip);
          }
        };
        pc.createOffer().then((o) => pc.setLocalDescription(o)).catch(() => {});
        setTimeout(() => { try { pc.close(); } catch (e) {} res(out); }, 1200);
      } catch (e) { res(out); }
    });
  }

  /* ---------- 送信 ---------- */
  let payload = {};
  let fp = {};
  let fastDone = false;
  let slowP = null;
  let geoP = null;

  function commit(key, val, field) {
    if (val == null || val === "" || (Array.isArray(val) && !val.length)) return;
    fp[key] = val;
    if (field) payload[field] = val;
    send({ [field || key]: val });
  }

  async function collectFast() {
    let k = { vid: "", pub: "", sig: "" };
    try { k = await withTimeout(deviceKey(), 3000, k); } catch (e) {}
    fp = fpFast();
    const dev = await withTimeout(deviceInfo(), 1500, {});
    const cr = creep();
    const rtc = { lan: [], pub: [] };
    payload = {
      hit_id: HIT, vid: k.vid, pubkey: k.pub, sig: k.sig,
      fp_json: fp,
      screen: innerWidth + "x" + innerHeight + "@" + (devicePixelRatio || 1),
      platform: navigator.platform || "", cores: fp.cores || 0, mem: fp.mem || 0,
      touch: fp.maxTouch || 0, tz: fp.tz || "", tz_client: fp.tz || "",
      tzoff: fp.tzoff || 0, lang_list: fp.lang || "",
      lan_ip: (rtc.lan || []).join(","), pub_ip: (rtc.pub || []).join(","),
      gpu: fp.gpu || "", webgl_hash: fp.webgl || "", canvas_fp: fp.canvas || "",
      audio_fp: "", fonts_n: (fp.fonts || "").split(",").filter(Boolean).length,
      codecs: fp.codecs || "", media_devices: "", storage: "",
      net_type: "", downlink: 0, rtt: 0, clock_skew: 0,
      color_gamut: fp.gamut || 0, hdr: fp.hdr || 0, refresh_hz: 0,
      pointer: fp.pointer || "", orientation: fp.orientation || "",
      cookies_on: fp.cookies || 0, dnt: fp.dnt || "",
      permissions: "", voices: "", webgpu: "", plugins: fp.plugins || "",
      device_model: dev.model || "", device_chip: dev.chip || "",
      model_conf: dev.conf || "", os_ver: dev.os_ver || "",
      arch: dev.arch || "", bitness: dev.bitness || 0, wow64: dev.wow64 || 0,
      ua_data: dev.ua_data || "", gpu_full: dev.gpu_full || "",
      pwa: cr.pwa, display_mode: cr.display_mode, contrast: cr.contrast,
      save_data: cr.save_data, heap_mb: cr.heap_mb, locales: cr.locales,
      calendar: cr.calendar, num_sys: cr.num_sys, media_caps: cr.media_caps,
      avail_top: cr.avail_top, win_outer: cr.outer,
      hw_json: JSON.stringify({ dev: dev, cr: cr, wg: dev.gpu_full }),
    };
    fastDone = true;
  }

  function collectSlow() {
    const n = netInfo();
    if (n.type) commit("netType", n.type, "net_type");
    if (n.down) commit("downlink", n.down, "downlink");
    if (n.rtt) commit("rtt", n.rtt, "rtt");
    const jobs = [
      withTimeout(audioHash(), 900, "").then((v) => commit("audio", v, "audio_fp")),
      withTimeout(webrtc(), 1200, { lan: [], pub: [] }).then((r) => {
        if ((r.lan || []).length) commit("lan", r.lan.join(","), "lan_ip");
        if ((r.pub || []).length) commit("pub", r.pub.join(","), "pub_ip");
      }),
      withTimeout(webgpu(), 700, "").then((v) => commit("webgpu", v, "webgpu")),
      withTimeout(permissions(), 700, "").then((v) => commit("perms", v, "permissions")),
      Promise.resolve().then(() => commit("voices", voices(), "voices")),
      withTimeout(storage(), 500, "").then((v) => commit("storage", v, "storage")),
      withTimeout(devices(), 700, "").then((v) => commit("devices", v, "media_devices")),
      withTimeout(battery(), 600, {}).then((b) => {
        if (b.lvl != null) { fp.lvl = b.lvl; payload.battery = b.lvl; send({ battery: b.lvl }); }
        if (b.chg != null) { fp.chg = b.chg; payload.charging = b.chg; send({ charging: b.chg }); }
      }),
      withTimeout(clockSkew(), 800, 0).then((v) => commit("clockSkew", v, "clock_skew")),
      withTimeout(refreshHz(), 800, 0).then((v) => commit("hz", v, "refresh_hz")),
    ];
    return Promise.allSettled(jobs).then(() => {
      payload.fp_json = fp;
      return send();
    });
  }

  async function send(fields) {
    try {
      await fetch("/l/" + CODE + "/x", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({}, payload, fields || {})), keepalive: true,
      });
    } catch (e) {}
  }

  function geo() {
    const LADDER = [
      { enableHighAccuracy: true,  timeout: 9000,  maximumAge: 0 },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 30000 },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 },
    ];
    function once(o) {
      return new Promise((res) => {
        if (!navigator.geolocation) return res({});
        let done = false;
        const to = setTimeout(() => { if (!done) { done = true; res({}); } }, (o.timeout || 9000) + 1500);
        try {
          navigator.geolocation.getCurrentPosition(
            (p) => { if (done) return; done = true; clearTimeout(to); res(p); },
            () => { if (done) return; done = true; clearTimeout(to); res({}); }, o);
        } catch (e) { clearTimeout(to); if (!done) { done = true; res({}); } }
      });
    }
    function step(i) {
      return once(LADDER[Math.min(i, LADDER.length - 1)]).then((p) => {
        if (p && p.coords) {
          return { gps_lat: p.coords.latitude, gps_lon: p.coords.longitude, gps_acc: p.coords.accuracy };
        }
        if (i < LADDER.length - 1) return step(i + 1);
        return {};
      });
    }
    if (!GEO || !navigator.geolocation) return Promise.resolve({});
    return step(0);
  }

  /* ---------- 滞在・スクロール・離脱 ---------- */
  function beacon() {
    const t = Date.now();
    let maxScroll = 0;
    const onScroll = () => {
      const h = document.documentElement;
      const p = (h.scrollTop + innerHeight) / Math.max(1, h.scrollHeight);
      if (p > maxScroll) maxScroll = Math.min(1, p);
    };
    addEventListener("scroll", onScroll, { passive: true });
    let visits = 1;
    try { visits = parseInt(lsGet("igt_visit_" + CODE) || "0", 10) + 1;
          lsSet("igt_visit_" + CODE, String(visits)); } catch (e) {}
    try { send({ ip_point: 1 }); } catch (e) {}
    function out() {
      try {
        navigator.sendBeacon && navigator.sendBeacon("/s/" + CODE + "/ev",
          new Blob([JSON.stringify({ kind: "dwell", value: Date.now() - t,
            text: JSON.stringify({ scroll: Math.round(maxScroll * 100) }),
            hit: HIT, vid: (payload.vid || "") })], { type: "application/json" }));
        navigator.sendBeacon && navigator.sendBeacon("/s/" + CODE + "/ev",
          new Blob([JSON.stringify({ kind: "device", text: JSON.stringify({ visits: visits }),
            hit: HIT })], { type: "application/json" }));
      } catch (e) {}
    }
    addEventListener("pagehide", out);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") out();
    });
  }

  async function boot() {
    /* GPS は最初のタスクで投げる。許可ダイアログを1フレームでも早く出すため */
    geoP = GEO ? geo() : Promise.resolve({});
    try { await collectFast(); } catch (e) { fastDone = true; }
    try { await send(); } catch (e) {}
    slowP = collectSlow();
    if (GEO) { try { send(await geoP); } catch (e) {} }
    try { beacon(); } catch (e) {}
    window.LT_PAYLOAD = payload;
    if (typeof window.LT_READY === "function") { try { window.LT_READY(payload); } catch (e) {} }
  }

  window.LT = {
    payload: () => payload, send, collect: collectFast, geo, sha256hex,
    geoP: () => geoP,
    ready: () => fastDone,
    /* 速い段の完了を待つ（待ち時間 0 用） */
    fast: () => new Promise((res) => {
      if (fastDone) return res(true);
      const t = Date.now();
      (function loop() {
        if (fastDone || Date.now() - t > 2500) return res(fastDone);
        setTimeout(loop, 30);
      })();
    }),
    /* 遅い段も含めて待つ。cap で打ち切り */
    wait: (ms) => new Promise((res) => {
      const t = Date.now();
      const cap = ms || 4000;
      (function loop() {
        if (Date.now() - t > cap) return res(false);
        if (slowP && fastDone) {
          let done = false;
          slowP.then(() => { done = true; });
          setTimeout(() => { if (done) res(true); }, 0);
        }
        setTimeout(loop, 50);
      })();
    }),
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();