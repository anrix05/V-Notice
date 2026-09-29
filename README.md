# V Notice — Smart Digital Notice Board

> **MCA Project**  
> *Platform: Raspberry Pi + 18-inch to 22-inch Monitor (Full HD 1080p / 900p / 720p & 7-inch LCD)*  
> *Tagline: "Your Campus. Your Notices. One Display."*

---

## 1. Project Overview

**V Notice** is a centralized smart digital notice board system developed for college campuses. It seamlessly connects faculty, administration, and students:

- **Faculty and Staff** publish, schedule, categorize, edit, and broadcast announcements instantly from any smartphone, tablet, or laptop from anywhere.
- **The Raspberry Pi** wall-mounted 18-inch to 22-inch monitor dynamically rotates active notices, prioritizes urgent campus alerts, plays campus video broadcasts, displays an Apple TV-style ambient frosted backdrop, and provides a continuous headline ticker with a live digital clock and campus weather readable from across corridors and lobbies.
- **Scan-to-Phone QR Code**: A dedicated high-DPI QR card on the sidebar rail lets passing students scan from 10 feet away to download notices and posters directly to their phones over campus Wi-Fi.
- **Zero manual refreshes**: The display automatically synchronizes within seconds via Server-Sent Events (SSE). Real-time additions, edits, and deletions reflect immediately.
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
                     ▼ (Cloudflare Tunnel / Campus Wi-Fi)
       ┌─────────────────────────────────────────┐
       │              Raspberry Pi               │
       │                                         │
       │  Port 5001: Admin Backend               │ ◄── Receives new & edited notices
       │  Port 5000: Display Backend             │
       │  Storage: notices.json + media/         │
       │                                         │
       │  Chromium Fullscreen Kiosk Mode         │ ──► Displays on 18"-22" Monitor
       │  (http://localhost:5000)                │     1080p / 900p / 720p HDMI
       └─────────────────────────────────────────┘
```

### Storage Layer
- **`notices.json`**: Flat JSON database storing notice metadata, priority, timing, and durations.
- **`media/`**: Directory storing uploaded campus posters (PNG/JPG/WEBP) and video announcements (MP4/WEBM, up to 200MB).

---

## 3. Key Upgrades & Features

### 🌟 1. Ambient Frosted Backdrop
For portrait posters and widescreen videos, instead of empty black dead bars on 18"–22" monitors, V Notice renders a soft, ambient frosted blur of the active media behind the centered artwork (like Apple TV and YouTube), creating a rich, premium television aesthetic.

### 📱 2. "Scan to Phone" QR Integration
- **High-DPI Medium QR Card**: Positioned cleanly at the bottom of the "Up next" sidebar rail without obstructing the main stage.
- **LAN IP Auto-Detection**: Generates the exact local Wi-Fi IP (e.g. `http://10.168.209.114:5000/notice/vnot0001?download=1`) so phones connect immediately.
- **1-Tap Direct Download**: Automatically downloads the flyer/PDF straight into student phone storage.

### 🌦️ 3. Real-Time Campus Weather & Clock
- Displays live temperature and condition icons (e.g. `29°C · Mumbai 🌤`) via Open-Meteo API.
- Auto-detects campus geographic coordinates via IP fallback with 10-minute caching to eliminate unnecessary external calls.

### ⚡ 4. Live Admin Preview & In-Place Editing
- Instant visual file preview with aspect ratio detection (16:9, 4:3, 9:16 portrait) before uploading.
- Edit existing notices directly (`PUT /api/notices/<id>`) without needing to delete and recreate.

---

## 4. Notice Data Model

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

## 5. REST API Specification

| Method | Endpoint | Site | Auth Required | Description |
| :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/notices` | Display (5000) | No | Returns currently active notices (`start <= now <= end`) |
| `GET` | `/api/notices` | Admin (5001) | Yes (`X-Password`) | Returns all notices with computed status (`live`, `scheduled`, `expired`) |
| `POST` | `/api/notices` | Admin (5001) | Yes (`X-Password`) | Creates new notice (supports multipart form for file uploads) |
| `PUT` | `/api/notices/<id>` | Admin (5001) | Yes (`X-Password`) | Updates existing notice title, body, priority, or schedule |
| `DELETE` | `/api/notices/<id>` | Admin (5001) | Yes (`X-Password`) | Deletes notice and associated media file from storage |
| `GET` | `/notice/<id>/download` | Display (5000) | No | Triggers 1-tap download of the notice media/text to phone |
| `GET` | `/api/system-info` | Display (5000) | No | Returns auto-detected campus weather, LAN IP, and ports |
| `POST` | `/api/login` | Admin (5001) | No | Authenticates admin password |
| `POST` | `/api/logout` | Admin (5001) | No | Terminates session |
| `GET` | `/media/<file>` | Both | No | Serves uploaded images and video files |
| `GET` | `/api/health` | Both | No | Health check endpoint |

---

## 6. Quick Start & Local Execution

### Prerequisites
- Python 3.10+ (Tested on Python 3.12 & 3.13)
- Modern web browser (Chrome, Edge, Chromium, Firefox)

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

### Running the Server
```bash
python app.py
```
*(On Windows, you can simply double-click `start.bat`)*

This automatically starts:
- **Display Interface**: `http://localhost:5000`
- **Admin Management Portal**: `http://localhost:5001`
- **Default Admin Password**: `vnotice2026` (configurable in `.env`)

---

## 7. Remote Management from Anywhere (Cloudflare Tunnel)

To allow faculty or administrators to manage notices from home or mobile data outside campus Wi-Fi, run the 1-click Cloudflare Tunnel:

### Windows:
- Double-click **`start_tunnel.bat`** to start remote access.
- Cloudflare will print your secure HTTPS URL (e.g. `https://random.trycloudflare.com`).
- Double-click **`stop_tunnel.bat`** to close public access.

### Raspberry Pi (Linux):
```bash
# Expose the Admin port (5001)
cloudflared tunnel --url http://localhost:5001
```

---

## 8. Raspberry Pi Deployment & Kiosk Mode

### Hardware
- **Raspberry Pi 4 / 3B+**
- **18-inch to 22-inch Monitor** (Full HD 1080p / 900p / 720p via HDMI)
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
