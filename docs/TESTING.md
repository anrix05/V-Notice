# V Notice Testing & Verification Guide

## 1. Automated Test Suite (pytest)

Run the backend automated test suite:
```bash
pytest -v
```

### Coverage by Phase:
- **Phase 1 (Data Integrity & Storage):** `tests/test_storage_phase1.py`
  - Tests SQLite database initialization and WAL journal mode.
  - Tests one-time automatic migration from `notices.json` to SQLite with backup creation.
  - Tests `MediaStorageBackend` interface and `LocalMediaStorage` save/delete operations.
  - Tests Safe Media Garbage Collection (10-minute in-flight grace period).
  - Tests multi-screen filtering (`screen_id`) and creator tracking (`created_by`).

---

## 2. Manual Verification Checklist (Frontend & End-to-End)

### Phase 1: Data Integrity & Storage
- [ ] **One-Time Migration Verification:**
  1. Verify that `notices.db` exists in the project root/storage directory.
  2. Verify that `notices.json.bak` exists as an intact backup of the original notices.
  3. Start the application (`python app.py`) and confirm existing notices appear on `/` and `/display`.
- [ ] **Multi-Screen Filtering:**
  1. Open the Admin Portal at `/` (or `http://localhost:5001/`).
  2. Click **"+ New notice"**.
  3. Verify the **Target Screen** dropdown is present with "Default Screen".
  4. Type a new screen name or select default, fill headline, and submit.
  5. In the notices feed, use the **Screen:** dropdown to switch between "All Screens" and specific screens. Confirm filtering works immediately.
  6. Open `/display?screen=default` on another tab and confirm only notices targeted to `default` appear.
- [ ] **Safe Media Garbage Collection:**
  1. Upload a notice with an image attachment.
  2. Delete the notice.
  3. Verify that the media file is removed if it is no longer referenced by any notice.
  4. Create a dummy file in `media/test_inflight.png` with current timestamp; confirm GC skips it because age is < 10 minutes.
- [ ] **Render Ephemeral Warning:**
  1. Run `RENDER=true python -c "import config"` in a terminal.
  2. Confirm the visible warning message is printed to `stderr` detailing that data will be lost on container redeploy unless a persistent disk is attached.


### Phase 2: Security Checklist
- [ ] **Password Hashing & Constant Time:**
  1. Set `ADMIN_PASSWORD_HASH` using `werkzeug.security.generate_password_hash("testpass")`.
  2. Verify login succeeds with `"testpass"` and fails with wrong passwords.
- [ ] **Rate Limiting (5 Attempts in 10 Mins):**
  1. Attempt 5 failed logins sequentially.
  2. Confirm 6th attempt returns HTTP 429 with `Retry-After` header.
- [ ] **CSRF Token Protection:**
  1. Log into Admin Portal via browser session.
  2. Send a `POST /api/notices` mutation without `X-CSRF-Token` header.
  3. Confirm server rejects with HTTP 403 Forbidden.
  4. Include valid `X-CSRF-Token` from `/api/csrf-token` and confirm 201 Created.
- [ ] **Spoofed Media Upload Validation:**
  1. Rename a `.txt` file to `sample.jpg`.
  2. Attempt to upload via notice form.
  3. Confirm magic-byte sniffer rejects file with 400 Bad Request error.
- [ ] **Enumeration Protection:**
  1. Create a scheduled or expired notice.
  2. Access `/notice/<id>` without authentication and confirm HTTP 404 is returned.
  3. Access `/notice/<id>` with admin credentials and confirm notice details load.
- [ ] **Security Headers:**
  1. Inspect response headers on any route (`curl -I http://localhost:5000/`).
  2. Verify `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and `Content-Security-Policy` are present.
  3. Verify `X-Frame-Options: DENY` on admin routes.


- **Phase 3 (Kiosk Resilience & Offline):** `tests/test_kiosk_resilience_phase3.py`
  - Tests `/api/system-info` with `WEATHER_ENABLED=false` and custom `WEATHER_LABEL`.
  - Tests `PUBLIC_BASE_URL` propagation for Scan-to-Download QR generation.
  - Tests `URGENT_CHIME` toggle in `/api/system-info`.
  - Tests `/sw.js` route MIME type, `Service-Worker-Allowed: /` header, and cache controls.
  - Tests presence of self-hosted WOFF2 fonts and `@font-face` definitions with `font-display: swap`.
  - Tests presence and integrity of vendored `static/js/qrcode.min.js`.
  - Tests Chromium kiosk script flags (`--user-data-dir`, `--noerrdialogs`, `--kiosk`, no `--incognito`).

---

### Phase 3: Kiosk Resilience & Offline
- [ ] **Service Worker Offline Playback:**
  1. Open Chrome DevTools at `http://localhost:5000/display` (or `http://localhost:5000/`).
  2. In the **Application** tab under **Service Workers**, confirm `/sw.js` is active and running.
  3. Under **Cache Storage**, verify `vnotice-shell-v1` contains HTML, CSS, JS, and WOFF2 fonts.
  4. In DevTools **Network** tab, toggle **Offline**.
  5. Refresh the page; verify the display shell loads smoothly and continues rotating notices without errors.
- [ ] **Weather Graceful Degradation:**
  1. Run with `WEATHER_ENABLED=false` or disconnect network; verify `#header-weather` hides cleanly without displaying broken icons or error text.
- [ ] **Scan-to-Save QR Code:**
  1. Set `PUBLIC_BASE_URL=https://v-notice.onrender.com`.
  2. Verify the QR card at the bottom of the Up Next rail points to `https://v-notice.onrender.com/notice/<id>?download=1`.
- [ ] **Urgent Audio Chime & Video Muting:**
  1. Publish an urgent notice. With `URGENT_CHIME=true`, verify a soft two-tone chime sounds when the notice appears on stage.
  2. Publish a video notice. Verify the video plays seamlessly and is strictly muted.


- **Phase 4 (Sync Efficiency & ETag):** `tests/test_sync_efficiency_phase4.py`
  - Tests presence of valid `ETag` and `Cache-Control: no-cache` on `GET /api/notices`.
  - Tests conditional `If-None-Match` request returns HTTP `304 Not Modified` with empty body.
  - Tests dynamic `ETag` invalidation when notices are created, updated, or deleted.
  - Tests distinct `ETag` values for multi-screen notice queries.
  - Tests admin notices conditional polling with `ETag`.
  - Tests `/api/events` disabled (404) and enabled (`text/event-stream`).
  - Tests `/api/system-info` returns `poll_interval_seconds` and `sse_enabled`.

---

### Phase 4: Sync Efficiency
- [ ] **HTTP 304 Conditional Polling Verification:**
  1. Open Chrome DevTools Network tab on `http://localhost:5000/display`.
  2. Observe background requests to `/api/notices`.
  3. Verify that requests after the initial load return status **`304 Not Modified`** with `0 B` transferred.
  4. In the Admin Portal (`http://localhost:5001/` or `/`), publish or edit a notice.
  5. Verify the very next `/api/notices` request on the display immediately returns status **`200 OK`** with the updated notice set, and subsequent polls return `304`.
- [ ] **Adaptive Backoff & Offline Jitter:**
  1. Disconnect network or stop server (`Ctrl+C`); verify `#offline-badge` appears on display.
  2. Inspect console logs: verify poll retry interval expands progressively up to 60s with random jitter.
  3. Reconnect network / restart server: verify display recovers immediately on next poll or `online` event and `#offline-badge` disappears.
- [ ] **Admin Visibility Throttling:**
  1. Open Admin Portal, switch to another browser tab for 30 seconds.
  2. Switch back: verify an immediate sync occurs upon tab focus without UI lag.
