/* 連続位置追跡クライアント (igtracker) v2
   window.LT_CODE / LT_IV / LT_MAX / LT_HIT を事前定義すること。
   開いている間ずっと記録し、閉じる時に停止を送る。
   送信に失敗しても点は捨てず、次回まとめて送る。 */
(function () {
  "use strict";

  var CODE = window.LT_CODE || "";
  if (!CODE) return;

  var API  = "/l/" + encodeURIComponent(CODE) + "/p";
  var IV   = Math.max(5, (window.LT_IV || 15) | 0) * 1000;  // 送信間隔(ms)
  var MAXMIN = (window.LT_MAX || 180) | 0;                  // 自動停止(分)
  var HIT  = window.LT_HIT || 0;
  var SEND_EVERY = Math.min(IV, 5000);

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
  var sending = false, last = 0, started = 0, count = 0;
  var wid = null, wake = null, clock = null, sender = null, nudge = null;
  var stopped = true, gotFix = false, bestAcc = null, fails = 0;
  var batt = null, chg = null;

  function $(id) { return document.getElementById(id); }
  function setTxt(id, v) { var e = $(id); if (e) e.textContent = v; }
  function iso(t) { try { return new Date(t).toISOString(); } catch (e) { return ""; } }
  function say(m, c) {
    var s = $("lt_st");
    if (s) { s.textContent = m; s.className = "lt-" + (c || "dim"); }
  }

  function tick() {
    if (!started) return;
    var sec = Math.floor((Date.now() - started) / 1000);
    setTxt("lt_time", ("0" + Math.floor(sec / 60)).slice(-2) + ":" +
                      ("0" + (sec % 60)).slice(-2));
  }

  function drop(arr) {
    q = q.filter(function (x) { return arr.indexOf(x) === -1; });
  }

  function send(extra) {
    if (sending) return;
    if (!q.length && !extra) return;
    sending = true;
    var pts = q.slice(0);
    var body = { sid: SID, kind: (extra && extra.kind) || "pt", hit: HIT, pts: pts };
    fetch(API, {
      method: "POST", cache: "no-store", keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        drop(pts);                       // 成功した分だけキューから消す
        last = Date.now(); fails = 0;
        if (j && j.iv && j.iv * 1000 !== IV) IV = j.iv * 1000;
      })
      .catch(function () { fails++; })   // 失敗時はキューに残す
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
    if (ok) drop(pts);
    else send({ kind: kind });
  }

  function onPos(p) {
    var c = (p && p.coords) || {};
    if (c.latitude == null || c.longitude == null) return;
    gotFix = true; count++;
    q.push({ ts: iso(p.timestamp || Date.now()), lat: c.latitude, lon: c.longitude,
             acc: c.accuracy, spd: c.speed, hdg: c.heading, batt: batt, chg: chg });
    if (q.length > 3000) q.splice(0, q.length - 3000);
    if (c.accuracy && (bestAcc === null || c.accuracy < bestAcc)) bestAcc = c.accuracy;
    setTxt("lt_now", c.latitude.toFixed(5) + ", " + c.longitude.toFixed(5) +
                    (c.accuracy ? " ±" + Math.round(c.accuracy) + "m" : ""));
    say("記録中 " + count + " 点" +
        (bestAcc ? "（最高精度 ±" + Math.round(bestAcc) + "m）" : ""), "on");
    if (count === 1 || q.length >= 10 || Date.now() - last > IV) send();
  }

  function onErr(e) {
    var c = e && e.code;
    if (c === 1) say("位置情報が「拒否」されています。ブラウザの設定で許可してください", "warn");
    else if (c === 2) say("位置を取得できません（アプリ内ブラウザの可能性）", "warn");
    else if (c === 3) say("測位がタイムアウト。再試行します", "warn");
    else say("測位エラー: " + ((e && e.message) || c), "warn");
    if (!gotFix && c !== 1) nudgeSoon();
  }

  function nudgeSoon() {
    if (nudge || !navigator.geolocation) return;
    nudge = setTimeout(function () {
      nudge = null;
      if (gotFix) return;
      navigator.geolocation.getCurrentPosition(onPos, function () {},
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
    }, 6000);
  }

  function showPerm() {
    var el = $("lt_perm");
    if (!el) return Promise.resolve("unknown");
    if (!navigator.permissions || !navigator.permissions.query) {
      el.textContent = "unknown"; el.className = "lt-dim";
      return Promise.resolve("unknown");
    }
    return navigator.permissions.query({ name: "geolocation" })
      .then(function (p) {
        el.textContent = p.state;
        el.className = p.state === "granted" ? "lt-on"
          : (p.state === "denied" ? "lt-warn" : "lt-dim");
        p.onchange = function () { showPerm(); };
        return p.state;
      })
      .catch(function () {
        el.textContent = "unknown"; el.className = "lt-dim";
        return "unknown";
      });
  }

  function checkInApp() {
    var ua = navigator.userAgent || "";
    var name = "";
    if (/Instagram/i.test(ua)) name = "Instagram";
    else if (/FBAN|FBAV/i.test(ua)) name = "Facebook";
    else if (/Line\//i.test(ua)) name = "LINE";
    else if (/Twitter/i.test(ua)) name = "X";
    if (!name) return;
    var box = $("lt_ia"), nm = $("lt_ia_name"), link = $("lt_safari");
    if (box) box.style.display = "block";
    if (nm) nm.textContent = name;
    if (link) {
      var ios = /iPhone|iPad|iPod/i.test(ua);
      link.href = ios ? location.href.replace(/^https:/, "x-safari-https:")
        : "intent://" + location.href.replace(/^https?:\/\//, "") +
          "#Intent;scheme=https;package=com.android.chrome;end";
    }
  }

  function ask() {
    return new Promise(function (res) {
      if (!navigator.geolocation) return res(false);
      navigator.geolocation.getCurrentPosition(
        function (p) { onPos(p); res(true); },
        function (e) { onErr(e); res(false); },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
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
    try {
      wid = navigator.geolocation.watchPosition(onPos, onErr,
        { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
    } catch (e) { wid = null; }
  }

  function restart() {
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    start();
  }

  function boot() {
    if (started) return;
    started = Date.now(); stopped = false;
    showPerm(); checkInApp(); readBatt(); keepAwake();
    if (!navigator.geolocation) { say("この端末は位置情報に非対応です", "warn"); return; }
    ask().then(function () {
      if (stopped) return;
      start();
      q.push({ ts: iso(Date.now()) });      // IPだけでも1点残す
      send({ kind: "open" });
      clock = setInterval(tick, 1000);
      sender = setInterval(function () {
        tick();
        if (q.length) send();
        else if (Date.now() - last > Math.max(30000, IV * 3)) send({ kind: "hb" });
        if (MAXMIN && Date.now() - started > MAXMIN * 60000) stop("時間上限");
      }, SEND_EVERY);
      say("記録を開始しました。この画面を開いている間ずっと送ります", "on");
      setTimeout(function () {
        if (!gotFix && !stopped) {
          say("まだ位置が取れていません。下の「再取得」をタップしてください", "warn");
        }
      }, 8000);
    });
  }

  function stop(why) {
    if (stopped) return;
    stopped = true; started = 0;
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    if (clock) clearInterval(clock);
    if (sender) clearInterval(sender);
    clock = sender = null;
    beacon("stop");
    say("停止しました" + (why ? "（" + why + "）" : "") + " 記録 " + count + " 点", "dim");
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { beacon("hb"); return; }
    if (!stopped) {
      keepAwake();
      send({ kind: "hb" });
      if (!gotFix) nudgeSoon();
    }
  });
  window.addEventListener("pagehide", function () { beacon("stop"); });
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    stopped = false;
    if (!started) started = Date.now();
    restart();
    send({ kind: "open" });
  });

  var go = $("lt_go"), sp = $("lt_stop"), cp = $("lt_copy");
  if (go) go.addEventListener("click", function () {
    if (stopped) { boot(); if (go) go.textContent = "再取得"; }
    else { gotFix = false; restart(); ask(); }
  });
  if (sp) sp.addEventListener("click", function () { stop("手動"); });
  if (cp) cp.addEventListener("click", function () {
    try { navigator.clipboard.writeText(location.href); } catch (e) {}
    cp.textContent = "コピーしました";
  });

  window.LT_LIVE = { start: boot, stop: stop, sid: SID };

  showPerm().then(function (st) {
    checkInApp();
    if (st === "denied") {
      if (go) go.textContent = "位置情報を許可して開始";
    } else {
      boot();                     // granted / unknown / prompt は自動開始
      if (go) go.textContent = "再取得";
    }
  });
})();