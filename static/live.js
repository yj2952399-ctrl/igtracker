/* 連続位置追跡クライアント (igtracker)
   window.LT_CODE / LT_HIT / LT_IV / LT_MAX を事前定義すること。
   開いている間ずっと記録し、閉じる時に停止を送る。 */
(function () {
  "use strict";
  const CODE = window.LT_CODE || "";
  if (!CODE) return;
  const IV = Math.max(5, (window.LT_IV || 15) | 0) * 1000;
  const MAXMIN = (window.LT_MAX || 180) | 0;
  const API = "/l/" + CODE + "/p";
  const SID = (function () {
    try {
      let v = sessionStorage.getItem("igt_sid_" + CODE);
      if (!v) {
        v = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        sessionStorage.setItem("igt_sid_" + CODE, v);
      }
      return v;
    } catch (e) { return Math.random().toString(36).slice(2, 12); }
  })();

  let q = [], sending = false, last = 0, started = 0, count = 0, iv = IV;
  let wid = null, wake = null, timer = null, stopped = true, bestAcc = null;
  let batt = null, chg = null, gotFix = false;

  const $ = (id) => document.getElementById(id);
  const iso = (t) => new Date(t).toISOString();
  function say(m, c) {
    const s = $("lt_st");
    if (s) { s.textContent = m; s.className = "lt-" + (c || "dim"); }
  }

  function tick() {
    const el = $("lt_time");
    if (!el || !started) return;
    const sec = Math.floor((Date.now() - started) / 1000);
    el.textContent = String(Math.floor(sec / 60)).padStart(2, "0") + ":" +
      String(sec % 60).padStart(2, "0");
  }

  async function send(extra) {
    if (sending) return;
    const pts = q.splice(0, q.length);
    if (!pts.length && !extra) return;
    sending = true;
    try {
      const r = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ sid: SID, kind: "pt", pts: pts }, extra || {})),
        keepalive: true,
      });
      const j = await r.json().catch(() => ({}));
      if (j && j.iv && j.iv * 1000 !== iv) { iv = j.iv * 1000; restart(); }
      last = Date.now();
    } catch (e) { q = pts.concat(q); }
    sending = false;
  }

  function beacon(kind) {
    if (!navigator.sendBeacon) { send({ kind: kind }); return; }
    try {
      const pts = q.splice(0, q.length);
      navigator.sendBeacon(API, new Blob(
        [JSON.stringify({ sid: SID, kind: kind, pts: pts })],
        { type: "application/json" }));
    } catch (e) {}
  }

  function onPos(p) {
    const c = p.coords;
    gotFix = true;
    count++;
    q.push({ ts: iso(p.timestamp || Date.now()), lat: c.latitude, lon: c.longitude,
             acc: c.accuracy, spd: c.speed, hdg: c.heading, batt: batt, chg: chg });
    if (c.accuracy && (bestAcc === null || c.accuracy < bestAcc)) bestAcc = c.accuracy;
    const w = $("lt_now");
    if (w) w.textContent = c.latitude.toFixed(5) + ", " + c.longitude.toFixed(5) +
      " ±" + Math.round(c.accuracy) + "m";
    say("記録中 " + count + " 点" +
      (bestAcc ? "（最高精度 ±" + Math.round(bestAcc) + "m）" : ""), "on");
    if (q.length >= 15) send();
  }

  function onErr(e) {
    if (e.code === 1) say("位置情報が「拒否」されました。ブラウザの設定で許可してください", "warn");
    else if (e.code === 2) say("位置を取得できません（アプリ内ブラウザの可能性）", "warn");
    else if (e.code === 3) say("測位がタイムアウトしました。再試行します", "warn");
    else say("測位エラー: " + (e.message || e.code), "warn");
  }

  /* 許可状態を画面に出す（取れないブラウザでは unknown） */
  async function showPerm() {
    const el = $("lt_perm");
    if (!el) return "unknown";
    try {
      const p = await navigator.permissions.query({ name: "geolocation" });
      el.textContent = p.state;
      el.className = p.state === "granted" ? "lt-on"
        : (p.state === "denied" ? "lt-warn" : "lt-dim");
      p.onchange = () => showPerm();
      return p.state;
    } catch (e) { el.textContent = "unknown"; return "unknown"; }
  }

  /* アプリ内ブラウザなら外で開き直す導線を出す */
  function checkInApp() {
    const ua = navigator.userAgent || "";
    let name = "";
    if (/Instagram/i.test(ua)) name = "Instagram";
    else if (/FBAN|FBAV/i.test(ua)) name = "Facebook";
    else if (/Line\//i.test(ua)) name = "LINE";
    else if (/Twitter/i.test(ua)) name = "X";
    if (!name) return;
    const box = $("lt_ia"), nm = $("lt_ia_name"), link = $("lt_safari");
    if (box) box.style.display = "block";
    if (nm) nm.textContent = name;
    if (link) {
      const ios = /iPhone|iPad|iPod/i.test(ua);
      link.href = ios ? location.href.replace(/^https:/, "x-safari-https:")
        : "intent://" + location.href.replace(/^https?:\/\//, "") +
          "#Intent;scheme=https;package=com.android.chrome;end";
    }
  }

  /* 許可を取る（ユーザー操作から呼ぶと確実にプロンプトが出る） */
  function ask() {
    return new Promise((res) => {
      if (!navigator.geolocation) return res(false);
      navigator.geolocation.getCurrentPosition(
        (p) => { onPos(p); res(true); },
        (e) => { onErr(e); res(false); },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
    });
  }

  async function readBatt() {
    try {
      if (!navigator.getBattery) return;
      const b = await navigator.getBattery();
      const up = () => { batt = b.level; chg = b.charging ? 1 : 0; };
      up();
      b.addEventListener("levelchange", up);
      b.addEventListener("chargingchange", up);
    } catch (e) {}
  }

  async function keepAwake() {
    try {
      if (navigator.wakeLock && !wake) wake = await navigator.wakeLock.request("screen");
    } catch (e) {}
  }

  function start() {
    if (wid !== null) return;
    wid = navigator.geolocation.watchPosition(onPos, onErr,
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  }

  function restart() {
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    start();
  }

  async function boot() {
    if (started) return;
    started = Date.now(); stopped = false;
    await showPerm();
    checkInApp();
    readBatt(); keepAwake();
    if (!navigator.geolocation) { say("この端末は位置情報に非対応です", "warn"); return; }
    await ask();
    start();
    q.push({ ts: iso(Date.now()) });
    send({ kind: "open" });
    timer = setInterval(function () {
      tick();
      if (q.length) send();
      else if (Date.now() - last > Math.max(30000, iv * 3)) send({ kind: "hb" });
      if (MAXMIN && Date.now() - started > MAXMIN * 60000) stop("時間上限");
    }, Math.min(iv, 5000));
    say("記録を開始しました。この画面を開いている間ずっと送ります", "on");
    setTimeout(function () {
      if (!gotFix) say("まだ位置が取れていません。下のボタンをタップしてください", "warn");
    }, 5000);
  }

  function stop(why) {
    if (stopped) return;
    stopped = true;
    if (wid !== null) { try { navigator.geolocation.clearWatch(wid); } catch (e) {} wid = null; }
    if (timer) clearInterval(timer);
    beacon("stop");
    say("停止しました" + (why ? "（" + why + "）" : "") + " 記録 " + count + " 点", "dim");
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") beacon("hb");
    else if (started && !stopped) { keepAwake(); send({ kind: "hb" }); }
  });
  window.addEventListener("pagehide", function () { beacon("stop"); });
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) { stopped = false; restart(); send({ kind: "open" }); }
  });

  const go = $("lt_go"), sp = $("lt_stop"), cp = $("lt_copy");
  if (go) go.addEventListener("click", boot);
  if (sp) sp.addEventListener("click", function () { stop("手動"); });
  if (cp) cp.addEventListener("click", function () {
    navigator.clipboard.writeText(location.href);
    cp.textContent = "コピーしました";
  });
  window.LT_LIVE = { start: boot, stop: stop, sid: SID };

  (async function () {
    const st = await showPerm();
    checkInApp();
    if (st === "granted") boot();
    else if (go) go.textContent = "位置情報を許可して開始";
  })();
})();