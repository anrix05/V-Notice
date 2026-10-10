# Architecture & Engineering Decisions (ADR)

## Decision 1: SQLite Storage with Write-Ahead Logging (WAL) Mode
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** The original storage engine read and wrote a single `notices.json` file under a threading Lock. This was prone to file corruption on sudden power loss (common on Raspberry Pi), prevented concurrent reads/writes, and did not scale cleanly with multi-worker/threaded Gunicorn servers.
- **Decision:** Transition from `notices.json` to standard library `sqlite3` using Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and `PRAGMA busy_timeout = 5000;`. Connections are managed per-request via Flask `g._db_conn` and automatically closed on `app.teardown_appcontext`.
- **Consequences:**
  - Zero added external dependencies (uses standard library `sqlite3`).
  - Concurrent readers do not block writers, and writers do not block readers.
  - Safe automatic migration from legacy `notices.json` with an atomic backup `notices.json.bak`.

## Decision 2: Pluggable MediaStorageBackend Interface
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** File uploads were saved directly to a local filesystem path. To prepare for cloud storage providers (such as Cloudflare R2 or AWS S3) without adding heavy SDK dependencies now, an abstraction was required.
- **Decision:** Define `MediaStorageBackend` with methods `save(file_obj, filename)`, `delete(filename)`, `exists(filename)`, `get_path(filename)`, and `url(filename)`. Implement `LocalMediaStorage(media_dir)` as the default.
- **Consequences:** Code in `storage.py` and `app.py` interacts only with the interface. An S3 or R2 backend can be dropped in later without modifying route or notice logic.

## Decision 3: Safe Media Garbage Collection with In-Flight Grace Period
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** Immediate deletion of unreferenced files on disk could delete files uploaded during in-flight form submissions or preview steps before the notice row is committed.
- **Decision:** Restrict garbage collection to files not referenced by any notice *and* whose file modification time is older than 10 minutes (`grace_period_seconds = 600`). Log every deleted unreferenced file at `INFO` level.
- **Consequences:** Protects concurrent or slow multi-part file uploads from race conditions while continuing to clean orphaned media.

## Decision 4: Multi-Screen Filtering Strategy
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** Institutional campuses need the ability to show different announcements in different corridors (e.g. `engineering-hall`, `library-lobby`, `canteen`).
- **Decision:** Add a `screens` table and `screen_id` column on `notices` defaulting to `'default'`. The display kiosk reads its target screen from `/display?screen=<id>`. The admin portal provides both a screen selector in the notice form and a filter in the feed header.


## Decision 5: Password Storage, Hashing & Constant-Time Fallback
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 2)
- **Context:** Storing passwords only in plaintext poses credential-theft risks, and standard string comparisons are vulnerable to timing attacks.
- **Decision:** Support `ADMIN_PASSWORD_HASH` using `werkzeug.security.check_password_hash`. If not set, fall back to `ADMIN_PASSWORD` compared strictly with `hmac.compare_digest` (constant-time). Emit a visible security warning on startup if the default password is active.

## Decision 6: In-Process Rate Limiting & Brute-Force Lockout
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 2)
- **Context:** Repeated automated brute-force attacks against `/api/login` could guess simple passwords or exhaust server CPU.
- **Decision:** Implement a lightweight, thread-safe in-process rate limiter without Redis. Cap failed login attempts at 5 per IP per 10 minutes (600s). Once locked, return HTTP 429 with `Retry-After` header. Successful logins clear failures. `X-Password` API requests are also rate-limited on invalid attempts.

## Decision 7: Session CSRF Tokens with API Header Exemption
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 2)
- **Context:** Mutation routes (`POST`, `PUT`, `DELETE`) authenticated by browser session cookies are vulnerable to Cross-Site Request Forgery (CSRF).
- **Decision:** Generate a 256-bit random hex CSRF token per session. Require and validate `X-CSRF-Token` on all session-authenticated mutations. Requests authenticated via `X-Password` headers are exempt from CSRF (stateless API clients) but rate-limited against brute force.

## Decision 8: Magic-Byte Sniffing & Server-Side Streaming
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 2)
- **Context:** Client-reported MIME types and file extensions can be spoofed, and loading 200MB files into memory causes memory exhaustion on low-RAM Raspberry Pi hardware (<60MB budget).
- **Decision:** Validate the first 64KB chunk against magic byte signatures for allowed types (`jpg`, `png`, `gif`, `webp`, `mp4`, `webm`). Generate unguessable server-side filenames (`f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"`). Stream chunks directly to disk without ever buffering the whole file in RAM.

## Decision 9: Enumeration Protection on Notice Routes
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 2)
- **Context:** Predictable IDs or public access to expired/scheduled notices allows competitors or unauthorized students to scrape upcoming exam questions or embargoed announcements.
- **Decision:** Generate 64-bit random URL-safe IDs (`secrets.token_urlsafe(8)`). Restrict `/notice/<id>` and `/notice/<id>/download` to return HTTP 404 for any notice not currently live, unless the caller is an authenticated administrator. Sanitize `created_by` and audit timestamps from public `/api/notices` output.


## Decision 10: Multi-Tier Service Worker Caching Strategy
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 3)
- **Context:** Raspberry Pi kiosk displays must survive flaky campus Wi-Fi or router reboots without crashing, displaying error screens, or stalling playback.
- **Decision:** Implement `/sw.js` with three distinct tiers:
  1. *App Shell (`vnotice-shell-v1`)*: Precaches HTML shell, styles, scripts, and local fonts. Falls back network-first to cache.
  2. *Media Cache (`vnotice-media-v1`)*: Cache-first for `/media/` assets, bounded to 50 items. Automatically evicts unreferenced media when fresh `/api/notices` manifests are received.
  3. *API Cache (`vnotice-api-v1`)*: Stale-while-revalidate for `/api/notices` and `/api/system-info`, keeping the display queue populated continuously during outages.

## Decision 11: Self-Hosted Fonts & Zero CDN Dependencies
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 3)
- **Context:** External Google Fonts link tags block rendering or cause FOIT (Flash of Invisible Text) when campus displays are air-gapped or disconnected from WAN.
- **Decision:** Download and vendor WOFF2 files for Inter and Outfit in `static/fonts/`. Declare `@font-face` with `font-display: swap` in stylesheets, removing all external font CDN calls.

## Decision 12: Silent Weather Degradation & Configurable Coordinates
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 3)
- **Context:** Remote weather APIs fail during network loss or DNS timeouts, which previously risked showing broken icons or error strings.
- **Decision:** Introduce `WEATHER_ENABLED`, `WEATHER_LABEL`, `WEATHER_LAT`, and `WEATHER_LON`. Requests enforce a strict 3-second timeout. Results are cached in `localStorage` for 60 minutes. If expired or network is unreachable, `#header-weather` hides completely and silently with no visual error.

## Decision 13: Web Audio API Urgent Chime & Strict Video Muting
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 3)
- **Context:** Displaying emergency notices can optionally notify nearby students via audio, but audio file loading fails offline and unmuted video playback disrupts corridors.
- **Decision:** Generate a synthetic two-tone chime (880Hz / 1046.5Hz) using the native `AudioContext` oscillator. Wrap playback in a silent exception handler to prevent browser autoplay policy rejections from breaking the rotation loop. Ensure all `<video>` notice elements have `muted = true` and `volume = 0`.
