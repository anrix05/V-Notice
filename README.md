# V Notice — Smart Campus Digital Notice Board & Kiosk

**V Notice** is a lightweight, offline-first smart digital notice board and announcement system purpose-built for college campus corridors, department lobbies, and academic kiosks. Running on a lean Python Flask backend (<60MB RAM footprint), it dynamically rotates campus announcements, urgent alerts, video broadcasts, and voice memos on standard 18"–22" monitors and Raspberry Pi kiosks, while providing faculty and department administrators with a mobile-friendly 30-second publishing dashboard and offering passing students instantaneous high-contrast announcement downloads via scan-to-phone QR codes.

---

## Repository Folder Map

| Directory | Purpose & Contents |
| :--- | :--- |
| [**`docs/`**](docs/) | Architectural blueprints ([`ARCHITECTURE.md`](docs/ARCHITECTURE.md)), deployment manuals ([`SETUP.md`](docs/SETUP.md)), design system tokens ([`DESIGN.md`](docs/DESIGN.md)), product requirements ([`PRD.md`](docs/PRD.md)), architectural decision records ([`DECISIONS.md`](docs/DECISIONS.md)), QA test plans ([`TESTING.md`](docs/TESTING.md)), engineering rules ([`RULES.md`](docs/RULES.md)), and historical context ([`MEMORY.md`](docs/MEMORY.md)). |
| [**`deploy/`**](deploy/) | Production deployment tooling: Raspberry Pi kiosk installer (`raspberry-pi/install_rpi.sh`), display-only thin client installer (`raspberry-pi/setup_rpi_kiosk_display_only.sh`), systemd units (`raspberry-pi/vnotice.service`), and Cloudflare remote admin tunnel launchers (`tunnel/`). |
| [**`scripts/`**](scripts/) | Platform launchers for Windows (`scripts/windows/`) and Linux (`scripts/linux/`), plus brand asset generation (`generate_brand_assets.py`) and verification screenshot scripts (`capture_verification_screenshots.py`). |
| [**`assets/`**](assets/) | Marketing and print assets, including the high-DPI vector poster generation harness (`assets/poster/`). |
| [**`archive/`**](archive/) | Historical verification screenshot runs, UI audit snapshots, and legacy database migration backups (`archive/legacy/` and `archive/verification/`). |
| [**`static/`**](static/) | Frontend client assets: design tokens (`css/tokens.css`), signage stylesheets (`css/`), vanilla JavaScript rotation engines (`js/`), self-hosted fonts (`fonts/`), official vector brand marks (`brand/`), PWA icons (`icons/`), and Service Workers (`sw.js`, `admin-sw.js`). |
| [**`templates/`**](templates/) | Jinja2 HTML templates: kiosk digital signage interface (`display.html`), mobile-first admin CMS (`admin.html`), standalone public notice viewer (`notice_public.html`), and diagnostic error pages (`screen_not_found.html`). |
| [**`tests/`**](tests/) | Automated pytest test suite covering authentication, storage CRUD, rate limiting, SSE real-time sync, video sound policy, voice notes, and UI responsiveness. |
| **`media/`** | Runtime disk storage for uploaded notice flyers, videos, and voice notes (gitignored; managed with automated 10-minute safe garbage collection). |

---

## Quick Start

### 1. Windows (Local Development & Testing)

1. **Clone & Install Dependencies:**
   ```powershell
   git clone https://github.com/your-org/v-notice.git
   cd v-notice
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Start Servers (Dual-Port Mode):**
   ```cmd
   start.bat
   ```
   * *Display Screen (Read-Only):* `http://localhost:5000` (or `http://localhost:5000/display/EXCS`)
   * *Admin Portal (Password Protected):* `http://localhost:5001/admin` (Default password: `vnotice2026`)
3. **Launch Kiosk Display Window:**
   ```cmd
   scripts\windows\start_display.bat
   ```

### 2. Raspberry Pi (Automated Corridor Kiosk)

1. **1-Click Full Node Installation (Backend + Fullscreen Kiosk):**
   ```bash
   chmod +x deploy/raspberry-pi/install_rpi.sh
   ./deploy/raspberry-pi/install_rpi.sh
   ```
   *Automatically configures system dependencies, Chromium enterprise autoplay policies, systemd auto-restart service (`vnotice.service`), and autostart on boot.*
2. **Dedicated Department Screen Parameter:**
   ```bash
   DEPARTMENT_CODE=CMPN ./deploy/raspberry-pi/install_rpi.sh
   ```
3. **Display-Only Thin Client (Points to Cloud URL):**
   ```bash
   chmod +x deploy/raspberry-pi/setup_rpi_kiosk_display_only.sh
   ./deploy/raspberry-pi/setup_rpi_kiosk_display_only.sh https://v-notice.onrender.com/display/ALL
   ```

### 3. Cloud Deployment (Render / Railway)

V Notice supports single-port cloud environments out of the box via Gunicorn:
* **Procfile & Railway:** Automatically executes `gunicorn app:unified_app -c gunicorn.conf.py` listening on the cloud provider's `$PORT`.
* **Permanent Data Persistence:**  
  * On **Render Free Tier**, the local filesystem is ephemeral (resets on container redeploy). To persist notices and media, attach a Render Persistent Disk and set `STORAGE_DIR=/var/data`, or configure `CLOUDINARY_URL` for cloud media storage.
  * On **Railway**, attach a persistent volume and configure `STORAGE_DIR` to the mount path.

---

## Documentation Index

Comprehensive documentation is maintained in the [`docs/`](docs/) directory:

* 📐 [**System Architecture (`docs/ARCHITECTURE.md`)**](docs/ARCHITECTURE.md) — Comprehensive technical blueprint, dual-port model, SQLite WAL engine, SSE real-time sync, and known limitations.
* 🚀 [**Deployment & Setup Manual (`docs/SETUP.md`)**](docs/SETUP.md) — Step-by-step installation guides for Raspberry Pi, Linux, Docker, Windows, and Cloud platforms.
* 🎨 [**Design System Specification (`docs/DESIGN.md`)**](docs/DESIGN.md) — Document Sheet Monogram brand geometry, design tokens, color palette, and layout rules.
* 📋 [**Product Requirements Document (`docs/PRD.md`)**](docs/PRD.md) — Product vision, user personas, success metrics, and release phases.
* ⚖️ [**Architectural Decision Records (`docs/DECISIONS.md`)**](docs/DECISIONS.md) — ADR log detailing decisions on dual-port security, frosted backdrops, and video sound policy.
* 🧪 [**Testing & QA Specification (`docs/TESTING.md`)**](docs/TESTING.md) — Test matrix, Playwright verification, security audits, and regression checklists.
* 📜 [**Engineering Rules & Contracts (`docs/RULES.md`)**](docs/RULES.md) — Development invariants, security boundaries, and coding standards.
* 🧠 [**Project Memory & Context (`docs/MEMORY.md`)**](docs/MEMORY.md) — Historical development notes, commit milestones, and implementation logs.
