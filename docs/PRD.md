# Product Requirements Document (PRD) — V Notice

**Document Version:** 2.2.0  
**Status:** Production Hardened & Fully Verified (Phases 1-8 Complete)  
**Author:** V Notice Development Team  
**Last Updated:** October 15, 2026  

---

## 1. Executive Summary

**V Notice** is an enterprise-grade, offline-first smart digital notice board and campus announcement system purpose-built for college departments, academic corridors, and institutional kiosks. Built on a lightweight, high-performance Python Flask and Gunicorn backend, V Notice delivers crystal-clear announcement rotations on standard 18"–22" monitors, Smart TVs, and Raspberry Pi kiosks, while providing faculty and administrators with an intuitive, 30-second mobile-friendly publishing dashboard.

V Notice operates seamlessly across two deployment paradigms:
1. **Permanent Cloud Hosting (Render / Railway):** Free, 24/7 cloud deployment with global HTTPS accessibility (`https://v-notice.onrender.com`). Faculty can publish notices from home or mobile devices anywhere in the world, while physical campus displays sync in real time.
2. **Local / Air-Gapped Campus Hardware (Raspberry Pi / Local Network):** offline-capable; weather and external links degrade gracefully, with dual-port operation, local storage garbage collection, and encrypted Cloudflare tunnel capabilities.

---

## 2. Problem Statement & User Personas

### 2.1 The Problem
1. **Paper Bulletin Inefficiency:** Outdated physical flyers, cluttered boards, manual cleanup overhead, and inability to convey urgent exam, weather, or emergency alerts immediately.
2. **Commercial Signage Fragility & Costs:** SaaS digital signage platforms require recurring monthly subscriptions, crash during network outages, and fail on low-bandwidth college networks.
3. **Complex Administrative Dashboards:** Faculty members resist posting updates when forced through convoluted enterprise CMS dashboards.
4. **Media Distortion & Video Lag:** Uploaded flyers and posters are frequently stretched or cropped awkwardly, and streaming videos lag on low-spec kiosk hardware.

### 2.2 Target Personas

| Persona | Role | Primary Goal | Pain Points Addressed |
| :--- | :--- | :--- | :--- |
| **Faculty & Department Staff** | Content Creator | Publish notices from laptop or smartphone in under 30 seconds from any network. | Permanent cloud admin URL, 1-click expiration presets, intuitive upload dropzone. |
| **College Students** | Consumer / Viewer | View schedules, exam rooms, and placement notices at a glance from 5–10 meters. | 60px high-contrast typography, QR code for 1-tap mobile flyer download. |
| **Campus IT / Lab Assistants** | Hardware Maintainer | Deploy hardware with zero ongoing maintenance. | Automated Raspberry Pi Chromium kiosk autostart, local media garbage collection, 24/7 keep-awake monitoring. |

---

## 3. Product Goals & Success Metrics

* **Zero-Downtime Resilience:** System continues smooth playback from local browser cache if Wi-Fi or Ethernet drops.
* **Instant Cloud Sync:** Notices published from faculty phones reflect on campus display screens within seconds.
* **Smooth Video Playback:** Background media preloading eliminates buffering stutter on high-definition video notices.
* **Effortless Scheduling:** Faculty can set expiration in 1 click (`End of Today`, `3 Days`, `1 Week`, `1 Month`) without complex calendar pickers.
* **Lightweight Hardware Footprint:** Entire backend footprint runs within <60MB RAM on Raspberry Pi 3B+/4/5 or free-tier cloud instances.

---

## 4. System Architecture & Modes of Operation

V Notice supports two production modes:

### 4.1 Mode A: Cloud Unified Server (Render / Railway)
A single-port WSGI architecture powered by Gunicorn (`gunicorn app:unified_app -c gunicorn.conf.py`) bound to the platform's dynamic `$PORT`:
* **Admin Portal (`/` and `/admin`):** Secure password-authenticated dashboard for faculty to manage announcements.
* **Display Kiosk (`/display`):** Clean, unauthenticated digital signage board running in full-screen on lobby TVs or Raspberry Pis.
* **Smart Dual API (`/api/notices`):** Authenticated requests return all notices (`active`, `scheduled`, `expired`); public kiosk calls return only active announcements.
* **Permanent Domain:** `https://v-notice.onrender.com` (kept active 24/7 via `/api/health` automated pings).

### 4.2 Mode B: Local Dual-Port Air-Gapped Server (Raspberry Pi / Laptop)
Enforces physical network port isolation for maximum local security:
```
+-------------------------------------------------------------------------+
|                              Raspberry Pi / Local OS                    |
|                                                                         |
|            Port 5000 (Display Kiosk)         Port 5001 (Admin Portal)   |
|            - display.html (Read-Only)        - admin.html (Write Access)|
|            - GET /api/notices (Active only)  - Full REST CRUD API       |
|            - No authentication needed        - Password / Session Auth  |
|            - Connected to Lobby Monitor      - Accessed by Faculty Wi-Fi|
+-------------------------------------------------------------------------+
```

### 4.3 Security Isolation Guarantee
* **No Mutation Endpoints on Public Display:** The Display screen contains zero administrative endpoints. Tampering with kiosk terminals cannot alter notices.
* **Session & Header Authentication:** All mutation endpoints (`POST`, `PUT`, `DELETE`) require a valid session or `X-Password` header validated against `ADMIN_PASSWORD`.

---

## 5. Functional Requirements & Features

### 5.1 Content Types & Intelligent Media Handling
* **Text Announcements:** Headline (up to 120 chars) + optional body text. Dynamically sized for corridor legibility.
* **Image Posters:** JPG, PNG, WEBP, GIF up to 200MB.
  * **Aspect Ratio Guidance:** Admin shows explicit recommendations: `16:9 Landscape` for full-screen fit or `3:4 / 4:3 Poster` for flyers.
  * **Ambient Frosted Backdrop:** Vertical posters automatically receive Apple TV-style ambient frosted backdrop blur, preventing letterboxing on 16:9 widescreen monitors.
* **Video Announcements:** MP4 or WEBM video up to 200MB.
  * **Audio Playback Policy:** Videos play with sound ONLY if the notice has sound enabled (`notice.play_sound: true`), the screen has sound enabled (`screen.sound_enabled: 1`), and the browser environment allows audio playback (`audio_ready: true`). In all other cases, videos play strictly muted (`muted=true, volume=0`).
  * The background preloaded next video must stay strictly muted and never emit sound. On slide transition, audio cuts off cleanly with zero tail.
  * Duration field is automatically hidden during video upload (duration matches the video clip length).
* **High-Performance Video Buffering Engine:**
  * **Background Preloader (`preloadNextMedia`):** While notice $N$ is playing, notice $N+1$'s video/image is preloaded in the background into browser memory.
  * **24-Hour Client Caching:** `Cache-Control: public, max-age=86400` headers ensure videos play from local cache on subsequent rotations with zero internet latency.

### 5.2 Priority Management & Urgent Takeover
* **Normal:** Cyclical rotation with configurable slide duration (default 10s).
* **Info:** Highlighted with a sleek blue informational badge in rotation.
* **Urgent Takeover:**
  * Immediately overrides all standard notices on the corridor screen.
  * Flashes high-visibility crimson banner with emergency audio chime.
  * Swaps header brand logo to the distinct Concept B mono-dot variant featuring a crimson `#EF4444` notification dot notched into the right stem.
  * Exits takeover automatically once expired or marked normal.

### 5.3 Schedule & Expiration Engine
* **One-Click "Now" Button:** Sets start timestamp immediately.
* **Quick Duration Presets:** One-tap presets for `End of Today` (23:59), `3 Days`, `1 Week`, `2 Weeks`, and `1 Month`.
* **Live Schedule Summary:** Real-time human-readable reassurance (e.g. `Active immediately • Ends Wednesday, 14 Oct at 11:59 PM (3 days)`).
* **Automatic Expiration Filtering:** Display server strictly serves notices where `start <= currentTime <= end`.

### 5.4 Automatic Media Garbage Collection (Storage Hygiene)
* When a notice is deleted or expired, the backend storage engine scans referenced media.
* Any unreferenced media files in `media/` are automatically deleted from disk to prevent Raspberry Pi SD card exhaustion.

### 5.5 Corridor Readability & "Up Next" Rail
* **Widescreen Monitor Support (18"–22" 1080p Full HD):** Dynamic viewport typography (up to 64px headlines).
* **Dynamic "Up Next" Queue:** Scales dynamically based on screen height, showing upcoming announcements with smooth overflow and `+ X more in rotation` badge.
* **Campus Weather & Clock:** Live campus weather widget locked to Mumbai (`19.0760 N, 72.8777 E`) by default, with clean Unicode temperature and condition icons (`☀️ 30°C MUMBAI`).
* **Cloud-Aware Dynamic QR Code:** Generates a real-time QR code on the kiosk rail linking to the public route `/n/<id>`. Labeled "Scan to view" with subline "Open this notice on your phone". Never forces an auto-download; allows viewers to inspect the full notice, view media, or selectively save to their phone.

---

## 6. Non-Functional Requirements

| Metric | Target Specification |
| :--- | :--- |
| **Response Latency** | API responses <30ms locally, <200ms over cloud HTTPS |
| **Real-time Sync** | Kiosk polls updates every 3 seconds for immediate addition/deletion feedback |
| **Memory Footprint** | Python Flask process <60MB RAM usage |
| **Offline Resilience** | Display operates indefinitely from browser cache without network connection |
| **Browser Compatibility** | Chrome, Chromium 90+, Edge, Firefox, Safari (Mobile & Desktop) |
| **Storage Reliability** | Atomic JSON writes with `.backup.json` fallback on power outage |

---

## 7. Deployment & Operations

### 7.1 Cloud Hosting (Render)
* **Start Command:** `gunicorn app:unified_app -c gunicorn.conf.py`
* **Build Command:** `pip install -r requirements.txt`
* **Zero-Downtime Keep-Awake:** Automated cron ping every 10 minutes (`https://v-notice.onrender.com/api/health`) via `cron-job.org` prevents free tier spin-down.

### 7.2 Raspberry Pi Kiosk Setup
* **Zero-Server Client Setup:** Connect Raspberry Pi to lobby screen and autostart Chromium in kiosk mode:
  ```ini
  [Desktop Entry]
  Type=Application
  Name=V-Notice Display
  Exec=chromium-browser --noerrdialogs --disable-infobars --kiosk --incognito https://v-notice.onrender.com/display
  ```
* **Full Local Server Setup:** Run `install_rpi.sh` to install local systemd service (`vnotice.service`) for air-gapped campus environments.


---

## 10. Production Hardening & Verification Status (Phases 1–7)

| Phase | Milestone | Status | Key Verifications |
| :--- | :--- | :---: | :--- |
| **Phase 1** | Data Integrity & Storage | ✅ Completed | SQLite WAL mode, auto-migration, `MediaStorageBackend`, 10-min safe GC grace period, multi-screen filtering. |
| **Phase 2** | Security Hardening | ✅ Completed | Timing-safe auth, rate limiting (5 attempts/10 min lockout), CSRF tokens, magic byte sniffing, anti-enumeration. |
| **Phase 3** | Kiosk Resilience & Offline | ✅ Completed | Service Worker app shell caching, self-hosted WOFF2 fonts, silent weather degradation (60m TTL), offline QR codes. |
| **Phase 4** | Sync Efficiency | ✅ Completed | Deterministic SHA-256 ETag, HTTP 304 Not Modified, adaptive backoff with jitter, optional SSE stream. |
| **Phase 5** | Display UX | ✅ Completed | 280ms card transitions, GPU-accelerated ticker marquee, urgent takeover state glow, responsive 18"–22" typography. |
| **Phase 6** | Admin UX | ✅ Completed | Audit Logs viewer modal, rate-limit 429 countdown, pre-upload dropzone validation, 1-click presets. |
| **Phase 7** | Quality & Observability | ✅ Completed | Comprehensive `/api/health` check, zero-dependency RSS memory profiling (<60MB), structured request logging, 44 pytest tests. |
| **Phase 8** | Public Notice Page & Display QR | ✅ Completed | Mobile-first `/n/<id>` route, `/n/<id>/file` attachment streaming, zero-leakage 404 diffs, Axe-core zero contrast violations, and QR barcode decode tests. |


## 9. Department-Wise Display Screens & Multi-Target Architecture (v2.1)

### 9.1 Overview & Auditing Model
V Notice supports department-specific digital displays where each department corresponds to a physical screen:
- `CMPN` — Computer Engineering
- `INFT` — Information Technology
- `EXTC` — Electronics & Telecommunication
- `EXCS` — Electronics & Computer Science
- `BIOM` — Biomedical Engineering
- `ALL` — All Departments (college-wide announcement board)

### 9.2 Data Model & Multi-Targeting
1. `departments` Table:
   - `code` VARCHAR(10) PRIMARY KEY: Uppercase alphanumeric (`[A-Z0-9_-]`).
   - `name` TEXT NOT NULL: Full human-readable department title.
   - `sort_order` INTEGER: Display ordering in lists and filters.
   - `active` BOOLEAN: Whether screen is currently active (0 or 1).
   - `accent_color` TEXT: Optional hex code for subtle brand styling.
   - `created_at` TIMESTAMP: ISO timestamp of creation.
2. `notice_screens` Join Table:
   - `notice_id` TEXT REFERENCES notices(id) ON DELETE CASCADE
   - `screen_code` TEXT REFERENCES departments(code)
   - Enables many-to-many relationship: A notice can target 1 to N departments.
   - Notices targeting `ALL` appear on all departmental displays.

### 9.3 Display Routing Rules
- `/display/<code>`: Canonical display route. Case-insensitive; redirects with HTTP 301 to uppercase canonical code.
- `/display`: Root display defaults to `ALL` college-wide audience.
- Unknown/Inactive Code: Returns HTTP 404 with a branded "Screen Not Found" page listing active department display links.
- Legacy URLs: `/display?screen=<id>` permanently redirects (301) to `/display/<CODE>`.

### 9.4 Real-Time Isolation & Efficiency
- `GET /api/notices?screen=<CODE>`: Returns active notices targeting `<code>` OR `ALL`, ordered by urgency and schedule.
- ETag generation is calculated per-screen query.
- SSE stream `/api/events?screen=<CODE>` is isolated: changes to `EXCS`-only notices do not emit events to `BIOM` kiosks. `ALL` notice mutations broadcast to all screens.
- Heartbeat tracking via `POST /api/heartbeat` records last-seen timestamps per screen code.

### 9.5 Administrative Interface
- Multi-select chip picker for target audience (`ALL` or specific department chips). Inline validation requires $\ge 1$ target.
- Screen filter and compact target badge badges (`+N` overflow) on feed cards.
- Dedicated "Screens" management panel with online/offline indicators, add/edit/deactivate controls, and one-click "Copy display link" buttons.

---

## 11. Public Notice Page & Display QR Architecture (v2.2)

### 11.1 Routing & Security Specifications
1. **Canonical Public Route (`/n/<id>`)**:
   - Lightweight, public-facing notice page. Plain visits **NEVER** force a file download (`Content-Disposition: inline`).
   - Only active notices (`start <= now <= end`, not deleted) are served to public visitors.
   - Increments an anonymous scan counter per notice without storing client IPs or user tracking identifiers.
   - Protected by an in-process sliding-window rate limiter (120 req/min/IP). Uses no cookies, logins, or tracking scripts.
2. **Attachment & Media Download Route (`/n/<id>/file`)**:
   - Triggered explicitly via user action ("Save image", "Save video", or direct download link).
   - Re-verifies notice active status and streams media with `Content-Disposition: attachment; filename="<DEPT>-<slug>.<ext>"`.
   - Sends strict headers: `Content-Type`, `Content-Length`, `X-Content-Type-Options: nosniff`, and `Cache-Control: public, max-age=3600`.
   - Text announcements without media generate a human-readable UTF-8 announcement text file (`<DEPT>-<slug>.txt`).
3. **Zero-Leakage Inactive Handler (`render_inactive_public_page`)**:
   - Inactive, scheduled, expired, deleted, or unknown notice IDs return the **EXACT SAME generic 404 HTML body**: "This notice is no longer active", with HTTP 404 and zero title, department, or date leakage.
   - Authenticated admin sessions retain preview capabilities for unpublished or expired notices via `?preview=1` or active session cookies.
4. **Backward Compatibility & Legacy Redirection**:
   - `/notice/<id>` and `/notice/<id>?download=1` permanently redirect (HTTP 301) to `/n/<id>` and do not download.
   - `/notice/<id>/download` permanently redirects (301) to `/n/<id>/file`.

### 11.2 The Public Notice Page (`notice_public.html`)
- **Performance**: Mobile-first architecture, inline critical CSS, under 60KB JS bundle, and lazy-loaded imagery.
- **Theming**: Automatic Dark and Light theme adaptation following `prefers-color-scheme`, tested for WCAG AA contrast compliance (>4.5:1).
- **Layout Hierarchy (Top to Bottom)**:
  - *App Bar:* Official VN monogram SVG, "V Notice" in Outfit 700, and department pill chip.
  - *Media Stage:* Natural aspect-ratio images with tap-to-zoom modal; HTML5 videos with native controls, `preload="metadata"`, poster frame, muted by default, and strict no-autoplay; text notices feature an Outfit headline tile rendered with deterministic gradient themes matching the display kiosk.
  - *Metadata Row:* Priority badge (Urgent/Info), pulsing Live dot, and "Valid till <date>".
  - *Title & Byline:* Semantic `<h1>` heading and "Posted <date> by <dept>".
  - *Details:* Full announcement body text.
  - *Thumb-Sized 48px Actions:*
    - Media notices: Primary "Save image" or "Save video" with explicit file size (e.g. `2.4 MB`). Prompts cell data confirmation if file >25 MB and connection is cellular (`navigator.connection.type === 'cellular'`).
    - Text notices: Primary "Share".
    - Secondary actions: "Share", "Copy text", and dynamic `.ics` "Add to calendar" (rendered only when start and end times exist).
  - *Toast & Error States:* Semantic toasts announced with `aria-live="polite"` and offline/error recovery state with a "Retry" button.

### 11.3 Sharing & Social Metadata
- Open Graph (`og:title`, `og:description`, `og:image`, `og:url`, `theme-color`) and Twitter Card tags.
- Dynamic 1200x630 branded OG images generated with high-contrast text overlays.
- Internal privacy: `<meta name="robots" content="noindex">` added to all notice pages to prevent public search engine indexing of campus notices.

### 11.4 Display Kiosk QR Integration
- Kiosk QR card encodes `https://<host>/n/<id>` derived from `PUBLIC_BASE_URL` (or request origin / LAN IP).
- Header updated to "Scan to view" with subline "Open this notice on your phone".
- Encoded with error correction level M, 4-module quiet zone, and white background, verified via automated ZXing decoders at 1080p and 480p resolutions.


## 12. Video Sound Controls & Daily National Flag Screen

### 12.1 Selective Video Sound (`VIDEO_SOUND_ENABLED`)
- **Notice-Level Sound**: Uploaded videos have audio track detection via `ffprobe` (`has_audio: "true" | "false" | "unknown"`). In the notice creation/edit modal, the "Play sound" toggle is disabled with the note *"This video has no audio track"* when `has_audio` is false. Default is `play_sound: false` (muted).
- **Screen-Level Sound & Volume**: Each screen card in the Screens tab provides a "Sound" switch (default off) and a Volume slider (0–100, default 70).
- **Display Autoplay Enforcement**: Videos only play unmuted if `notice.play_sound AND screen.sound_enabled AND audio_ready`. Preloaded next videos stay strictly muted (`muted=true, volume=0`).
- **Stage Speaker Badge**: A small unobtrusive speaker icon appears on the stage while a sound-enabled video is actively playing.
- **Heartbeat & Status**: The display client tests audio autoplay capability on boot and reports `audio_ready` in the heartbeat. The Screens tab displays a subtle `Sound ready` or `Sound blocked` badge exclusively for sound-enabled screens.

### 12.2 Daily National Flag Screen (`FLAG_EVENT_ENABLED`)
- **Display Only (Strictly No Anthem Audio)**: V Notice must NOT play, store, or reference any anthem audio. The college plays the anthem using an external system.
- **Timing & Schedule**: At 11:00 AM Asia/Kolkata (configurable start time, start offset -60 to +60s, duration 10–300s, default 60s), all enrolled screens display the Indian national flag fullscreen, then smoothly return to normal rotation without page reload.
- **High-Precedence Takeover**: The flag event outranks everything, including active urgent broadcasts. When the event ends, urgent notices or rotation resume cleanly.
- **Sub-Second Screen Synchronization**: The display client computes a network round-trip clock offset against `/api/events/today` every 5 minutes, ensuring all campus screens switch within 1 second of each other.
- **Pure Vector Flag**: Standard 3:2 ratio SVG with saffron `#FF9933`, white `#FFFFFF`, and green `#138808` horizontal bands, centered 24-spoke navy `#000080` Ashoka Chakra (diameter 3/4 white band height). Scaled preserving 3:2 on `#0B1020` canvas with zero text overlays.
- **Optional Standup Screen**: When enabled, displays a 15-second lead-in screen with 3 stacked lines in self-hosted Noto Sans Devanagari (English, Hindi, Marathi) before transitioning to the flag.
- **Admin Configuration**: Card in Settings with full schedule controls, skip dates, "Skip today", 5x silent preview, "Run now on screen...", manual "Show flag now" / "End flag now", and optional Bearer token API (`/api/events/flag/start` and `/end`).

