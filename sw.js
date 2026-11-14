/* 小股塔-2026 Service Worker：同源資源優先連線，離線使用快取 */
const CACHE='smallstockgift-2026-v3.7';
const SHELL=['./','./index.html','./stockgift_2026.csv','./manifest.webmanifest','./icon.svg'];
self.addEventListener('install', event => {
 event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate', event => {
 event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('smallstockgift-2026-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
 const req=event.request;
 if(req.method!=='GET'||new URL(req.url).origin!==self.location.origin)return;
 event.respondWith(fetch(req).then(resp=>{
  if(resp.ok){const copy=resp.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(req,copy)));}
  return resp;
 }).catch(()=>caches.match(req)));
});
