import os
import sys
import hashlib
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
STRICT_PRODUCTION = (
    os.environ.get('FLASK_ENV') == 'production' or 
    os.environ.get('PRODUCTION', '').lower() in ('true', '1')
)
IS_PRODUCTION = STRICT_PRODUCTION or IS_RENDER or IS_RAILWAY

# Production & Proxy Configuration
ALLOW_WEAK_SECRETS = os.environ.get('ALLOW_WEAK_SECRETS', 'false').lower() in ('true', '1', 'yes')
ALLOW_API_KEY_AUTH = os.environ.get(
    'ALLOW_API_KEY_AUTH',
    'false' if IS_PRODUCTION else 'true'
).lower() in ('true', '1', 'yes')
TRUSTED_PROXY_HOPS = int(os.environ.get('TRUSTED_PROXY_HOPS', '1' if IS_RENDER else '0'))

# Phase 2A: Accounts, Invites & Session Lifetimes
ALLOW_BOOTSTRAP_ADMIN_ENV = os.environ.get('ALLOW_BOOTSTRAP_ADMIN')  # None = auto until first DB admin exists
INVITE_EXPIRY_HOURS = int(os.environ.get('INVITE_EXPIRY_HOURS', 72))
ADMIN_SESSION_HOURS = int(os.environ.get('ADMIN_SESSION_HOURS', 8))
FACULTY_SESSION_DAYS = int(os.environ.get('FACULTY_SESSION_DAYS', 30))

# Known weak default password hashes (SHA-256) so no literal default secret is shipped
_KNOWN_WEAK_PASSWORD_HASHES = {
    '19f27a1c037c6db3e5aa85f4b7e6eb3d36373bf763b69908f62506f101a0a871',  # legacy default
    '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918',  # admin
    '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8',  # password
    '753bb5652c0b9565e103d1413283c63718d3e3f9888751d93026a99787b7cb7b',  # changeme
    '37a8eec1ce19687d132fe29051dca629d164e2c4958ba141d5f4133a33f0688f',  # default
}
_KNOWN_WEAK_SECRETS = {'default', 'vnotice-default-secret', 'changeme', 'secret', 'dev-secret'}

def validate_production_secrets(is_prod=None, allow_weak=None):
    """Validate SECRET_KEY and ADMIN_PASSWORD in production. Never logs secret values."""
    prod = IS_PRODUCTION if is_prod is None else is_prod
    weak_ok = ALLOW_WEAK_SECRETS if allow_weak is None else allow_weak
    if not prod:
        return True, []

    issues = []
    raw_secret = os.environ.get('SECRET_KEY', '')
    if not raw_secret or len(raw_secret) < 32 or raw_secret in _KNOWN_WEAK_SECRETS:
        issues.append('SECRET_KEY must be set and at least 32 characters long')

    raw_hash = os.environ.get('ADMIN_PASSWORD_HASH', '')
    if not raw_hash:
        raw_pw = os.environ.get('ADMIN_PASSWORD', '')
        pw_digest = hashlib.sha256(raw_pw.encode('utf-8')).hexdigest() if raw_pw else ''
        if not raw_pw or len(raw_pw) < 12 or pw_digest in _KNOWN_WEAK_PASSWORD_HASHES:
            issues.append('ADMIN_PASSWORD must be at least 12 characters and not a known default (or set ADMIN_PASSWORD_HASH)')

    if issues:
        header = 'SECURITY WARNING (ALLOW_WEAK_SECRETS=true):' if weak_ok else 'FATAL SECURITY ERROR:'
        print('!' * 72, file=sys.stderr)
        print(header, file=sys.stderr)
        for msg in issues:
            print(f' - {msg}', file=sys.stderr)
        print('!' * 72, file=sys.stderr)
        if not weak_ok:
            sys.exit(1)
        return False, issues
    return True, []

# SECRET_KEY Configuration
SECRET_KEY = os.environ.get('SECRET_KEY')
if IS_PRODUCTION and os.environ.get('VNOTICE_TEST_MODE') != '1':
    validate_production_secrets()

if not SECRET_KEY or SECRET_KEY in _KNOWN_WEAK_SECRETS:
    SECRET_KEY = os.environ.get('DEV_SECRET_KEY') or secrets.token_hex(32)
    if not IS_PRODUCTION:
        print('!' * 72, file=sys.stderr)
        print('WARNING: SECRET_KEY environment variable is not set or using insecure default.', file=sys.stderr)
        print('Generated an ephemeral secure random key for this session. Admin sessions will invalidate on process restart.', file=sys.stderr)
        print('For production persistence, set SECRET_KEY in your environment variables.', file=sys.stderr)
        print('!' * 72, file=sys.stderr)

# Storage directory (supports optional STORAGE_DIR volume on Railway / Docker / Render)
STORAGE_DIR = Path(os.environ.get('STORAGE_DIR', BASE_DIR))

# Media directory (configurable via MEDIA_DIR, defaults to STORAGE_DIR / 'media')
MEDIA_DIR = Path(os.environ.get('MEDIA_DIR', STORAGE_DIR / 'media'))
MEDIA_FOLDER = MEDIA_DIR  # Backwards compatibility alias

# Cloudinary Storage Configuration
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL')

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
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
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
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'm4a', 'wav', 'webm', 'ogg'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS | ALLOWED_AUDIO_EXTENSIONS

ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
    'video/mp4',
    'video/webm',
    'audio/mpeg',
    'audio/mp3',
    'audio/mp4',
    'audio/x-m4a',
    'audio/wav',
    'audio/wave',
    'audio/x-wav',
    'audio/webm',
    'audio/ogg',
}

# Voice Notices configuration
VOICE_NOTICES_ENABLED = os.environ.get('VOICE_NOTICES_ENABLED', 'false').lower() in ('true', '1', 'yes')
MAX_VOICE_DURATION_SECONDS = int(os.environ.get('MAX_VOICE_DURATION_SECONDS', 120))
MAX_VOICE_UPLOAD_MB = int(os.environ.get('MAX_VOICE_UPLOAD_MB', 10))
MAX_VOICE_CONTENT_LENGTH = MAX_VOICE_UPLOAD_MB * 1024 * 1024


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


# Observability & Version (Phase 7)
VERSION = '2.2.0'
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

# Feature Flags
VIDEO_SOUND_ENABLED = os.environ.get('VIDEO_SOUND_ENABLED', 'true').lower() in ('true', '1', 'yes')
FLAG_EVENT_ENABLED = os.environ.get('FLAG_EVENT_ENABLED', 'true').lower() in ('true', '1', 'yes')
FLAG_TRIGGER_TOKEN = os.environ.get('FLAG_TRIGGER_TOKEN', '')
SHOW_POSTED_BY_ON_DISPLAY = os.environ.get('SHOW_POSTED_BY_ON_DISPLAY', 'false').lower() in ('true', '1', 'yes')
