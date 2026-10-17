import os
import sys
import time
import hmac
import secrets
import threading
from typing import Optional, Tuple
from werkzeug.security import check_password_hash
from config import ADMIN_PASSWORD, BASE_DIR

# ==============================================================================
# 1. Admin Password Verification (Hash with constant-time or plaintext fallback)
# ==============================================================================
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")

def verify_admin_password(candidate: str) -> bool:
    if not candidate:
        return False
    if ADMIN_PASSWORD_HASH:
        try:
            return check_password_hash(ADMIN_PASSWORD_HASH, candidate)
        except Exception:
            return False
    # Fallback to constant-time plaintext comparison
    return hmac.compare_digest(candidate.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8"))

def check_password_config_warnings():
    if not ADMIN_PASSWORD_HASH:
        if ADMIN_PASSWORD == "vnotice2026":
            print("!" * 72, file=sys.stderr)
            print("SECURITY WARNING: Using default ADMIN_PASSWORD ('vnotice2026').", file=sys.stderr)
            print("Set ADMIN_PASSWORD_HASH (or custom ADMIN_PASSWORD) in production.", file=sys.stderr)
            print("!" * 72, file=sys.stderr)
        else:
            print("[INFO] Admin authentication using plaintext ADMIN_PASSWORD env var.", file=sys.stderr)
            print("       Recommendation: Set ADMIN_PASSWORD_HASH for cryptographic hashing.", file=sys.stderr)

# ==============================================================================
# 2. In-Process Rate Limiter & Lockout (5 failed attempts per 10 mins per IP)
# ==============================================================================
class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._failures = {}  # ip -> list of timestamps

    def is_locked(self, key: str) -> Tuple[bool, int]:
        """Returns (is_locked, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            attempts = self._failures.get(key, [])
            # Prune attempts older than window
            attempts = [t for t in attempts if now - t < self.window_seconds]
            self._failures[key] = attempts
            
            if len(attempts) >= self.max_attempts:
                # Lockout: time until the oldest attempt leaves the window
                oldest = attempts[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                return True, retry_after
            return False, 0

    def record_failure(self, key: str):
        now = time.time()
        with self._lock:
            attempts = self._failures.get(key, [])
            attempts = [t for t in attempts if now - t < self.window_seconds]
            attempts.append(now)
            self._failures[key] = attempts

    def record_success(self, key: str):
        with self._lock:
            self._failures.pop(key, None)

login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=600)
api_key_rate_limiter = RateLimiter(max_attempts=15, window_seconds=600)

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
