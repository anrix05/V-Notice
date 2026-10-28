#!/usr/bin/env bash
# V Notice Display Kiosk Launcher (Linux / Raspberry Pi)
# Launches Chromium or Chrome with autoplay policy set to no-user-gesture-required

DISPLAY_URL="${1:-https://v-notice.onrender.com/display/ALL}"
KIOSK_USER_DATA="${HOME}/.config/vnotice-kiosk"
mkdir -p "${KIOSK_USER_DATA}"

# Find Chrome / Chromium binary
CHROME_BIN=$(command -v google-chrome || command -v chromium-browser || command -v chromium || command -v google-chrome-stable)

if [ -z "$CHROME_BIN" ]; then
  echo "[ERROR] Neither Chrome nor Chromium was found on this system." >&2
  exit 1
fi

echo "Starting V Notice kiosk for ${DISPLAY_URL}..."
exec "$CHROME_BIN" --kiosk "${DISPLAY_URL}" \
  --user-data-dir="${KIOSK_USER_DATA}" \
  --autoplay-policy=no-user-gesture-required \
  --noerrdialogs \
  --disable-infobars \
  --start-fullscreen \
  --check-for-update-interval=31536000 "$@"
