import os
import sys
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
IS_RENDER = os.environ.get('RENDER') is not None
if IS_RENDER:
    # Check if MEDIA_DIR is default ephemeral or custom mounted volume
    is_custom_mount = os.environ.get('STORAGE_DIR') or os.environ.get('MEDIA_DIR')
    if not is_custom_mount:
        print('!' * 72, file=sys.stderr)
        print('WARNING: Running on Render free tier with ephemeral disk storage.', file=sys.stderr)
        print('Notice data and uploaded media will be lost on container redeploy/restart.', file=sys.stderr)
        print('To persist data across redeploys, attach a Render Persistent Disk and set STORAGE_DIR.', file=sys.stderr)
        print('!' * 72, file=sys.stderr)

# Admin authentication (Rule 11: read from ADMIN_PASSWORD env var)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'vnotice2026')

# Server ports (Rule 3)
DISPLAY_PORT = int(os.environ.get('DISPLAY_PORT', 5000))
ADMIN_PORT = int(os.environ.get('ADMIN_PORT', 5001))
PORT = int(os.environ.get('PORT', ADMIN_PORT))

# File uploads (Rule 12: 200 MB maximum)
MAX_CONTENT_LENGTH = 200 * 1024 * 1024

# Rule 12: Only allow .jpg, .jpeg, .png, .webp, .gif, .mp4, .webm
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
