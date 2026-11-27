import os
import sys
import time
import hmac
import secrets
import threading
from typing import Optional, Tuple
from werkzeug.security import check_password_hash
import config
from config import BASE_DIR

# ==============================================================================
# 1. Admin Password Verification (Hash with constant-time or plaintext fallback)
# ==============================================================================
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

def verify_admin_password(candidate: str) -> bool:
    if not candidate:
        return False
    pw_hash = ADMIN_PASSWORD_HASH or getattr(config, "ADMIN_PASSWORD_HASH", None)
    if pw_hash:
        try:
            return check_password_hash(pw_hash, candidate)
        except Exception:
            return False
    admin_pw = getattr(config, "ADMIN_PASSWORD", "")
    if not admin_pw:
        return False
    # Fallback to constant-time plaintext comparison
    return hmac.compare_digest(candidate.encode("utf-8"), admin_pw.encode("utf-8"))

def check_password_config_warnings():
    pw_hash = ADMIN_PASSWORD_HASH or getattr(config, "ADMIN_PASSWORD_HASH", None)
    admin_pw = getattr(config, "ADMIN_PASSWORD", "")
    if not pw_hash:
        if not admin_pw:
            print("!" * 72, file=sys.stderr)
            print("SECURITY WARNING: ADMIN_PASSWORD is not set; super-admin password login is disabled.", file=sys.stderr)
            print("Set ADMIN_PASSWORD_HASH (or ADMIN_PASSWORD) in your environment.", file=sys.stderr)
            print("!" * 72, file=sys.stderr)
        elif len(admin_pw) < 12:
            print("!" * 72, file=sys.stderr)
            print("SECURITY WARNING: ADMIN_PASSWORD is shorter than 12 characters.", file=sys.stderr)
            print("Set ADMIN_PASSWORD_HASH or a stronger ADMIN_PASSWORD (>= 12 chars) in production.", file=sys.stderr)
            print("!" * 72, file=sys.stderr)
        else:
            print("[INFO] Admin authentication using plaintext ADMIN_PASSWORD env var.", file=sys.stderr)
            print("       Recommendation: Set ADMIN_PASSWORD_HASH for cryptographic hashing.", file=sys.stderr)

# ==============================================================================
# 2. In-Process Rate Limiter & Progressive Lockout (by IP and account)
# ==============================================================================
class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 600, base_delay_seconds: int = 30, max_delay_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._lock = threading.Lock()
        self._failures = {}  # key -> list of timestamps
        self._locked_until = {}  # key -> unix timestamp

    def is_locked(self, key: str) -> Tuple[bool, int]:
        """Returns (is_locked, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            attempts = self._failures.get(key, [])
            attempts = [t for t in attempts if now - t < self.window_seconds]
            self._failures[key] = attempts

            if not attempts:
                self._locked_until.pop(key, None)
                return False, 0

            locked_until = self._locked_until.get(key, 0)
            if locked_until > now:
                return True, max(1, int(locked_until - now))
            return False, 0

    def record_failure(self, key: str) -> int:
        """Record a failed attempt and return the progressive cooldown delay (0 if below threshold)."""
        now = time.time()
        with self._lock:
            attempts = self._failures.get(key, [])
            attempts = [t for t in attempts if now - t < self.window_seconds]
            attempts.append(now)
            self._failures[key] = attempts

            count = len(attempts)
            if count >= self.max_attempts:
                exponent = count - self.max_attempts
                delay = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** exponent))
                self._locked_until[key] = max(self._locked_until.get(key, 0), now + delay)
                return delay
            return 0

    def record_success(self, key: str):
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=900, base_delay_seconds=30, max_delay_seconds=900)
account_rate_limiter = RateLimiter(max_attempts=5, window_seconds=900, base_delay_seconds=30, max_delay_seconds=900)
api_key_rate_limiter = RateLimiter(max_attempts=15, window_seconds=600, base_delay_seconds=30, max_delay_seconds=900)
invite_rate_limiter = RateLimiter(max_attempts=10, window_seconds=600, base_delay_seconds=30, max_delay_seconds=900)
import_rate_limiter = RateLimiter(max_attempts=30, window_seconds=300, base_delay_seconds=15, max_delay_seconds=300)

# ==============================================================================
# 2B. Password Strength Validation (min 12 chars + bundled common list)
# ==============================================================================
def _load_common_passwords() -> set:
    path = BASE_DIR / "common_passwords.txt"
    if not path.is_file():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except Exception:
        return set()

_COMMON_PASSWORDS = _load_common_passwords()

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Enforce >= 12 chars and reject bundled common passwords. No composition rules."""
    if not password or len(password) < 12:
        return False, "Password must be at least 12 characters long."
    if password.strip().lower() in _COMMON_PASSWORDS:
        return False, "Password is too common. Please choose a stronger passphrase."
    return True, ""

# ==============================================================================
# 3. Magic-Byte Content Sniffing & File Validation
# ==============================================================================
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "webm", "mp3", "m4a", "wav", "ogg"}

def sniff_media_type(header_bytes: bytes) -> Optional[Tuple[str, str]]:
    """Inspects file header magic bytes. Returns (normalized_ext, media_category) or None.
    media_category is 'image', 'video', or 'audio'."""
    if len(header_bytes) < 4:
        return None

    # JPEG: FF D8 FF
    if header_bytes.startswith(b"\xFF\xD8\xFF"):
        return "jpg", "image"

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image"

    # GIF: GIF87a or GIF89a
    if header_bytes.startswith(b"GIF87a") or header_bytes.startswith(b"GIF89a"):
        return "gif", "image"

    # WEBP: RIFF....WEBP
    if header_bytes.startswith(b"RIFF") and len(header_bytes) >= 12 and header_bytes[8:12] == b"WEBP":
        return "webp", "image"

    # WAV: RIFF....WAVE
    if header_bytes.startswith(b"RIFF") and len(header_bytes) >= 12 and header_bytes[8:12] == b"WAVE":
        return "wav", "audio"

    # OGG: OggS
    if header_bytes.startswith(b"OggS"):
        return "ogg", "audio"

    # MP3: ID3 or MPEG audio frame sync (0xFF and (b1 & 0xE0) == 0xE0)
    if header_bytes.startswith(b"ID3") or (header_bytes[0] == 0xFF and (header_bytes[1] & 0xE0) == 0xE0):
        return "mp3", "audio"

    # MP4 / M4A: ....ftyp (box type at offset 4..8)
    if header_bytes[4:8] == b"ftyp":
        return "mp4", "video"

    # WEBM: 1A 45 DF A3 (EBML Header)
    if header_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm", "video"

    return None

def save_stream_to_disk(
    file_stream,
    dest_path,
    max_bytes: int = 200 * 1024 * 1024,
    chunk_size: int = 64 * 1024,
    expected_type: Optional[str] = None
) -> Tuple[str, str]:
    """Streams file to disk in chunks, validating magic bytes on first chunk without
    loading the full file into memory. Returns (detected_ext, media_category)."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    first_chunk = file_stream.read(chunk_size)
    if not first_chunk:
        raise ValueError("Uploaded file is empty.")

    detected = sniff_media_type(first_chunk)
    if not detected:
        if expected_type == "voice":
            raise ValueError("Unsupported or corrupted voice audio format. Allowed: MP3, M4A, WAV, WEBM, OGG.")
        raise ValueError("Unsupported or corrupted file format. Allowed: JPG, PNG, WEBP, GIF, MP4, WEBM.")

    ext, category = detected

    if expected_type == "voice":
        allowed_voice_exts = {"mp3", "m4a", "wav", "webm", "ogg", "mp4"}
        if ext not in allowed_voice_exts:
            raise ValueError("Unsupported or corrupted voice audio format. Allowed: MP3, M4A, WAV, WEBM, OGG.")
        category = "voice"
    elif category not in ("image", "video"):
        raise ValueError("Unsupported or corrupted file format. Allowed: JPG, PNG, WEBP, GIF, MP4, WEBM.")

    total_bytes = len(first_chunk)
    if total_bytes > max_bytes:
        raise ValueError(f"File exceeds maximum allowed size ({max_bytes // (1024*1024)}MB).")

    try:
        with open(dest_path, "wb") as f:
            f.write(first_chunk)
            while True:
                chunk = file_stream.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise ValueError(f"File exceeds maximum allowed size ({max_bytes // (1024*1024)}MB).")
                f.write(chunk)
    except Exception:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        raise

    return ext, category

# ==============================================================================
# 4. Random URL-Safe ID Generator
# ==============================================================================
def generate_notice_id() -> str:
    # secrets.token_urlsafe(8) generates 11 URL-safe characters with 64 bits of entropy
    return secrets.token_urlsafe(8)

# ==============================================================================
# 5. CSRF Protection for Session Mutations
# ==============================================================================
def generate_csrf_token() -> str:
    return secrets.token_hex(32)

def validate_csrf_token(session_token: str, request_token: str) -> bool:
    if not session_token or not request_token:
        return False
    return hmac.compare_digest(session_token, request_token)
