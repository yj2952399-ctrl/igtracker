/* 位置情報の取得をここに一本化（igtracker v2）

   設計方針：
   ・「許可ダイアログが出ない」＝すでに許可済みか拒否済み。それを画面に出す
   ・タイムアウトは長め（iOSの1点目は10〜30秒かかる）
   ・打ち切り→投げ直しを繰り返すと取得がリセットされるので、watchを主役にする
   ・どうしても取れないときは onFail を出して、呼び出し側が回線推定に落とす */
(function () {
  "use strict";
  if (window.LTGEO) return;

  var UA = navigator.userAgent || "";
  var IS_IOS = /iPhone|iPad|iPod/i.test(UA);
  var IS_ANDROID = /Android/i.test(UA);
  var INAPP = /Instagram/i.test(UA) ? "Instagram"
            : /FBAN|FBAV/i.test(UA) ? "Facebook"
            : /Line\//i.test(UA) ? "LINE"
            : /Twitter/i.test(UA) ? "X" : "";

  /* 長めのタイムアウト。途中で切らない */
  var STRAT = [
    { enableHighAccuracy: false, timeout: 20000, maximumAge: 300000 },
    { enableHighAccuracy: true,  timeout: 30000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 30000, maximumAge: Infinity },
    { timeout: 30000, maximumAge: 0 }
  ];
  var NUDGE_MS = 15000;     // 取れないときに軽くつつく間隔
  var GIVEUP_MS = 70000;    // これだけ取れなければ onFail

  var subs = [], failSubs = [], statusSubs = [];
  var inflight = false, tries = 0, running = false, startedAt = 0;
  var nudge = null, wid = null, watchHi = false, perm = "unknown";
  var lastCode = 0, lastFix = null, lastFixAt = 0, failed = false;

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

  /* 許可状態に応じた文言（＝ダイアログが出ない理由を伝える） */
  function permText() {
    if (perm === "granted") return "位置情報：許可済み（ダイアログは出ません）取得中…";
    if (perm === "denied") return "位置情報：このサイトでブロックされています";
    if (perm === "prompt") return "位置情報：許可を待っています…";
    return "位置情報：許可状態を確認しています…";
  }

  function checkPerm() {
    try {
      if (!navigator.permissions || !navigator.permissions.query) return;
      navigator.permissions.query({ name: "geolocation" }).then(function (p) {
        perm = p.state;
        if (!lastFix) stat(permText(), perm === "denied");
        try {
          p.onchange = function () {
            perm = p.state;
            if (!lastFix) stat(permText(), perm === "denied");
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
    startWatch(true);              // 取れたら高精度に切り替える
  }

  function onErr(e) {
    lastCode = (e && e.code) || 0;
    if (lastFix) return;
    if (lastCode === 1) {
      stat("位置情報：許可されていません", true);
      emitFail("denied");
      return;
    }
    if (!failed) stat(permText() + "（試行 " + (++tries) + " / code=" + lastCode + "）");
    if (elapsed() * 1000 > GIVEUP_MS && !failed) {
      stat("位置情報：端末が位置を出せていません（回線からの推定で記録します）", true);
      emitFail("unavailable");
    }
  }

  function one() {
    if (!navigator.geolocation) { emitFail("unsupported"); return; }
    if (!running || inflight) return;
    inflight = true;
    var o = STRAT[Math.min(tries, STRAT.length - 1)];
    var done = false;
    var to = setTimeout(function () {
      if (done) return; done = true; inflight = false;
      onErr({ code: 3 });
    }, (o.timeout || 20000) + 2500);
    try {
      navigator.geolocation.getCurrentPosition(
        function (p) { if (done) return; done = true; clearTimeout(to); inflight = false; ok(p); },
        function (e) { if (done) return; done = true; clearTimeout(to); inflight = false; onErr(e || { code: 2 }); },
        o);
    } catch (e) {
      clearTimeout(to); inflight = false;
      if (!done) { done = true; onErr({ code: 2 }); }
    }
  }

  /* watch が主役。エラーでは消さずに走らせ続ける */
  function startWatch(hi) {
    if (!navigator.geolocation) return;
    if (wid !== null && watchHi === !!hi) return;
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    watchHi = !!hi;
    try {
      wid = navigator.geolocation.watchPosition(
        function (p) { ok(p); },
        function (e) { onErr(e || { code: 2 }); },
        hi ? { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
           : { enableHighAccuracy: false, timeout: 20000, maximumAge: 300000 });
    } catch (e) { wid = null; }
  }

  function start() {
    if (running) return;
    running = true; failed = false; tries = 0; startedAt = now();
    stat(permText());
    checkPerm();
    startWatch(false);     // ★ 先にwatchを張る（粘るのはこちら）
    one();                 // ★ 呼び出し元のタップと同じタスクで1発目
    if (nudge) clearInterval(nudge);
    nudge = setInterval(function () {
      if (!running) return;
      if (lastFix && now() - lastFixAt < 20000) return;
      if (!inflight) one();
    }, NUDGE_MS);
  }

  function retry() {
    if (!running) { start(); return; }
    failed = false; tries = 0; startedAt = now();
    if (!lastFix) stat(permText());
    one();
    startWatch(false);
  }

  function stop() {
    running = false;
    if (nudge) { clearInterval(nudge); nudge = null; }
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
  }

  /* 設定手順の案内 */
  function hint() {
    if (INAPP) {
      return INAPP + " のブラウザでは位置情報が取れないことがあります。"
           + "右上のメニューから「" + (IS_IOS ? "Safariで開く" : "Chromeで開く")
           + "」を選んでください。";
    }
    if (IS_IOS) {
      return "設定アプリ →「プライバシーとセキュリティ」→「位置情報サービス」をON、"
           + "そのうえで 設定アプリ →「Safari」→「位置情報」→ このサイトを「許可」にしてください。"
           + "変更後はページを再読み込みしてください。";
    }
    if (IS_ANDROID) {
      return "アドレスバー左の鍵アイコン →「位置情報」→「許可」にしてください。"
           + "端末の設定 →「位置情報」もONか確認してください。";
    }
    return "ブラウザのアドレスバー左のアイコンから、このサイトの位置情報を「許可」にしてください。"
         + "PCの場合はOSの位置情報サービスもONにしてください。";
  }
  function showHint() {
    var b = document.getElementById("lt_help") || document.getElementById("ia");
    var t = document.getElementById("lt_help_t") || document.getElementById("ia_name");
    if (b) b.style.display = "block";
    if (t) t.textContent = hint();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && running && now() - lastFixAt > 10000) retry();
  });
  window.addEventListener("focus", function () {
    if (running && now() - lastFixAt > 10000) retry();
  });

  window.LTGEO = {
    start: start, retry: retry, stop: stop, hint: hint, showHint: showHint,
    subscribe: function (f) { if (subs.indexOf(f) < 0) subs.push(f); },
    subscribeFail: function (f) { if (failSubs.indexOf(f) < 0) failSubs.push(f); },
    subscribeStatus: function (f) { if (statusSubs.indexOf(f) < 0) statusSubs.push(f); },
    info: function () {
      return { running: running, perm: perm, tries: tries, elapsed: elapsed(),
               code: lastCode, hasFix: !!lastFix, inapp: INAPP,
               secure: !!window.isSecureContext, geo: !!navigator.geolocation };
    },
  };
})();