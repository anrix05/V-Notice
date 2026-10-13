/**
 * V Notice - Service Worker for Kiosk Offline Resilience
 * Strategy:
 *  - Shell & Fonts: Precaching + Network-first fallback to Cache
 *  - Media: Cache-first, bounded to 50 items, orphan eviction on /api/notices
 *  - API (/api/notices, /api/system-info): Stale-While-Revalidate
 */

const SHELL_CACHE = 'vnotice-shell-v1';
const MEDIA_CACHE = 'vnotice-media-v1';
const API_CACHE = 'vnotice-api-v1';
const MAX_MEDIA_ITEMS = 50;

const SHELL_ASSETS = [
  '/',
  '/admin',
  '/display',
  '/static/manifest.json',
  '/static/css/admin.css?v=5',
  '/static/js/admin.js',
  '/static/css/display.css',
  '/static/js/display.js',
  '/static/js/qrcode.min.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/images/logo.svg',
  '/static/favicon.png',
  '/static/fonts/Inter-Regular.woff2',
  '/static/fonts/Inter-Bold.woff2',
  '/static/fonts/Outfit-Regular.woff2',
  '/static/fonts/Outfit-Bold.woff2'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => {
      return Promise.allSettled(
        SHELL_ASSETS.map((url) =>
          fetch(url).then((res) => {
            if (res.ok) {
              return cache.put(url, res);
            }
          }).catch((err) => {
            console.warn('[SW] Failed to precache:', url, err);
          })
        )
      );
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (![SHELL_CACHE, MEDIA_CACHE, API_CACHE].includes(key)) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

async function trimCache(cacheName, maxItems) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length > maxItems) {
      const toDelete = keys.slice(0, keys.length - maxItems);
      for (const req of toDelete) {
        await cache.delete(req);
      }
    }
  } catch (e) {
    console.warn('[SW] Cache trim error:', e);
  }
}

async function evictOrphanedMedia(activeNotices) {
  try {
    if (!Array.isArray(activeNotices)) return;
    const activeMediaPaths = new Set();
    activeNotices.forEach((n) => {
      if (n && n.media_url) {
        try {
          const u = new URL(n.media_url, self.location.origin);
          activeMediaPaths.add(u.pathname);
        } catch (e) {
          activeMediaPaths.add(n.media_url);
        }
      }
    });

    const cache = await caches.open(MEDIA_CACHE);
    const requests = await cache.keys();
    for (const req of requests) {
      try {
        const u = new URL(req.url);
        if (u.pathname.startsWith('/media/')) {
          if (!activeMediaPaths.has(u.pathname)) {
            await cache.delete(req);
          }
        }
      } catch (e) {}
    }
  } catch (err) {
    console.warn('[SW] Orphan media cleanup failed:', err);
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // 1. Media requests (/media/*): Cache-first bounded
  if (url.pathname.startsWith('/media/')) {
    event.respondWith(
      caches.open(MEDIA_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        if (cached) return cached;
        try {
          const networkRes = await fetch(req);
          if (networkRes && networkRes.ok) {
            cache.put(req, networkRes.clone());
            trimCache(MEDIA_CACHE, MAX_MEDIA_ITEMS);
          }
          return networkRes;
        } catch (err) {
          return cached || new Response('', { status: 404, statusText: 'Offline media missing' });
        }
      })
    );
    return;
  }

  // 2. API requests (/api/notices, /api/system-info): Stale-While-Revalidate
  if (url.pathname.startsWith('/api/notices') || url.pathname.startsWith('/api/system-info')) {
    event.respondWith(
      caches.open(API_CACHE).then(async (cache) => {
        const cachedPromise = cache.match(req);
        const networkPromise = fetch(req).then((networkRes) => {
          if (networkRes && networkRes.ok) {
            cache.put(req, networkRes.clone());
            if (url.pathname.startsWith('/api/notices')) {
              networkRes.clone().json().then((data) => {
                evictOrphanedMedia(data);
              }).catch(() => {});
            }
          }
          return networkRes;
        }).catch(() => null);

        const cachedRes = await cachedPromise;
        if (cachedRes) {
          networkPromise;
          return cachedRes;
        }
        const netRes = await networkPromise;
        if (netRes) return netRes;
        return new Response('[]', { headers: { 'Content-Type': 'application/json' } });
      })
    );
    return;
  }

  // 3. Navigation / Shell / Static assets: Network-first with cache fallback
  if (req.mode === 'navigate' || url.pathname.startsWith('/static/') || url.pathname === '/' || url.pathname === '/display' || url.pathname.startsWith('/admin')) {
    event.respondWith(
      fetch(req).then(async (networkRes) => {
        if (networkRes && networkRes.ok) {
          const cache = await caches.open(SHELL_CACHE);
          cache.put(req, networkRes.clone());
        }
        return networkRes;
      }).catch(async () => {
        const cache = await caches.open(SHELL_CACHE);
        const match = await cache.match(req);
        if (match) return match;
        if (req.mode === 'navigate') {
          if (url.pathname.startsWith('/admin')) {
            return (await cache.match('/admin')) || (await cache.match('/'));
          }
          return (await cache.match('/display')) || (await cache.match('/'));
        }
        return new Response('Offline', { status: 503, statusText: 'Offline' });
      })
    );
    return;
  }
});
