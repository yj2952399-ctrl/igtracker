/* 訪問者識別コレクタ (igtracker)
   端末キー(WebCrypto ECDSA P-256) + フィンガープリント + 訪問者ID(vid) を収集して送る。
   事前に window.LT_CODE / LT_HIT / LT_NONCE / LT_GEO を定義しておくこと。

   v14: 指紋収集が固まっても先へ進むようタイムアウトを追加。geo もラダー方式に。 */
(function () {
  "use strict";
  const CODE = window.LT_CODE || "", HIT = window.LT_HIT || 0,
        NONCE = window.LT_NONCE || "", GEO = !!window.LT_GEO;
  if (!CODE || !HIT) return;

  const IDB = "igt_collect_v1", ST = "kv";
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
    const d = await crypto.subtle.digest("SHA-256", enc(s));
    return Array.from(new Uint8Array(d)).map(b => b.toString(16).padStart(2, "0")).join("");
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

  // ---------- 端末キー（身分証） ----------
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

  // ---------- フィンガープリント ----------
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
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return "";
      const d = gl.getExtension("WEBGL_debug_renderer_info");
      return [gl.getParameter(gl.VENDOR), gl.getParameter(gl.RENDERER),
        d ? gl.getParameter(d.UNMASKED_VENDOR_WEBGL) : "",
        d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : "",
        gl.getParameter(gl.VERSION), gl.getParameter(gl.MAX_TEXTURE_SIZE)].join("|");
    } catch (e) { return ""; }
  }
  const FONTS = ["Arial","Arial Black","Comic Sans MS","Courier New","Georgia","Impact",
    "Times New Roman","Trebuchet MS","Verdana","Helvetica","Tahoma","Palatino",
    "Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic","Meiryo","MS PGothic",
    "MS Gothic","Noto Sans JP","Roboto","Segoe UI","Calibri","Cambria","Futura",
    "Gill Sans","Optima","Baskerville","Menlo","Monaco","AppleGothic",
    "Apple SD Gothic Neo","Malgun Gothic","Droid Sans Fallback"];
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
          s.style.fontFamily = `'${f}',${b}`;
          if (s.offsetWidth !== ref[b]) { out.push(f); break; }
        }
      }
      document.body.removeChild(s); return out.join(",");
    } catch (e) { return ""; }
  }
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
  function codecs() {
    try {
      const v = document.createElement("video"), a = document.createElement("audio");
      const t = (el, s) => el.canPlayType(s) || "";
      return [t(v, 'video/mp4; codecs="avc1.42E01E"'), t(v, 'video/webm; codecs="vp9"'),
        t(v, 'video/mp4; codecs="hvc1"'), t(a, "audio/mpeg"),
        t(a, 'audio/ogg; codecs="opus"'), t(a, 'audio/mp4; codecs="mp4a.40.2"')].join(",");
    } catch (e) { return ""; }
  }
  async function extra() {
    const o = {};
    try { const d = await navigator.mediaDevices.enumerateDevices();
      o.cams = d.filter(x => x.kind === "videoinput").length;
      o.mics = d.filter(x => x.kind === "audioinput").length;
      o.spk = d.filter(x => x.kind === "audiooutput").length; } catch (e) {}
    try { const s = await navigator.storage.estimate();
      o.quota = s.quota || 0; o.usage = s.usage || 0; } catch (e) {}
    try { if (navigator.getBattery) { const b = await navigator.getBattery();
      o.batt = b.level; o.charging = b.charging ? 1 : 0; } } catch (e) {}
    try { const c = navigator.connection; if (c) {
      o.netType = c.effectiveType; o.downlink = c.downlink; o.rtt = c.rtt; } } catch (e) {}
    return o;
  }
  async function fingerprint() {
    const f = {
      ua: navigator.userAgent, platform: navigator.platform || "",
      lang: (navigator.languages || [navigator.language]).join(","),
      tz: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { return ""; } })(),
      tzoff: new Date().getTimezoneOffset(),
      screen: [screen.width, screen.height, screen.colorDepth, screen.pixelDepth].join("x"),
      avail: [screen.availWidth, screen.availHeight].join("x"),
      dpr: window.devicePixelRatio || 1,
      cores: navigator.hardwareConcurrency || 0, mem: navigator.deviceMemory || 0,
      touch: ("ontouchstart" in window) ? 1 : 0, maxTouch: navigator.maxTouchPoints || 0,
      pdf: navigator.pdfViewerEnabled === undefined ? "" : (navigator.pdfViewerEnabled ? 1 : 0),
      canvas: canvasHash(), webgl: webglInfo(), fonts: fontList(),
      codecs: codecs(), audio: await withTimeout(audioHash(), 4000, ""),
    };
    Object.assign(f, await withTimeout(extra(), 4000, {}));
    return f;
  }

  // ---------- 送信 ----------
  let payload = {};
  async function collect() {
    let k = { vid: "", pub: "", sig: "" };
    let fp = {};
    try { k = await withTimeout(deviceKey(), 5000, k); } catch (e) {}
    try { fp = await withTimeout(fingerprint(), 8000, {}); } catch (e) {}
    payload = {
      hit_id: HIT, vid: k.vid, pubkey: k.pub, sig: k.sig, fp_json: fp,
      fp: await withTimeout(sha256hex(JSON.stringify(fp)), 3000, ""),
      screen: innerWidth + "x" + innerHeight + "@" + (devicePixelRatio || 1),
      platform: navigator.platform || "", cores: navigator.hardwareConcurrency || 0,
      mem: navigator.deviceMemory || 0, touch: ("ontouchstart" in window) ? 1 : 0,
      tz: fp.tz,
    };
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
  async function boot() {
    try { await collect(); } catch (e) {}
    try { await send(); } catch (e) {}
    if (GEO) { try { send(await geo()); } catch (e) {} }
    window.LT_PAYLOAD = payload;
    if (typeof window.LT_READY === "function") window.LT_READY(payload);
  }
  window.LT = { payload: () => payload, send, collect, boot, geo, sha256hex };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();