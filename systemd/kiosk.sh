#!/usr/bin/env bash
# V Notice Chromium Kiosk Launcher for Raspberry Pi OS
# Optimized for 18-inch & 22-inch standard monitors (1080p / 900p / 720p) & 7-inch displays

# Disable screen blanking & power saving
xset s noblank
xset s off
xset -dpms

# Hide mouse cursor when idle
unclutter -idle 0.5 -root &

# Wait for Flask display server to become active
while ! curl -s http://localhost:5000/api/health > /dev/null; do
    sleep 1
done

# Persistent user data directory so Service Worker and local caches survive reboot
KIOSK_USER_DATA="${HOME}/.config/vnotice-kiosk"
mkdir -p "${KIOSK_USER_DATA}/Default"

# Reset Chromium crash warnings after reboot or power loss
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "${KIOSK_USER_DATA}/Default/Preferences" 2>/dev/null
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "${KIOSK_USER_DATA}/Default/Preferences" 2>/dev/null
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' ~/.config/chromium/Default/Preferences 2>/dev/null
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' ~/.config/chromium/Default/Preferences 2>/dev/null

# Find Chromium binary (chromium-browser on Bullseye, chromium on Bookworm)
CHROMIUM_BIN=$(command -v chromium-browser || command -v chromium)

# Launch Chromium in true fullscreen kiosk mode (persists service worker and cache across reboots)
"$CHROMIUM_BIN" --kiosk http://localhost:5000 \
  --user-data-dir="${KIOSK_USER_DATA}" \
  --autoplay-policy=no-user-gesture-required \
  --noerrdialogs \
  --disable-infobars \
  --start-fullscreen \
  --check-for-update-interval=31536000
