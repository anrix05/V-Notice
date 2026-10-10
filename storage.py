import os
import sys
import time
import secrets
import mimetypes
import logging
import sqlite3
import shutil
import json
from pathlib import Path
from werkzeug.utils import secure_filename
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
        # If file_obj has .stream, stream in chunks to avoid memory spike
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

media_storage = LocalMediaStorage()

# ==============================================================================
# SQLite Notice Storage with Audit Logs
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS screens (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        created_at INTEGER NOT NULL
                    );
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO screens (id, name, created_at)
                    VALUES ('default', 'Default Screen', ?);
                """, (get_current_time_ms(),))

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
                        screen_id TEXT NOT NULL DEFAULT 'default' REFERENCES screens(id),
                        created_by TEXT NOT NULL DEFAULT 'admin',
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notices_screen ON notices(screen_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notices_status ON notices(is_active, start, end);")

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
        """Verify database connectivity, WAL mode, and return basic counts."""
        conn = self.get_connection()
        try:
            conn.execute("SELECT 1;").fetchone()
            wal_row = conn.execute("PRAGMA journal_mode;").fetchone()
            journal_mode = wal_row[0] if wal_row else "unknown"
            notices_count = conn.execute("SELECT COUNT(*) FROM notices;").fetchone()[0]
            screens_count = conn.execute("SELECT COUNT(*) FROM screens;").fetchone()[0]
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
            count = conn.execute("SELECT COUNT(*) FROM notices;").fetchone()[0]
            if count == 0 and self.data_file.exists():
                try:
                    with open(self.data_file, "r", encoding="utf-8") as f:
                        items = json.load(f)
                    if isinstance(items, list) and len(items) > 0:
                        now = get_current_time_ms()
                        logger.info("Migrating %d notices from %s into SQLite...", len(items), self.data_file)
                        with conn:
                            for n in items:
                                n_id = n.get("id") or generate_notice_id()
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
                                    n.get("screen_id", "default"),
                                    n.get("created_by", "admin"),
                                    int(n.get("created_at", n.get("start", now))),
                                    int(n.get("updated_at", now)),
                                ))
                        bak_path = self.data_file.with_name(self.data_file.name + ".bak")
                        shutil.copy2(self.data_file, bak_path)
                        logger.info("One-time migration complete. Backup preserved at %s", bak_path)
                except Exception as e:
                    logger.error("Migration error from JSON to SQLite: %s", e)
        finally:
            conn.close()

    def _row_to_dict(self, row, now_ms=None):
        if row is None:
            return None
        d = dict(row)
        d["status"] = compute_status(d, now_ms)
        return d

    def get_screens(self):
        conn = self.get_connection()
        try:
            rows = conn.execute("SELECT id, name, created_at FROM screens ORDER BY id ASC;").fetchall()
            return [dict(r) for r in rows]
        finally:
            if not self._is_in_flask():
                conn.close()

    def add_screen(self, screen_id, name=None):
        screen_id = str(screen_id).strip() or "default"
        name = name or screen_id.title()
        conn = self.get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT OR IGNORE INTO screens (id, name, created_at)
                    VALUES (?, ?, ?);
                """, (screen_id, name, get_current_time_ms()))
            return {"id": screen_id, "name": name}
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_all(self, screen_id=None):
        conn = self.get_connection()
        now_ms = get_current_time_ms()
        try:
            if screen_id and screen_id != "all":
                rows = conn.execute("""
                    SELECT * FROM notices 
                    WHERE screen_id = ? AND is_active = 1
                    ORDER BY created_at DESC;
                """, (screen_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM notices 
                    WHERE is_active = 1
                    ORDER BY created_at DESC;
                """).fetchall()
            return [self._row_to_dict(r, now_ms) for r in rows]
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_active(self, screen_id=None, now_ms=None):
        if now_ms is None:
            now_ms = get_current_time_ms()
        conn = self.get_connection()
        try:
            if screen_id and screen_id != "all":
                rows = conn.execute("""
                    SELECT * FROM notices 
                    WHERE is_active = 1 
                      AND screen_id = ?
                      AND start <= ? 
                      AND (end IS NULL OR end >= ?)
                    ORDER BY 
                      CASE priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'info' THEN 2 
                        ELSE 3 
                      END, 
                      created_at DESC;
                """, (screen_id, now_ms, now_ms)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM notices 
                    WHERE is_active = 1 
                      AND start <= ? 
                      AND (end IS NULL OR end >= ?)
                    ORDER BY 
                      CASE priority 
                        WHEN 'urgent' THEN 1 
                        WHEN 'info' THEN 2 
                        ELSE 3 
                      END, 
                      created_at DESC;
                """, (now_ms, now_ms)).fetchall()
            return [self._row_to_dict(r, now_ms) for r in rows]
        finally:
            if not self._is_in_flask():
                conn.close()

    def get_by_id(self, notice_id):
        conn = self.get_connection()
        try:
            row = conn.execute("SELECT * FROM notices WHERE id = ?;", (notice_id,)).fetchone()
            return self._row_to_dict(row)
        finally:
            if not self._is_in_flask():
                conn.close()

    def add(self, data, file_obj=None, created_by="admin"):
        # URL-safe random token ID per Phase 2 requirement 4
        notice_id = generate_notice_id()
        media_filename = ""
        media_type = data.get("type", "text")
        
        if file_obj and getattr(file_obj, "filename", None):
            # Server-side filename generation: never trust original client filename
            stream = getattr(file_obj, "stream", file_obj)
            dest_temp = self.media_folder / f"tmp_{notice_id}"
            ext, category = save_stream_to_disk(stream, dest_temp, max_bytes=MAX_CONTENT_LENGTH)
            
            media_filename = f"{notice_id}_{secrets.token_urlsafe(8)}.{ext}"
            final_path = self.media_folder / media_filename
            dest_temp.rename(final_path)
            media_type = category

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

        screen_id = str(data.get("screen_id", "default")).strip() or "default"
        self.add_screen(screen_id)

        creator = str(data.get("created_by") or created_by or "admin").strip()
        now = get_current_time_ms()

        conn = self.get_connection()
        try:
            with conn:
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
                    screen_id,
                    creator,
                    now,
                    now
                ))
            
            # Record audit log
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

        screen_id = str(data.get("screen_id", target.get("screen_id", "default"))).strip() or "default"
        self.add_screen(screen_id)

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
                    screen_id,
                    creator,
                    now,
                    notice_id
                ))
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

storage = NoticeStorage()
