#!/usr/bin/env bash
# ==============================================================================
# V NOTICE — Raspberry Pi Display-Only Kiosk Setup (Thin Client)
# For Raspberry Pis that ONLY display the live Render link without running backend.
# Configures:
# 1. Zero-click unmuted audio policy for https://v-notice.onrender.com
# 2. Fullscreen auto-start on boot with no mouse cursor and no screen sleep
# ==============================================================================

set -e

DISPLAY_URL="${1:-https://v-notice.onrender.com/display/ALL}"
CURRENT_USER="$(whoami)"

echo "Setting up V Notice Display-Only Kiosk for: ${DISPLAY_URL}"

# 1. Install helper packages (unclutter hides mouse, xdotool for synthetic click fallback)
echo "[1/4] Installing display utilities..."
sudo apt update
sudo apt install -y unclutter xdotool curl

# 2. Setup Chromium Enterprise Autoplay Policy
echo "[2/4] Whitelisting ${DISPLAY_URL} for automatic sound..."
sudo mkdir -p /etc/chromium/policies/managed /etc/chromium-browser/policies/managed 2>/dev/null || true

cat <<EOF | sudo tee /etc/chromium/policies/managed/vnotice_display.json > /dev/null
{
  "AutoplayAllowed": true,
  "AutoplayAllowlist": [
    "https://v-notice.onrender.com",
    "https://v-notice.onrender.com/*",
    "http://localhost:5000",
    "http://localhost:5000/*"
  ]
}
EOF
sudo cp /etc/chromium/policies/managed/vnotice_display.json /etc/chromium-browser/policies/managed/vnotice_display.json 2>/dev/null || true

# 3. Create persistent launch script
echo "[3/4] Creating kiosk launch script at ~/start_vnotice.sh..."
cat <<EOF > "/home/${CURRENT_USER}/start_vnotice.sh"
#!/usr/bin/env bash
# Disable screen sleep & blanking
xset s noblank 2>/dev/null || true
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

# Hide mouse cursor
unclutter -idle 0.5 -root &

# Synthetic click backup after 4 seconds to guarantee audio unlock without mouse/keyboard
(sleep 4 && xdotool click 1 2>/dev/null || true) &

# Find Chromium binary (chromium-browser or chromium)
CHROMIUM_BIN=\$(command -v chromium-browser || command -v chromium)

if [ -z "\$CHROMIUM_BIN" ]; then
  echo "Error: Chromium browser not found. Installing..."
  sudo apt install -y chromium-browser
  CHROMIUM_BIN=\$(command -v chromium-browser || command -v chromium)
fi

# Reset crash dialogs from unexpected power cuts
mkdir -p "/home/${CURRENT_USER}/.config/vnotice-kiosk/Default"
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' "/home/${CURRENT_USER}/.config/vnotice-kiosk/Default/Preferences" 2>/dev/null || true
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' "/home/${CURRENT_USER}/.config/vnotice-kiosk/Default/Preferences" 2>/dev/null || true

# Launch fullscreen with autoplay enabled
"\$CHROMIUM_BIN" --kiosk "${DISPLAY_URL}" \\
  --user-data-dir="/home/${CURRENT_USER}/.config/vnotice-kiosk" \\
  --autoplay-policy=no-user-gesture-required \\
  --noerrdialogs \\
  --disable-infobars \\
  --start-fullscreen \\
  --check-for-update-interval=31536000
EOF

chmod +x "/home/${CURRENT_USER}/start_vnotice.sh"

# 4. Configure auto-start on boot
echo "[4/4] Configuring auto-start on desktop boot..."
AUTOSTART_DIR="/home/${CURRENT_USER}/.config/autostart"
mkdir -p "${AUTOSTART_DIR}"

cat <<EOF > "${AUTOSTART_DIR}/vnotice-display.desktop"
[Desktop Entry]
Type=Application
Name=V Notice Display Board
Exec=/home/${CURRENT_USER}/start_vnotice.sh
X-GNOME-Autostart-enabled=true
EOF

echo ""
echo "=========================================================="
echo " ✔ SETUP COMPLETE!"
echo " Display URL: ${DISPLAY_URL}"
echo "=========================================================="
echo "When you reboot the Raspberry Pi, it will automatically:"
echo " 1. Turn on and launch V Notice in fullscreen kiosk mode."
echo " 2. Play sound automatically without needing a mouse or keyboard."
echo ""
echo "To test it now, run: ~/start_vnotice.sh"
echo "Or reboot with:      sudo reboot"
