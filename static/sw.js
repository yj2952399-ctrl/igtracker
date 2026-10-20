/* igtracker Service Worker: 静的資産のキャッシュ + タブを閉じた後の定期 ping */
const V = "igt-v1";
const SHELL = ["/static/keepalive.js", "/static/live.js", "/static/spy.js",
               "/static/collect.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(V).then((c) => Promise.all(
      SHELL.map((u) => c.add(u).catch(() => {}))
    )).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function idb() {
  return new Promise((res) => {
    try {
      const r = indexedDB.open("igt", 1);
      r.onupgradeneeded = () => { r.result.createObjectStore("kv"); };
      r.onsuccess = () => res(r.result);
      r.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}
async function setKV(k, v) {
  const d = await idb();
  if (!d) return;
  try { d.transaction("kv", "readwrite").objectStore("kv").put(v, k); } catch (e) {}
}
async function getKV(k) {
  const d = await idb();
  if (!d) return null;
  return new Promise((res) => {
    try {
      const t = d.transaction("kv").objectStore("kv").get(k);
      t.onsuccess = () => res(t.result);
      t.onerror = () => res(null);
    } catch (e) { res(null); }
  });
}

self.addEventListener("message", (e) => {
  const d = e.data || {};
  if (d.type === "code") {
    setKV("code", d.code);
    setKV("hit", d.hit || 0);
  }
});

async function ping() {
  const code = await getKV("code");
  if (!code) return;
  const hit = (await getKV("hit")) || 0;
  try {
    await fetch("/s/" + encodeURIComponent(code) + "/ping?hit=" + hit,
                { cache: "no-store" });
  } catch (e) {}
}

self.addEventListener("periodicsync", (e) => {
  if (e.tag === "igt-ping") e.waitUntil(ping());
});
self.addEventListener("sync", (e) => { e.waitUntil(ping()); });

self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (!u.pathname.startsWith("/static/")) return;
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request).then((res) => {
      const cp = res.clone();
      caches.open(V).then((c) => c.put(e.request, cp)).catch(() => {});
      return res;
    }).catch(() => r))
  );
});