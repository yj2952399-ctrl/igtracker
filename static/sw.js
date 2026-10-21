/* igtracker Service Worker v2
   /static/ は「ネットワーク優先 + キャッシュ退避」。
   キャッシュ名 V を上げないと古い JS が配られ続けるので、修正時は V も必ず上げること。 */
const V = "igt-v2";

self.addEventListener("install", (e) => {
  e.waitUntil(self.skipWaiting());
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
  if (d.type === "skipwaiting") self.skipWaiting();
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

/* 静的資産はネットワーク優先。取れなければキャッシュ。 */
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  let u;
  try { u = new URL(req.url); } catch (err) { return; }
  if (u.origin !== self.location.origin) return;
  if (!u.pathname.startsWith("/static/")) return;

  e.respondWith(
    fetch(req).then((res) => {
      if (res && res.ok) {
        const cp = res.clone();
        caches.open(V).then((c) => c.put(req, cp)).catch(() => {});
      }
      return res;
    }).catch(async () => {
      const hit = await caches.match(req);
      return hit || new Response("", { status: 504, statusText: "offline" });
    })
  );
});