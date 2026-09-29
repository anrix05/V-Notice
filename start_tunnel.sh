#!/usr/bin/env bash
# ==============================================================================
# V Notice — Cloudflare Remote Admin Tunnel for Raspberry Pi / Linux
# Allows faculty/admins to access http://localhost:5001 from anywhere on mobile/home
# ==============================================================================

echo "=========================================================="
echo "        V NOTICE — SECURE REMOTE ADMIN TUNNEL            "
echo "=========================================================="
echo "Starting Cloudflare Tunnel for Admin Portal (Port 5001)..."
echo ""

# Check if cloudflared is installed; install if missing
if ! command -v cloudflared &> /dev/null; then
    echo "Installing cloudflared for Raspberry Pi..."
    ARCH="$(uname -m)"
    if [ "$ARCH" = "aarch64" ]; then
        curl -sL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    else
        curl -sL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm.deb
    fi
    sudo dpkg -i /tmp/cloudflared.deb
    rm -f /tmp/cloudflared.deb
fi

echo "Connecting to Cloudflare edge..."
cloudflared tunnel --url http://localhost:5001
