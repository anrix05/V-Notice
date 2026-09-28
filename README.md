# V Notice — Smart Digital Notice Board

> **MCA Project**  
> *Platform: Raspberry Pi + 7-inch LCD Display (800×480)*  
> *Tagline: "Your Campus. Your Notices. One Display."*

---

## 1. Project Overview

**V Notice** is a centralized smart digital notice board system developed for college campuses. It seamlessly connects faculty, administration, and students:

- **Faculty and Staff** publish, schedule, categorize, and broadcast announcements instantly from any smartphone, tablet, or laptop from anywhere.
- **The Raspberry Pi** wall-mounted 7-inch LCD display (800×480) dynamically rotates active notices, prioritizes urgent campus alerts, plays campus video broadcasts, and provides a continuous headline ticker with a live digital clock.
- **Zero manual refreshes**: The display automatically polls and updates within seconds. Real-time deletion and additions reflect seamlessly.
- **Offline resilience**: In the event of Wi-Fi or network dropouts, the display continues cycling cached notices from `localStorage` without interruptions or blank screens.

---

## 2. System Architecture

V Notice runs a unified Flask backend serving two distinct interfaces on dedicated ports:

| Site | Port | Access | Description |
| :--- | :---: | :--- | :--- |
| **V Notice Display** | `5000` | Read-only (Public) | Wall-mounted kiosk display rotating active notices |
| **V Notice Admin** | `5001` | Password-protected | Mobile-first portal to publish, schedule, and manage notices |

```
   [ Faculty Phone / Laptop (Anywhere) ]
                     │
                     ▼ (Cloudflare Tunnel / LAN)
       ┌─────────────────────────────────────┐
       │            Raspberry Pi             │
       │                                     │
       │  Port 5001: Admin Backend           │ ◄── Receives new notices
       │  Port 5000: Display Backend         │
       │  Storage: notices.json + media/     │
       │                                     │
       │  Chromium Fullscreen Kiosk Mode     │ ──► Displays on 7-inch
       │  (http://localhost:5000)            │     800x480 LCD Screen
       └─────────────────────────────────────┘
```

### Storage Layer
- **`notices.json`**: Flat JSON database storing notice metadata, priority, timing, and durations.
- **`media/`**: Directory storing uploaded campus posters (PNG/JPG/WEBP) and video announcements (MP4/WEBM, up to 200MB).

---

## 3. Notice Data Model

Each notice adheres to the following JSON schema:

```json
{
  "id": "vnot0001",
  "title": "MCA Project Viva – Phase 1 Review",
  "body": "Batch A & B: 9:00 AM · Lab B4. Carry printed spiral-bound synopsis and working demo on laptops.",
  "priority": "urgent",
  "type": "text",
  "media": "",
  "duration": 10,
  "start": 1700000000000,
  "end": 1900000000000
}
```

- **Priority**: `urgent` (priority takeover), `normal` (standard rotation), `info` (guidelines/hours).
- **Type**: `text` (large typography), `image` (poster with caption strip), `video` (muted playback, auto-advances on end).
- **Start / End**: Timestamps in milliseconds for automated scheduling and expiry.

---

## 4. REST API Specification

| Method | Endpoint | Site | Auth Required | Description |
| :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/notices` | Display (5000) | No | Returns currently active notices (`start <= now <= end`) |
| `GET` | `/api/notices` | Admin (5001) | Yes (`X-Password`) | Returns all notices with computed status (`live`, `scheduled`, `expired`) |
| `POST` | `/api/notices` | Admin (5001) | Yes (`X-Password`) | Creates new notice (supports multipart form for file uploads) |
| `DELETE` | `/api/notices/<id>` | Admin (5001) | Yes (`X-Password`) | Deletes notice and associated media file from storage |
| `POST` | `/api/login` | Admin (5001) | No | Authenticates admin password |
| `POST` | `/api/logout` | Admin (5001) | No | Terminates session |
| `GET` | `/media/<file>` | Both | No | Serves uploaded images and video files |
| `GET` | `/api/health` | Both | No | Health check endpoint |

---

## 5. UI & Design Direction

Built with a calm, minimal, type-led interface where notice content is the primary focus:

- **Strict Palette**:
  - Background: `#0F172A`
  - Panel: `#162238`
  - Electric Blue: `#2F6BFF`
  - Urgent Red: `#E5484D`
  - Text: `#F8FAFC`
  - Neutrals: Muted text `#A3B1C6`, Border `#24344F`, Raised panel `#1C2B45`
- **Flat Surfaces**: No gradients, glows, text-shadows, or vignettes. Separation achieved via 1px crisp borders.
- **Display Composition (800×480)**:
  - Header (56px): 32px vector "V" brand mark, "V Notice" title, tabular `10:42 AM` clock and date.
  - Stage (~64%): Big responsive headline (scales 40px $\rightarrow$ 32px $\rightarrow$ 26px for long titles), body copy ($\ge 20\text{px}$), meta row, and centered bottom progress dots.
  - Up Next Rail (`min(26rem, 36%)`): Numbered queue positions, 2-line max headline, and type tags.
  - Ticker (40px): Seamless headline marquee with "Latest" label.
- **Admin Portal**: Mobile-first single 720px centered column, $\ge 48\text{px}$ touch targets, merged summary/filter segmented control, and bottom sheet / modal form.

---

## 6. Quick Start & Local Execution

### Prerequisites
- Python 3.10+ (Tested on Python 3.12 & 3.13)
- Modern web browser (Chrome, Edge, Chromium, Firefox, Safari)

### Installation
```bash
# 1. Clone repository
git clone https://github.com/anrix05/V-Notice.git
cd V-Notice

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file (optional, defaults provided)
cp .env.example .env
```

### Running the Dual Server
```bash
python app.py
```
This automatically starts:
- **Display Interface**: `http://localhost:5000`
- **Admin Management Portal**: `http://localhost:5001`
- **Default Admin Password**: `vnotice2026`

To run with a custom password:
```bash
# Linux / Raspberry Pi:
ADMIN_PASSWORD="MyCollegeSecurePassword" python3 app.py

# Windows PowerShell:
$env:ADMIN_PASSWORD="MyCollegeSecurePassword"; python app.py
```

---

## 7. Remote Management from Anywhere (Cloudflare Tunnel)

To allow faculty or administrators to manage notices from home or mobile data outside campus Wi-Fi, run Cloudflare Tunnel on the Raspberry Pi:

```bash
# 1. Install cloudflared on Raspberry Pi
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# 2. Expose the Admin port (5001)
cloudflared tunnel --url http://localhost:5001
```

Cloudflare generates a secure, free public HTTPS link (e.g. `https://vnotice-admin.trycloudflare.com`) that can be opened on any phone or laptop worldwide.

---

## 8. Raspberry Pi Deployment & Kiosk Mode

### Hardware
- **Raspberry Pi 4 / 3B+**
- **7-inch LCD Display** (800×480 resolution via DSI or HDMI)
- **5V / 3A USB-C Power Supply**

### Auto-Start Services Configuration

1. **Systemd Service (`/etc/systemd/system/vnotice.service`)**:
```bash
sudo cp systemd/vnotice.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vnotice.service
```

2. **Chromium Kiosk Auto-Start on Boot**:
Make [`systemd/kiosk.sh`](systemd/kiosk.sh) executable and add to autostart:
```bash
chmod +x systemd/kiosk.sh
mkdir -p ~/.config/autostart
nano ~/.config/autostart/vnotice-kiosk.desktop
```
Add the following content:
```ini
[Desktop Entry]
Type=Application
Name=V Notice Kiosk
Exec=/home/pi/v-notice/systemd/kiosk.sh
X-GNOME-Autostart-enabled=true
```

---

## 9. Automated Test Matrix

A comprehensive 21-point test script verifies all PRD and architectural rules:

```bash
python test_vnotice_complete.py
```

- [x] Create text, image, and video notices with multipart file uploads
- [x] Schedule future notices and auto-expire past notices
- [x] Immediate notice deletion and disk media cleanup
- [x] Urgent notice priority takeover and state styling
- [x] Admin password authentication enforcement (HTTP 401)
- [x] Secure file upload validation and 200 MB maximum limit enforcement
- [x] Missing media graceful fallback (HTTP 404)
- [x] Offline resilience with `localStorage` caching
- [x] Sub-second display polling and instant updates
- [x] Video autoplay, end-detection, loop, and memory cleanup
- [x] 800×480 resolution constraints and mobile admin fluid responsiveness
- [x] Systemd auto-start and Chromium kiosk script configuration
