import os
import sys
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'

# Load .env if present (without external dependencies)
if ENV_FILE.exists():
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# Environment & Production detection
IS_RENDER = os.environ.get('RENDER') is not None
IS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None
IS_PRODUCTION = (
    IS_RENDER or 
    IS_RAILWAY or 
    os.environ.get('FLASK_ENV') == 'production' or 
    os.environ.get('PRODUCTION', '').lower() in ('true', '1')
)

# SECRET_KEY Configuration (Requirement: Required in production, refuse to start if default/missing)
SECRET_KEY = os.environ.get('SECRET_KEY')
if IS_PRODUCTION:
    if not SECRET_KEY or SECRET_KEY in ('default', 'vnotice-default-secret', 'changeme'):
        print('FATAL SECURITY ERROR: SECRET_KEY environment variable is required in production.', file=sys.stderr)
        print('Set a secure random string (e.g. openssl rand -hex 32) in your environment variables.', file=sys.stderr)
        sys.exit(1)
else:
    if not SECRET_KEY:
        SECRET_KEY = os.environ.get('DEV_SECRET_KEY') or secrets.token_hex(32)

# Storage directory (supports optional STORAGE_DIR volume on Railway / Docker / Render)
STORAGE_DIR = Path(os.environ.get('STORAGE_DIR', BASE_DIR))

# Media directory (configurable via MEDIA_DIR, defaults to STORAGE_DIR / 'media')
MEDIA_DIR = Path(os.environ.get('MEDIA_DIR', STORAGE_DIR / 'media'))
MEDIA_FOLDER = MEDIA_DIR  # Backwards compatibility alias

# Database file (SQLite in WAL mode)
DB_FILE = Path(os.environ.get('DB_FILE', STORAGE_DIR / 'notices.db'))
DATA_FILE = STORAGE_DIR / 'notices.json'  # Used for migration

# Ensure storage directories exist
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Render ephemeral storage detection warning
if IS_RENDER:
    is_custom_mount = os.environ.get('STORAGE_DIR') or os.environ.get('MEDIA_DIR')
    if not is_custom_mount:
        print('!' * 72, file=sys.stderr)
        print('WARNING: Running on Render free tier with ephemeral disk storage.', file=sys.stderr)
        print('Notice data and uploaded media will be lost on container redeploy/restart.', file=sys.stderr)
        print('To persist data across redeploys, attach a Render Persistent Disk and set STORAGE_DIR.', file=sys.stderr)
        print('!' * 72, file=sys.stderr)

# Admin authentication credentials
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'vnotice2026')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')

# Server ports
DISPLAY_PORT = int(os.environ.get('DISPLAY_PORT', 5000))
ADMIN_PORT = int(os.environ.get('ADMIN_PORT', 5001))
PORT = int(os.environ.get('PORT', ADMIN_PORT))

# File uploads (MAX_UPLOAD_MB, default 200MB)
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', 200))
MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

# Allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
    'video/mp4',
    'video/webm',
}


# Weather configuration (Phase 3: Resilient & Gracefully Degrading)
WEATHER_ENABLED = os.environ.get('WEATHER_ENABLED', 'true').lower() in ('true', '1', 'yes')
WEATHER_LAT = float(os.environ.get('WEATHER_LAT', os.environ.get('CAMPUS_LAT', 19.0760)))
WEATHER_LON = float(os.environ.get('WEATHER_LON', os.environ.get('CAMPUS_LON', 72.8777)))
WEATHER_LABEL = os.environ.get('WEATHER_LABEL', os.environ.get('CAMPUS_CITY', 'Mumbai'))

# Public base URL (for QR code scan target, e.g. https://v-notice.onrender.com)
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')

# Urgent notice audio chime (default disabled; purely client-side synthetic audio when enabled)
URGENT_CHIME = os.environ.get('URGENT_CHIME', 'false').lower() in ('true', '1', 'yes')


# Sync & Polling Efficiency (Phase 4)
POLL_INTERVAL_SECONDS = int(os.environ.get('POLL_INTERVAL_SECONDS', 5))
SSE_ENABLED = os.environ.get('SSE_ENABLED', 'false').lower() in ('true', '1', 'yes')
