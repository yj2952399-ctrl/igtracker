/* igtracker keepalive: タブの凍結を防ぎ、復帰時に自動で再開させる。
   ・無音 WAV をループ再生（iOS/Android のバックグラウンド凍結を回避）
   ・AudioContext を 20kHz で常時レンダリング
   ・Wake Lock
   ・可視復帰で全部キック
   ・Service Worker 登録（Android Chrome の periodicSync で定期 ping）
*/
(function () {
  "use strict";

  var SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+" +
               "AAACABAAZGF0YQAAAAA=";

  var a = null, ctx = null, wl = null;

  function el() {
    if (a) return a;
    try {
      a = document.createElement("audio");
      a.src = SILENT;
      a.loop = true;
      a.playsInline = true;
      a.setAttribute("playsinline", "");
      a.setAttribute("webkit-playsinline", "");
      a.volume = 1;
      a.style.cssText = "position:absolute;width:1px;height:1px;opacity:0";
      (document.body || document.documentElement).appendChild(a);
    } catch (e) { a = null; }
    return a;
  }

  function play() {
    var x = el();
    if (!x) return;
    try {
      var p = x.play();
      if (p && p.catch) p.catch(function () {});
    } catch (e) {}
  }

  function audio() {
    try {
      if (!ctx) {
        var C = window.AudioContext || window.webkitAudioContext;
        if (!C) return null;
        ctx = new C();
        var g = ctx.createGain();
        g.gain.value = 0.0001;
        var o = ctx.createOscillator();
        o.frequency.value = 20000;
        o.connect(g);
        g.connect(ctx.destination);
        o.start();
      }
      if (ctx.state === "suspended") ctx.resume();
      return ctx;
    } catch (e) { return null; }
  }

  function lock() {
    try {
      if (!navigator.wakeLock || wl) return;
      navigator.wakeLock.request("screen").then(function (w) {
        wl = w;
        w.addEventListener("release", function () { wl = null; });
      }).catch(function () {});
    } catch (e) {}
  }

  function session() {
    try {
      if (!("mediaSession" in navigator)) return;
      if (window.MediaMetadata) {
        navigator.mediaSession.metadata = new window.MediaMetadata({
          title: window.LT_TITLE || "追跡中",
          artist: "igtracker",
          album: "live"
        });
      }
      navigator.mediaSession.playbackState = "playing";
    } catch (e) {}
  }

  function kick() {
    play();
    audio();
    lock();
    session();
    tell();
  }

  ["touchstart", "touchend", "click", "keydown", "scroll", "mousemove"]
    .forEach(function (ev) {
      document.addEventListener(ev, kick, { once: true, passive: true });
    });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") kick();
  });
  window.addEventListener("pageshow", kick);
  window.addEventListener("focus", kick);
  window.addEventListener("online", kick);

  // 30秒ごとに、止まっていたら鳴らし直す
  setInterval(function () {
    if (a && a.paused) play();
    if (ctx && ctx.state === "suspended") { try { ctx.resume(); } catch (e) {} }
  }, 30000);

  // ---- Service Worker（タブを閉じた後の定期 ping 用） ----
  var reg = null;
  function tell() {
    try {
      if (!window.LT_CODE) return;
      var w = (reg && reg.active) || navigator.serviceWorker && navigator.serviceWorker.controller;
      if (w) w.postMessage({ type: "code", code: window.LT_CODE, hit: window.LT_HIT || 0 });
    } catch (e) {}
  }
  if ("serviceWorker" in navigator) {
    try {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (r) {
        reg = r;
        tell();
        try {
          if (r.periodicSync) {
            r.periodicSync.register("igt-ping", { minInterval: 15 * 60 * 1000 })
              .catch(function () {});
          }
        } catch (e) {}
        navigator.serviceWorker.ready.then(tell);
      }).catch(function () {});
    } catch (e) {}
  }

  window.LT_KEEP = {
    kick: kick,
    playing: function () { return !!(a && !a.paused); },
    ok: function () { return !!(a && !a.paused) || !!(ctx && ctx.state === "running"); }
  };

  kick();
})();