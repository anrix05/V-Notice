#!/usr/bin/env bash
# V Notice Chromium Kiosk Launcher for Raspberry Pi OS (7-inch 800x480 LCD)

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

# Launch Chromium in Kiosk mode
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' ~/.config/chromium/Default/Preferences
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' ~/.config/chromium/Default/Preferences

chromium-browser --kiosk http://localhost:5000 \
  --noerrdialogs \
  --disable-infobars \
  --window-size=800,480 \
  --window-position=0,0 \
  --check-for-update-interval=31536000
