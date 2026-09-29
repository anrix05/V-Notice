#!/usr/bin/env bash
# ==============================================================================
# V NOTICE — Automated 1-Click Raspberry Pi Kiosk Installer
# Compatible with Raspberry Pi OS (Bullseye & Bookworm 32-bit / 64-bit)
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}      V NOTICE — RASPBERRY PI KIOSK AUTO-INSTALLER        ${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo ""

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"

echo -e "📂 Install Directory: ${GREEN}${APP_DIR}${NC}"
echo -e "👤 Running as User:  ${GREEN}${CURRENT_USER}${NC}"
echo ""

# 1. Update and install system dependencies
echo -e "${BLUE}[1/5] Installing system packages & Chromium...${NC}"
sudo apt update
sudo apt install -y python3 python3-pip python3-venv chromium-browser unclutter curl

# 2. Setup Python Virtual Environment (Bookworm & Bullseye compatible)
echo -e "${BLUE}[2/5] Setting up Python environment...${NC}"
if [ ! -d "${APP_DIR}/venv" ]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# 3. Create .env if not exists
if [ ! -f "${APP_DIR}/.env" ]; then
    echo -e "${BLUE}[3/5] Creating default .env configuration...${NC}"
    cat <<EOF > "${APP_DIR}/.env"
DISPLAY_PORT=5000
ADMIN_PORT=5001
ADMIN_PASSWORD=vnotice2026
EOF
else
    echo -e "${BLUE}[3/5] Existing .env file found. Preserving configuration.${NC}"
fi

# 4. Install systemd background service
echo -e "${BLUE}[4/5] Installing systemd auto-start service...${NC}"
SERVICE_FILE="/etc/systemd/system/vnotice.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=V Notice Smart Digital Notice Board
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python ${APP_DIR}/app.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable vnotice.service
sudo systemctl restart vnotice.service

echo -e "${GREEN}✓ V Notice service installed and started successfully!${NC}"

# 5. Configure Fullscreen Kiosk Mode on Boot
echo -e "${BLUE}[5/5] Configuring Fullscreen Chromium Kiosk on display boot...${NC}"
chmod +x "${APP_DIR}/systemd/kiosk.sh"
chmod +x "${APP_DIR}/start.sh"

# Setup autostart directory for desktop session
AUTOSTART_DIR="/home/${CURRENT_USER}/.config/autostart"
mkdir -p "${AUTOSTART_DIR}"

cat <<EOF > "${AUTOSTART_DIR}/vnotice-kiosk.desktop"
[Desktop Entry]
Type=Application
Name=V Notice Kiosk
Exec=${APP_DIR}/systemd/kiosk.sh
X-GNOME-Autostart-enabled=true
EOF

echo ""
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}           🎉 V NOTICE INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}==========================================================${NC}"
echo -e "🖥️  Display Screen:  ${BLUE}http://localhost:5000${NC}"
echo -e "⚙️  Admin Portal:    ${BLUE}http://$(hostname -I | awk '{print $1}'):5001${NC}"
echo -e "🔑 Default Password: ${GREEN}vnotice2026${NC}"
echo ""
echo -e "To launch fullscreen kiosk now, run:"
echo -e "  ${BLUE}${APP_DIR}/systemd/kiosk.sh${NC}"
echo ""
echo -e "On reboot, the Raspberry Pi will automatically display V Notice full screen!"
echo ""
