// Hogs & Dogs service worker: makes the game installable, keeps pictures cached, opens offline to the last version,
// and brings the game forward when a notification is tapped. The page itself always comes from the network first,
// so updates show up right away; pictures (content-hashed, never change) come from the cache first.
const CACHE='hd-v1';
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{const r=e.request,u=new URL(r.url);if(r.method!=='GET'||u.origin!==self.location.origin)return;
  if(u.pathname.startsWith('/assets/')){e.respondWith(caches.open(CACHE).then(async c=>{const hit=await c.match(r);if(hit)return hit;const n=await fetch(r);if(n.ok)c.put(r,n.clone());return n}));return}
  if(r.mode==='navigate'){e.respondWith(fetch(r).then(n=>{const cp=n.clone();caches.open(CACHE).then(c=>c.put('/',cp));return n}).catch(()=>caches.match('/')))}});
self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(ws=>ws.length?ws[0].focus():self.clients.openWindow('/')))});
