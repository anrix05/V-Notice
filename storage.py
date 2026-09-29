import json
import os
import time
import uuid
import mimetypes
from threading import Lock
from werkzeug.utils import secure_filename
from config import (
    DATA_FILE,
    MEDIA_FOLDER,
    ALLOWED_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_MIME_TYPES,
)

lock = Lock()

def get_current_time_ms():
    return int(time.time() * 1000)

def allowed_file(filename, mimetype=None):
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
    if mimetype and mimetype not in ALLOWED_MIME_TYPES:
        # Check guessed type if client sent generic octet-stream
        guessed, _ = mimetypes.guess_type(filename)
        if guessed not in ALLOWED_MIME_TYPES:
            return False
    return True

def compute_status(notice, now_ms=None):
    if now_ms is None:
        now_ms = get_current_time_ms()
    start = notice.get("start", 0)
    end = notice.get("end", float("inf"))
    
    if now_ms < start:
        return "scheduled"
    elif now_ms > end:
        return "expired"
    else:
        return "live"

class NoticeStorage:
    def __init__(self, data_file=DATA_FILE, media_folder=MEDIA_FOLDER):
        self.data_file = data_file
        self.media_folder = media_folder
        self._ensure_storage()

    def _ensure_storage(self):
        self.media_folder.mkdir(exist_ok=True)
        if not self.data_file.exists():
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def _read_data(self):
        with lock:
            if not self.data_file.exists():
                return []
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []

    def _write_data(self, notices):
        with lock:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(notices, f, indent=2, ensure_ascii=False)

    def get_all(self):
        notices = self._read_data()
        now_ms = get_current_time_ms()
        for n in notices:
            n["status"] = compute_status(n, now_ms)
        return notices

    def get_active(self):
        all_notices = self.get_all()
        # Rule 5: A notice is active only when start <= current_time <= end
        return [n for n in all_notices if n.get("status") == "live"]

    def get_by_id(self, notice_id):
        notices = self.get_all()
        for n in notices:
            if n.get("id") == notice_id:
                return n
        return None

    def add(self, data, file_obj=None):
        notices = self._read_data()
        notice_id = uuid.uuid4().hex[:8]
        
        media_filename = ""
        media_type = data.get("type", "text")
        
        if file_obj and file_obj.filename:
            raw_filename = secure_filename(file_obj.filename)
            if not raw_filename or not allowed_file(raw_filename, file_obj.mimetype):
                raise ValueError("Invalid file extension or unsupported media type.")

            ext = raw_filename.rsplit(".", 1)[1].lower()
            # Rule 12: Do not trust original filename. Generate safe filename with zero path traversal.
            media_filename = f"{notice_id}_{uuid.uuid4().hex[:8]}.{ext}"
            dest_path = self.media_folder / media_filename
            
            try:
                file_obj.save(dest_path)
            except Exception as e:
                # Rule 20: Remove partially uploaded files on failure
                if dest_path.exists():
                    os.remove(dest_path)
                raise IOError(f"Failed to save upload: {e}")

            if ext in ALLOWED_VIDEO_EXTENSIONS:
                media_type = "video"
            elif ext in ALLOWED_IMAGE_EXTENSIONS:
                media_type = "image"

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
            end_ms = int(data.get("end", default_end))
        except (ValueError, TypeError):
            end_ms = start_ms + (7 * 24 * 60 * 60 * 1000)

        priority = str(data.get("priority", "normal")).lower()
        if priority not in ("urgent", "normal", "info"):
            priority = "normal"

        new_notice = {
            "id": notice_id,
            "title": str(data.get("title", "")).strip(),
            "body": str(data.get("body", "")).strip(),
            "priority": priority,
            "type": media_type,
            "media": media_filename,
            "duration": duration,
            "start": start_ms,
            "end": end_ms
        }

        notices.insert(0, new_notice)
        self._write_data(notices)
        new_notice["status"] = compute_status(new_notice)
        return new_notice

    def update(self, notice_id, data, file_obj=None):
        notices = self._read_data()
        target_idx = None
        target_notice = None
        for idx, n in enumerate(notices):
            if n.get("id") == notice_id:
                target_idx = idx
                target_notice = n
                break
        
        if target_notice is None:
            return None

        media_filename = target_notice.get("media", "")
        media_type = data.get("type", target_notice.get("type", "text"))

        if file_obj and file_obj.filename:
            raw_filename = secure_filename(file_obj.filename)
            if not raw_filename or not allowed_file(raw_filename, file_obj.mimetype):
                raise ValueError("Invalid file extension or unsupported media type.")

            ext = raw_filename.rsplit(".", 1)[1].lower()
            new_media_filename = f"{notice_id}_{uuid.uuid4().hex[:8]}.{ext}"
            dest_path = self.media_folder / new_media_filename
            
            try:
                file_obj.save(dest_path)
            except Exception as e:
                if dest_path.exists():
                    os.remove(dest_path)
                raise IOError(f"Failed to save upload: {e}")

            # Delete old media file if existed
            if media_filename:
                old_path = self.media_folder / media_filename
                if old_path.exists():
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass

            media_filename = new_media_filename
            if ext in ALLOWED_VIDEO_EXTENSIONS:
                media_type = "video"
            elif ext in ALLOWED_IMAGE_EXTENSIONS:
                media_type = "image"
        elif media_type == "text" and media_filename:
            old_path = self.media_folder / media_filename
            if old_path.exists():
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            media_filename = ""

        try:
            duration = int(data.get("duration", target_notice.get("duration", 10)))
            if duration <= 0:
                duration = 10
        except (ValueError, TypeError):
            duration = 10

        try:
            start_ms = int(data.get("start", target_notice.get("start", get_current_time_ms())))
        except (ValueError, TypeError):
            start_ms = target_notice.get("start", get_current_time_ms())

        try:
            end_ms = int(data.get("end", target_notice.get("end", start_ms + (7 * 24 * 60 * 60 * 1000))))
        except (ValueError, TypeError):
            end_ms = target_notice.get("end", start_ms + (7 * 24 * 60 * 60 * 1000))

        priority = str(data.get("priority", target_notice.get("priority", "normal"))).lower()
        if priority not in ("urgent", "normal", "info"):
            priority = "normal"

        target_notice["title"] = str(data.get("title", target_notice.get("title", ""))).strip()
        target_notice["body"] = str(data.get("body", target_notice.get("body", ""))).strip()
        target_notice["priority"] = priority
        target_notice["type"] = media_type
        target_notice["media"] = media_filename
        target_notice["duration"] = duration
        target_notice["start"] = start_ms
        target_notice["end"] = end_ms

        notices[target_idx] = target_notice
        self._write_data(notices)
        target_notice["status"] = compute_status(target_notice)
        return target_notice

    def delete(self, notice_id):
        notices = self._read_data()
        target = None
        remaining = []
        for n in notices:
            if n.get("id") == notice_id:
                target = n
            else:
                remaining.append(n)
        
        if not target:
            return False

        # Rule 4: Deleting a notice must also remove its associated media file.
        if target.get("media"):
            media_path = self.media_folder / target["media"]
            if media_path.exists():
                try:
                    os.remove(media_path)
                except Exception:
                    pass

        self._write_data(remaining)
        return True

storage = NoticeStorage()
