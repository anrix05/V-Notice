import os
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

# Storage directory (supports optional STORAGE_DIR volume on Railway / Docker)
STORAGE_DIR = Path(os.environ.get('STORAGE_DIR', BASE_DIR))
MEDIA_FOLDER = STORAGE_DIR / 'media'
DATA_FILE = STORAGE_DIR / 'notices.json'

# Ensure directories exist
MEDIA_FOLDER.mkdir(parents=True, exist_ok=True)

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
