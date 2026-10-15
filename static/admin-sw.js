/**
 * V Notice - Service Worker for Admin Portal PWA
 * Strategy:
 *  - Admin Shell & Static Assets: Pre-cached + Network-first fallback to Cache
 *  - Admin HTML (/admin, /): Network-first for fresh state, offline shell fallback
 *  - REST APIs (/api/*): Network-only, NEVER cached
 *  - Authentication & Login (/login, /api/login, /api/logout, /api/me): Network-only, NEVER cached
 *  - File Uploads & Mutations: Network-only, NEVER cached
 *  - Media/Range requests (206 Partial Content): NEVER cached, pass through
 */

const ADMIN_SHELL_CACHE = 'vnotice-admin-shell-v1';

const ADMIN_SHELL_ASSETS = [
  '/admin',
  '/manifest.webmanifest',
  '/static/manifest.json',
  '/static/css/admin.css?v=12',
  '/static/js/admin.js?v=10',
  '/static/icons/icon-192.png',
  '/static/icons/icon-maskable-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-512.png',
  '/static/apple-touch-icon.png',
  '/static/favicon.png',
  '/static/favicon.svg',
  '/static/images/logo.svg',
  '/static/fonts/Inter-Regular.woff2',
  '/static/fonts/Inter-Bold.woff2',
  '/static/fonts/Outfit-Regular.woff2',
  '/static/fonts/Outfit-Bold.woff2'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(ADMIN_SHELL_CACHE).then((cache) => {
      return Promise.allSettled(
        ADMIN_SHELL_ASSETS.map((url) =>
          fetch(url, { cache: 'no-cache' }).then((res) => {
            if (res.ok && res.status !== 206) {
              return cache.put(url, res);
            }
          }).catch((err) => {
            console.warn('[Admin SW] Failed to precache:', url, err);
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
          if (key !== ADMIN_SHELL_CACHE) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // 1. Never cache non-GET requests (POST, PUT, DELETE, uploads)
  if (req.method !== 'GET') {
    return;
  }

  // 2. Never cache requests with a Range header (206 partial responses)
  if (req.headers.has('range')) {
    return;
  }

  const url = new URL(req.url);

  // 3. Never cache /api/* requests (all REST API endpoints are network-only)
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // 4. Never cache login, logout, or auth routes
  if (
    url.pathname === '/login' ||
    url.pathname.startsWith('/login/') ||
    url.pathname === '/logout' ||
    url.pathname.startsWith('/auth')
  ) {
    return;
  }

  // 5. Never cache uploads or media processing endpoints
  if (url.pathname.startsWith('/upload')) {
    return;
  }

  // 6. Admin HTML Navigation (/admin, /): Network-first with cache fallback
  if (req.mode === 'navigate' || url.pathname === '/admin' || url.pathname === '/') {
    event.respondWith(
      fetch(req).then(async (networkRes) => {
        if (networkRes && networkRes.ok && networkRes.status !== 206) {
          const cache = await caches.open(ADMIN_SHELL_CACHE);
          cache.put('/admin', networkRes.clone());
        }
        return networkRes;
      }).catch(async () => {
        const cache = await caches.open(ADMIN_SHELL_CACHE);
        const cached = await cache.match('/admin');
        if (cached) return cached;
        return new Response(
          '<!DOCTYPE html><html><head><title>Offline - V Notice Admin</title></head><body><h1>Offline</h1><p>V Notice Admin is currently offline. Please reconnect to the network.</p></body></html>',
          { status: 503, headers: { 'Content-Type': 'text/html' } }
        );
      })
    );
    return;
  }

  // 7. Static Assets & App Shell: Stale-While-Revalidate or Network-first
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest' || url.pathname === '/manifest.json') {
    event.respondWith(
      caches.open(ADMIN_SHELL_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const fetchPromise = fetch(req).then((networkRes) => {
          if (networkRes && networkRes.ok && networkRes.status !== 206) {
            cache.put(req, networkRes.clone());
          }
          return networkRes;
        }).catch(() => null);

        if (cached) {
          return cached;
        }
        const netRes = await fetchPromise;
        if (netRes) return netRes;
        return new Response('', { status: 404, statusText: 'Resource not found offline' });
      })
    );
    return;
  }
});
