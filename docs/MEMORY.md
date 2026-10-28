# V Notice — Project Memory & Architecture Context

**Last Updated:** October 15, 2026  
**Active Branch:** `main`  
**Latest Remote Sync:** Synced with `origin/main` (`3353b05`)  

---

## 1. Project Overview & Identity

* **Project Name:** V Notice
* **Purpose:** Smart digital notice board for college campuses and academic departments.
* **Core Philosophy:** Offline-first resilience, dual-port physical security, zero recurring costs, fast 30-second mobile administration, and maximum readability on 18"–22" monitors and 7" Raspberry Pi displays.
* **Technology Stack:**
  * **Backend:** Python 3.10+ with Flask (Lightweight, <60MB RAM footprint).
  * **Frontend:** Vanilla HTML5, Vanilla CSS3 (Custom design system tokens), Vanilla JavaScript (No React, Vue, or Tailwind overhead).
  * **Storage:** Atomic JSON storage (`notices.json`) with auto-backup + local media directory (`media/`).
  * **Real-time Engine:** Server-Sent Events (SSE) push with 30s background polling fallback.
  * **Hardware Target:** Raspberry Pi 4 / 3B+ / 5 with HDMI monitor.

---

## 2. Key Architecture Decisions & Rationales (ADR Log)

### ADR-001: Dual Port Separation (Port 5000 vs Port 5001)
* **Decision:** Run two distinct HTTP servers in a single Python process:
  * Port 5000: Display screen (Strictly read-only, no write APIs, no authentication required).
  * Port 5001: Admin portal (Password protected with `X-Password` authentication, full CRUD and file uploads).
* **Rationale:** Physical kiosk security. If students or external users access the kiosk URL or inspect network requests on port 5000, there are zero administrative endpoints or tokens exposed.

### ADR-002: Cloudflare Quick Tunnels vs Custom Domain (`anrix.me`)
* **Decision:** Provide 1-click ephemeral Cloudflare Quick Tunnels (`start_tunnel.bat` / `start_tunnel.sh`) for remote access rather than pointing personal DNS (`anrix.me`) to campus hardware.
* **Rationale:**
  1. The user's personal domain (`anrix.me`) is a 1-year student portfolio domain that should not be permanently coupled to college department hardware.
  2. Bypasses strict university firewall NAT, CGNAT, and blocked inbound ports without requiring IT admin permissions or router port-forwarding.
  3. Preserves offline-first local network autonomy: the notice board continues operating even if the tunnel or external WAN drops.

### ADR-003: Ambient Frosted Backdrop for Posters
* **Decision:** Use CSS `filter: blur(40px)` background clone for non-16:9 vertical posters and flyers (3:4, 4:3).
* **Rationale:** College campus notices are almost universally designed as vertical flyers. Forcing vertical flyers onto 16:9 widescreen corridor monitors causes either severe letterboxing (black bars) or awkward cropping. The ambient frosted backdrop creates a high-end, Apple TV-style presentation while keeping the original poster centered and uncropped.

### ADR-004: Separate Date & Time Pickers with `color-scheme: dark;`
* **Decision:** Replace the native `<input type="datetime-local">` with separate `📅 Date` (`type="date"`) and `🕒 Time` (`type="time"`) inputs, styled with `color-scheme: dark;` and quick preset buttons (`End of Today`, `3 Days`, `1 Week`, `1 Month`).
* **Rationale:** Chromium on Windows renders combined `datetime-local` with confusing, unlabeled dual scroll wheels on a jarring white background. Splitting the fields allows users to open a pure calendar grid without side scroll wheels, and enables one-click preset scheduling with a live human-readable summary.

### ADR-005: Pinned Modal Dialog Architecture
* **Decision:** Structure the Admin "New Notice" modal into three separate flex layers:
  * Pinned Header (`.modal-header`)
  * Smooth Scrollable Body (`.modal-body-scroll`)
  * Pinned Footer (`.modal-footer`)
* **Rationale:** Previously, `<form class="modal-body">` had a sticky footer inside the scroll container. As the form expanded, the `Cancel` and `Publish` buttons floated on top of the date fields and duration controls. Pinning the footer outside the scroll body guarantees action buttons never obscure form inputs on any screen size.

### ADR-006: Automatic Media Garbage Collection (Storage Hygiene)
* **Decision:** Automatically scan and delete orphaned media files from disk upon notice deletion or notice expiration.
* **Rationale:** Raspberry Pi systems run on micro-SD cards (16GB–64GB). Without automated garbage collection, video clips and poster images uploaded over months of college semesters would silently fill the disk and crash the system.

### ADR-007: Dedicated Mobile Public Notice Page (`/n/<id>`) Replacing QR Auto-Download
* **Decision:** Replace the QR auto-download mechanism (`/notice/<id>?download=1`) with a responsive, mobile-first public notice web page served at `/n/<id>`. Plain page loads never trigger file downloads. Downloading is reserved for explicit user actions via the `/n/<id>/file` route.
* **Rationale:**
  1. Auto-downloading flyers over cellular connections consumes student mobile data unexpectedly and clutters downloads folders without context.
  2. Text announcements previously had nothing meaningful to download; a web page provides proper presentation with deterministic gradients matching the display kiosk.
  3. Displays complete metadata (department chip, priority, validity dates, full details text, and site address).
  4. Supports modern mobile behaviors: Web Share API (`navigator.share({files: [...]})`) for direct iOS/Android camera roll integration, dynamic `.ics` calendar generation for scheduled events, and cellular data warnings for media >25 MB.

### ADR-008: Invariant Zero-Leakage 404 Responses for Inactive Notices
* **Decision:** Return the exact same byte-for-byte HTML body with HTTP 404 for all inactive, scheduled, expired, deleted, or unknown notice IDs.
* **Rationale:** Eliminates information disclosure and prevents ID enumeration attacks. Attackers cannot determine whether a notice ID ever existed, was scheduled for the future, or was deleted. Authenticated admin sessions retain preview capabilities via `?preview=1` or active session cookies.

### ADR-009: Selective Video Sound Architecture & Autoplay Safeguards
* **Decision:** Allow selective video audio playback only when explicitly enabled on both notice (`notice.play_sound: true`) and screen (`screen.sound_enabled: 1`), and permitted by the browser environment (`audio_ready: true`). Keep all other video notices, preloaded next videos, and silent screens strictly muted. Detect audio tracks via `ffprobe` on upload.
* **Rationale:** Corridor digital signage must avoid unwanted loud audio. Only specific admin-chosen videos should play sound, and only on screens designated with sound enabled (with configurable 0-100 volume). Autoplay safeguards ensure video rotation is never blocked if an unmuted video is rejected by browser policy.

### ADR-010: Daily Fullscreen National Flag Event (Display Only, Zero Anthem Audio)
* **Decision:** Implement a daily 11:00 AM Indian National Flag screen event across all campus displays with strictly zero audio playback, storage, or reference. The external student-built Raspberry Pi anthem audio system remains completely separate. Use pure 3:2 vector SVG, RTT clock offset sync, and high precedence over all notices (including urgent).
* **Rationale:** Honors the college tradition of the daily 11:00 AM national anthem while strictly adhering to the architectural separation of concerns: V Notice handles visual display only, ensuring zero audio duplication or interference with the separate hardware audio system.

---

## 3. Repository File Map & Responsibilities

```
d:\V Notice\
├── app.py                # Main backend entry point: runs Dual Server (5000 & 5001) + SSE hub
├── config.py             # Environment configurations, ports, and default paths
├── storage.py            # Thread-safe JSON CRUD storage with atomic writes & garbage collection
├── requirements.txt      # Minimal Python dependencies (Flask >= 3.0.0, Werkzeug >= 3.0.0)
│
├── templates/
│   ├── display.html      # High-visibility kiosk interface (weather, clock, queue rail, QR)
│   ├── admin.html        # Responsive admin dashboard with live media preview & schedule presets
│   └── notice_public.html # Standalone mobile-first public notice view (/n/<id>) with zero-leakage 404
│
├── tests/
│   ├── test_public_notice_qr.py   # Public route, /file streaming, 404 diffs, QR decode, Axe contrast
│   ├── test_security_phase2.py    # Authentication, timing-safety, rate-limits, enumeration tests
│   └── ...                        # Comprehensive suite covering phases 1 through 8
│
├── static/
│   ├── css/
│   │   ├── display.css   # Signage stylesheet with 1080p dynamic scaling & urgent red theme
│   │   └── admin.css     # Clean dark UI theme (#0F172A, #162238, #2F6BFF) with custom scrollbars
│   ├── js/
│   │   ├── display.js    # Client rotation engine, SSE listener, QR code generator, weather
│   │   ├── admin.js      # CRUD actions, live aspect ratio inspector, schedule summary engine
│   │   └── qrcode.min.js # Zero-network offline QR code generation library
│   ├── brand/
│   │   ├── logo-obsidian.svg # V Notice official document sheet brand vector mark (#111318 ink sheet, #B08D57 gold fold/line)
│   │   ├── logo-light-tile.svg # Reversed ivory sheet mark (#F5F1E8) for dark kiosk and admin surfaces
│   │   ├── logo-lockup-dark.svg # Dark horizontal lockup with Outfit 700 wordmark & Inter 500 descriptor
│   │   ├── logo-lockup-light.svg # Light horizontal lockup with Outfit 700 wordmark & #8A6B3A descriptor
│   │   └── contact-sheet.png # Verification contact sheet (16, 24, 32, 64, 180px on light, dark, kiosk)
│   └── images/
│       └── logo.svg      # Legacy vector asset mapped to new document sheet mark
│
├── systemd/
│   ├── vnotice.service   # Linux systemd auto-restart service for Raspberry Pi boot
│   └── kiosk.sh          # Chromium kiosk launcher (disables sleep, hides mouse cursor)
│
├── install_rpi.sh        # 1-click automated Raspberry Pi setup & kiosk installer
├── start_tunnel.sh       # 1-click Cloudflare Tunnel launcher for Raspberry Pi / Linux
├── start_tunnel.bat      # 1-click Cloudflare Tunnel launcher for Windows
├── stop_tunnel.bat       # 1-click tunnel terminator for Windows
├── start.bat             # 1-click local Windows execution script
├── start.sh              # 1-click local Linux execution script
│
├── prd.md                # Comprehensive Product Requirements Document (PRD)
├── memory.md             # This document: Architecture decisions, constraints, and project log
├── rules.md              # Core engineering specifications and interface contracts
├── notices.json          # Active notices database (atomic JSON storage)
└── .gitignore            # Git rules (strictly ignoring local AI agent/brag files and .env)
```

---

## 4. Invariant Rules & Constraints

1. **Never Commit AI Agent Plugins:**
   * `.agents/`, `.claude/`, `.claude-plugin/`, and `brag-output/` are strictly ignored in `.gitignore`.
2. **Never Break Read-Only Kiosk Contract:**
   * Port 5000 must never expose notice creation, update, or deletion routes.
3. **No Heavy Frontend Frameworks:**
   * Keep frontend strictly Vanilla JS and Vanilla CSS. Raspberry Pi browsers struggle with React virtual DOM diffing and heavy JavaScript bundles.
4. **Offline Autonomy:**
   * Every core feature (notice rotation, clock, QR generation, media serving) must function without active internet connectivity.

---

## 5. Development Milestones & Recent Commits

* **Phase 8 (Latest):** Replaced legacy QR auto-download behavior (`?download=1`) with a responsive, mobile-first public notice web page (`/n/<id>`), direct attachment download route (`/n/<id>/file`), zero-leakage invariant 404 responses, display kiosk QR card update to "Scan to view", anonymous scan metrics, and 100% passing test coverage.
* **`3353b05`:** Added automated 1-click Raspberry Pi kiosk installer (`install_rpi.sh`), Linux Cloudflare tunnel launcher (`start_tunnel.sh`), and dual-OS Chromium detection in `kiosk.sh`.
* **`e37a163`:** Overhauled modal layout to eliminate sticky footer overlap, removed redundant Display button from navbar, integrated aspect ratio guidance badges, and split date/time pickers with live human schedule summaries.
* **`65994f1`:** Cleaned temporary test files, updated documentation, and locked down `.gitignore`.
