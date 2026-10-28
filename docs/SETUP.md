# V Notice — Raspberry Pi & Kiosk Setup Guide

This guide covers everything you need to set up a digital notice board on a **Raspberry Pi** (or Windows / Linux PC) without needing a mouse or keyboard once mounted on the wall.

---

## ⚡ Option A: Display-Only Kiosk (Cloud URL — Recommended)

Use this option if your V Notice system is hosted online (e.g. `https://v-notice.onrender.com`) and your Raspberry Pi is only used as a display screen connected to a TV or monitor via HDMI.

### 🚀 1-Minute Automated Setup
Connect your Raspberry Pi to Wi-Fi/Ethernet, open the **Terminal** (or SSH into it), and run:

```bash
curl -sSL https://raw.githubusercontent.com/anrix05/V-Notice/main/setup_rpi_kiosk_display_only.sh | bash
```

> **For specific department screens (e.g. Computer Engineering, IT, etc.):**
> ```bash
> curl -sSL https://raw.githubusercontent.com/anrix05/V-Notice/main/setup_rpi_kiosk_display_only.sh | bash -s "https://v-notice.onrender.com/display/CMPN"
> ```

Reboot your Pi:
```bash
sudo reboot
```
The Raspberry Pi will boot directly into fullscreen kiosk mode with automatic sound unlocked.

---

### 🛠️ Manual Step-by-Step Setup (Display-Only)

If you prefer to configure the Raspberry Pi manually without the automated script, follow these 3 steps:

#### Step 1: Install Required Display Utilities
Installs `unclutter` (hides idle mouse cursor) and `xdotool` (simulates synthetic click on boot to guarantee audio unlock):
```bash
sudo apt update
sudo apt install -y unclutter xdotool curl
```

#### Step 2: Whitelist V Notice for Automatic Sound (Zero-Click Audio)
Chromium blocks unmuted audio on web pages by default unless configured via Enterprise Policy. Run this to whitelist V Notice permanently on the Raspberry Pi:
```bash
sudo mkdir -p /etc/chromium/policies/managed /etc/chromium-browser/policies/managed

cat << 'EOF' | sudo tee /etc/chromium/policies/managed/vnotice_display.json
{
  "AutoplayAllowed": true,
  "AutoplayAllowlist": [
    "https://v-notice.onrender.com",
    "https://v-notice.onrender.com/*"
  ]
}
EOF

sudo cp /etc/chromium/policies/managed/vnotice_display.json /etc/chromium-browser/policies/managed/vnotice_display.json 2>/dev/null || true
```

#### Step 3: Configure Kiosk Autostart on Boot
Create a launch script at `~/start_vnotice.sh`:
```bash
cat << 'EOF' > ~/start_vnotice.sh
#!/usr/bin/env bash
# Disable screen sleep & blanking
xset s noblank 2>/dev/null || true
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

# Hide mouse pointer
unclutter -idle 0.5 -root &

# Synthetic click after 4 seconds to guarantee audio context unlock
(sleep 4 && xdotool click 1 2>/dev/null || true) &

# Find Chromium binary
CHROMIUM_BIN=$(command -v chromium-browser || command -v chromium)

# Launch fullscreen with autoplay flag
"$CHROMIUM_BIN" --kiosk "https://v-notice.onrender.com/display/ALL" \
  --user-data-dir="${HOME}/.config/vnotice-kiosk" \
  --autoplay-policy=no-user-gesture-required \
  --noerrdialogs \
  --disable-infobars \
  --start-fullscreen \
  --check-for-update-interval=31536000
EOF

chmod +x ~/start_vnotice.sh
```

Now register it in the desktop autostart folder:
```bash
mkdir -p ~/.config/autostart

cat << 'EOF' > ~/.config/autostart/vnotice.desktop
[Desktop Entry]
Type=Application
Name=V Notice Display
Exec=/home/pi/start_vnotice.sh
X-GNOME-Autostart-enabled=true
EOF
```
*(Note: If your Raspberry Pi username is not `pi`, replace `/home/pi/` with `/home/yourusername/` or `$HOME`).*

#### Step 4: Reboot
```bash
sudo reboot
```

---

## 🖥️ Option B: Full Local Server on Raspberry Pi (Offline Resilient)

Use this if you want the Raspberry Pi to host both the **backend server** and the **display** locally on the device (so notices keep rotating even if the internet goes down completely).

1. Clone your repository to the Raspberry Pi:
   ```bash
   git clone https://github.com/anrix05/V-Notice.git ~/v-notice
   cd ~/v-notice
   ```
2. Run the automated installer:
   ```bash
   chmod +x install_rpi.sh systemd/kiosk.sh
   ./install_rpi.sh
   ```
   *(To target a specific department board, use `DEPARTMENT_CODE=CMPN ./install_rpi.sh`)*
3. The installer sets up:
   - Systemd background service (`vnotice.service`) running the Flask backend.
   - Chromium fullscreen kiosk autostarting on display boot.
   - Offline-first cache syncing via local Service Worker.

---

## 💻 Option C: Windows Kiosk Mode (Testing or Intel NUC / Mini PC)

To run the display in kiosk mode with automatic sound on a Windows PC:

1. Open Command Prompt or PowerShell in the project directory.
2. Run:
   ```cmd
   start_display.bat https://v-notice.onrender.com/display/ALL
   ```
   *(Defaults to `https://v-notice.onrender.com/display/ALL` if no URL is provided).*

---

## 🔊 How Audio Works on the Display

For sound to play from a video notice:
1. **Notice Setting**: When creating or editing the video notice in the Admin Portal, toggle **"Play sound"** to **ON**.
2. **Screen Setting**: Under the **Screens** tab in the Admin Portal, make sure the target screen's **"Sound"** switch is **ON** (and adjust volume slider as desired).
3. **Display Output**: When that video notice rotates onto the screen, audio will play automatically at the configured volume without requiring anyone to click or touch the display.

---

## ❓ Frequently Asked Questions & Troubleshooting

### 1. How do I exit kiosk mode if I plug in a keyboard?
Press **`Alt + F4`** or **`Ctrl + W`** to close the Chromium kiosk window and return to the Raspberry Pi desktop.

### 2. How do I prevent the screen from going black (blanking)?
In Raspberry Pi OS:
```bash
sudo raspi-config
```
Navigate to **Display Options** > **Screen Blanking** > Select **No** (Disable screen blanking).

### 3. How do I change the display to a different department?
Simply edit the URL in `~/start_vnotice.sh` (or `~/.config/autostart/vnotice.desktop`):
- College-Wide (All): `https://v-notice.onrender.com/display/ALL`
- Computer Engineering: `https://v-notice.onrender.com/display/CMPN`
- Information Technology: `https://v-notice.onrender.com/display/INFT`
- Electronics & Telecom: `https://v-notice.onrender.com/display/EXTC`
- Electronics & Computer Science: `https://v-notice.onrender.com/display/EXCS`
- Biomedical Engineering: `https://v-notice.onrender.com/display/BIOM`
