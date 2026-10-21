/* 位置情報の取得をここに一本化（igtracker v1）
   ・呼び出し元のタップと同じタスクで1発目を投げる（ダイアログが出る条件）
   ・まず「回線ベース（低精度・高速）」→ 既定 → 高精度 → キャッシュ許可 の順で粘る
   ・同時に watchPosition も張って、取れるまで待ち続ける
   ・多重呼び出しは直列化（iOSで固まるのを防ぐ）
   ・どうしても取れないときは onFail を出して、呼び出し側が回線推定に落とせるようにする */
(function () {
  "use strict";
  if (window.LTGEO) return;

  /* 1番目が「端末のGPSを使わない回線ベース」なので、GPSが死んでる端末でも拾える */
  var STRAT = [
    { enableHighAccuracy: false, timeout: 6000,  maximumAge: 600000 },
    { timeout: 8000, maximumAge: 0 },
    { enableHighAccuracy: true,  timeout: 12000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: Infinity }
  ];
  var MAX_TRIES = 16;

  var subs = [], failSubs = [], statusSubs = [];
  var inflight = false, tries = 0, running = false, startedAt = 0, timer = null;
  var wid = null, watchHi = false, perm = "unknown";
  var lastCode = 0, lastMsg = "", lastFix = null, lastFixAt = 0, failed = false;

  function now() { return Date.now(); }
  function elapsed() { return startedAt ? Math.round((now() - startedAt) / 1000) : 0; }
  function stat(t, w) { statusSubs.forEach(function (f) { try { f(t, w); } catch (e) {} }); }
  function emitFix(p) {
    lastFix = p; lastFixAt = now(); failed = false;
    subs.forEach(function (f) { try { f(p); } catch (e) {} });
  }
  function emitFail(why) {
    if (failed) return;
    failed = true;
    failSubs.forEach(function (f) { try { f(why); } catch (e) {} });
  }

  function checkPerm() {
    try {
      if (!navigator.permissions || !navigator.permissions.query) return;
      navigator.permissions.query({ name: "geolocation" }).then(function (p) {
        perm = p.state;
        try {
          p.onchange = function () {
            perm = p.state;
            if (p.state === "granted") retry();
          };
        } catch (e) {}
      }).catch(function () {});
    } catch (e) {}
  }

  function ok(p) {
    if (!p || !p.coords || p.coords.latitude == null) return;
    tries = 0;
    emitFix(p);
    startWatch(true);              // 取れたら高精度に切り替えて精度を上げる
  }

  function onErr(e) {
    lastCode = (e && e.code) || 0;
    lastMsg = (e && e.message) || "";
    if (lastFix) return;
    if (lastCode === 1) {
      stat("位置情報：許可されていません（ブラウザの設定で許可してください）", true);
      emitFail("denied");
      if (timer) clearTimeout(timer);
      timer = setTimeout(one, 8000);       // 許可されたら拾えるようゆるく回す
      return;
    }
    tries++;
    if (tries >= MAX_TRIES) {
      stat("位置情報：端末が位置を出せていません（回線からの推定で記録します）", true);
      emitFail("unavailable");
      if (timer) clearTimeout(timer);
      timer = setTimeout(one, 10000);
      return;
    }
    stat("位置情報を取得中…（" + tries + "回目 / code=" + lastCode + "）");
    if (timer) clearTimeout(timer);
    timer = setTimeout(one, 900);
  }

  function one() {
    if (!navigator.geolocation) { emitFail("unsupported"); return; }
    if (!running || inflight) return;
    inflight = true;
    var o = STRAT[Math.min(tries, STRAT.length - 1)];
    var done = false;
    var to = setTimeout(function () {
      if (done) return; done = true; inflight = false;
      onErr({ code: 3, message: "js-timeout" });
    }, (o.timeout || 8000) + 1200);
    try {
      navigator.geolocation.getCurrentPosition(
        function (p) { if (done) return; done = true; clearTimeout(to); inflight = false; ok(p); },
        function (e) { if (done) return; done = true; clearTimeout(to); inflight = false; onErr(e || { code: 2 }); },
        o);
    } catch (e) {
      clearTimeout(to); inflight = false;
      if (!done) { done = true; onErr({ code: 2, message: String(e) }); }
    }
  }

  function startWatch(hi) {
    if (!navigator.geolocation) return;
    if (wid !== null && watchHi === !!hi) return;
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    watchHi = !!hi;
    try {
      wid = navigator.geolocation.watchPosition(
        function (p) { ok(p); },
        function (e) { if (!lastFix) onErr(e || { code: 2 }); },
        hi ? { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
           : { enableHighAccuracy: false, timeout: 10000, maximumAge: 30000 });
    } catch (e) { wid = null; }
  }

  function start() {
    if (running) return;
    running = true; failed = false; tries = 0; startedAt = now();
    stat("位置情報の許可を確認しています…");
    checkPerm();
    one();                 // ★ 呼び出し元のタップと同じタスクで投げる
    startWatch(false);     // 並行して粘る
  }

  function retry() {
    if (!running) { start(); return; }
    failed = false; tries = 0; startedAt = now();
    one();
    startWatch(false);
  }

  function stop() {
    running = false;
    if (timer) { clearTimeout(timer); timer = null; }
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && running && now() - lastFixAt > 8000) retry();
  });
  window.addEventListener("focus", function () {
    if (running && now() - lastFixAt > 8000) retry();
  });

  window.LTGEO = {
    start: start, retry: retry, stop: stop,
    subscribe: function (f) { if (subs.indexOf(f) < 0) subs.push(f); },
    subscribeFail: function (f) { if (failSubs.indexOf(f) < 0) failSubs.push(f); },
    subscribeStatus: function (f) { if (statusSubs.indexOf(f) < 0) statusSubs.push(f); },
    info: function () {
      return { running: running, perm: perm, tries: tries, elapsed: elapsed(),
               code: lastCode, msg: lastMsg, hasFix: !!lastFix,
               secure: !!window.isSecureContext, geo: !!navigator.geolocation };
    },
  };
})();