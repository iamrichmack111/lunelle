const CACHE='lunelle-v15-velvet-motion';
const PUBLIC=['/login','/signup','/static/style.css?v=15','/static/editorial.css?v=15','/static/core.css?v=15','/static/vibe.css?v=15','/static/app.js?v=15','/static/icon.svg?v=15','/static/manifest.webmanifest?v=15'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(PUBLIC).catch(()=>{})).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const req=event.request,url=new URL(req.url);
  if(req.method!=='GET'||url.origin!==location.origin)return;
  const privatePath=/^\/(dashboard|calendar|compare|discoveries|wrapped|insights|journal|settings|medications|products|recap|doctor-summary|history|astrology|sky|api\/sky|log|unlock|backup\.json|export\.csv)/.test(url.pathname);
  if(privatePath)return;
  event.respondWith(fetch(req).then(res=>{const copy=res.clone();if(res.ok)caches.open(CACHE).then(c=>c.put(req,copy));return res;}).catch(()=>caches.match(req).then(r=>r||caches.match('/'))));
});
