import os
import sys
import time
import secrets
import mimetypes
import logging
import sqlite3
import shutil
import json
import re
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from config import (
    DB_FILE,
    DATA_FILE,
    MEDIA_DIR,
    MAX_CONTENT_LENGTH,
    ALLOWED_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_MIME_TYPES,
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
    def save(self, file_obj, filename: str) -> str:
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

    def save(self, file_obj, filename: str) -> str:
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
    def __init__(self, cloudinary_url: str = None):
        self.is_cloud = True
        import cloudinary
        import cloudinary.uploader
        self.cloudinary = cloudinary
        self.uploader = cloudinary.uploader
        if cloudinary_url:
            os.environ["CLOUDINARY_URL"] = cloudinary_url
        cloudinary.reset_config()

    def save(self, file_obj, filename: str) -> str:
        try:
            target = file_obj
            if isinstance(file_obj, (str, Path)):
                target = str(file_obj)
            else:
                target = getattr(file_obj, "stream", file_obj)
            res = self.uploader.upload(
                target,
                folder="vnotice",
                resource_type="auto",
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
            if "res.cloudinary.com" in filename:
                parts = filename.split("/upload/")
                if len(parts) > 1:
                    path_after = parts[1]
                    if path_after.startswith("v") and "/" in path_after:
                        path_after = path_after.split("/", 1)[1]
                    public_id = path_after.rsplit(".", 1)[0]
                    self.uploader.destroy(public_id, resource_type="image")
                    self.uploader.destroy(public_id, resource_type="video")
                    return True
            return False
        except Exception as e:
            logger.warning("Cloudinary delete failed: %s", e)
            return False

    def exists(self, filename: str) -> bool:
        return bool(filename and ("res.cloudinary.com" in filename or filename.startswith("http")))

    def get_path(self, filename: str) -> Path:
        return None

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
                        details TEXT DEFAULT ''
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);")

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
        finally:
            conn.close()

    def record_audit(self, actor: str, action: str, target_id: str, details: str = ""):
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO audit_logs (timestamp, actor, action, target_id, details)
                    VALUES (?, ?, ?, ?, ?);
                """, (get_current_time_ms(), actor or "admin", action, target_id, details))
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

    def get_audit_logs(self, limit: int = 50):
        conn = self.get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?;
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
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
                    SELECT code, name, sort_order, active, accent_color, created_at
                    FROM departments
                    WHERE active = 1
                    ORDER BY sort_order ASC, code ASC;
                """).fetchall()
            else:
                rows = conn.execute("""
                    SELECT code, name, sort_order, active, accent_color, created_at
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
                SELECT code, name, sort_order, active, accent_color, created_at
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
                "created_at": row["created_at"],
            }
        finally:
            if not self._is_in_flask():
                conn.close()

    def add_department(self, code: str, name: str, sort_order: int = 0, active: bool = True, accent_color: str = None):
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
        now_ms = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO departments (code, name, sort_order, active, accent_color, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (code, name, sort_order, active_int, accent_color, now_ms))
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

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    UPDATE departments SET
                        name = ?,
                        sort_order = ?,
                        active = ?,
                        accent_color = ?
                    WHERE code = ?;
                """, (name, sort_order, active_int, accent_color, code))
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
                # Check if notices target this screen
                count = conn.execute("""
                    SELECT COUNT(*) FROM notice_screens WHERE screen_code = ?;
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

    # ==========================================================================
    # Notice Mutations
    # ==========================================================================
    def add(self, data, file_obj=None, created_by="admin"):
        notice_id = generate_notice_id()
        media_filename = ""
        media_type = data.get("type", "text")
        
        if file_obj and getattr(file_obj, "filename", None):
            stream = getattr(file_obj, "stream", file_obj)
            dest_temp = self.media_folder / f"tmp_{notice_id}"
            ext, category = save_stream_to_disk(stream, dest_temp, max_bytes=MAX_CONTENT_LENGTH)
            
            media_filename = f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"
            final_path = self.media_folder / media_filename
            dest_temp.rename(final_path)
            media_type = category

            if getattr(self.media_storage, "is_cloud", False):
                try:
                    cloud_url = self.media_storage.save(final_path, media_filename)
                    if cloud_url:
                        media_filename = cloud_url
                        try:
                            final_path.unlink()
                        except Exception:
                            pass
                except Exception as e:
                    logger.error("Cloud upload error, falling back to local file: %s", e)

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

                conn.execute("""
                    INSERT INTO notices (
                        id, title, body, priority, type, media, duration, start, end,
                        screen_id, created_by, created_at, updated_at, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
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
                    now
                ))

                for s_code in target_screens:
                    code_val = s_code.upper() if SCREEN_CODE_REGEX.match(s_code.upper()) else s_code
                    conn.execute("""
                        INSERT OR IGNORE INTO notice_screens (notice_id, screen_code)
                        VALUES (?, ?);
                    """, (notice_id, code_val))
            
            self.record_audit(creator, "CREATE", notice_id, f"Created notice '{data.get('title', '')}'")
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
        media_type = data.get("type", target.get("type", "text"))

        if file_obj and getattr(file_obj, "filename", None):
            stream = getattr(file_obj, "stream", file_obj)
            dest_temp = self.media_folder / f"tmp_{notice_id}"
            ext, category = save_stream_to_disk(stream, dest_temp, max_bytes=MAX_CONTENT_LENGTH)
            
            old_media = media_filename
            media_filename = f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"
            final_path = self.media_folder / media_filename
            dest_temp.rename(final_path)
            media_type = category

            if getattr(self.media_storage, "is_cloud", False):
                try:
                    cloud_url = self.media_storage.save(final_path, media_filename)
                    if cloud_url:
                        media_filename = cloud_url
                        try:
                            final_path.unlink()
                        except Exception:
                            pass
                except Exception as e:
                    logger.error("Cloud upload error, falling back to local file: %s", e)
            
            if old_media and old_media != media_filename:
                self.media_storage.delete(old_media)

        title = str(data.get("title", target["title"])).strip()
        body = str(data.get("body", target.get("body", ""))).strip()
        
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
                        updated_at = ?
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

    def delete(self, notice_id, actor="admin"):
        target = self.get_by_id(notice_id)
        if not target:
            return False

        if target.get("media"):
            self.media_storage.delete(target["media"])

        conn = self.get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM notice_screens WHERE notice_id = ?;", (notice_id,))
                conn.execute("DELETE FROM notices WHERE id = ?;", (notice_id,))
            self.record_audit(actor or "admin", "DELETE", notice_id, f"Deleted notice '{target.get('title', '')}'")
            self.safe_garbage_collect_media()
            return True
        finally:
            if not self._is_in_flask():
                conn.close()

    def safe_garbage_collect_media(self, grace_period_seconds: int = 600):
        if not hasattr(self.media_storage, "media_dir"):
            return

        media_dir = self.media_storage.media_dir
        if not media_dir.exists():
            return

        conn = self.get_connection()
        try:
            rows = conn.execute("SELECT DISTINCT media FROM notices WHERE media IS NOT NULL AND media != '';").fetchall()
            referenced = {r[0] for r in rows}
        finally:
            if not self._is_in_flask():
                conn.close()

        now = time.time()
        for item in media_dir.iterdir():
            if item.is_file() and item.name not in referenced and not item.name.startswith("tmp_"):
                try:
                    stat = item.stat()
                    age = now - stat.st_mtime
                    if age > grace_period_seconds:
                        item.unlink()
                        logger.info("Safe Media GC: deleted unreferenced file %s (age: %.1f minutes)", item.name, age / 60)
                    else:
                        logger.debug("Safe Media GC: retained in-flight file %s (age: %.1f minutes)", item.name, age / 60)
                except OSError as e:
                    logger.warning("Safe Media GC error on %s: %s", item.name, e)

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


storage = NoticeStorage()
