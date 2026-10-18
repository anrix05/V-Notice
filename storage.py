import os
import sys
import time
import datetime
import secrets
import mimetypes
import logging
import sqlite3
import shutil
import json
import re
import subprocess
from typing import Tuple, Optional, List, Dict, Any
try:
    from zoneinfo import ZoneInfo
    KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    KOLKATA_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30), name="Asia/Kolkata")
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import config
from config import (
    DB_FILE,
    DATA_FILE,
    MEDIA_DIR,
    MAX_CONTENT_LENGTH,
    ALLOWED_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    VIDEO_SOUND_ENABLED,
    FLAG_EVENT_ENABLED,
    FLAG_TRIGGER_TOKEN,
    VOICE_NOTICES_ENABLED,
    MAX_VOICE_DURATION_SECONDS,
    MAX_VOICE_UPLOAD_MB,
    MAX_VOICE_CONTENT_LENGTH,
    ALLOWED_AUDIO_EXTENSIONS,
)
from security import (
    generate_notice_id,
    sniff_media_type,
    save_stream_to_disk,
)

logger = logging.getLogger("vnotice.storage")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def detect_video_audio(file_path) -> str:
    """Detect whether video has an audio track using ffprobe.
    Returns 'true' if audio track exists, 'false' if silent video, 'unknown' if ffprobe is unavailable or error."""
    if not file_path:
        return "unknown"
    p = Path(file_path)
    if not p.is_file():
        return "unknown"
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffprobe_cmd:
        return "unknown"
    try:
        proc = subprocess.run(
            [
                ffprobe_cmd,
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(p)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            output = proc.stdout.strip().lower()
            return "true" if "audio" in output else "false"
        return "unknown"
    except Exception as e:
        logger.warning("ffprobe audio detection failed for %s: %s", file_path, e)
        return "unknown"

def probe_voice_media(file_path) -> Tuple[bool, Optional[float], str]:
    """Inspects media file with ffprobe to verify it is audio-only (has audio, no video).
    Returns (is_valid, duration_seconds, error_message)."""
    if not file_path:
        return False, None, "File path is required."
    p = Path(file_path)
    if not p.is_file():
        return False, None, "Media file not found on disk."
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffprobe_cmd:
        return True, None, ""

    try:
        proc = subprocess.run(
            [
                ffprobe_cmd,
                "-v", "error",
                "-show_entries", "stream=codec_type,codec_name:stream_disposition=attached_pic:format=duration",
                "-of", "json",
                str(p)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if proc.returncode != 0:
            return False, None, f"ffprobe error: {proc.stderr.strip()}"
        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        has_video = False
        for s in streams:
            if s.get("codec_type") == "video":
                disp = s.get("disposition") or {}
                if disp.get("attached_pic") != 1:
                    has_video = True
                    break

        if not has_audio:
            return False, None, "Voice notice must contain an audio track."
        if has_video:
            return False, None, "Voice notice cannot contain a video stream."

        duration = None
        fmt = data.get("format", {})
        if fmt.get("duration"):
            try:
                duration = float(fmt["duration"])
            except (ValueError, TypeError):
                duration = None

        # Check mean volume with ffmpeg volumedetect
        ffmpeg_cmd = shutil.which("ffmpeg")
        if ffmpeg_cmd:
            devnull = "NUL" if os.name == "nt" else "/dev/null"
            try:
                proc_vol = subprocess.run(
                    [
                        ffmpeg_cmd,
                        "-i", str(p),
                        "-filter:a", "volumedetect",
                        "-vn",
                        "-sn",
                        "-f", "null",
                        devnull
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10
                )
                match = re.search(r"mean_volume:\s*(-?(?:[0-9.]+|inf))\s*dB", proc_vol.stderr)
                if match:
                    val_str = match.group(1).lower()
                    if val_str in ("inf", "-inf"):
                        return False, None, "We did not hear anything. Check that your microphone is on and the right one is selected."
                    try:
                        mean_vol = float(val_str)
                        if mean_vol < -60.0:
                            return False, None, "We did not hear anything. Check that your microphone is on and the right one is selected."
                    except ValueError:
                        pass
            except Exception as e_vol:
                logger.warning("ffmpeg volumedetect failed for %s: %s", file_path, e_vol)

        return True, duration, ""
    except Exception as e:
        logger.warning("ffprobe probe_voice_media failed for %s: %s", file_path, e)
        return True, None, ""

def sanitize_or_generate_waveform(raw_waveform, audio_file_path=None) -> str:
    """Validates that waveform is a list of exactly 64 integers in 0..100.
    If valid, returns JSON string of the list. Otherwise, generates from audio file
    via ffmpeg/ffprobe when available, or returns a neutral static bar pattern."""
    if raw_waveform:
        try:
            val = raw_waveform
            if isinstance(val, str):
                val = json.loads(val)
            if isinstance(val, list) and len(val) == 64:
                cleaned = [max(0, min(100, int(round(float(v))))) for v in val]
                return json.dumps(cleaned)
        except Exception:
            pass

    # Try generating waveform server-side from audio file if available
    if audio_file_path:
        p = Path(audio_file_path)
        if p.is_file() and shutil.which("ffmpeg"):
            try:
                cmd = [
                    "ffmpeg", "-y", "-i", str(p),
                    "-ac", "1", "-ar", "8000", "-f", "s16le", "-"
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=6)
                raw = res.stdout
                if raw and len(raw) >= 128:
                    import struct, math
                    num_samples = len(raw) // 2
                    samples = struct.unpack(f"<{num_samples}h", raw[:num_samples * 2])
                    chunk_sz = max(1, num_samples // 64)
                    rms_values = []
                    for i in range(64):
                        chunk = samples[i * chunk_sz:(i + 1) * chunk_sz]
                        if chunk:
                            rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
                            rms_values.append(rms)
                        else:
                            rms_values.append(0.0)
                    max_rms = max(rms_values) if rms_values else 0
                    if max_rms > 0:
                        peaks = [max(8, min(100, int(round((r / max_rms) * 90 + 10)))) for r in rms_values]
                        return json.dumps(peaks)
            except Exception as e:
                logger.debug("Server-side waveform extraction via ffmpeg failed: %s", e)

    import math
    peaks = []
    for i in range(64):
        v = 20 + 50 * math.sin((i / 64) * math.pi) * (0.6 + 0.4 * math.sin(i * 0.7))
        peaks.append(max(5, min(100, int(round(v)))))
    return json.dumps(peaks)

def get_current_time_ms():
    return int(time.time() * 1000)

def compute_status(notice, now_ms=None):
    if now_ms is None:
        now_ms = get_current_time_ms()
    start = notice.get("start", 0)
    end = notice.get("end", float("inf"))
    if end is None:
        end = float("inf")
    
    if now_ms < start:
        return "scheduled"
    elif now_ms > end:
        return "expired"
    else:
        return "live"

SCREEN_CODE_REGEX = re.compile(r"^[A-Z0-9_-]{2,10}$")


def sanitize_screen_codes(raw_input):
    if not raw_input:
        return ["ALL"]
    results = []
    if isinstance(raw_input, str):
        cleaned = raw_input.strip()
        if cleaned.lower() == "default":
            return ["ALL"]
        if cleaned.startswith("[") and cleaned.endswith("]"):
            try:
                import json
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    return sanitize_screen_codes(parsed)
            except Exception:
                pass
        cleaned = cleaned.replace("[", "").replace("]", "").replace('"', "").replace("'", "")
        for part in cleaned.split(","):
            p = part.strip()
            if p.lower() == "default":
                results.append("ALL")
            elif p:
                results.append(p)
    elif isinstance(raw_input, (list, tuple, set)):
        for item in raw_input:
            if isinstance(item, str):
                results.extend(sanitize_screen_codes(item))
            elif item:
                results.append(str(item).strip())
    deduped = list(dict.fromkeys(results))
    if any(s.upper() == "ALL" for s in deduped):
        return ["ALL"]
    return deduped or ["ALL"]

def validate_screen_code(code: str) -> str:
    if not isinstance(code, str):
        raise ValueError("Screen code must be a string.")
    code = code.strip()
    if not SCREEN_CODE_REGEX.match(code):
        raise ValueError("Screen code must be 2-10 uppercase alphanumeric characters, underscores, or hyphens (e.g. CMPN, EXCS).")
    return code

def check_event_overlap(cand: dict, other: dict) -> bool:
    """Check if two daily events overlap on the same day and screen (including standup lead time and offset)."""
    # 1. Day overlap
    days_cand = set(d.strip().lower() for d in (cand.get("days_of_week") or []))
    days_other = set(d.strip().lower() for d in (other.get("days_of_week") or []))
    if not (days_cand & days_other):
        return False

    # 2. Screen overlap
    screens_cand = sanitize_screen_codes(cand.get("screens", "ALL"))
    screens_other = sanitize_screen_codes(other.get("screens", "ALL"))
    screen_overlap = ("ALL" in screens_cand or "ALL" in screens_other or bool(set(screens_cand) & set(screens_other)))
    if not screen_overlap:
        return False

    # 3. Time window (in seconds from midnight)
    def get_window(ev):
        st = ev.get("start_time", "11:00")
        try:
            parts = str(st).split(":")
            hh, mm = int(parts[0]), int(parts[1])
        except Exception:
            hh, mm = 11, 0
        offset = int(ev.get("start_offset_seconds", 0) or 0)
        dur = int(ev.get("duration_seconds", 60) or 60)
        show_standup = bool(ev.get("show_standup_text", False))
        lead = 15 if show_standup else 0
        base_sec = hh * 3600 + mm * 60 + offset
        start_sec = base_sec - lead
        end_sec = base_sec + dur
        return start_sec, end_sec

    s1, e1 = get_window(cand)
    s2, e2 = get_window(other)

    return (s1 < e2) and (s2 < e1)

SEED_DEPARTMENTS = [
    ("ALL", "All Departments (college-wide)", 0, 1, None),
    ("CMPN", "Computer Engineering", 1, 1, "#3B82F6"),
    ("INFT", "Information Technology", 2, 1, "#10B981"),
    ("EXTC", "Electronics & Telecommunication", 3, 1, "#F59E0B"),
    ("EXCS", "Electronics & Computer Science", 4, 1, "#8B5CF6"),
    ("BIOM", "Biomedical Engineering", 5, 1, "#EC4899"),
]

# ==============================================================================
# Media Storage Interface
# ==============================================================================
class MediaStorageBackend:
    def save(self, file_obj, filename: str, resource_type: str = "auto") -> str:
        raise NotImplementedError

    def delete(self, filename: str) -> bool:
        raise NotImplementedError

    def exists(self, filename: str) -> bool:
        raise NotImplementedError

    def get_path(self, filename: str) -> Path:
        raise NotImplementedError

    def url(self, filename: str) -> str:
        raise NotImplementedError

class LocalMediaStorage(MediaStorageBackend):
    def __init__(self, media_dir: Path = MEDIA_DIR):
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file_obj, filename: str, resource_type: str = "auto") -> str:
        dest_path = self.media_dir / filename
        stream = getattr(file_obj, "stream", file_obj)
        save_stream_to_disk(stream, dest_path, max_bytes=MAX_CONTENT_LENGTH)
        return filename

    def delete(self, filename: str) -> bool:
        if not filename:
            return False
        dest_path = self.media_dir / filename
        if dest_path.exists():
            try:
                dest_path.unlink()
                return True
            except OSError as e:
                logger.warning("Failed to delete media file %s: %s", filename, e)
                return False
        return False

    def exists(self, filename: str) -> bool:
        if not filename:
            return False
        return (self.media_dir / filename).exists()

    def get_path(self, filename: str) -> Path:
        return self.media_dir / filename

    def url(self, filename: str) -> str:
        return f"/media/{filename}"


class CloudinaryMediaStorage(MediaStorageBackend):
    def __init__(self, cloudinary_url: str = None, media_dir: Path = None):
        self.is_cloud = True
        import config
        self.media_dir = Path(media_dir) if media_dir else Path(getattr(config, "MEDIA_DIR", MEDIA_DIR))
        import cloudinary
        import cloudinary.uploader
        self.cloudinary = cloudinary
        self.uploader = cloudinary.uploader
        if cloudinary_url:
            os.environ["CLOUDINARY_URL"] = cloudinary_url
        cloudinary.reset_config()

    def save(self, file_obj, filename: str, resource_type: str = "auto") -> str:
        try:
            target = file_obj
            if isinstance(file_obj, (str, Path)):
                target = str(file_obj)
            else:
                target = getattr(file_obj, "stream", file_obj)
            res = self.uploader.upload(
                target,
                folder="vnotice",
                resource_type=resource_type,
                use_filename=True,
                unique_filename=True
            )
            return res.get("secure_url") or res.get("url") or filename
        except Exception as e:
            logger.error("Cloudinary upload failed: %s", e)
            raise

    def delete(self, filename: str) -> bool:
        if not filename:
            return False
        try:
            import re
            res_type = "image"
            public_id = None
            if "res.cloudinary.com" in filename:
                parts = filename.split("/upload/")
                if len(parts) >= 2:
                    m_type = re.search(r"/(image|video|raw)/upload/", filename)
                    if m_type:
                        res_type = m_type.group(1)
                    
                    segments = parts[1].split("/")
                    cleaned_segments = []
                    found_public = False
                    for seg in segments:
                        if not found_public:
                            if re.match(r"^v\d+$", seg):
                                found_public = True
                                continue
                            if any(seg.startswith(p) for p in ("c_", "w_", "h_", "q_", "f_", "b_", "g_", "e_", "fl_", "o_")) or "," in seg:
                                continue
                            found_public = True
                            cleaned_segments.append(seg)
                        else:
                            cleaned_segments.append(seg)
                    public_id_with_ext = "/".join(cleaned_segments) if cleaned_segments else segments[-1]
                    public_id = public_id_with_ext.rsplit(".", 1)[0]
            elif not filename.startswith("http"):
                public_id = filename.rsplit(".", 1)[0]

            if public_id:
                types_to_try = [res_type] if res_type in ("image", "video", "raw") else ["image", "video"]
                if "video" not in types_to_try:
                    types_to_try.append("video")
                if "image" not in types_to_try:
                    types_to_try.append("image")
                
                success = False
                for r_type in types_to_try:
                    try:
                        res = self.uploader.destroy(public_id, resource_type=r_type, invalidate=True)
                        if res and res.get("result") in ("ok", "not found"):
                            if res.get("result") == "ok":
                                success = True
                    except Exception as inner_e:
                        logger.debug("Cloudinary destroy error on %s (%s): %s", public_id, r_type, inner_e)
                logger.info("Cloudinary delete for '%s' completed (success=%s)", public_id, success)
                return True
            return False
        except Exception as e:
            logger.warning("Cloudinary delete failed for %s: %s", filename, e)
            return False

    def clean_orphaned_media(self, active_urls: set):
        deleted_count = 0
        try:
            import cloudinary.api
            for r_type in ("image", "video"):
                try:
                    res = cloudinary.api.resources(
                        type="upload",
                        prefix="vnotice/",
                        resource_type=r_type,
                        max_results=500
                    )
                    resources = res.get("resources", [])
                    for item in resources:
                        pub_id = item.get("public_id")
                        sec_url = item.get("secure_url", "")
                        url = item.get("url", "")
                        is_referenced = any(
                            (bool(pub_id) and pub_id in u) or
                            (bool(sec_url) and sec_url in u) or
                            (bool(url) and url in u)
                            for u in active_urls if u
                        )
                        if not is_referenced and pub_id:
                            try:
                                self.uploader.destroy(pub_id, resource_type=r_type, invalidate=True)
                                deleted_count += 1
                                logger.info("Cleaned orphaned Cloudinary asset %s (%s)", pub_id, r_type)
                            except Exception as de:
                                logger.warning("Failed destroying Cloudinary asset %s: %s", pub_id, de)
                except Exception as e:
                    logger.warning("Error scanning Cloudinary %s resources: %s", r_type, e)
        except Exception as e:
            logger.warning("Failed running Cloudinary orphan cleanup: %s", e)
        return deleted_count

    def exists(self, filename: str) -> bool:
        if not filename:
            return False
        if "res.cloudinary.com" in filename or filename.startswith("http"):
            return True
        import config
        base_dir = getattr(self, "media_dir", None) or Path(getattr(config, "MEDIA_DIR", MEDIA_DIR))
        p = Path(base_dir) / filename
        return p.is_file()

    def get_path(self, filename: str) -> Path:
        if not filename or filename.startswith("http://") or filename.startswith("https://"):
            return None
        import config
        base_dir = getattr(self, "media_dir", None) or Path(getattr(config, "MEDIA_DIR", MEDIA_DIR))
        p = Path(base_dir) / filename
        return p if p.is_file() else None

    def url(self, filename: str) -> str:
        return filename if filename.startswith("http") else f"/media/{filename}"


try:
    from config import CLOUDINARY_URL
except ImportError:
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL")

if CLOUDINARY_URL:
    try:
        media_storage = CloudinaryMediaStorage(CLOUDINARY_URL)
        logger.info("Initialized Cloudinary media storage backend.")
    except Exception as e:
        logger.warning("Failed to initialize Cloudinary storage, falling back to local: %s", e)
        media_storage = LocalMediaStorage()
else:
    media_storage = LocalMediaStorage()

# ==============================================================================
# SQLite Notice Storage with Multi-Screen Departments and Audit Logs
# ==============================================================================
class NoticeStorage:
    def __init__(self, db_file: Path = DB_FILE, data_file: Path = DATA_FILE, media_backend: MediaStorageBackend = None):
        self.db_file = Path(db_file)
        self.data_file = Path(data_file)
        self.media_storage = media_backend or media_storage
        self.media_folder = getattr(self.media_storage, "media_dir", MEDIA_DIR)
        self._flag_manual_override = None
        self._init_db()
        self._run_migration_if_needed()

    def get_connection(self):
        try:
            from flask import g, has_app_context
            if has_app_context():
                if not hasattr(g, "_db_conn") or g._db_conn is None:
                    g._db_conn = self._create_connection()
                return g._db_conn
        except ImportError:
            pass
        return self._create_connection()

    def _create_connection(self):
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_file), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def close_connection(self, conn=None):
        try:
            from flask import g, has_app_context
            if has_app_context() and hasattr(g, "_db_conn") and g._db_conn is not None:
                g._db_conn.close()
                g._db_conn = None
                return
        except ImportError:
            pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self):
        conn = self._create_connection()
        try:
            with conn:
                # 1. Departments table (Phase 1)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS departments (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        active INTEGER NOT NULL DEFAULT 1,
                        accent_color TEXT,
                        created_at INTEGER NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_dept_order ON departments(sort_order, code);")

                # 2. Legacy screens table (maintained for compatibility)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS screens (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at INTEGER NOT NULL
                    );
                """)

                # Seed initial departments
                now_ms = get_current_time_ms()
                for code, name, sort_order, active, accent in SEED_DEPARTMENTS:
                    conn.execute("""
                        INSERT OR IGNORE INTO departments (code, name, sort_order, active, accent_color, created_at)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """, (code, name, sort_order, active, accent, now_ms))
                    conn.execute("""
                        INSERT OR IGNORE INTO screens (id, name, created_at)
                        VALUES (?, ?, ?);
                    """, (code, name, now_ms))

                # 3. Notices table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notices (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        body TEXT DEFAULT '',
                        priority TEXT NOT NULL DEFAULT 'normal',
                        type TEXT NOT NULL DEFAULT 'text',
                        media TEXT DEFAULT '',
                        duration INTEGER NOT NULL DEFAULT 10,
                        start INTEGER NOT NULL DEFAULT 0,
                        end INTEGER,
                        screen_id TEXT NOT NULL DEFAULT 'ALL',
                        created_by TEXT NOT NULL DEFAULT 'admin',
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notices_screen ON notices(screen_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notices_status ON notices(is_active, start, end);")

                # 4. Notice Screens join table (Phase 1)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS notice_screens (
                        notice_id TEXT NOT NULL,
                        screen_code TEXT NOT NULL,
                        PRIMARY KEY (notice_id, screen_code),
                        FOREIGN KEY (notice_id) REFERENCES notices(id) ON DELETE CASCADE
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ns_screen ON notice_screens(screen_code);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ns_notice ON notice_screens(notice_id);")

                # 5. Audit logs table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp INTEGER NOT NULL,
                        actor TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        details TEXT DEFAULT '',
                        ip TEXT DEFAULT '127.0.0.1'
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);")

                # Schema migration: ensure 'ip' column exists in audit_logs
                cursor = conn.execute("PRAGMA table_info(audit_logs);")
                cols = [r[1] for r in cursor.fetchall()]
                if "ip" not in cols:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN ip TEXT DEFAULT '127.0.0.1';")

                # Schema migration: ensure 'deleted' column in notices
                cursor_n = conn.execute("PRAGMA table_info(notices);")
                ncols = [r[1] for r in cursor_n.fetchall()]
                if "deleted" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN deleted INTEGER DEFAULT 0;")
                if "deleted_at" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN deleted_at INTEGER DEFAULT NULL;")
                if "scan_count" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN scan_count INTEGER DEFAULT 0;")

                # Automatic backup before schema migration if database exists
                cursor_d = conn.execute("PRAGMA table_info(departments);")
                dcols = [r[1] for r in cursor_d.fetchall()]
                needs_migration = (
                    "has_audio" not in ncols or
                    "play_sound" not in ncols or
                    "sound_enabled" not in dcols or
                    "sound_volume" not in dcols
                )
                if needs_migration and self.db_file.exists():
                    backup_path = self.db_file.with_name(self.db_file.name + ".bak")
                    try:
                        shutil.copy2(self.db_file, backup_path)
                        logger.info("Automatic database backup created at %s", backup_path)
                    except Exception as e:
                        logger.warning("Automatic database backup warning: %s", e)

                if "has_audio" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN has_audio TEXT DEFAULT 'unknown';")
                    try:
                        vrows = conn.execute("SELECT id, media FROM notices WHERE type = 'video';").fetchall()
                        for vr in vrows:
                            if vr["media"]:
                                mp = self.media_folder / vr["media"]
                                if mp.is_file():
                                    da = detect_video_audio(mp)
                                    conn.execute("UPDATE notices SET has_audio = ? WHERE id = ?;", (da, vr["id"]))
                    except Exception as e:
                        logger.warning("Failed backfilling has_audio: %s", e)

                if "play_sound" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN play_sound INTEGER DEFAULT 0;")

                if "sound_enabled" not in dcols:
                    conn.execute("ALTER TABLE departments ADD COLUMN sound_enabled INTEGER NOT NULL DEFAULT 0;")
                if "sound_volume" not in dcols:
                    conn.execute("ALTER TABLE departments ADD COLUMN sound_volume INTEGER NOT NULL DEFAULT 70;")

                # Voice notices migration: audio_duration, waveform, caption, repeat_gap_minutes
                needs_voice_migration = (
                    "audio_duration" not in ncols or
                    "waveform" not in ncols or
                    "caption" not in ncols or
                    "repeat_gap_minutes" not in ncols
                )
                if needs_voice_migration and self.db_file.exists():
                    backup_path = self.db_file.with_name(self.db_file.name + ".bak")
                    try:
                        shutil.copy2(self.db_file, backup_path)
                        logger.info("Automatic database backup created at %s before voice columns migration", backup_path)
                    except Exception as e:
                        logger.warning("Automatic database backup warning: %s", e)

                if "audio_duration" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN audio_duration REAL DEFAULT NULL;")
                if "waveform" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN waveform TEXT DEFAULT '';")
                if "caption" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN caption TEXT DEFAULT '';")
                if "repeat_gap_minutes" not in ncols:
                    conn.execute("ALTER TABLE notices ADD COLUMN repeat_gap_minutes INTEGER DEFAULT 5;")

                # 6. Users table for Phase 6 role-based permissions
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'dept_admin',
                        departments TEXT NOT NULL DEFAULT '',
                        can_target_all INTEGER NOT NULL DEFAULT 0,
                        created_at INTEGER NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")

                # 7. Daily events table (Multi-event support with auto-migration and backup)
                cursor_e = conn.execute("PRAGMA table_info(daily_events);")
                ecols = [r[1] for r in cursor_e.fetchall()]
                needs_events_migration = (
                    len(ecols) > 0 and (
                        "label" not in ecols or
                        "id" not in ecols or
                        "standup_en" not in ecols
                    )
                )

                if needs_events_migration and self.db_file.exists():
                    backup_path = self.db_file.with_name(self.db_file.name + ".bak")
                    try:
                        shutil.copy2(self.db_file, backup_path)
                        logger.info("Automatic database backup created at %s before daily_events migration", backup_path)
                    except Exception as be:
                        logger.warning("Automatic database backup warning: %s", be)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_events_v2 (
                        id TEXT PRIMARY KEY,
                        type TEXT NOT NULL DEFAULT 'flag',
                        label TEXT NOT NULL DEFAULT 'National Anthem',
                        enabled INTEGER NOT NULL DEFAULT 0,
                        start_time TEXT NOT NULL DEFAULT '11:00',
                        start_offset_seconds INTEGER NOT NULL DEFAULT 0,
                        duration_seconds INTEGER NOT NULL DEFAULT 60,
                        days_of_week TEXT NOT NULL DEFAULT 'mon,tue,wed,thu,fri,sat',
                        screens TEXT NOT NULL DEFAULT 'ALL',
                        show_standup_text INTEGER NOT NULL DEFAULT 0,
                        standup_en TEXT NOT NULL DEFAULT 'Please stand for the National Anthem',
                        standup_hi TEXT NOT NULL DEFAULT 'कृपया राष्ट्रगान के लिए खड़े हो जाएँ',
                        standup_mr TEXT NOT NULL DEFAULT 'कृपया राष्ट्रगीतासाठी उभे राहा',
                        skip_dates TEXT NOT NULL DEFAULT '[]',
                        last_run_at INTEGER,
                        last_run_result TEXT,
                        override_start_ms INTEGER DEFAULT NULL,
                        override_end_ms INTEGER DEFAULT NULL,
                        override_screens TEXT DEFAULT NULL,
                        override_show_standup INTEGER DEFAULT 0,
                        ended_early_date TEXT DEFAULT NULL,
                        updated_at INTEGER NOT NULL
                    );
                """)

                if needs_events_migration:
                    try:
                        existing_rows = conn.execute("SELECT * FROM daily_events;").fetchall()
                        for row in existing_rows:
                            r_dict = dict(row)
                            ev_id = r_dict.get("id") or ("anthem" if r_dict.get("type") == "flag" else r_dict.get("type", "anthem"))
                            ev_type = r_dict.get("type") or "flag"
                            ev_label = r_dict.get("label") or ("National Anthem" if ev_id in ("flag", "anthem") else ev_id.replace("_", " ").title())
                            ev_standup_en = r_dict.get("standup_en") or "Please stand for the National Anthem"
                            ev_standup_hi = r_dict.get("standup_hi") or "कृपया राष्ट्रगान के लिए खड़े हो जाएँ"
                            ev_standup_mr = r_dict.get("standup_mr") or "कृपया राष्ट्रगीतासाठी उभे राहा"
                            conn.execute("""
                                INSERT OR REPLACE INTO daily_events_v2 (
                                    id, type, label, enabled, start_time, start_offset_seconds, duration_seconds,
                                    days_of_week, screens, show_standup_text, standup_en, standup_hi, standup_mr,
                                    skip_dates, last_run_at, last_run_result, override_start_ms, override_end_ms,
                                    override_screens, override_show_standup, ended_early_date, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """, (
                                ev_id, ev_type, ev_label,
                                r_dict.get("enabled", 0),
                                r_dict.get("start_time", "11:00"),
                                r_dict.get("start_offset_seconds", 0),
                                r_dict.get("duration_seconds", 60),
                                r_dict.get("days_of_week", "mon,tue,wed,thu,fri,sat"),
                                r_dict.get("screens", "ALL"),
                                r_dict.get("show_standup_text", 0),
                                ev_standup_en, ev_standup_hi, ev_standup_mr,
                                r_dict.get("skip_dates", "[]"),
                                r_dict.get("last_run_at"),
                                r_dict.get("last_run_result"),
                                r_dict.get("override_start_ms"),
                                r_dict.get("override_end_ms"),
                                r_dict.get("override_screens"),
                                r_dict.get("override_show_standup", 0),
                                r_dict.get("ended_early_date"),
                                r_dict.get("updated_at", now_ms)
                            ))
                        conn.execute("DROP TABLE daily_events;")
                        conn.execute("ALTER TABLE daily_events_v2 RENAME TO daily_events;")
                        logger.info("Migrated daily_events to multi-event schema v2 successfully.")
                    except Exception as me:
                        logger.error("Failed migrating daily_events table: %s", me)
                elif len(ecols) == 0:
                    conn.execute("ALTER TABLE daily_events_v2 RENAME TO daily_events;")
                else:
                    conn.execute("DROP TABLE IF EXISTS daily_events_v2;")

                # Seed Anthem if not present
                conn.execute("""
                    INSERT OR IGNORE INTO daily_events (
                        id, type, label, enabled, start_time, start_offset_seconds, duration_seconds,
                        days_of_week, screens, show_standup_text, standup_en, standup_hi, standup_mr,
                        skip_dates, updated_at
                    ) VALUES (
                        'anthem', 'flag', 'National Anthem', 0, '11:00', 0, 60,
                        'mon,tue,wed,thu,fri,sat', 'ALL', 0,
                        'Please stand for the National Anthem',
                        'कृपया राष्ट्रगान के लिए खड़े हो जाएँ',
                        'कृपया राष्ट्रगीतासाठी उभे राहा',
                        '[]', ?
                    );
                """, (now_ms,))

                # Seed Vande Mataram (DISABLED) if not present
                conn.execute("""
                    INSERT OR IGNORE INTO daily_events (
                        id, type, label, enabled, start_time, start_offset_seconds, duration_seconds,
                        days_of_week, screens, show_standup_text, standup_en, standup_hi, standup_mr,
                        skip_dates, updated_at
                    ) VALUES (
                        'vande_mataram', 'flag', 'Vande Mataram', 0, '17:00', 0, 90,
                        'mon,tue,wed,thu,fri,sat', 'ALL', 0,
                        'Please stand for Vande Mataram',
                        'कृपया वंदे मातरम् के लिए खड़े हो जाएँ',
                        'कृपया वंदे मातरमसाठी उभे राहा',
                        '[]', ?
                    );
                """, (now_ms,))
        finally:
            conn.close()

    def record_audit(self, actor: str, action: str, target_id: str, details: str = "", ip: str = "127.0.0.1"):
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO audit_logs (timestamp, actor, action, target_id, details, ip)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (get_current_time_ms(), actor or "admin", action, str(target_id or ""), details, ip or "127.0.0.1"))
        except Exception as e:
            logger.warning("Failed to record audit log: %s", e)
        finally:
            if not self._is_in_flask():
                conn.close()

    def check_health(self) -> dict:
        conn = self.get_connection()
        try:
            conn.execute("SELECT 1;").fetchone()
            wal_row = conn.execute("PRAGMA journal_mode;").fetchone()
            journal_mode = wal_row[0] if wal_row else "unknown"
            notices_count = conn.execute("SELECT COUNT(*) FROM notices;").fetchone()[0]
            screens_count = conn.execute("SELECT COUNT(*) FROM departments;").fetchone()[0]
            return {
                "connected": True,
                "journal_mode": journal_mode,
                "notices_count": notices_count,
                "screens_count": screens_count,
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }

    def get_audit_logs(self, limit: int = 50, offset: int = 0, action: str = None, actor: str = None, date_from: int = None, date_to: int = None):
        conn = self.get_connection()
        try:
            where_clauses = ["1=1"]
            params = []
            if action and action != "ALL":
                where_clauses.append("action = ?")
                params.append(action)
            if actor:
                where_clauses.append("actor LIKE ?")
                params.append(f"%{actor}%")
            if date_from:
                where_clauses.append("timestamp >= ?")
                params.append(date_from)
            if date_to:
                where_clauses.append("timestamp <= ?")
                params.append(date_to)

            where_str = " AND ".join(where_clauses)
            total = conn.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {where_str};", params).fetchone()[0]

            query = f"SELECT * FROM audit_logs WHERE {where_str} ORDER BY timestamp DESC LIMIT ? OFFSET ?;"
            rows = conn.execute(query, params + [limit, offset]).fetchall()
            logs = []
            for r in rows:
                d = dict(r)
                d["ip_address"] = d.get("ip") or "127.0.0.1"
                d["created_at"] = d["timestamp"]
                logs.append(d)
            return {"audit_logs": logs, "logs": logs, "total": total}
        finally:
            if not self._is_in_flask():
                conn.close()

    def _run_migration_if_needed(self):
        conn = self._create_connection()
        try:
            with conn:
                # 1. JSON migration if DB is empty
                count = conn.execute("SELECT COUNT(*) FROM notices;").fetchone()[0]
                if count == 0 and self.data_file.exists():
                    try:
                        with open(self.data_file, "r", encoding="utf-8") as f:
                            items = json.load(f)
                        if isinstance(items, list) and len(items) > 0:
                            now = get_current_time_ms()
                            logger.info("Migrating %d notices from %s into SQLite...", len(items), self.data_file)
                            for n in items:
                                n_id = n.get("id") or generate_notice_id()
                                sid = n.get("screen_id", "default")
                                target_code = "ALL" if sid == "default" else sid
                                conn.execute("""
                                    INSERT OR REPLACE INTO notices (
                                        id, title, body, priority, type, media, duration, start, end,
                                        screen_id, created_by, created_at, updated_at, is_active
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                                """, (
                                    n_id,
                                    n.get("title", ""),
                                    n.get("body", ""),
                                    n.get("priority", "normal"),
                                    n.get("type", "text"),
                                    n.get("media", ""),
                                    int(n.get("duration", 10)),
                                    int(n.get("start", 0)),
                                    int(n["end"]) if n.get("end") is not None else None,
                                    target_code,
                                    n.get("created_by", "admin"),
                                    int(n.get("created_at", n.get("start", now))),
                                    int(n.get("updated_at", now)),
                                ))
                                conn.execute("""
                                    INSERT OR IGNORE INTO notice_screens (notice_id, screen_code)
                                    VALUES (?, ?);
                                """, (n_id, target_code))
                            bak_path = self.data_file.with_name(self.data_file.name + ".bak")
                            shutil.copy2(self.data_file, bak_path)
                            logger.info("One-time JSON migration complete. Backup preserved at %s", bak_path)
                    except Exception as e:
                        logger.error("Migration error from JSON to SQLite: %s", e)

                # 2. Phase 1 Database Migration: Migrate existing 'default' notices to 'ALL'
                conn.execute("""
                    UPDATE notices SET screen_id = 'ALL' 
                    WHERE screen_id = 'default' OR screen_id = 'DEFAULT';
                """)

                # Clean up any legacy corrupted screen_codes or notices containing brackets, quotes, commas, or JSON
                all_notices = conn.execute("SELECT id, screen_id FROM notices;").fetchall()
                for r in all_notices:
                    nid = r[0]
                    raw_sid = str(r[1] or "")
                    if any(ch in raw_sid for ch in ['[', ']', '"', "'", ',', '\\']):
                        clean_codes = sanitize_screen_codes(raw_sid)
                        primary = clean_codes[0] if clean_codes else "ALL"
                        conn.execute("UPDATE notices SET screen_id = ? WHERE id = ?;", (primary, nid))
                        conn.execute("DELETE FROM notice_screens WHERE notice_id = ?;", (nid,))
                        for sc in clean_codes:
                            conn.execute("INSERT OR IGNORE INTO notice_screens (notice_id, screen_code) VALUES (?, ?);", (nid, sc))

                all_screens = conn.execute("SELECT notice_id, screen_code FROM notice_screens;").fetchall()
                for r in all_screens:
                    nid = r[0]
                    raw_sc = str(r[1] or "")
                    if any(ch in raw_sc for ch in ['[', ']', '"', "'", ',', '\\']):
                        conn.execute("DELETE FROM notice_screens WHERE notice_id = ? AND screen_code = ?;", (nid, raw_sc))
                        for sc in sanitize_screen_codes(raw_sc):
                            conn.execute("INSERT OR IGNORE INTO notice_screens (notice_id, screen_code) VALUES (?, ?);", (nid, sc))

                # Populate notice_screens for any existing notices missing join entries
                unlinked = conn.execute("""
                    SELECT n.id, n.screen_id FROM notices n
                    LEFT JOIN notice_screens ns ON n.id = ns.notice_id
                    WHERE ns.notice_id IS NULL;
                """).fetchall()

                for r in unlinked:
                    nid = r[0]
                    sid = r[1] or "ALL"
                    target = "ALL" if sid.lower() == "default" else sid.upper()
                    # Ensure target exists in departments if valid
                    if SCREEN_CODE_REGEX.match(target):
                        conn.execute("""
                            INSERT OR IGNORE INTO departments (code, name, sort_order, active, created_at)
                            VALUES (?, ?, 10, 1, ?);
                        """, (target, target, get_current_time_ms()))
                    conn.execute("""
                        INSERT OR IGNORE INTO notice_screens (notice_id, screen_code)
                        VALUES (?, ?);
                    """, (nid, target))
        finally:
            conn.close()

    def _row_to_dict(self, row, now_ms=None):
        if row is None:
            return None
        d = dict(row)
        d["status"] = compute_status(d, now_ms)
        raw_sid = str(d.get("screen_id") or "ALL")
        if any(ch in raw_sid for ch in ['[', ']', '"', "'", ',', '\\']):
            clean = sanitize_screen_codes(raw_sid)
            d["screen_id"] = clean[0] if clean else "ALL"
        d["scan_count"] = int(d.get("scan_count") or 0)
        d["has_audio"] = str(d.get("has_audio") or "unknown")
        d["play_sound"] = bool(d.get("play_sound") or 0)
        if d.get("audio_duration") is not None:
            try:
                d["audio_duration"] = float(d["audio_duration"])
            except Exception:
                d["audio_duration"] = None
        else:
            d["audio_duration"] = None

        if "repeat_gap_minutes" in d and d.get("repeat_gap_minutes") is not None:
            try:
                d["repeat_gap_minutes"] = int(d["repeat_gap_minutes"])
            except Exception:
                d["repeat_gap_minutes"] = 5
        else:
            d["repeat_gap_minutes"] = 5

        d["caption"] = str(d.get("caption") or "")
        d["waveform"] = str(d.get("waveform") or "")
        return d

    def _enrich_notices(self, notices, conn=None):
        if not notices:
            return notices
        need_close = False
        if conn is None:
            conn = self.get_connection()
            need_close = not self._is_in_flask()

        try:
            ids = [n["id"] for n in notices if "id" in n]
            if not ids:
                return notices

            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(f"""
                SELECT notice_id, screen_code FROM notice_screens
                WHERE notice_id IN ({placeholders});
            """, ids).fetchall()

            mapping = {}
            for r in rows:
                nid, code = r[0], r[1]
                if nid not in mapping:
                    mapping[nid] = []
                mapping[nid].append(code)

            for n in notices:
                screens = mapping.get(n["id"])
                if screens:
                    clean_s = sanitize_screen_codes(screens)
                    n["screens"] = clean_s
                    if not n.get("screen_id") or any(ch in str(n.get("screen_id")) for ch in ['[', ']', '"', "'", ',', '\\']):
                        n["screen_id"] = clean_s[0] if clean_s else "ALL"
                else:
                    fallback = sanitize_screen_codes(n.get("screen_id") or "ALL")
                    n["screens"] = fallback
                    if not n.get("screen_id") or any(ch in str(n.get("screen_id")) for ch in ['[', ']', '"', "'", ',', '\\']):
                        n["screen_id"] = fallback[0] if fallback else "ALL"
            return notices
        finally:
            if need_close:
                conn.close()

    # ==========================================================================
    # Screen / Department Operations (Phase 1)
    # ==========================================================================
    def get_departments(self, active_only: bool = False):
        conn = self.get_connection()
        try:
            if active_only:
                rows = conn.execute("""
                    SELECT code, name, sort_order, active, accent_color, sound_enabled, sound_volume, created_at
                    FROM departments
                    WHERE active = 1
                    ORDER BY sort_order ASC, code ASC;
                """).fetchall()
            else:
                rows = conn.execute("""
                    SELECT code, name, sort_order, active, accent_color, sound_enabled, sound_volume, created_at
                    FROM departments
                    ORDER BY sort_order ASC, code ASC;
                """).fetchall()
            return [
                {
                    "code": r["code"],
                    "name": r["name"],
                    "id": r["code"],
                    "sort_order": r["sort_order"],
                    "active": bool(r["active"]),
                    "accent_color": r["accent_color"],
                    "sound_enabled": bool(r["sound_enabled"]) if "sound_enabled" in r.keys() else False,
                    "sound_volume": int(r["sound_volume"]) if "sound_volume" in r.keys() else 70,
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_department(self, code: str):
        if not code:
            return None
        code = str(code).strip().upper()
        conn = self.get_connection()
        try:
            row = conn.execute("""
                SELECT code, name, sort_order, active, accent_color, sound_enabled, sound_volume, created_at
                FROM departments WHERE code = ?;
            """, (code,)).fetchone()
            if not row:
                return None
            return {
                "code": row["code"],
                "name": row["name"],
                "id": row["code"],
                "sort_order": row["sort_order"],
                "active": bool(row["active"]),
                "accent_color": row["accent_color"],
                "sound_enabled": bool(row["sound_enabled"]) if "sound_enabled" in row.keys() else False,
                "sound_volume": int(row["sound_volume"]) if "sound_volume" in row.keys() else 70,
                "created_at": row["created_at"],
            }
        finally:
            if not self._is_in_flask():
                conn.close()

    def add_department(self, code: str, name: str, sort_order: int = 0, active: bool = True, accent_color: str = None, sound_enabled: bool = False, sound_volume: int = 70):
        code = validate_screen_code(code)
        if not name or not str(name).strip():
            raise ValueError("Department name is required.")
        name = str(name).strip()

        if self.get_department(code):
            raise ValueError(f"Department code '{code}' already exists.")

        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = 0

        active_int = 1 if active else 0
        sound_enabled_int = 1 if sound_enabled else 0
        try:
            sound_volume = max(0, min(100, int(sound_volume)))
        except (ValueError, TypeError):
            sound_volume = 70
        now_ms = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO departments (code, name, sort_order, active, accent_color, sound_enabled, sound_volume, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, (code, name, sort_order, active_int, accent_color, sound_enabled_int, sound_volume, now_ms))
                conn.execute("""
                    INSERT OR IGNORE INTO screens (id, name, created_at)
                    VALUES (?, ?, ?);
                """, (code, name, now_ms))
            self.record_audit("admin", "CREATE_SCREEN", code, f"Created screen {code} ({name})")
            return self.get_department(code)
        finally:
            if not self._is_in_flask():
                conn.close()

    def update_department(self, code: str, data: dict):
        code = str(code).strip().upper()
        existing = self.get_department(code)
        if not existing:
            return None

        name = str(data.get("name", existing["name"])).strip()
        if not name:
            name = existing["name"]

        sort_order = data.get("sort_order", existing["sort_order"])
        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = existing["sort_order"]

        active = data.get("active", existing["active"])
        active_int = 1 if active else 0

        accent_color = data.get("accent_color", existing["accent_color"])

        sound_enabled = existing.get("sound_enabled", False)
        if "sound_enabled" in data:
            val = data["sound_enabled"]
            sound_enabled = val in (True, 1, "1", "true")
        sound_enabled_int = 1 if sound_enabled else 0

        sound_volume = existing.get("sound_volume", 70)
        if "sound_volume" in data:
            try:
                sound_volume = max(0, min(100, int(data["sound_volume"])))
            except (ValueError, TypeError):
                sound_volume = existing.get("sound_volume", 70)

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE departments SET
                        name = ?,
                        sort_order = ?,
                        active = ?,
                        accent_color = ?,
                        sound_enabled = ?,
                        sound_volume = ?
                    WHERE code = ?;
                """, (name, sort_order, active_int, accent_color, sound_enabled_int, sound_volume, code))
                conn.execute("""
                    UPDATE screens SET name = ? WHERE id = ?;
                """, (name, code))
            self.record_audit("admin", "UPDATE_SCREEN", code, f"Updated screen {code} ({name})")
            return self.get_department(code)
        finally:
            if not self._is_in_flask():
                conn.close()

    def delete_department(self, code: str):
        code = str(code).strip().upper()
        if code == "ALL":
            raise ValueError("The college-wide 'ALL' screen cannot be deleted.")

        dept = self.get_department(code)
        if not dept:
            return None

        conn = self.get_connection()
        try:
            with conn:
                # Check if non-deleted notices target this screen
                count = conn.execute("""
                    SELECT COUNT(*) FROM notice_screens ns
                    JOIN notices n ON ns.notice_id = n.id
                    WHERE ns.screen_code = ? AND n.deleted = 0;
                """, (code,)).fetchone()[0]

                if count > 0:
                    # Soft-deactivate if notices exist
                    conn.execute("UPDATE departments SET active = 0 WHERE code = ?;", (code,))
                    self.record_audit("admin", "DEACTIVATE_SCREEN", code, f"Deactivated screen {code} (has {count} notices)")
                    return {"success": True, "deactivated": True, "message": "Department has notices and was deactivated instead of deleted."}
                else:
                    # Hard-delete if no notices target this department
                    conn.execute("DELETE FROM departments WHERE code = ?;", (code,))
                    conn.execute("DELETE FROM screens WHERE id = ?;", (code,))
                    self.record_audit("admin", "DELETE_SCREEN", code, f"Deleted screen {code}")
                    return {"success": True, "deleted": True}
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_screens(self, active_only: bool = False):
        return self.get_departments(active_only=active_only)

    def add_screen(self, screen_id, name=None):
        screen_id_str = str(screen_id).strip() or "ALL"
        if screen_id_str.lower() == "default":
            screen_id_str = "ALL"
        name = name or screen_id_str.title()
        
        # Check if valid uppercase code
        if SCREEN_CODE_REGEX.match(screen_id_str.upper()):
            code = screen_id_str.upper()
            existing = self.get_department(code)
            if existing:
                return existing
            return self.add_department(code, name)
        
        # Fallback for arbitrary screen names in legacy tests
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT OR IGNORE INTO screens (id, name, created_at)
                    VALUES (?, ?, ?);
                """, (screen_id_str, name, get_current_time_ms()))
            return {"id": screen_id_str, "code": screen_id_str, "name": name}
        finally:
            if not self._is_in_flask():
                conn.close()

    # ==========================================================================
    # Notice Queries
    # ==========================================================================
    def get_all(self, screen_id=None):
        conn = self.get_connection()
        now_ms = get_current_time_ms()
        try:
            if screen_id and str(screen_id).lower() not in ("all", "all_screens", ""):
                screen_code = str(screen_id).strip().upper()
                rows = conn.execute("""
                    SELECT DISTINCT n.* FROM notices n
                    JOIN notice_screens ns ON n.id = ns.notice_id
                    WHERE (ns.screen_code = ? OR n.screen_id = ? OR ns.screen_code = ?)
                      AND n.is_active = 1
                    ORDER BY n.created_at DESC;
                """, (screen_code, str(screen_id).strip(), str(screen_id).strip())).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM notices 
                    WHERE is_active = 1
                    ORDER BY created_at DESC;
                """).fetchall()

            notices = [self._row_to_dict(r, now_ms) for r in rows]
            return self._enrich_notices(notices, conn=conn)
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_active(self, screen_id=None, now_ms=None):
        if now_ms is None:
            now_ms = get_current_time_ms()

        conn = self.get_connection()
        try:
            if screen_id is None or str(screen_id).strip().upper() == "ALL" or str(screen_id).strip().lower() == "default":
                # Board for college-wide (ALL)
                rows = conn.execute("""
                    SELECT DISTINCT n.* FROM notices n
                    JOIN notice_screens ns ON n.id = ns.notice_id
                    WHERE n.is_active = 1 
                      AND ns.screen_code = 'ALL'
                      AND n.start <= ? 
                      AND (n.end IS NULL OR n.end >= ?)
                    ORDER BY 
                      CASE n.priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'info' THEN 2 
                        ELSE 3 
                      END, 
                      n.created_at DESC;
                """, (now_ms, now_ms)).fetchall()
            else:
                # Department display: shows department notices OR ALL notices
                screen_code = str(screen_id).strip().upper()
                raw_code = str(screen_id).strip()
                rows = conn.execute("""
                    SELECT DISTINCT n.* FROM notices n
                    JOIN notice_screens ns ON n.id = ns.notice_id
                    WHERE n.is_active = 1 
                      AND (ns.screen_code = ? OR ns.screen_code = 'ALL' OR n.screen_id = ? OR ns.screen_code = ?)
                      AND n.start <= ? 
                      AND (n.end IS NULL OR n.end >= ?)
                    ORDER BY 
                      CASE n.priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'info' THEN 2 
                        ELSE 3 
                      END, 
                      n.created_at DESC;
                """, (screen_code, raw_code, raw_code, now_ms, now_ms)).fetchall()

            notices = [self._row_to_dict(r, now_ms) for r in rows]
            return self._enrich_notices(notices, conn=conn)
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_by_id(self, notice_id):
        conn = self.get_connection()
        try:
            row = conn.execute("SELECT * FROM notices WHERE id = ?;", (notice_id,)).fetchone()
            if not row:
                return None
            notice = self._row_to_dict(row)
            enriched = self._enrich_notices([notice], conn=conn)
            return enriched[0] if enriched else notice
        finally:
            if not self._is_in_flask():
                conn.close()

    def increment_scan_count(self, notice_id):
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("UPDATE notices SET scan_count = COALESCE(scan_count, 0) + 1 WHERE id = ?;", (notice_id,))
        except Exception as e:
            logger.warning("Failed to increment scan count: %s", e)
        finally:
            if not self._is_in_flask():
                conn.close()

    def is_voice_media(self, filename: str) -> bool:
        if not filename:
            return False
        clean = Path(filename).name
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM notices WHERE type = 'voice' AND (media = ? OR media LIKE ? OR media LIKE ?) LIMIT 1;",
                (clean, f"%/{clean}", f"%{clean}%")
            )
            return bool(cur.fetchone())
        except Exception:
            return False
        finally:
            if not self._is_in_flask():
                conn.close()

    # ==========================================================================
    # Notice Mutations
    # ==========================================================================
    def add(self, data, file_obj=None, created_by="admin"):
        notice_id = generate_notice_id()
        media_filename = str(data.get("media", "")).strip() if data.get("media") else ""
        req_type = str(data.get("type", "text")).strip().lower()
        if req_type == "voice":
            if not getattr(config, "VOICE_NOTICES_ENABLED", False):
                raise ValueError("Voice notices are currently disabled.")

        media_type = req_type if req_type == "voice" else data.get("type", "text")
        audio_duration = None
        waveform_json = ""
        caption = ""
        repeat_gap_minutes = 5

        if req_type == "voice":
            caption = str(data.get("caption") or "").strip()[:500]
            try:
                rgm = int(data.get("repeat_gap_minutes", 5))
                repeat_gap_minutes = rgm if rgm in (0, 5, 15, 30) else 5
            except Exception:
                repeat_gap_minutes = 5

        dest_temp = None
        final_path = None
        try:
            if file_obj and getattr(file_obj, "filename", None):
                stream = getattr(file_obj, "stream", file_obj)
                dest_temp = self.media_folder / f"tmp_{notice_id}"
                max_bytes = MAX_VOICE_CONTENT_LENGTH if req_type == "voice" else MAX_CONTENT_LENGTH
                ext, category = save_stream_to_disk(stream, dest_temp, max_bytes=max_bytes, expected_type=req_type)

                if req_type == "voice":
                    is_valid, probed_dur, err = probe_voice_media(dest_temp)
                    if not is_valid:
                        if dest_temp.exists():
                            dest_temp.unlink()
                        raise ValueError(err)

                    raw_dur = probed_dur if (probed_dur and probed_dur > 0) else data.get("audio_duration")
                    try:
                        dur_val = float(raw_dur or 10.0)
                    except (ValueError, TypeError):
                        dur_val = 10.0
                    audio_duration = round(min(float(MAX_VOICE_DURATION_SECONDS), max(1.0, dur_val)), 2)
                    waveform_json = sanitize_or_generate_waveform(data.get("waveform"), dest_temp)
                    duration = int(round(audio_duration)) + 1
                    media_type = "voice"
                else:
                    media_type = category

                media_filename = f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"
                final_path = self.media_folder / media_filename
                dest_temp.rename(final_path)
                dest_temp = None

                # Reject images over 10MB when cloud storage is active or on Render
                if req_type == "image":
                    file_sz = final_path.stat().st_size
                    if (getattr(self.media_storage, "is_cloud", False) or getattr(config, "IS_RENDER", False)) and file_sz > 10 * 1024 * 1024:
                        try: final_path.unlink()
                        except Exception: pass
                        raise ValueError("Image is over 10 MB, choose a smaller file")

                if getattr(self.media_storage, "is_cloud", False):
                    try:
                        cloud_res_type = "video" if req_type == "voice" else "auto"
                        cloud_url = self.media_storage.save(final_path, media_filename, resource_type=cloud_res_type)
                        if cloud_url:
                            media_filename = cloud_url
                            try:
                                final_path.unlink()
                                final_path = None
                            except Exception:
                                pass
                    except Exception as e:
                        logger.error("Cloud upload error: %s", e)
                        try:
                            if final_path and final_path.exists():
                                final_path.unlink()
                        except Exception:
                            pass
                        err_str = str(e)
                        if "too large" in err_str.lower() or "maximum is" in err_str.lower():
                            raise ValueError("Image is over 10 MB, choose a smaller file")
                        if getattr(config, "IS_RENDER", False) or getattr(self.media_storage, "is_cloud", False):
                            raise ValueError(f"Cloud storage upload failed: {err_str}. Please try a smaller file.")
            elif req_type == "voice":
                if not media_filename:
                    raise ValueError("Voice notice requires an audio recording or file.")
                raw_dur = data.get("audio_duration")
                try:
                    dur_val = float(raw_dur or 10.0)
                except (ValueError, TypeError):
                    dur_val = 10.0
                audio_duration = round(min(float(MAX_VOICE_DURATION_SECONDS), max(1.0, dur_val)), 2)
                waveform_json = sanitize_or_generate_waveform(data.get("waveform"))
                duration = int(round(audio_duration)) + 1
                media_type = "voice"
        except Exception:
            if dest_temp and dest_temp.exists():
                try: dest_temp.unlink()
                except Exception: pass
            if final_path and final_path.exists():
                try: final_path.unlink()
                except Exception: pass
            raise

        if req_type != "voice":
            try:
                duration = int(data.get("duration", 10))
                if duration <= 0:
                    duration = 10
            except (ValueError, TypeError):
                duration = 10

        try:
            start_ms = int(data.get("start", get_current_time_ms()))
        except (ValueError, TypeError):
            start_ms = get_current_time_ms()

        try:
            default_end = start_ms + (7 * 24 * 60 * 60 * 1000)
            end_val = data.get("end")
            end_ms = int(end_val) if end_val not in (None, "", "null") else default_end
        except (ValueError, TypeError):
            end_ms = start_ms + (7 * 24 * 60 * 60 * 1000)

        priority = str(data.get("priority", "normal")).lower()
        if priority not in ("urgent", "normal", "info"):
            priority = "normal"

        # Determine target screens
        raw_input = data.get("screens") or data.get("screen_id") or "ALL"
        target_screens = sanitize_screen_codes(raw_input)

        primary_screen = target_screens[0]

        creator = str(data.get("created_by") or created_by or "admin").strip()
        now = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
                # Ensure screens exist in departments/screens
                for s_code in target_screens:
                    if SCREEN_CODE_REGEX.match(s_code.upper()):
                        conn.execute("""
                            INSERT OR IGNORE INTO departments (code, name, sort_order, active, created_at)
                            VALUES (?, ?, 10, 1, ?);
                        """, (s_code.upper(), s_code.upper(), now))
                        conn.execute("""
                            INSERT OR IGNORE INTO screens (id, name, created_at)
                            VALUES (?, ?, ?);
                        """, (s_code.upper(), s_code.upper(), now))
                    else:
                        conn.execute("""
                            INSERT OR IGNORE INTO screens (id, name, created_at)
                            VALUES (?, ?, ?);
                        """, (s_code, s_code, now))

                if req_type == "voice":
                    has_audio = "true"
                    play_sound_val = 1
                else:
                    has_audio = "unknown"
                    if media_type == "video" and media_filename:
                        final_path = self.media_folder / media_filename
                        if final_path.is_file():
                            has_audio = detect_video_audio(final_path)

                    raw_play_sound = data.get("play_sound")
                    play_sound_val = 1 if (raw_play_sound in (True, 1, "1", "true") and has_audio != "false") else 0

                conn.execute("""
                    INSERT INTO notices (
                        id, title, body, priority, type, media, duration, start, end,
                        screen_id, created_by, created_at, updated_at, is_active,
                        has_audio, play_sound, audio_duration, waveform, caption, repeat_gap_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?);
                """, (
                    notice_id,
                    str(data.get("title", "")).strip(),
                    str(data.get("body", "")).strip(),
                    priority,
                    media_type,
                    media_filename,
                    duration,
                    start_ms,
                    end_ms,
                    primary_screen,
                    creator,
                    now,
                    now,
                    has_audio,
                    play_sound_val,
                    audio_duration,
                    waveform_json,
                    caption,
                    repeat_gap_minutes
                ))

                for s_code in target_screens:
                    code_val = s_code.upper() if SCREEN_CODE_REGEX.match(s_code.upper()) else s_code
                    conn.execute("""
                        INSERT OR IGNORE INTO notice_screens (notice_id, screen_code)
                        VALUES (?, ?);
                    """, (notice_id, code_val))
            
            self.record_audit(creator, "CREATE", notice_id, f"Created {media_type} notice '{data.get('title', '')}'")
            self.safe_garbage_collect_media()
            return self.get_by_id(notice_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def update(self, notice_id, data, file_obj=None, updated_by="admin"):
        target = self.get_by_id(notice_id)
        if not target:
            return None

        media_filename = target.get("media", "")
        req_type = str(data.get("type", target.get("type", "text"))).strip().lower()
        if req_type == "voice":
            import config
            if not getattr(config, "VOICE_NOTICES_ENABLED", False):
                raise ValueError("Voice notices are currently disabled.")

        media_type = req_type if req_type == "voice" else data.get("type", target.get("type", "text"))
        audio_duration = target.get("audio_duration")
        waveform_json = target.get("waveform", "")
        caption = target.get("caption", "")
        repeat_gap_minutes = target.get("repeat_gap_minutes", 5)

        if req_type == "voice":
            if "caption" in data:
                caption = str(data.get("caption") or "").strip()[:500]
            if "repeat_gap_minutes" in data:
                try:
                    rgm = int(data.get("repeat_gap_minutes", 5))
                    repeat_gap_minutes = rgm if rgm in (0, 5, 15, 30) else 5
                except Exception:
                    repeat_gap_minutes = 5

        dest_temp = None
        final_path = None
        try:
            if file_obj and getattr(file_obj, "filename", None):
                stream = getattr(file_obj, "stream", file_obj)
                dest_temp = self.media_folder / f"tmp_{notice_id}"
                max_bytes = MAX_VOICE_CONTENT_LENGTH if req_type == "voice" else MAX_CONTENT_LENGTH
                ext, category = save_stream_to_disk(stream, dest_temp, max_bytes=max_bytes, expected_type=req_type)

                if req_type == "voice":
                    is_valid, probed_dur, err = probe_voice_media(dest_temp)
                    if not is_valid:
                        if dest_temp.exists():
                            dest_temp.unlink()
                        raise ValueError(err)

                    raw_dur = probed_dur if (probed_dur and probed_dur > 0) else data.get("audio_duration")
                    try:
                        dur_val = float(raw_dur or target.get("audio_duration") or 10.0)
                    except (ValueError, TypeError):
                        dur_val = 10.0
                    audio_duration = round(min(float(MAX_VOICE_DURATION_SECONDS), max(1.0, dur_val)), 2)
                    waveform_json = sanitize_or_generate_waveform(data.get("waveform"), dest_temp)
                    duration = int(round(audio_duration)) + 1
                    media_type = "voice"
                else:
                    media_type = category

                old_media = media_filename
                media_filename = f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"
                final_path = self.media_folder / media_filename
                dest_temp.rename(final_path)
                dest_temp = None

                # Reject images over 10MB when cloud storage is active or on Render
                if req_type == "image":
                    file_sz = final_path.stat().st_size
                    if (getattr(self.media_storage, "is_cloud", False) or getattr(config, "IS_RENDER", False)) and file_sz > 10 * 1024 * 1024:
                        try: final_path.unlink()
                        except Exception: pass
                        raise ValueError("Image is over 10 MB, choose a smaller file")

                if getattr(self.media_storage, "is_cloud", False):
                    try:
                        cloud_res_type = "video" if req_type == "voice" else "auto"
                        cloud_url = self.media_storage.save(final_path, media_filename, resource_type=cloud_res_type)
                        if cloud_url:
                            media_filename = cloud_url
                            try:
                                final_path.unlink()
                                final_path = None
                            except Exception:
                                pass
                    except Exception as e:
                        logger.error("Cloud upload error: %s", e)
                        try:
                            if final_path and final_path.exists():
                                final_path.unlink()
                        except Exception:
                            pass
                        err_str = str(e)
                        if "too large" in err_str.lower() or "maximum is" in err_str.lower():
                            raise ValueError("Image is over 10 MB, choose a smaller file")
                        if getattr(config, "IS_RENDER", False) or getattr(self.media_storage, "is_cloud", False):
                            raise ValueError(f"Cloud storage upload failed: {err_str}. Please try a smaller file.")
                
                if old_media and old_media != media_filename:
                    self.media_storage.delete(old_media)
            elif req_type == "voice":
                if "audio_duration" in data:
                    raw_dur = data.get("audio_duration")
                    try:
                        dur_val = float(raw_dur or target.get("audio_duration") or 10.0)
                    except (ValueError, TypeError):
                        dur_val = 10.0
                    audio_duration = round(min(float(MAX_VOICE_DURATION_SECONDS), max(1.0, dur_val)), 2)
                if "waveform" in data:
                    waveform_json = sanitize_or_generate_waveform(data.get("waveform"))
                if audio_duration:
                    duration = int(round(audio_duration)) + 1
                media_type = "voice"
        except Exception:
            if dest_temp and dest_temp.exists():
                try: dest_temp.unlink()
                except Exception: pass
            if final_path and final_path.exists():
                try: final_path.unlink()
                except Exception: pass
            raise

        title = str(data.get("title", target["title"])).strip()
        body = str(data.get("body", target.get("body", ""))).strip()
        
        if req_type != "voice":
            try:
                duration = int(data.get("duration", target.get("duration", 10)))
                if duration <= 0:
                    duration = 10
            except (ValueError, TypeError):
                duration = target.get("duration", 10)

        try:
            start_ms = int(data.get("start", target.get("start", 0)))
        except (ValueError, TypeError):
            start_ms = target.get("start", 0)

        try:
            end_val = data.get("end")
            end_ms = int(end_val) if end_val not in (None, "", "null") else target.get("end")
        except (ValueError, TypeError):
            end_ms = target.get("end")

        priority = str(data.get("priority", target.get("priority", "normal"))).lower()
        if priority not in ("urgent", "normal", "info"):
            priority = target.get("priority", "normal")

        # Parse screens
        target_screens = None
        if "screens" in data or "screen_id" in data:
            raw_input = data.get("screens") or data.get("screen_id")
            target_screens = sanitize_screen_codes(raw_input)
            primary_screen = target_screens[0]
        else:
            primary_screen = target.get("screen_id", "ALL")

        creator = str(data.get("created_by") or target.get("created_by", "admin")).strip()
        now = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
                if req_type == "voice":
                    has_audio = "true"
                    play_sound_val = 1
                else:
                    has_audio = target.get("has_audio", "unknown")
                    if media_type == "video" and media_filename:
                        final_path = self.media_folder / media_filename
                        if final_path.is_file():
                            has_audio = detect_video_audio(final_path)

                    if "play_sound" in data:
                        raw_play_sound = data.get("play_sound")
                        play_sound_val = 1 if (raw_play_sound in (True, 1, "1", "true") and has_audio != "false") else 0
                    else:
                        play_sound_val = 1 if (target.get("play_sound") and has_audio != "false") else 0

                conn.execute("""
                    UPDATE notices SET
                        title = ?,
                        body = ?,
                        priority = ?,
                        type = ?,
                        media = ?,
                        duration = ?,
                        start = ?,
                        end = ?,
                        screen_id = ?,
                        created_by = ?,
                        updated_at = ?,
                        has_audio = ?,
                        play_sound = ?,
                        audio_duration = ?,
                        waveform = ?,
                        caption = ?,
                        repeat_gap_minutes = ?
                    WHERE id = ?;
                """, (
                    title,
                    body,
                    priority,
                    media_type,
                    media_filename,
                    duration,
                    start_ms,
                    end_ms,
                    primary_screen,
                    creator,
                    now,
                    has_audio,
                    play_sound_val,
                    audio_duration,
                    waveform_json,
                    caption,
                    repeat_gap_minutes,
                    notice_id
                ))

                if target_screens is not None:
                    conn.execute("DELETE FROM notice_screens WHERE notice_id = ?;", (notice_id,))
                    for s_code in target_screens:
                        if SCREEN_CODE_REGEX.match(s_code.upper()):
                            conn.execute("""
                                INSERT OR IGNORE INTO departments (code, name, sort_order, active, created_at)
                                VALUES (?, ?, 10, 1, ?);
                            """, (s_code.upper(), s_code.upper(), now))
                        conn.execute("""
                            INSERT OR IGNORE INTO notice_screens (notice_id, screen_code)
                            VALUES (?, ?);
                        """, (notice_id, s_code.upper() if SCREEN_CODE_REGEX.match(s_code.upper()) else s_code))

            self.record_audit(updated_by or creator, "UPDATE", notice_id, f"Updated notice '{title}'")
            self.safe_garbage_collect_media()
            return self.get_by_id(notice_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def delete(self, notice_id, actor="admin", ip="127.0.0.1"):
        target = self.get_by_id(notice_id)
        if not target:
            return False

        now = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("UPDATE notices SET is_active = 0, deleted = 1, deleted_at = ?, updated_at = ? WHERE id = ?;", (now, now, notice_id))
            
            # Immediately delete media from Cloudinary / storage backend when notice is deleted
            media_val = target.get("media")
            if media_val:
                try:
                    other_using = conn.execute(
                        "SELECT COUNT(*) FROM notices WHERE media = ? AND id != ? AND deleted = 0;",
                        (media_val, notice_id)
                    ).fetchone()[0]
                    if other_using == 0:
                        self.media_storage.delete(media_val)
                        logger.info("Deleted media asset '%s' for notice '%s'", media_val, notice_id)
                except Exception as me:
                    logger.warning("Failed to delete media for notice %s: %s", notice_id, me)

            self.record_audit(actor or "admin", "DELETE", notice_id, f"Deleted notice '{target.get('title', '')}'", ip=ip)
            return True
        finally:
            if not self._is_in_flask():
                conn.close()

    def restore(self, notice_id, actor="admin", ip="127.0.0.1"):
        target = self.get_by_id(notice_id)
        if not target:
            return None

        now = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("UPDATE notices SET is_active = 1, deleted = 0, deleted_at = NULL, updated_at = ? WHERE id = ?;", (now, notice_id))
            self.record_audit(actor or "admin", "RESTORE", notice_id, f"Restored notice '{target.get('title', '')}'", ip=ip)
            return self.get_by_id(notice_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def safe_garbage_collect_media(self, grace_period_seconds: int = 600):
        # 1. Cloudinary / remote storage cleanup
        if hasattr(self.media_storage, "clean_orphaned_media"):
            conn = self.get_connection()
            try:
                rows = conn.execute("SELECT DISTINCT media FROM notices WHERE media IS NOT NULL AND media != '' AND deleted = 0;").fetchall()
                active_urls = {r[0] for r in rows}
                return self.media_storage.clean_orphaned_media(active_urls)
            finally:
                if not self._is_in_flask():
                    conn.close()

        # 2. Local filesystem storage cleanup
        if not hasattr(self.media_storage, "media_dir"):
            return 0

        media_dir = self.media_storage.media_dir
        if not media_dir.exists():
            return 0

        conn = self.get_connection()
        try:
            rows = conn.execute("SELECT DISTINCT media FROM notices WHERE media IS NOT NULL AND media != '';").fetchall()
            referenced = {r[0] for r in rows}
        finally:
            if not self._is_in_flask():
                conn.close()

        deleted_local = 0
        now = time.time()
        for item in media_dir.iterdir():
            if item.is_file() and item.name not in referenced and not item.name.startswith("tmp_"):
                try:
                    stat = item.stat()
                    age = now - stat.st_mtime
                    if age > grace_period_seconds:
                        item.unlink()
                        deleted_local += 1
                        logger.info("Safe Media GC: deleted unreferenced file %s (age: %.1f minutes)", item.name, age / 60)
                    else:
                        logger.debug("Safe Media GC: retained in-flight file %s (age: %.1f minutes)", item.name, age / 60)
                except OSError as e:
                    logger.warning("Safe Media GC error on %s: %s", item.name, e)
        return deleted_local

    def _is_in_flask(self):
        try:
            from flask import has_app_context
            return has_app_context()
        except ImportError:
            return False

    # ==========================================================================
    # User & Department Permissions Operations (Phase 6)
    # ==========================================================================
    def create_user(self, username: str, password: str, role: str = "dept_admin", departments=None, can_target_all: bool = False):
        username = str(username).strip().lower()
        if not username:
            raise ValueError("Username cannot be empty.")
        if not password:
            raise ValueError("Password cannot be empty.")
        if role not in ("super_admin", "dept_admin"):
            raise ValueError("Role must be 'super_admin' or 'dept_admin'.")

        depts_list = []
        if departments:
            if isinstance(departments, list):
                depts_list = [str(d).strip().upper() for d in departments if str(d).strip()]
            elif isinstance(departments, str):
                depts_list = [str(d).strip().upper() for d in departments.split(",") if str(d).strip()]
        depts_str = ",".join(sorted(set(depts_list)))

        pw_hash = generate_password_hash(password)
        now_ms = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO users (username, password_hash, role, departments, can_target_all, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (username, pw_hash, role, depts_str, 1 if can_target_all else 0, now_ms))
            self.record_audit("admin", "CREATE_USER", username, f"Created {role} user '{username}' (depts: [{depts_str}])")
            return self.get_user(username)
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_user(self, username: str):
        if not username:
            return None
        username = str(username).strip().lower()
        conn = self.get_connection()
        try:
            row = conn.execute("""
                SELECT id, username, password_hash, role, departments, can_target_all, created_at
                FROM users WHERE username = ?;
            """, (username,)).fetchone()
            if not row:
                return None
            depts_str = row["departments"] or ""
            depts_list = [d.strip().upper() for d in depts_str.split(",") if d.strip()]
            return {
                "id": row["id"],
                "username": row["username"],
                "password_hash": row["password_hash"],
                "role": row["role"],
                "departments": depts_list,
                "can_target_all": bool(row["can_target_all"]),
                "created_at": row["created_at"],
            }
        finally:
            if not self._is_in_flask():
                conn.close()

    def list_users(self):
        conn = self.get_connection()
        try:
            rows = conn.execute("""
                SELECT id, username, role, departments, can_target_all, created_at
                FROM users ORDER BY created_at DESC;
            """,).fetchall()
            result = []
            for r in rows:
                depts_str = r["departments"] or ""
                depts_list = [d.strip().upper() for d in depts_str.split(",") if d.strip()]
                result.append({
                    "id": r["id"],
                    "username": r["username"],
                    "role": r["role"],
                    "departments": depts_list,
                    "can_target_all": bool(r["can_target_all"]),
                    "created_at": r["created_at"],
                })
            return result
        finally:
            if not self._is_in_flask():
                conn.close()

    def delete_user(self, username: str):
        username = str(username).strip().lower()
        conn = self.get_connection()
        try:
            with conn:
                cur = conn.execute("DELETE FROM users WHERE username = ?;", (username,))
                deleted = cur.rowcount > 0
            if deleted:
                self.record_audit("admin", "DELETE_USER", username, f"Deleted user '{username}'")
            return deleted
        finally:
            if not self._is_in_flask():
                conn.close()

    def verify_user_credentials(self, username: str, password: str):
        user = self.get_user(username)
        if not user:
            return None
        if check_password_hash(user["password_hash"], password):
            safe = dict(user)
            safe.pop("password_hash", None)
            return safe
        return None

    # ==========================================================================
    # Daily Flag Event Operations (Multi-event support)
    # ==========================================================================
    def get_daily_events(self) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute("SELECT * FROM daily_events ORDER BY start_time ASC, id ASC;").fetchall()
            events = []
            for r in rows:
                d = dict(r)
                d["enabled"] = bool(d.get("enabled", 0))
                d["show_standup_text"] = bool(d.get("show_standup_text", 0))
                try:
                    d["skip_dates"] = json.loads(d.get("skip_dates") or "[]")
                except Exception:
                    d["skip_dates"] = []
                raw_days = str(d.get("days_of_week") or "mon,tue,wed,thu,fri,sat")
                d["days_of_week"] = [x.strip().lower() for x in raw_days.split(",") if x.strip()]
                events.append(d)
            return events
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_daily_event(self, event_id: str = "flag") -> dict:
        conn = self.get_connection()
        try:
            if event_id in ("flag", "anthem"):
                row = conn.execute("SELECT * FROM daily_events WHERE id = ? OR id = 'anthem' OR id = 'flag' OR type = 'flag' ORDER BY CASE WHEN id IN ('anthem', 'flag') THEN 1 ELSE 2 END LIMIT 1;", (event_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM daily_events WHERE id = ?;", (event_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["enabled"] = bool(d.get("enabled", 0))
            d["show_standup_text"] = bool(d.get("show_standup_text", 0))
            try:
                d["skip_dates"] = json.loads(d.get("skip_dates") or "[]")
            except Exception:
                d["skip_dates"] = []
            raw_days = str(d.get("days_of_week") or "mon,tue,wed,thu,fri,sat")
            d["days_of_week"] = [x.strip().lower() for x in raw_days.split(",") if x.strip()]
            return d
        finally:
            if not self._is_in_flask():
                conn.close()

    def add_daily_event(self, data: dict = None, actor: str = "admin", ip: str = "127.0.0.1") -> dict:
        data = data or {}
        conn = self.get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM daily_events;").fetchone()[0]
            if count >= 6:
                raise ValueError("Maximum of 6 daily events allowed.")
        finally:
            if not self._is_in_flask():
                conn.close()

        label = str(data.get("label", "Custom Event")).strip() or "Custom Event"
        event_id = data.get("id") or f"event_{secrets.token_hex(4)}"

        # Prepare candidate settings for overlap validation
        raw_days = data.get("days_of_week", ["mon", "tue", "wed", "thu", "fri", "sat"])
        if isinstance(raw_days, list):
            days_list = [str(d).strip().lower() for d in raw_days if str(d).strip()]
        else:
            days_list = [x.strip().lower() for x in str(raw_days).split(",") if x.strip()]
        if not days_list:
            days_list = ["mon", "tue", "wed", "thu", "fri", "sat"]

        raw_screens = data.get("screens", "ALL")
        clean_screens = sanitize_screen_codes(raw_screens)

        start_time = str(data.get("start_time", "12:00")).strip()
        if not re.match(r"^\d{1,2}:\d{2}$", start_time):
            start_time = "12:00"
        else:
            parts = start_time.split(":")
            start_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

        start_offset_seconds = max(-60, min(60, int(data.get("start_offset_seconds", 0) or 0)))
        duration_seconds = max(10, min(300, int(data.get("duration_seconds", 60) or 60)))
        show_standup = bool(data.get("show_standup_text", False))

        cand_dict = {
            "start_time": start_time,
            "start_offset_seconds": start_offset_seconds,
            "duration_seconds": duration_seconds,
            "days_of_week": days_list,
            "screens": clean_screens,
            "show_standup_text": show_standup
        }

        # Check overlap against all other existing events
        for other in self.get_daily_events():
            if check_event_overlap(cand_dict, other):
                raise ValueError(f"This overlaps {other['label']} at {other['start_time']}")

        days_str = ",".join(days_list)
        screens_str = ",".join(clean_screens)
        enabled_int = 1 if data.get("enabled") in (True, 1, "1", "true") else 0
        show_standup_int = 1 if show_standup else 0

        standup_en = str(data.get("standup_en", "Please stand for the event")).strip()[:60]
        standup_hi = str(data.get("standup_hi", "")).strip()[:60]
        standup_mr = str(data.get("standup_mr", "")).strip()[:60]

        now_ms = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO daily_events (
                        id, type, label, enabled, start_time, start_offset_seconds, duration_seconds,
                        days_of_week, screens, show_standup_text, standup_en, standup_hi, standup_mr,
                        skip_dates, updated_at
                    ) VALUES (?, 'flag', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?);
                """, (
                    event_id, label, enabled_int, start_time, start_offset_seconds, duration_seconds,
                    days_str, screens_str, show_standup_int, standup_en, standup_hi, standup_mr, now_ms
                ))
            self.record_audit(actor, "FLAG_CREATE", event_id, f"Created {label} ({event_id}): time={start_time}", ip)
            return self.get_daily_event(event_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def update_daily_event(self, event_type: str = "flag", data: dict = None, actor: str = "admin", ip: str = "127.0.0.1") -> dict:
        data = data or {}
        existing = self.get_daily_event(event_type)
        if not existing:
            return None
        actual_id = existing["id"]

        label = str(data.get("label", existing.get("label", "National Anthem"))).strip() or existing.get("label", "National Anthem")

        # Enabled toggle
        enabled = data.get("enabled", existing["enabled"])
        enabled_int = 1 if enabled in (True, 1, "1", "true") else 0

        # Start time (HH:MM)
        start_time = str(data.get("start_time", existing["start_time"])).strip()
        if not re.match(r"^\d{1,2}:\d{2}$", start_time):
            start_time = existing["start_time"]
        else:
            parts = start_time.split(":")
            hh = max(0, min(23, int(parts[0])))
            mm = max(0, min(59, int(parts[1])))
            start_time = f"{hh:02d}:{mm:02d}"

        # Start offset (-60 to +60)
        try:
            start_offset_seconds = int(data.get("start_offset_seconds", existing["start_offset_seconds"]))
            start_offset_seconds = max(-60, min(60, start_offset_seconds))
        except (ValueError, TypeError):
            start_offset_seconds = existing["start_offset_seconds"]

        # Duration (10 to 300)
        try:
            duration_seconds = int(data.get("duration_seconds", existing["duration_seconds"]))
            duration_seconds = max(10, min(300, duration_seconds))
        except (ValueError, TypeError):
            duration_seconds = existing["duration_seconds"]

        # Days of week
        raw_days = data.get("days_of_week", existing["days_of_week"])
        if isinstance(raw_days, list):
            days_list = [str(d).strip().lower() for d in raw_days if str(d).strip()]
        else:
            days_list = [x.strip().lower() for x in str(raw_days).split(",") if x.strip()]
        if not days_list:
            days_list = ["mon", "tue", "wed", "thu", "fri", "sat"]
        days_str = ",".join(days_list)

        # Screens
        raw_screens = data.get("screens", existing["screens"])
        clean_screens = sanitize_screen_codes(raw_screens)
        screens_str = ",".join(clean_screens)

        # Standup text toggle
        show_standup = data.get("show_standup_text", existing["show_standup_text"])
        show_standup_int = 1 if show_standup in (True, 1, "1", "true") else 0

        # Standup text prompts (max 60 chars)
        standup_en = str(data.get("standup_en", existing.get("standup_en", ""))).strip()[:60]
        standup_hi = str(data.get("standup_hi", existing.get("standup_hi", ""))).strip()[:60]
        standup_mr = str(data.get("standup_mr", existing.get("standup_mr", ""))).strip()[:60]

        # Skip dates
        raw_skips = data.get("skip_dates", existing["skip_dates"])
        if isinstance(raw_skips, list):
            valid_skips = [s for s in raw_skips if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", s)]
            skip_dates_str = json.dumps(sorted(list(set(valid_skips))))
        else:
            skip_dates_str = json.dumps(existing["skip_dates"])

        # Check overlap against all other events
        cand_dict = {
            "start_time": start_time,
            "start_offset_seconds": start_offset_seconds,
            "duration_seconds": duration_seconds,
            "days_of_week": days_list,
            "screens": clean_screens,
            "show_standup_text": bool(show_standup_int)
        }
        for other in self.get_daily_events():
            if other["id"] == actual_id:
                continue
            if check_event_overlap(cand_dict, other):
                raise ValueError(f"This overlaps {other['label']} at {other['start_time']}")

        now_ms = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE daily_events SET
                        label = ?,
                        enabled = ?,
                        start_time = ?,
                        start_offset_seconds = ?,
                        duration_seconds = ?,
                        days_of_week = ?,
                        screens = ?,
                        show_standup_text = ?,
                        standup_en = ?,
                        standup_hi = ?,
                        standup_mr = ?,
                        skip_dates = ?,
                        ended_early_date = NULL,
                        updated_at = ?
                    WHERE id = ?;
                """, (
                    label, enabled_int, start_time, start_offset_seconds, duration_seconds,
                    days_str, screens_str, show_standup_int, standup_en, standup_hi, standup_mr,
                    skip_dates_str, now_ms, actual_id
                ))
            self.record_audit(actor, "FLAG_UPDATE", actual_id, f"Updated {label} ({actual_id}): enabled={bool(enabled_int)}, time={start_time}, offset={start_offset_seconds}s, dur={duration_seconds}s", ip)
            return self.get_daily_event(actual_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def delete_daily_event(self, event_id: str, actor: str = "admin", ip: str = "127.0.0.1") -> bool:
        existing = self.get_daily_event(event_id)
        if not existing:
            return False
        actual_id = existing["id"]
        label = existing.get("label", actual_id)
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM daily_events WHERE id = ?;", (actual_id,))
            self.record_audit(actor, "FLAG_DELETE", actual_id, f"Deleted {label} ({actual_id})", ip)
            return True
        finally:
            if not self._is_in_flask():
                conn.close()

    def skip_daily_event_today(self, event_type: str = "flag", actor: str = "admin", ip: str = "127.0.0.1") -> dict:
        evt = self.get_daily_event(event_type)
        if not evt:
            return None
        actual_id = evt["id"]
        label = evt.get("label", actual_id)
        now_dt = datetime.datetime.now(KOLKATA_TZ)
        today_str = now_dt.strftime("%Y-%m-%d")
        current_skips = list(evt.get("skip_dates") or [])
        if today_str not in current_skips:
            current_skips.append(today_str)
            current_skips.sort()
        now_ms = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE daily_events SET skip_dates = ?, updated_at = ? WHERE id = ?;
                """, (json.dumps(current_skips), now_ms, actual_id))
            self.record_audit(actor, "FLAG_SKIP", actual_id, f"Skipped {label} ({actual_id}) for today ({today_str})", ip)
            return self.get_daily_event(actual_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def record_daily_event_run(self, event_type: str = "flag", result: str = "success", actor: str = "admin", ip: str = "127.0.0.1") -> dict:
        evt = self.get_daily_event(event_type)
        actual_id = evt["id"] if evt else event_type
        label = evt.get("label", actual_id) if evt else actual_id
        now_ms = get_current_time_ms()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE daily_events SET last_run_at = ?, last_run_result = ?, updated_at = ? WHERE id = ?;
                """, (now_ms, result, now_ms, actual_id))
            self.record_audit(actor, "FLAG_TEST_RUN", actual_id, f"Test run {label} ({actual_id}): {result}", ip)
            return self.get_daily_event(actual_id)
        finally:
            if not self._is_in_flask():
                conn.close()

    def set_flag_manual_override(self, screens="ALL", duration_seconds: int = 60, show_standup_text: bool = False, event_id: str = None):
        now_ms = get_current_time_ms()
        try:
            dur = int(duration_seconds)
            dur = max(5, min(86400, dur))
        except (ValueError, TypeError):
            dur = 60
        clean_screens = sanitize_screen_codes(screens)
        start_ms = now_ms
        end_ms = now_ms + (dur * 1000)
        show_standup_int = 1 if show_standup_text else 0

        screens_str = ",".join(clean_screens) if isinstance(clean_screens, list) else str(clean_screens)

        target_row_id = None
        if event_id:
            ev = self.get_daily_event(event_id)
            if ev:
                target_row_id = ev["id"]

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("UPDATE daily_events SET override_start_ms = NULL, override_end_ms = NULL, override_screens = NULL, override_show_standup = 0;")
                if target_row_id:
                    conn.execute("""
                        UPDATE daily_events SET
                            override_start_ms = ?,
                            override_end_ms = ?,
                            override_screens = ?,
                            override_show_standup = ?,
                            ended_early_date = NULL,
                            updated_at = ?
                        WHERE id = ?;
                    """, (start_ms, end_ms, screens_str, show_standup_int, now_ms, target_row_id))
                else:
                    conn.execute("""
                        UPDATE daily_events SET
                            override_start_ms = ?,
                            override_end_ms = ?,
                            override_screens = ?,
                            override_show_standup = ?,
                            ended_early_date = NULL,
                            updated_at = ?
                        WHERE id = 'anthem' OR id = 'flag' OR type = 'flag';
                    """, (start_ms, end_ms, screens_str, show_standup_int, now_ms))
        finally:
            if not self._is_in_flask():
                conn.close()

        self._flag_manual_override = {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "screens": clean_screens,
            "show_standup_text": bool(show_standup_text),
            "event_id": target_row_id
        }
        return self._flag_manual_override

    def clear_flag_manual_override(self, ended_early: bool = True):
        now_ms = get_current_time_ms()
        now_dt = datetime.datetime.now(KOLKATA_TZ)
        today_str = now_dt.strftime("%Y-%m-%d") if ended_early else None

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE daily_events SET
                        override_start_ms = NULL,
                        override_end_ms = NULL,
                        override_screens = NULL,
                        override_show_standup = 0,
                        updated_at = ?;
                """, (now_ms,))
                if ended_early:
                    active_evt = self.get_flag_event_today()
                    if active_evt and active_evt.get("event_id"):
                        conn.execute("UPDATE daily_events SET ended_early_date = ? WHERE id = ?;", (today_str, active_evt["event_id"]))
                    else:
                        conn.execute("UPDATE daily_events SET ended_early_date = ? WHERE id = 'anthem' OR id = 'flag';", (today_str,))
        finally:
            if not self._is_in_flask():
                conn.close()

        self._flag_manual_override = None

    def compute_next_run_text(self, event_data: dict, now_dt: datetime.datetime = None) -> str:
        if not event_data:
            return "No event configured"
        now_dt = now_dt or datetime.datetime.now(KOLKATA_TZ)
        days_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        days_name_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
        
        start_time_str = event_data.get("start_time", "11:00")
        try:
            hh, mm = map(int, start_time_str.split(":"))
        except Exception:
            hh, mm = 11, 0
        offset = int(event_data.get("start_offset_seconds", 0) or 0)
        dur = int(event_data.get("duration_seconds", 60) or 60)
        skip_dates = set(event_data.get("skip_dates") or [])
        active_days = set(event_data.get("days_of_week") or [])

        for day_offset in range(14):
            candidate_date = now_dt + datetime.timedelta(days=day_offset)
            c_str = candidate_date.strftime("%Y-%m-%d")
            if c_str in skip_dates:
                continue
            c_day_code = days_map[candidate_date.weekday()]
            if c_day_code not in active_days:
                continue
            
            c_start = candidate_date.replace(hour=hh, minute=mm, second=0, microsecond=0) + datetime.timedelta(seconds=offset)
            c_end = c_start + datetime.timedelta(seconds=dur)
            if c_end <= now_dt:
                continue
            
            time_display = f"{hh:02d}:{mm:02d}"
            if day_offset == 0:
                return f"Today {time_display}"
            elif day_offset == 1:
                return f"Tomorrow {time_display}"
            else:
                return f"{days_name_map[candidate_date.weekday()]} {time_display}"

        return f"{start_time_str}"

    def compute_overall_next_run_text(self, now_dt: datetime.datetime = None) -> str:
        now_dt = now_dt or datetime.datetime.now(KOLKATA_TZ)
        events = self.get_daily_events()
        enabled_events = [e for e in events if e.get("enabled")]
        if not enabled_events:
            return "No event enabled"

        days_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        days_name_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}

        earliest_candidate = None
        earliest_dt = None

        for evt in enabled_events:
            start_time_str = evt.get("start_time", "11:00")
            try:
                hh, mm = map(int, start_time_str.split(":"))
            except Exception:
                hh, mm = 11, 0
            offset = int(evt.get("start_offset_seconds", 0) or 0)
            dur = int(evt.get("duration_seconds", 60) or 60)
            skip_dates = set(evt.get("skip_dates") or [])
            active_days = set(evt.get("days_of_week") or [])

            for day_offset in range(14):
                c_date = now_dt + datetime.timedelta(days=day_offset)
                c_str = c_date.strftime("%Y-%m-%d")
                if c_str in skip_dates:
                    continue
                if days_map[c_date.weekday()] not in active_days:
                    continue
                c_start = c_date.replace(hour=hh, minute=mm, second=0, microsecond=0) + datetime.timedelta(seconds=offset)
                c_end = c_start + datetime.timedelta(seconds=dur)
                if c_end <= now_dt:
                    continue
                if earliest_dt is None or c_start < earliest_dt:
                    earliest_dt = c_start
                    earliest_candidate = (day_offset, c_date, f"{hh:02d}:{mm:02d}", evt.get("label", "Flag"))
                break

        if not earliest_candidate:
            return "Not scheduled"

        day_offset, c_date, time_disp, label = earliest_candidate
        if day_offset == 0:
            return f"Today {time_disp} ({label})"
        elif day_offset == 1:
            return f"Tomorrow {time_disp} ({label})"
        else:
            return f"{days_name_map[c_date.weekday()]} {time_disp} ({label})"

    def get_flag_event_today(self, screen_code: str = "ALL", now_dt: datetime.datetime = None) -> dict:
        now_dt = now_dt or datetime.datetime.now(KOLKATA_TZ)
        server_time_ms = int(now_dt.timestamp() * 1000)
        screen_code_clean = str(screen_code or "ALL").strip().upper()
        today_str = now_dt.strftime("%Y-%m-%d")

        empty_response = {
            "server_time_ms": server_time_ms,
            "flag_start_ms": None,
            "flag_end_ms": None,
            "show_standup_text": False,
            "standup_lead_seconds": 0,
            "event_id": None,
            "label": None,
            "standup_en": None,
            "standup_hi": None,
            "standup_mr": None
        }

        # 1. Check persistent manual override from database
        conn = self.get_connection()
        try:
            ov_row = conn.execute("SELECT * FROM daily_events WHERE override_start_ms IS NOT NULL AND override_end_ms IS NOT NULL LIMIT 1;").fetchone()
            if ov_row:
                ov = dict(ov_row)
                ov_start = ov.get("override_start_ms")
                ov_end = ov.get("override_end_ms")
                if ov_start is not None and ov_end is not None:
                    if server_time_ms < ov_end:
                        ov_screens = sanitize_screen_codes(ov.get("override_screens") or "ALL")
                        if "ALL" in ov_screens or screen_code_clean in ov_screens:
                            show_standup = bool(ov.get("override_show_standup"))
                            return {
                                "server_time_ms": server_time_ms,
                                "flag_start_ms": ov_start,
                                "flag_end_ms": ov_end,
                                "show_standup_text": show_standup,
                                "standup_lead_seconds": 15 if show_standup else 0,
                                "event_id": ov.get("id", "anthem"),
                                "label": ov.get("label", "National Anthem"),
                                "standup_en": ov.get("standup_en") or "Please stand for the National Anthem",
                                "standup_hi": ov.get("standup_hi") or "कृपया राष्ट्रगान के लिए खड़े हो जाएँ",
                                "standup_mr": ov.get("standup_mr") or "कृपया राष्ट्रगीतासाठी उभे राहा"
                            }
                    else:
                        self.clear_flag_manual_override(ended_early=False)
        finally:
            if not self._is_in_flask():
                conn.close()

        # 2. Check feature flag
        import config
        if not getattr(config, "FLAG_EVENT_ENABLED", True):
            return empty_response

        # 3. Find next occurrence across all enabled events for this screen
        events = self.get_daily_events()
        days_map = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
        today_code = days_map[now_dt.weekday()]

        candidates = []
        for evt in events:
            if not evt.get("enabled"):
                continue
            if evt.get("ended_early_date") == today_str:
                continue

            target_screens = evt.get("screens", "ALL")
            if isinstance(target_screens, str):
                target_screens = sanitize_screen_codes(target_screens)
            if "ALL" not in target_screens and screen_code_clean not in target_screens:
                continue

            skip_dates = set(evt.get("skip_dates") or [])
            if today_str in skip_dates:
                continue

            active_days = set(evt.get("days_of_week") or [])
            if today_code not in active_days:
                continue

            start_time_str = evt.get("start_time", "11:00")
            try:
                hh, mm = map(int, start_time_str.split(":"))
            except Exception:
                hh, mm = 11, 0
            offset_sec = int(evt.get("start_offset_seconds", 0) or 0)
            dur_sec = int(evt.get("duration_seconds", 60) or 60)

            event_start = now_dt.replace(hour=hh, minute=mm, second=0, microsecond=0) + datetime.timedelta(seconds=offset_sec)
            event_end = event_start + datetime.timedelta(seconds=dur_sec)
            start_ms = int(event_start.timestamp() * 1000)
            end_ms = int(event_end.timestamp() * 1000)

            if server_time_ms >= end_ms:
                continue

            candidates.append({
                "event": evt,
                "start_ms": start_ms,
                "end_ms": end_ms
            })

        if not candidates:
            return empty_response

        # Pick earliest upcoming/running candidate
        candidates.sort(key=lambda c: c["start_ms"])
        chosen = candidates[0]
        evt = chosen["event"]
        show_standup = bool(evt.get("show_standup_text", False))

        return {
            "server_time_ms": server_time_ms,
            "flag_start_ms": chosen["start_ms"],
            "flag_end_ms": chosen["end_ms"],
            "show_standup_text": show_standup,
            "standup_lead_seconds": 15 if show_standup else 0,
            "event_id": evt["id"],
            "label": evt.get("label", "National Anthem"),
            "standup_en": evt.get("standup_en") or "Please stand for the National Anthem",
            "standup_hi": evt.get("standup_hi") or "कृपया राष्ट्रगान के लिए खड़े हो जाएँ",
            "standup_mr": evt.get("standup_mr") or "कृपया राष्ट्रगीतासाठी उभे राहा"
        }


storage = NoticeStorage()
