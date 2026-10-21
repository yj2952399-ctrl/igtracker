/* 位置情報の取得をここに一本化（igtracker v3）

   設計方針：
   ・プロンプトを確実に出すため、1発目は「ユーザー操作と同じタスク」で1回だけ投げる
   ・watchPosition を同時に投げない
     （Safari は位置情報セッションを同時に1本しか扱えず、初回fixが返らなくなる）
     watch は 1.5 秒後に別タスクで張る
   ・見切り（GIVEUP）の基準は「最初に start した時刻」。
     retry で巻き戻さない（これが「許可済みなのに未取得のまま」の原因だった）
   ・許可状態は permissions API が使えれば表示に使う（Safari は信用しすぎない）
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

  /* 1発目は軽い条件。取れたら高精度 watch に切り替える */
  var FIRST = { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 };
  var NEXT = [
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 0 },
    { enableHighAccuracy: true,  timeout: 20000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 25000, maximumAge: Infinity }
  ];
  var WATCH_LO = { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 };
  var WATCH_HI = { enableHighAccuracy: true,  timeout: 20000, maximumAge: 0 };

  var WATCH_DELAY = 1500;   // 1発目と watch をぶつけないための待ち
  var NUDGE_MS    = 20000;  // 取れないときのやり直し間隔
  var GIVEUP_MS   = 60000;  // 最初の start からこれだけ取れなければ onFail

  var subs = [], failSubs = [], statusSubs = [];
  var inflight = false, tries = 0, running = false;
  var firstStartAt = 0, startedAt = 0, lastFixAt = 0, lastFix = null;
  var wid = null, watchHi = null, watchTimer = null, nudge = null;
  var perm = "unknown", lastCode = 0, failed = false;

  function now() { return Date.now(); }
  function sinceStart() {
    return firstStartAt ? Math.round((now() - firstStartAt) / 1000) : 0;
  }
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

  function onErr(e, fromWatch) {
    lastCode = (e && e.code) || 0;
    if (lastFix) return;
    if (lastCode === 1) {
      stat("位置情報：許可されていません", true);
      emitFail("denied");
      return;
    }
    if (!fromWatch) tries++;
    if (!failed) stat(permText() + "（試行 " + tries + " / code=" + lastCode + "）");
    /* ★ 見切りは firstStartAt 基準。retry で巻き戻らない */
    if (firstStartAt && now() - firstStartAt > GIVEUP_MS && !failed) {
      stat("位置情報：端末が位置を出せていません（回線からの推定で記録します）", true);
      emitFail("unavailable");
    }
  }

  /* 1発だけ投げる。同時実行しない */
  function one(o) {
    if (!navigator.geolocation) { emitFail("unsupported"); return; }
    if (!running || inflight) return;
    inflight = true;
    o = o || FIRST;
    var done = false;
    var to = setTimeout(function () {
      if (done) return; done = true; inflight = false;
      onErr({ code: 3 }, false);
    }, (o.timeout || 15000) + 2500);
    try {
      navigator.geolocation.getCurrentPosition(
        function (p) { if (done) return; done = true; clearTimeout(to); inflight = false; ok(p); },
        function (e) { if (done) return; done = true; clearTimeout(to); inflight = false; onErr(e || { code: 2 }, false); },
        o);
    } catch (e) {
      clearTimeout(to); inflight = false;
      if (!done) { done = true; onErr({ code: 2 }, false); }
    }
  }

  /* watch は張りっぱなし。精度レベルが変わるときだけ作り直す */
  function startWatch(hi) {
    if (!navigator.geolocation) return;
    hi = !!hi;
    if (wid !== null && watchHi === hi) return;
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    watchHi = hi;
    try {
      wid = navigator.geolocation.watchPosition(
        function (p) { ok(p); },
        function (e) { onErr(e || { code: 2 }, true); },
        hi ? WATCH_HI : WATCH_LO);
    } catch (e) { wid = null; watchHi = null; }
  }

  function start() {
    if (running) return;
    running = true; failed = false; tries = 0;
    firstStartAt = now(); startedAt = now();
    stat(permText());
    checkPerm();
    one(FIRST);                                  // ★ タップと同じタスクで1発目
    if (watchTimer) clearTimeout(watchTimer);
    watchTimer = setTimeout(function () {         // ★ 別タスクで watch を張る
      watchTimer = null;
      if (running && wid === null) startWatch(false);
    }, WATCH_DELAY);
    if (nudge) clearInterval(nudge);
    nudge = setInterval(function () {
      if (!running || inflight) return;
      if (lastFix && now() - lastFixAt < NUDGE_MS) return;
      if (firstStartAt && now() - firstStartAt > GIVEUP_MS) return;
      one(NEXT[Math.min(tries, NEXT.length - 1)]);
    }, NUDGE_MS);
  }

  function retry() {
    if (!running) { start(); return; }
    failed = false; tries = 0;
    if (!firstStartAt) firstStartAt = now();
    startedAt = now();                 // 表示用のみ。firstStartAt は触らない
    if (!lastFix) stat(permText());
    if (wid === null && !watchTimer) startWatch(false);
    one(NEXT[0]);
  }

  function stop() {
    running = false;
    if (nudge) { clearInterval(nudge); nudge = null; }
    if (watchTimer) { clearTimeout(watchTimer); watchTimer = null; }
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    watchHi = null;
  }

  /* 設定手順の案内 */
  function hint() {
    if (INAPP && INAPP !== "LINE") {
      return INAPP + " のブラウザでは位置情報が取れないことがあります。"
           + "右上のメニューから「" + (IS_IOS ? "Safariで開く" : "Chromeで開く")
           + "」を選んでください。";
    }
    if (IS_IOS) {
      return "設定アプリ →「プライバシーとセキュリティ」→「位置情報サービス」をON、"
           + "その中の「Safari Webサイト」を「確認」ではなく「使用中のみ許可」にしてください。"
           + "（「確認」のままだとダイアログが出ないことがあります）"
           + "変更後はページを再読み込みしてください。";
    }
    if (IS_ANDROID) {
      return "アドレスバー左の鍵アイコン →「位置情報」→「許可」にしてください。"
           + "端末の設定 →「位置情報」もONか確認してください。";
    }
    return "システム設定 →「プライバシーとセキュリティ」→「位置情報サービス」をONにし、"
         + "一覧の「Safari」にチェックを入れてください。"
         + "そのうえで Safari のアドレスバー左のアイコンから、このサイトの位置情報を「許可」にしてください。";
  }
  function showHint() {
    var b = document.getElementById("lt_help") || document.getElementById("ia");
    var t = document.getElementById("lt_help_t") || document.getElementById("ia_name");
    if (b) b.style.display = "block";
    if (t) t.textContent = hint();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && running && now() - lastFixAt > 12000) retry();
  });
  window.addEventListener("focus", function () {
    if (running && now() - lastFixAt > 12000) retry();
  });

  window.LTGEO = {
    start: start, retry: retry, stop: stop, hint: hint, showHint: showHint,
    subscribe: function (f) { if (subs.indexOf(f) < 0) subs.push(f); },
    subscribeFail: function (f) { if (failSubs.indexOf(f) < 0) failSubs.push(f); },
    subscribeStatus: function (f) { if (statusSubs.indexOf(f) < 0) statusSubs.push(f); },
    info: function () {
      return { running: running, perm: perm, tries: tries, elapsed: sinceStart(),
               code: lastCode, hasFix: !!lastFix, inapp: INAPP,
               secure: !!window.isSecureContext, geo: !!navigator.geolocation };
    },
  };
})();