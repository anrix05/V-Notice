import re
import csv
import io
import secrets
import config
import hashlib
import queue
import threading
import sys
import os
import math
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    send_from_directory,
    send_file,
    redirect,
    Response,
    make_response,
    stream_with_context,
)
from pathlib import Path
import mimetypes
from werkzeug.serving import run_simple
from werkzeug.middleware.proxy_fix import ProxyFix
from config import (
    DISPLAY_PORT,
    ADMIN_PORT,
    MEDIA_FOLDER,
    SECRET_KEY,
    MAX_CONTENT_LENGTH,
)
SCREEN_CODE_REGEX = re.compile(r"^[A-Z0-9_-]{2,10}$")
from security import (
    verify_admin_password,
    validate_password_strength,
    login_rate_limiter,
    account_rate_limiter,
    api_key_rate_limiter,
    invite_rate_limiter,
    import_rate_limiter,
    generate_csrf_token,
    validate_csrf_token,
    check_password_config_warnings,
)
from storage import storage, compute_status, sanitize_screen_codes, KOLKATA_TZ
import datetime
import socket
import urllib.request
import json
import time

# Emit security warnings on startup
check_password_config_warnings()

_weather_cache = {"data": None, "timestamp": 0}

def get_lan_ip():
    env_ip = os.environ.get("SERVER_IP")
    if env_ip:
        return env_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return ip

def get_client_ip():
    return request.remote_addr or "127.0.0.1"


# ==============================================================================
# Phase 4: Sync Efficiency - ETag & SSE Helpers
# ==============================================================================

def compute_etag(data):
    """Compute a deterministic 16-character SHA-256 hex digest for JSON-serializable notice data."""
    dumped = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(dumped.encode('utf-8')).hexdigest()[:16]

def make_etag_response(data):
    """Return HTTP 304 Not Modified if client If-None-Match matches, else 200 with ETag header."""
    etag = compute_etag(data)
    client_etag = request.headers.get("If-None-Match", "").strip('"')
    if client_etag and client_etag == etag:
        res = Response(status=304)
        res.headers["ETag"] = f'"{etag}"'
        res.headers["Cache-Control"] = "no-cache"
        return res
    res = jsonify(data)
    res.headers["ETag"] = f'"{etag}"'
    res.headers["Cache-Control"] = "no-cache"
    return res

def make_flag_event_response(data):
    """Return HTTP 304 if flag event schedule has not changed, else 200 with Cache-Control: no-store."""
    schedule_payload = {
        "event_id": data.get("event_id"),
        "label": data.get("label"),
        "flag_start_ms": data.get("flag_start_ms"),
        "flag_end_ms": data.get("flag_end_ms"),
        "show_standup_text": data.get("show_standup_text"),
        "standup_lead_seconds": data.get("standup_lead_seconds"),
        "standup_en": data.get("standup_en"),
        "standup_hi": data.get("standup_hi"),
        "standup_mr": data.get("standup_mr")
    }
    etag = compute_etag(schedule_payload)
    client_etag = request.headers.get("If-None-Match", "").strip('"')
    if client_etag and client_etag == etag:
        res = Response(status=304)
        res.headers["ETag"] = f'"{etag}"'
        res.headers["Cache-Control"] = "no-store, max-age=0"
        return res
    res = jsonify(data)
    res.headers["ETag"] = f'"{etag}"'
    res.headers["Cache-Control"] = "no-store, max-age=0"
    return res

_sse_subscribers = []
_sse_lock = threading.Lock()

_screen_heartbeats = {}
_screen_audio_ready = {}
_screen_heartbeats_lock = threading.Lock()

def record_heartbeat(screen_code: str, audio_ready: bool = None):
    if not screen_code:
        return
    code = str(screen_code).strip().upper()
    with _screen_heartbeats_lock:
        _screen_heartbeats[code] = int(time.time() * 1000)
        if audio_ready is not None:
            _screen_audio_ready[code] = bool(audio_ready)

def get_screen_last_seen(screen_code: str):
    if not screen_code:
        return None
    code = str(screen_code).strip().upper()
    with _screen_heartbeats_lock:
        return _screen_heartbeats.get(code)

def get_screen_audio_ready(screen_code: str) -> bool:
    if not screen_code:
        return False
    code = str(screen_code).strip().upper()
    with _screen_heartbeats_lock:
        return _screen_audio_ready.get(code, False)

def notify_notice_change(affected_screens=None):
    """Broadcast notice change to affected SSE listeners. ALL changes notify everyone."""
    with _sse_lock:
        if affected_screens:
            aff_set = {str(s).strip().upper() for s in affected_screens if str(s).strip()}
        else:
            aff_set = None

        is_college_wide = (aff_set is None) or ("ALL" in aff_set)
        for item in list(_sse_subscribers):
            q, sub_screen = item
            if sub_screen is None or is_college_wide or (aff_set and sub_screen in aff_set):
                try:
                    payload = json.dumps({
                        "action": "update",
                        "screens": list(aff_set) if aff_set else ["ALL"]
                    })
                    q.put_nowait(("notice_update", payload))
                except Exception:
                    pass

def notify_flag_change(affected_screens=None):
    """Broadcast flag_changed event to affected SSE listeners only."""
    with _sse_lock:
        if affected_screens:
            if isinstance(affected_screens, str):
                aff_set = {s.strip().upper() for s in affected_screens.split(",") if s.strip()}
            else:
                aff_set = {str(s).strip().upper() for s in affected_screens if str(s).strip()}
        else:
            aff_set = None

        is_college_wide = (aff_set is None) or ("ALL" in aff_set)
        for item in list(_sse_subscribers):
            q, sub_screen = item
            if sub_screen is None or is_college_wide or (aff_set and sub_screen in aff_set):
                try:
                    payload = json.dumps({
                        "action": "flag_changed",
                        "screens": list(aff_set) if aff_set else ["ALL"]
                    })
                    q.put_nowait(("flag_changed", payload))
                except Exception:
                    pass

def sse_event_stream(screen_code=None):
    """Generator for Server-Sent Events with keep-alive pings and screen scoping."""
    sub_screen = str(screen_code).strip().upper() if screen_code else None
    q = queue.Queue(maxsize=10)
    item = (q, sub_screen)
    with _sse_lock:
        _sse_subscribers.append(item)
    try:
        yield "event: connected\ndata: ok\n\n"
        while True:
            try:
                msg = q.get(timeout=15)
                if isinstance(msg, tuple):
                    evt_type, data_str = msg
                else:
                    evt_type = "notice_update"
                    data_str = str(msg)
                yield f"event: {evt_type}\ndata: {data_str}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        with _sse_lock:
            if item in _sse_subscribers:
                _sse_subscribers.remove(item)

def get_system_weather():
    import config
    weather_enabled = getattr(config, "WEATHER_ENABLED", True)
    city = getattr(config, "WEATHER_LABEL", "Mumbai").strip() or "Mumbai"
    lat = float(getattr(config, "WEATHER_LAT", 19.0760))
    lon = float(getattr(config, "WEATHER_LON", 72.8777))
    public_base_url = getattr(config, "PUBLIC_BASE_URL", "")
    urgent_chime = getattr(config, "URGENT_CHIME", False)

    if not weather_enabled:
        return {
            "weather_enabled": False,
            "city": city.upper(),
            "temp": None,
            "icon": None,
            "lan_ip": get_lan_ip(),
            "display_port": DISPLAY_PORT,
            "public_base_url": public_base_url,
            "urgent_chime": urgent_chime,
            "poll_interval_seconds": getattr(config, "POLL_INTERVAL_SECONDS", 5),
            "sse_enabled": getattr(config, "SSE_ENABLED", False),
            "voice_notices_enabled": getattr(config, "VOICE_NOTICES_ENABLED", False),
        }

    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["timestamp"] < 600):
        data = dict(_weather_cache["data"])
        data["weather_enabled"] = True
        data["city"] = city.upper()
        data["public_base_url"] = public_base_url
        data["urgent_chime"] = urgent_chime
        data["poll_interval_seconds"] = getattr(config, "POLL_INTERVAL_SECONDS", 5)
        data["sse_enabled"] = getattr(config, "SSE_ENABLED", False)
        data["voice_notices_enabled"] = getattr(config, "VOICE_NOTICES_ENABLED", False)
        return data

    temp = "30°C"
    icon = "☀️"
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
        req = urllib.request.Request(url, headers={"User-Agent": "VNotice/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            w_data = json.loads(r.read().decode("utf-8", "ignore"))
            if "current" in w_data:
                raw_temp = round(w_data["current"]["temperature_2m"])
                temp = f"{raw_temp}°C"
                code = w_data["current"]["weather_code"]
                icons = {
                    0: "☀️",
                    1: "🌤️",
                    2: "⛅",
                    3: "☁️",
                    45: "🌫️",
                    48: "🌫️",
                    51: "🌦️",
                    53: "🌧️",
                    55: "🌧️",
                    61: "🌧️",
                    63: "🌧️",
                    65: "⛈️",
                    71: "🌨️",
                    80: "🌦️",
                    81: "🌧️",
                    82: "⛈️",
                    95: "⚡"
                }
                icon = icons.get(code, "☀️")
    except Exception:
        if _weather_cache["data"]:
            data = dict(_weather_cache["data"])
            data["weather_enabled"] = True
            data["city"] = city.upper()
            data["public_base_url"] = public_base_url
            data["urgent_chime"] = urgent_chime
            data["poll_interval_seconds"] = getattr(config, "POLL_INTERVAL_SECONDS", 5)
            data["sse_enabled"] = getattr(config, "SSE_ENABLED", False)
            return data

    result = {
        "weather_enabled": True,
        "city": city.upper(),
        "temp": temp,
        "icon": icon,
        "lan_ip": get_lan_ip(),
        "display_port": DISPLAY_PORT,
        "public_base_url": public_base_url,
        "urgent_chime": urgent_chime,
        "poll_interval_seconds": getattr(config, "POLL_INTERVAL_SECONDS", 5),
        "sse_enabled": getattr(config, "SSE_ENABLED", False),
    }
    _weather_cache["data"] = result
    _weather_cache["timestamp"] = now
    return result

def sanitize_public_notice(notice_dict):
    """Phase 2 Requirement 7: Do not leak admin-only data (created_by, internal audit) to unauthenticated callers."""
    if not notice_dict:
        return notice_dict
    safe = dict(notice_dict)
    safe.pop("created_by", None)
    safe.pop("updated_at", None)
    if not getattr(config, "SHOW_POSTED_BY_ON_DISPLAY", False):
        safe.pop("created_by_name", None)
        safe.pop("posted_by", None)
    return safe

def _is_bootstrap_allowed() -> bool:
    env_val = getattr(config, "ALLOW_BOOTSTRAP_ADMIN_ENV", None)
    if env_val is not None:
        return str(env_val).lower() in ("true", "1", "yes")
    return not storage.has_admin_user()

def _validate_and_load_session_user():
    """Load and validate the current session user on every request."""
    if session.get("is_admin") is not True:
        return None
    now_ms = int(time.time() * 1000)
    expires_at = session.get("expires_at")
    if expires_at is not None and now_ms > int(expires_at):
        session.clear()
        return None

    if session.get("is_bootstrap"):
        if not _is_bootstrap_allowed():
            session.clear()
            return None
        return {
            "id": None,
            "username": "admin",
            "name": "Admin",
            "email": "admin",
            "role": "admin",
            "departments": ["ALL"],
            "can_post_college_wide": True,
            "can_target_all": True,
            "can_post_urgent": True,
            "is_bootstrap": True,
        }

    user_id = session.get("user_id")
    if not user_id:
        session.clear()
        return None

    u = storage.get_user_by_id(user_id)
    if not u or u.get("status") != "active" or int(u.get("session_version", 0)) != int(session.get("session_version", -1)):
        session.clear()
        return None

    u.pop("password_hash", None)
    return u

def _check_api_key_header():
    """Validate optional X-Password script header when ALLOW_API_KEY_AUTH is enabled.
    Returns (status, retry_after) where status is 'valid', 'invalid', 'locked', or 'none'."""
    auth_header = request.headers.get("X-Password")
    if not auth_header:
        return "none", 0
    if not getattr(config, "ALLOW_API_KEY_AUTH", False):
        return "none", 0
    ip = get_client_ip()
    locked, retry_after = api_key_rate_limiter.is_locked(ip)
    if locked:
        return "locked", retry_after
    if verify_admin_password(auth_header):
        api_key_rate_limiter.record_success(ip)
        return "valid", 0
    api_key_rate_limiter.record_failure(ip)
    return "invalid", 0

def check_admin_auth():
    api_status, _ = _check_api_key_header()
    if api_status == "valid":
        return True
    return _validate_and_load_session_user() is not None

def read_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_status, retry_after = _check_api_key_header()
        if api_status == "valid":
            return f(*args, **kwargs)

        if _validate_and_load_session_user() is not None:
            return f(*args, **kwargs)

        if api_status == "locked":
            res = jsonify({"error": "Rate limit exceeded. Too many invalid credentials.", "retry_after": retry_after})
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res
        if api_status == "invalid":
            return jsonify({"error": "Unauthorized. Invalid admin password."}), 401

        return jsonify({"error": "Unauthorized. Authentication required."}), 401
    return decorated_function


def get_current_user():
    api_status, _ = _check_api_key_header()
    if api_status == "valid":
        return {
            "id": None,
            "username": "admin",
            "name": "Admin",
            "email": "admin",
            "role": "admin",
            "departments": ["ALL"],
            "can_post_college_wide": True,
            "can_target_all": True,
            "can_post_urgent": True,
        }

    return _validate_and_load_session_user()

def check_notice_permissions(user, target_screens, priority="normal", existing_notice=None, is_mutation=True):
    """Phase 2A: Enforce admin vs faculty permissions on notice create/edit/delete."""
    if not user:
        return False, "Authentication required."
    if user.get("role") == "admin":
        return True, None

    if existing_notice is not None and is_mutation:
        if existing_notice.get("created_by") != user.get("id"):
            return False, "Permission denied: faculty can only modify notices they created."

    if str(priority or "normal").strip().lower() == "urgent" and not user.get("can_post_urgent", False):
        return False, "Permission denied: faculty cannot post urgent notices without can_post_urgent permission."

    screens = [str(s).strip().upper() for s in (target_screens or []) if str(s).strip()]
    if not screens:
        screens = ["ALL"]

    can_cw = bool(user.get("can_post_college_wide", False))
    if "ALL" in screens and not can_cw:
        return False, "Permission denied: faculty cannot target All Departments (college-wide)."

    user_depts = {str(d).strip().upper() for d in user.get("departments", [])}
    for sc in screens:
        if sc == "ALL":
            continue
        if sc not in user_depts and not can_cw:
            return False, f"Permission denied: faculty cannot target department '{sc}'."

    return True, None

def _filter_notices_for_user(user, notices_list):
    if not user or user.get("role") == "admin":
        return notices_list
    user_depts = {str(d).strip().upper() for d in user.get("departments", [])}
    uid = user.get("id")
    filtered = []
    for n in notices_list:
        if n.get("created_by") == uid:
            filtered.append(n)
            continue
        n_screens = {str(s).strip().upper() for s in (n.get("screens") or [n.get("screen_id") or "ALL"])}
        if "ALL" in n_screens or (n_screens & user_depts):
            filtered.append(n)
    return filtered

def mutation_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_status, retry_after = _check_api_key_header()
        if api_status == "valid":
            return f(*args, **kwargs)

        if _validate_and_load_session_user() is not None:
            csrf_token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            session_token = session.get("csrf_token")
            if not validate_csrf_token(session_token, csrf_token):
                return jsonify({"error": "Forbidden: CSRF token validation failed."}), 403
            return f(*args, **kwargs)

        if api_status == "locked":
            res = jsonify({"error": "Rate limit exceeded. Too many invalid credentials.", "retry_after": retry_after})
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res
        if api_status == "invalid":
            return jsonify({"error": "Unauthorized. Invalid admin password."}), 401

        return jsonify({"error": "Unauthorized. Authentication required."}), 401
    return decorated_function

def apply_security_headers(app):
    @app.after_request
    def set_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        is_display = request.path.startswith("/display")
        frame_ancestors = "'self' http://localhost:5000 http://localhost:5001 http://127.0.0.1:5000 http://127.0.0.1:5001" if is_display else "'none'"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' blob: https://res.cloudinary.com https://*.cloudinary.com; "
            "media-src 'self' blob: https://res.cloudinary.com https://*.cloudinary.com; "
            "connect-src 'self' https://res.cloudinary.com https://*.cloudinary.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "manifest-src 'self'; "
            "worker-src 'self'; "
            "frame-src 'self' http://localhost:5000 http://localhost:5001 http://127.0.0.1:5000 http://127.0.0.1:5001; "
            f"frame-ancestors {frame_ancestors};"
        )
        if request.path.startswith("/admin") or request.path == "/" or request.path.startswith("/api"):
            response.headers["X-Frame-Options"] = "DENY"
        elif is_display:
            response.headers.pop("X-Frame-Options", None)
        
        # If HTTPS, enforce Secure session cookies
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            for cookie_name in ("session", "csrf_token"):
                if cookie_name in response.headers.get("Set-Cookie", ""):
                    pass
        return response

import logging
import shutil
import sys

SERVER_START_TIME = time.time()

# Configure structured logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("vnotice")

def get_process_memory_mb():
    """Cross-platform process RSS memory measurement without external dependencies."""
    # 1. Linux procfs (Raspberry Pi & Render containers)
    if os.path.exists('/proc/self/status'):
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        return round(int(line.split()[1]) / 1024, 2)
        except Exception:
            pass
    # 2. Windows ctypes
    if sys.platform == 'win32':
        try:
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ('cb', wintypes.DWORD),
                    ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t),
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            fn = ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            h = ctypes.windll.kernel32.GetCurrentProcess()
            if fn(h, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / (1024 * 1024), 2)
        except Exception:
            pass
    # 3. Unix resource fallback
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
    except Exception:
        pass
    return None

def get_health_payload(app_name):
    """Produce comprehensive health status payload."""
    db_health = storage.check_health()
    free_mb = 0
    try:
        total, used, free = shutil.disk_usage(MEDIA_FOLDER)
        free_mb = round(free / (1024 * 1024), 1)
    except Exception:
        pass
    writable = os.access(MEDIA_FOLDER, os.W_OK)
    mem_mb = get_process_memory_mb()
    uptime = round(time.time() - SERVER_START_TIME, 1)

    is_healthy = db_health.get("connected", False) and writable
    status_str = "healthy" if is_healthy else "unhealthy"

    data = {
        "status": status_str,
        "app": app_name,
        "version": getattr(config, "VERSION", "2.0.0"),
        "uptime_seconds": uptime,
        "memory_rss_mb": mem_mb,
        "database": db_health,
        "storage": {
            "media_dir": str(MEDIA_FOLDER),
            "writable": writable,
            "free_space_mb": free_mb,
        },
        "ports": {
            "display_port": DISPLAY_PORT,
            "admin_port": ADMIN_PORT,
        }
    }
    status_code = 200 if is_healthy else 503
    return data, status_code

def configure_app_security(app):
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(getattr(config, "IS_PRODUCTION", False))
    app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=getattr(config, "FACULTY_SESSION_DAYS", 30))
    proxy_hops = int(getattr(config, "TRUSTED_PROXY_HOPS", 0) or 0)
    if proxy_hops > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_hops, x_proto=proxy_hops, x_host=proxy_hops, x_port=proxy_hops)
    apply_security_headers(app)

def _issue_user_session(user_dict, is_bootstrap=False):
    now_ms = int(time.time() * 1000)
    role = user_dict.get("role", "faculty")
    if role == "admin":
        ttl_ms = int(getattr(config, "ADMIN_SESSION_HOURS", 8)) * 3600 * 1000
    else:
        ttl_ms = int(getattr(config, "FACULTY_SESSION_DAYS", 30)) * 86400 * 1000

    session.clear()
    session.permanent = True
    session["is_admin"] = True
    session["role"] = role
    session["expires_at"] = now_ms + ttl_ms
    if is_bootstrap:
        session["is_bootstrap"] = True
    else:
        session["user_id"] = user_dict["id"]
        session["session_version"] = int(user_dict.get("session_version", 0))
    token = generate_csrf_token()
    session["csrf_token"] = token
    return token

def _handle_login():
    ip = get_client_ip()
    data = request.get_json(silent=True) or request.form
    ident = str(data.get("email") or data.get("username") or "").strip()
    password = str(data.get("password", "")).strip()
    account_key = (ident or "admin").lower()

    ip_locked, ip_retry = login_rate_limiter.is_locked(ip)
    acct_locked, acct_retry = account_rate_limiter.is_locked(account_key)
    if ip_locked or acct_locked:
        retry_after = max(ip_retry, acct_retry)
        res = jsonify({
            "success": False,
            "error": "Too many failed login attempts. Please try again later.",
            "retry_after": retry_after
        })
        res.status_code = 429
        res.headers["Retry-After"] = str(retry_after)
        return res

    # 1. Break-glass env ADMIN_PASSWORD login (only while ALLOW_BOOTSTRAP_ADMIN=true)
    if (not ident or ident.lower() == "admin") and _is_bootstrap_allowed():
        if verify_admin_password(password):
            login_rate_limiter.record_success(ip)
            account_rate_limiter.record_success(account_key)
            bootstrap_user = {
                "id": None,
                "username": "admin",
                "name": "Admin",
                "email": "admin",
                "role": "admin",
                "departments": ["ALL"],
                "can_post_college_wide": True,
                "can_target_all": True,
                "can_post_urgent": True,
            }
            token = _issue_user_session(bootstrap_user, is_bootstrap=True)
            storage.record_audit(
                actor="admin",
                action="BOOTSTRAP_LOGIN",
                target_id="admin",
                details="Break-glass bootstrap admin login",
                ip=ip,
            )
            return jsonify({
                "success": True,
                "message": "Authentication successful",
                "csrf_token": token,
                "user": bootstrap_user,
            })

    # 2. Database user login by email (or legacy username)
    if ident and ident.lower() != "admin":
        user = storage.verify_user_credentials(ident, password)
        if user:
            login_rate_limiter.record_success(ip)
            account_rate_limiter.record_success(account_key)
            token = _issue_user_session(user, is_bootstrap=False)
            storage.record_audit(
                actor=user["email"],
                action="LOGIN_SUCCESS",
                target_id=str(user["id"]),
                details=f"User {user['email']} logged in",
                ip=ip,
            )
            return jsonify({
                "success": True,
                "message": "Authentication successful",
                "csrf_token": token,
                "user": user,
            })

    login_rate_limiter.record_failure(ip)
    account_rate_limiter.record_failure(account_key)
    storage.record_audit(
        actor=ident or "admin",
        action="LOGIN_FAILED",
        target_id=ident or "admin",
        details="Failed login: invalid credentials",
        ip=ip,
    )
    return jsonify({"success": False, "error": "Invalid username or password"}), 401

def _handle_logout():
    user = _validate_and_load_session_user()
    if user is not None:
        csrf_token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not validate_csrf_token(session.get("csrf_token"), csrf_token):
            return jsonify({"error": "Forbidden: CSRF token validation failed."}), 403
        actor = user.get("email") or "admin"
        storage.record_audit(actor=actor, action="LOGOUT", target_id=str(user.get("id") or "admin"), details="User logged out", ip=get_client_ip())
    session.clear()
    return jsonify({"success": True})

# ==============================================================================
# Public Notice Routes (/n/<id>, /n/<id>/file, redirects, and OG cards)
# ==============================================================================
_public_rate_limit = {}
_public_rate_lock = threading.Lock()

def check_public_rate_limit(ip, max_requests=120, window_sec=60):
    now = time.time()
    with _public_rate_lock:
        reqs = _public_rate_limit.get(ip, [])
        reqs = [t for t in reqs if now - t < window_sec]
        if len(reqs) >= max_requests:
            _public_rate_limit[ip] = reqs
            return False
        reqs.append(now)
        _public_rate_limit[ip] = reqs
        if len(_public_rate_limit) > 2000:
            for k in list(_public_rate_limit.keys())[:500]:
                if not _public_rate_limit[k] or (now - _public_rate_limit[k][-1] > window_sec):
                    _public_rate_limit.pop(k, None)
        return True

def check_flag_trigger_auth():
    import config
    token = getattr(config, "FLAG_TRIGGER_TOKEN", "")
    if not token or not str(token).strip():
        return False, 404, "Trigger API is disabled"
    ip = get_client_ip()
    if not check_public_rate_limit(ip, max_requests=30, window_sec=60):
        return False, 429, "Rate limit exceeded"
    provided = request.headers.get("X-Flag-Token")
    if not provided:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header[7:].strip()
    if not provided or not secrets.compare_digest(provided, str(token).strip()):
        return False, 401, "Invalid trigger token"
    return True, 200, "OK"

def generate_download_slug(notice, ext=None):
    dept = str(notice.get("screen_id") or "ALL").strip().upper()
    dept = "".join(c for c in dept if c.isalnum() or c in ("-", "_")) or "ALL"
    title = str(notice.get("title") or "notice").strip()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    slug = slug[:50] or "notice"
    if not ext:
        if notice.get("media"):
            m_str = str(notice["media"])
            if "?" in m_str:
                m_str = m_str.split("?")[0]
            ext = Path(m_str).suffix.lstrip(".").lower()
        if not ext:
            ntype = str(notice.get("type") or "text").lower()
            if ntype == "image":
                ext = "jpg"
            elif ntype == "video":
                ext = "mp4"
            elif ntype == "voice":
                ext = "mp3"
            else:
                ext = "txt"
    ext = ext.lstrip(".") or "txt"
    if "?" in ext:
        ext = ext.split("?")[0]
    return f"{dept}-{slug}.{ext}"

def get_public_base_url():
    base = getattr(config, "PUBLIC_BASE_URL", "")
    if base and str(base).strip():
        return str(base).strip().rstrip("/")
    try:
        if request and request.host_url:
            return request.host_url.rstrip("/")
    except Exception:
        pass
    return ""

def format_notice_for_display(notice):
    if not notice:
        return None
    n = dict(notice)
    start_ms = n.get("start") or 0
    end_ms = n.get("end")
    created_ms = n.get("created_at") or start_ms or int(time.time() * 1000)

    if created_ms:
        time_t = time.localtime(created_ms / 1000)
        n["posted_date_str"] = time.strftime("%d %b %Y", time_t)
    else:
        n["posted_date_str"] = "Today"

    now_ms = int(time.time() * 1000)
    if end_ms:
        diff_ms = end_ms - now_ms
        time_end = time.localtime(end_ms / 1000)
        time_formatted = time.strftime("%d %b %Y, %I:%M %p", time_end).lstrip("0")
        n["valid_till_str"] = f"Valid till {time_formatted}"
        n["exact_valid_till_str"] = f"Until {time_formatted}"
        if diff_ms > 0:
            days = math.ceil(diff_ms / (24 * 3600 * 1000))
            if days > 1:
                n["validity_badge_str"] = f"Valid for {days} more days"
            elif days == 1:
                hours = math.ceil(diff_ms / (3600 * 1000))
                if hours > 1:
                    n["validity_badge_str"] = f"Valid for {hours} more hours"
                else:
                    n["validity_badge_str"] = "Valid for 1 more hour"
            else:
                n["validity_badge_str"] = "Valid today"
        else:
            n["validity_badge_str"] = "Expired"
    else:
        n["valid_till_str"] = "Ongoing"
        n["validity_badge_str"] = "Ongoing announcement"
        n["exact_valid_till_str"] = "No expiry date set"

    nid_str = str(n.get("id") or "")
    h = sum(ord(c) for c in nid_str)
    n["gradient_theme_idx"] = h % 4

    raw_dept = str(n.get("screen_id") or "ALL").strip().upper()
    n["clean_dept"] = raw_dept
    n["display_dept"] = "College-wide" if raw_dept == "ALL" else raw_dept

    n["file_size_formatted"] = ""
    n["file_size_bytes"] = 0
    n["media_url"] = ""
    if n.get("media"):
        m_filename = str(n["media"])
        if m_filename.startswith("http://") or m_filename.startswith("https://"):
            n["media_url"] = m_filename
        else:
            n["media_url"] = f"/media/{m_filename}"
        if not m_filename.startswith("http://") and not m_filename.startswith("https://"):
            media_path = None
            if hasattr(storage.media_storage, "get_path"):
                try:
                    media_path = storage.media_storage.get_path(m_filename)
                except Exception:
                    media_path = None
            if not media_path or not Path(media_path).is_file():
                candidate = Path(MEDIA_FOLDER) / m_filename
                if candidate.is_file():
                    media_path = candidate
            if media_path and Path(media_path).exists():
                sz = Path(media_path).stat().st_size
                n["file_size_bytes"] = sz
                if sz < 1024 * 1024:
                    n["file_size_formatted"] = f"{round(sz / 1024, 1)} KB"
                else:
                    n["file_size_formatted"] = f"{round(sz / (1024 * 1024), 1)} MB"

    n["download_slug"] = generate_download_slug(n)

    # Hero image display URL (resized for display only, never 14MB original)
    media_val = str(n.get("media") or "").strip()
    notice_type = str(n.get("type") or "text").lower()
    if media_val and notice_type == "image":
        if "res.cloudinary.com" in media_val and "/upload/" in media_val:
            if "w_1200" not in media_val:
                n["hero_display_url"] = media_val.replace("/upload/", "/upload/w_1200,q_auto,f_auto/", 1)
            else:
                n["hero_display_url"] = media_val
        elif media_val.startswith("http://") or media_val.startswith("https://"):
            n["hero_display_url"] = media_val
        else:
            n["hero_display_url"] = f"/media/thumb/w1200/{media_val}"
    else:
        n["hero_display_url"] = n.get("media_url") or ""

    # Voice waveform validation and pre-rendered bars
    if notice_type == "voice":
        wf_raw = n.get("waveform")
        wf_list = None
        try:
            val = json.loads(wf_raw) if isinstance(wf_raw, str) else wf_raw
            if isinstance(val, list) and len(val) == 64:
                wf_list = [max(5, min(100, int(round(float(v))))) for v in val]
        except Exception:
            wf_list = None

        if not wf_list:
            audio_candidate = None
            if media_val and not media_val.startswith("http"):
                candidate = Path(MEDIA_FOLDER) / media_val
                if candidate.is_file():
                    audio_candidate = candidate
            wf_json = storage.sanitize_or_generate_waveform(None, audio_file_path=audio_candidate)
            n["waveform"] = wf_json
            try:
                wf_list = json.loads(wf_json)
            except Exception:
                wf_list = [50] * 64
        else:
            n["waveform"] = json.dumps(wf_list)
        n["waveform_list"] = wf_list

    return n

def render_inactive_public_page():
    return render_template(
        "notice_public.html",
        notice=None,
        is_active=False,
        is_admin_preview=False,
        public_base_url=get_public_base_url(),
        og_title="Notice not active — V Notice",
        og_description="This notice is no longer active on the campus notice board.",
        og_image=f"{get_public_base_url()}/static/brand/og-image.png"
    ), 404

def _require_admin_role():
    user = get_current_user()
    if not user or user.get("role") != "admin":
        return None, (jsonify({"error": "Permission denied: admin role required."}), 403)
    return user, None

def _get_invite_base_url():
    base = get_public_base_url()
    if base:
        return base.rstrip("/")
    return request.host_url.rstrip("/")

def register_admin_account_and_invite_routes(app):
    """Phase 2A: Shared account, invite, reset, and self-service routes for admin & unified apps."""

    @app.route("/api/me", methods=["GET"])
    def get_me():
        user = get_current_user()
        if not user:
            return jsonify({"authenticated": False}), 200
        return jsonify({
            "authenticated": True,
            "id": user.get("id"),
            "name": user.get("name") or user.get("username") or "Admin",
            "email": user.get("email") or user.get("username") or "admin",
            "username": user.get("email") or user.get("username") or "admin",
            "role": user["role"],
            "departments": user["departments"],
            "can_post_college_wide": bool(user.get("can_post_college_wide", False)),
            "can_target_all": bool(user.get("can_post_college_wide", False)),
            "can_post_urgent": bool(user.get("can_post_urgent", False)),
        })

    @app.route("/api/me/password", methods=["POST"])
    @mutation_admin_required
    def change_my_password():
        user = get_current_user()
        if not user or not user.get("id"):
            return jsonify({"error": "Bootstrap admin cannot change password via self-service."}), 400
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        current_pw = str(data.get("current_password", "")).strip()
        new_pw = str(data.get("new_password", "")).strip()
        if not current_pw or not new_pw:
            return jsonify({"error": "Current password and new password are required."}), 400
        verified = storage.verify_user_credentials(user["email"], current_pw)
        if not verified:
            return jsonify({"error": "Current password is incorrect."}), 401
        ok, err = validate_password_strength(new_pw)
        if not ok:
            return jsonify({"error": err}), 400
        new_sv = storage.change_user_password(user["id"], new_pw)
        session["session_version"] = new_sv
        storage.record_audit(user["email"], "PASSWORD_CHANGED", str(user["id"]), "User changed password", ip=get_client_ip())
        return jsonify({"success": True})

    @app.route("/api/me/sessions/revoke-all", methods=["POST"])
    @mutation_admin_required
    def revoke_my_sessions():
        user = get_current_user()
        if not user or not user.get("id"):
            return jsonify({"error": "Session revocation is only available for database accounts."}), 400
        new_sv = storage.revoke_user_sessions(user["id"])
        session["session_version"] = new_sv
        storage.record_audit(user["email"], "SESSIONS_REVOKED", str(user["id"]), "Revoked all other sessions", ip=get_client_ip())
        return jsonify({"success": True})

    @app.route("/api/users", methods=["GET"])
    @read_admin_required
    def get_users_list():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        return jsonify({"success": True, "users": storage.list_users()})

    @app.route("/api/users", methods=["POST"])
    @mutation_admin_required
    def create_dept_user():
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        email = str(data.get("email") or data.get("username") or "").strip()
        name = str(data.get("name") or email.split("@")[0] or "").strip()
        password = str(data.get("password", "")).strip()
        role = str(data.get("role", "faculty")).strip()
        departments = data.get("departments", [])
        can_cw = bool(data.get("can_post_college_wide", data.get("can_target_all", False)))
        can_urgent = bool(data.get("can_post_urgent", False))
        phone = data.get("phone")
        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400
        ok, pw_err = validate_password_strength(password)
        if not ok:
            return jsonify({"error": pw_err}), 400
        try:
            created = storage.create_user(
                email=email,
                name=name,
                password=password,
                role=role,
                departments=departments,
                can_post_college_wide=can_cw,
                can_post_urgent=can_urgent,
                phone=phone,
                created_by=actor_user.get("id"),
            )
            created.pop("password_hash", None)
            return jsonify({"success": True, "user": created}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/users/<int:user_id>", methods=["PATCH", "PUT"])
    @mutation_admin_required
    def update_user_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        if actor_user.get("id") == user_id:
            if data.get("status") == "disabled" or ("role" in data and str(data.get("role")).strip().lower() not in ("admin", "super_admin")):
                return jsonify({"error": "You cannot disable or demote your own account."}), 400
        actor = actor_user.get("email") or "admin"
        try:
            updated = storage.update_user(user_id, data, actor=actor, ip=get_client_ip())
            if not updated:
                return jsonify({"error": "User not found"}), 404
            return jsonify({"success": True, "user": updated}), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/users/<int:user_id>/sessions/revoke", methods=["POST"])
    @mutation_admin_required
    def revoke_user_sessions_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        target = storage.get_user_by_id(user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404
        storage.revoke_user_sessions(user_id)
        storage.record_audit(
            actor_user.get("email") or "admin",
            "SESSIONS_REVOKED",
            str(user_id),
            f"Admin revoked all sessions for {target['email']}",
            ip=get_client_ip(),
        )
        return jsonify({"success": True}), 200

    @app.route("/api/users/<int:user_id>/disable", methods=["POST"])
    @mutation_admin_required
    def disable_user_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        if actor_user.get("id") == user_id:
            return jsonify({"error": "Cannot disable your own active admin account."}), 400
        updated = storage.update_user(user_id, {"status": "disabled"}, actor=actor_user.get("email") or "admin", ip=get_client_ip())
        if not updated:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"success": True, "user": updated}), 200

    @app.route("/api/users/<int:user_id>/enable", methods=["POST"])
    @mutation_admin_required
    def enable_user_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        updated = storage.update_user(user_id, {"status": "active"}, actor=actor_user.get("email") or "admin", ip=get_client_ip())
        if not updated:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"success": True, "user": updated}), 200

    @app.route("/api/users/<identifier>", methods=["DELETE"])
    @mutation_admin_required
    def delete_dept_user(identifier):
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        if str(identifier).lower() == "admin":
            return jsonify({"error": "Cannot delete primary admin"}), 400
        deleted = storage.delete_user(identifier)
        if deleted:
            return jsonify({"success": True, "user": identifier})
        return jsonify({"error": "User not found"}), 404

    @app.route("/api/users/invite", methods=["POST"])
    @mutation_admin_required
    def invite_user_route():
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        if not name or not email or "@" not in email:
            return jsonify({"error": "Valid name and email are required."}), 400
        if storage.get_user(email):
            return jsonify({"error": "A user with this email already exists."}), 409
        role = str(data.get("role", "faculty")).strip().lower()
        departments = data.get("departments", [])
        can_cw = bool(data.get("can_post_college_wide", False))
        can_urgent = bool(data.get("can_post_urgent", False))
        phone = data.get("phone")
        try:
            created = storage.create_user(
                email=email,
                name=name,
                role=role,
                departments=departments,
                can_post_college_wide=can_cw,
                can_post_urgent=can_urgent,
                phone=phone,
                status="invited",
                created_by=actor_user.get("id"),
            )
            created.pop("password_hash", None)
            token, inv = storage.create_invite(
                user_id=created["id"],
                purpose="invite",
                expires_hours=getattr(config, "INVITE_EXPIRY_HOURS", 72),
                created_by=actor_user.get("id"),
            )
            storage.record_audit(
                actor_user.get("email") or "admin",
                "USER_INVITED",
                str(created["id"]),
                f"Invited {email} as {created['role']}",
                ip=get_client_ip(),
            )
            return jsonify({
                "success": True,
                "user": created,
                "invite_id": inv["id"],
                "expires_at": inv["expires_at"],
                "invite_url": f"{_get_invite_base_url()}/invite/{token}",
            }), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/users/<int:user_id>/invite", methods=["POST"])
    @mutation_admin_required
    def reissue_invite_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        target = storage.get_user_by_id(user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404
        token, inv = storage.create_invite(
            user_id=user_id,
            purpose="invite",
            expires_hours=getattr(config, "INVITE_EXPIRY_HOURS", 72),
            created_by=actor_user.get("id"),
            revoke_existing=True,
        )
        storage.record_audit(
            actor_user.get("email") or "admin",
            "USER_INVITED",
            str(user_id),
            f"Re-issued invite for {target['email']}",
            ip=get_client_ip(),
        )
        return jsonify({
            "success": True,
            "invite_id": inv["id"],
            "expires_at": inv["expires_at"],
            "invite_url": f"{_get_invite_base_url()}/invite/{token}",
        }), 201

    @app.route("/api/users/<int:user_id>/reset-link", methods=["POST"])
    @mutation_admin_required
    def create_reset_link_route(user_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        target = storage.get_user_by_id(user_id)
        if not target or target.get("status") != "active":
            return jsonify({"error": "Active user not found"}), 404
        token, inv = storage.create_invite(
            user_id=user_id,
            purpose="reset",
            expires_hours=getattr(config, "INVITE_EXPIRY_HOURS", 72),
            created_by=actor_user.get("id"),
            revoke_existing=True,
        )
        storage.record_audit(
            actor_user.get("email") or "admin",
            "RESET_LINK_CREATED",
            str(user_id),
            f"Created password reset link for {target['email']}",
            ip=get_client_ip(),
        )
        return jsonify({
            "success": True,
            "invite_id": inv["id"],
            "expires_at": inv["expires_at"],
            "invite_url": f"{_get_invite_base_url()}/invite/{token}",
        }), 201

    @app.route("/api/invites/<int:invite_id>/revoke", methods=["POST"])
    @mutation_admin_required
    def revoke_invite_route(invite_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        revoked = storage.revoke_invite(invite_id)
        if not revoked:
            return jsonify({"error": "Invite not found or already used/revoked"}), 404
        storage.record_audit(
            actor_user.get("email") or "admin",
            "INVITE_REVOKED",
            str(invite_id),
            f"Revoked invite #{invite_id}",
            ip=get_client_ip(),
        )
        return jsonify({"success": True, "invite_id": invite_id}), 200

    _IMPORT_LOCK = threading.Lock()
    _IMPORT_BATCHES = {}
    _IMPORT_LINKS_CACHE = {}
    _HOURLY_INVITE_COUNTS = {}
    _EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    _CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
    _MAX_IMPORT_BYTES = 1024 * 1024
    _MAX_IMPORT_ROWS = 500

    def _has_csv_injection(val: str) -> bool:
        s = str(val or "").lstrip()
        return bool(s) and s.startswith(_CSV_INJECTION_PREFIXES)

    def _neutralize_csv_cell(val: str) -> str:
        s = str(val or "")
        if s.lstrip().startswith(_CSV_INJECTION_PREFIXES):
            return "'" + s
        return s

    def _prune_import_caches_locked(now_ts: float):
        for k in [k for k, v in _IMPORT_BATCHES.items() if now_ts > v.get("expires_at", 0)]:
            _IMPORT_BATCHES.pop(k, None)
        for k in [k for k, v in _IMPORT_LINKS_CACHE.items() if now_ts > v.get("expires_at", 0)]:
            _IMPORT_LINKS_CACHE.pop(k, None)

    @app.route("/api/users/import/template", methods=["GET"])
    @read_admin_required
    def download_import_template():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["name", "email", "phone", "departments", "role"])
        resp = Response(buf.getvalue(), mimetype="text/csv; charset=utf-8")
        resp.headers["Content-Disposition"] = 'attachment; filename="vnotice_faculty_template.csv"'
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/api/users/import/preview", methods=["POST"])
    @mutation_admin_required
    def preview_bulk_import():
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res

        ip = get_client_ip()
        locked, retry_after = import_rate_limiter.is_locked(ip)
        if locked:
            res = jsonify({"error": "Too many import requests. Try again later.", "retry_after": retry_after})
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res
        import_rate_limiter.record_failure(ip)

        upload = request.files.get("file")
        if not upload or not upload.filename:
            return jsonify({"error": "Please select a .csv file."}), 400
        if not upload.filename.lower().endswith(".csv"):
            return jsonify({"error": "Only .csv files are allowed."}), 400

        raw_bytes = upload.read(_MAX_IMPORT_BYTES + 1)
        if len(raw_bytes) > _MAX_IMPORT_BYTES:
            return jsonify({"error": "CSV file must be 1 MB or smaller."}), 400
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return jsonify({"error": "CSV file must be UTF-8 encoded."}), 400

        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames:
            return jsonify({"error": "CSV file is missing a header row."}), 400

        norm_fields = [str(h or "").strip().lower() for h in reader.fieldnames]
        if "name" not in norm_fields or "email" not in norm_fields:
            return jsonify({"error": "CSV must include 'name' and 'email' columns."}), 400

        raw_rows = list(reader)
        if not raw_rows:
            return jsonify({"error": "CSV file contains no data rows."}), 400
        if len(raw_rows) > _MAX_IMPORT_ROWS:
            return jsonify({"error": f"CSV file exceeds the maximum of {_MAX_IMPORT_ROWS} rows."}), 400

        valid_dept_codes = {
            str(s.get("code", "")).strip().upper()
            for s in (storage.get_screens() or [])
            if s.get("code")
        }

        seen_emails = set()
        preview_rows = []
        ready_rows = []
        skipped_rows = []
        counts = {
            "total": len(raw_rows),
            "ready": 0,
            "skipped": 0,
            "duplicate_email": 0,
            "invalid_email": 0,
            "unknown_department": 0,
            "invalid_role": 0,
            "csv_injection": 0,
        }

        for idx, raw in enumerate(raw_rows, start=1):
            norm_map = {str(k or "").strip().lower(): str(v or "").strip() for k, v in raw.items() if k is not None}
            name = norm_map.get("name", "")
            email = norm_map.get("email", "").lower()
            phone = norm_map.get("phone", "")
            depts_raw = norm_map.get("departments", "")
            role = (norm_map.get("role", "") or "faculty").lower()

            depts = [d.strip().upper() for d in depts_raw.split(";") if d.strip()]

            status = "Ready"
            reason = ""

            if any(_has_csv_injection(v) for v in (name, email, phone, depts_raw, role)):
                status = "CSV injection"
                reason = "Cell starts with a disallowed formula prefix (=, +, -, or @)."
                counts["csv_injection"] += 1
            elif not name:
                status = "Invalid email"
                reason = "Name is required."
                counts["invalid_email"] += 1
            elif not email or not _EMAIL_RE.match(email):
                status = "Invalid email"
                reason = "Invalid email format."
                counts["invalid_email"] += 1
            elif email in seen_emails or storage.get_user(email):
                status = "Duplicate email"
                reason = "Email already exists." if storage.get_user(email) else "Duplicate email in CSV."
                counts["duplicate_email"] += 1
            elif role not in ("faculty", "admin"):
                status = "Invalid role"
                reason = "Role must be faculty or admin."
                counts["invalid_role"] += 1
            else:
                unknown = [d for d in depts if d not in valid_dept_codes]
                if unknown:
                    status = "Unknown department"
                    reason = f"Unknown department(s): {', '.join(unknown)}"
                    counts["unknown_department"] += 1

            seen_emails.add(email)
            row_obj = {
                "row": idx,
                "name": name,
                "email": email,
                "phone": phone,
                "departments": depts,
                "role": role,
                "status": status,
                "reason": reason,
            }
            preview_rows.append(row_obj)
            if status == "Ready":
                counts["ready"] += 1
                ready_rows.append(row_obj)
            else:
                counts["skipped"] += 1
                skipped_rows.append(row_obj)

        batch_id = secrets.token_urlsafe(24)
        now_ts = time.time()
        expires_at_ts = now_ts + 1800
        with _IMPORT_LOCK:
            _prune_import_caches_locked(now_ts)
            _IMPORT_BATCHES[batch_id] = {
                "batch_id": batch_id,
                "actor_id": actor_user.get("id"),
                "created_at": now_ts,
                "expires_at": expires_at_ts,
                "ready_rows": ready_rows,
                "skipped_rows": skipped_rows,
                "counts": counts,
                "committed": False,
                "commit_summary": None,
            }

        return jsonify({
            "batch_id": batch_id,
            "expires_at": int(expires_at_ts * 1000),
            "counts": counts,
            "rows": preview_rows,
        }), 200

    @app.route("/api/users/import/commit", methods=["POST"])
    @mutation_admin_required
    def commit_bulk_import():
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res

        ip = get_client_ip()
        locked, retry_after = import_rate_limiter.is_locked(ip)
        if locked:
            res = jsonify({"error": "Too many import requests. Try again later.", "retry_after": retry_after})
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res
        import_rate_limiter.record_failure(ip)

        data = request.get_json(silent=True) or {}
        batch_id = str(data.get("batch_id", "")).strip()
        if not batch_id:
            return jsonify({"error": "batch_id is required."}), 400

        now_ts = time.time()
        actor_key = str(actor_user.get("id") or "bootstrap")
        hourly_cap = int(getattr(config, "MAX_INVITES_PER_HOUR_PER_ADMIN", 500))

        with _IMPORT_LOCK:
            _prune_import_caches_locked(now_ts)
            batch = _IMPORT_BATCHES.get(batch_id)
            if not batch:
                return jsonify({"error": "Import batch not found or expired."}), 404
            if batch.get("actor_id") != actor_user.get("id"):
                return jsonify({"error": "Forbidden"}), 403
            if batch.get("committed"):
                summary = dict(batch["commit_summary"])
                summary["already_committed"] = True
                summary["links_available"] = batch_id in _IMPORT_LINKS_CACHE
                return jsonify(summary), 200

            ready_rows = batch["ready_rows"]
            if not ready_rows:
                return jsonify({"error": "No valid rows to import."}), 400

            recent = [t for t in _HOURLY_INVITE_COUNTS.get(actor_key, []) if now_ts - t < 3600]
            if len(recent) + len(ready_rows) > hourly_cap:
                return jsonify({"error": f"Hourly invite limit ({hourly_cap}) reached for your account."}), 429

        try:
            created_items = storage.bulk_create_invited_users_with_invites(
                ready_rows,
                created_by=actor_user.get("id"),
                expires_hours=getattr(config, "INVITE_EXPIRY_HOURS", 72),
            )
        except Exception:
            return jsonify({"error": "Import rolled back: one or more accounts could not be created (possible duplicate email)."}), 409

        actor_email = actor_user.get("email") or "admin"
        for item in created_items:
            storage.record_audit(
                actor_email,
                "USER_INVITED",
                str(item["user_id"]),
                f"Invited {item['email']} as {item['role']} (bulk import)",
                ip=ip,
            )
        storage.record_audit(
            actor_email,
            "USERS_IMPORTED",
            batch_id,
            f"Imported {len(created_items)} users, skipped {len(batch['skipped_rows'])}",
            ip=ip,
        )

        base_url = _get_invite_base_url()
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf, lineterminator="\r\n")
        writer.writerow(["name", "email", "link", "expiry"])
        whatsapp_messages = []
        for item in created_items:
            link = f"{base_url}/invite/{item['token']}"
            exp_iso = datetime.datetime.fromtimestamp(item["expires_at"] / 1000, tz=KOLKATA_TZ).strftime("%Y-%m-%d %H:%M %Z")
            writer.writerow([
                _neutralize_csv_cell(item["name"]),
                _neutralize_csv_cell(item["email"]),
                _neutralize_csv_cell(link),
                _neutralize_csv_cell(exp_iso),
            ])
            whatsapp_messages.append(
                f"Hi {item['name']}, your V Notice account is ready. Set your password here: {link} (expires {exp_iso})."
            )

        links_expires_ts = time.time() + 600
        summary = {
            "success": True,
            "batch_id": batch_id,
            "created_count": len(created_items),
            "skipped_count": len(batch["skipped_rows"]),
            "skipped": [
                {"row": r["row"], "email": r["email"], "status": r["status"], "reason": r["reason"]}
                for r in batch["skipped_rows"]
            ],
            "links_expires_at": int(links_expires_ts * 1000),
            "links_available": True,
            "whatsapp_messages": whatsapp_messages,
        }

        with _IMPORT_LOCK:
            recent = [t for t in _HOURLY_INVITE_COUNTS.get(actor_key, []) if now_ts - t < 3600]
            recent.extend([now_ts] * len(created_items))
            _HOURLY_INVITE_COUNTS[actor_key] = recent
            _IMPORT_LINKS_CACHE[batch_id] = {
                "actor_id": actor_user.get("id"),
                "csv_text": csv_buf.getvalue(),
                "expires_at": links_expires_ts,
            }
            batch["committed"] = True
            batch["commit_summary"] = {
                "success": True,
                "batch_id": batch_id,
                "created_count": len(created_items),
                "skipped_count": len(batch["skipped_rows"]),
                "skipped": summary["skipped"],
                "links_expires_at": int(links_expires_ts * 1000),
            }

        return jsonify(summary), 200

    @app.route("/api/users/import/<batch_id>/links.csv", methods=["GET"])
    @read_admin_required
    def download_import_links_once(batch_id):
        actor_user, err_res = _require_admin_role()
        if err_res:
            return err_res
        now_ts = time.time()
        with _IMPORT_LOCK:
            entry = _IMPORT_LINKS_CACHE.get(batch_id)
            if not entry or now_ts > entry.get("expires_at", 0):
                _IMPORT_LINKS_CACHE.pop(batch_id, None)
                return jsonify({"error": "This one-time links file has expired or was already downloaded."}), 410
            if entry.get("actor_id") != actor_user.get("id"):
                return jsonify({"error": "Forbidden"}), 403
            _IMPORT_LINKS_CACHE.pop(batch_id, None)

        resp = Response(entry["csv_text"], mimetype="text/csv; charset=utf-8")
        resp.headers["Content-Disposition"] = 'attachment; filename="vnotice_invite_links.csv"'
        return _apply_no_leak_headers(resp)

    _GENERIC_INVITE_ERR = "This link is not valid. Ask your admin for a new one."

    def _apply_no_leak_headers(resp):
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.route("/invite/<token>", methods=["GET"])
    def view_invite_page(token):
        ip = get_client_ip()
        locked, retry_after = invite_rate_limiter.is_locked(ip)
        if locked:
            res = Response("Too many requests. Please try again later.", status=429)
            res.headers["Retry-After"] = str(retry_after)
            return _apply_no_leak_headers(res)

        inv = storage.get_invite_by_token(token)
        now_ms = int(time.time() * 1000)
        is_valid = bool(
            inv
            and inv.get("used_at") is None
            and inv.get("revoked_at") is None
            and inv.get("expires_at", 0) > now_ms
            and inv.get("user")
            and inv["user"].get("status") != "disabled"
        )
        if not is_valid:
            invite_rate_limiter.record_failure(ip)
            resp = make_response(render_template("invite_accept.html", valid=False, error_message=_GENERIC_INVITE_ERR), 400)
            return _apply_no_leak_headers(resp)

        csrf = session.get("csrf_token") or generate_csrf_token()
        session["csrf_token"] = csrf
        resp = make_response(render_template(
            "invite_accept.html",
            valid=True,
            token=token,
            user=inv["user"],
            purpose=inv.get("purpose", "invite"),
            csrf_token=csrf,
            error_message=None,
        ))
        return _apply_no_leak_headers(resp)

    @app.route("/invite/<token>/accept", methods=["POST"])
    def accept_invite_page(token):
        ip = get_client_ip()
        locked, retry_after = invite_rate_limiter.is_locked(ip)
        if locked:
            res = jsonify({"error": "Too many requests. Please try again later.", "retry_after": retry_after})
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return _apply_no_leak_headers(res)

        is_json = request.is_json
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        csrf_token = request.headers.get("X-CSRF-Token") or data.get("csrf_token")
        if not is_json and not validate_csrf_token(session.get("csrf_token"), csrf_token):
            resp = make_response(render_template("invite_accept.html", valid=False, error_message=_GENERIC_INVITE_ERR), 403)
            return _apply_no_leak_headers(resp)

        pw = str(data.get("password", ""))
        pw2 = str(data.get("confirm_password", pw if is_json and "confirm_password" not in data else ""))
        inv_preview = storage.get_invite_by_token(token)
        now_ms = int(time.time() * 1000)
        pre_valid = bool(
            inv_preview
            and inv_preview.get("used_at") is None
            and inv_preview.get("revoked_at") is None
            and inv_preview.get("expires_at", 0) > now_ms
            and inv_preview.get("user")
            and inv_preview["user"].get("status") != "disabled"
        )
        if not pre_valid:
            invite_rate_limiter.record_failure(ip)
            if is_json:
                return _apply_no_leak_headers(make_response(jsonify({"error": _GENERIC_INVITE_ERR}), 400))
            resp = make_response(render_template("invite_accept.html", valid=False, error_message=_GENERIC_INVITE_ERR), 400)
            return _apply_no_leak_headers(resp)

        if pw != pw2:
            err_msg = "Passwords do not match."
            if is_json:
                return _apply_no_leak_headers(make_response(jsonify({"error": err_msg}), 400))
            resp = make_response(render_template(
                "invite_accept.html",
                valid=True,
                token=token,
                user=inv_preview["user"],
                purpose=inv_preview.get("purpose", "invite"),
                csrf_token=session.get("csrf_token"),
                error_message=err_msg,
            ), 400)
            return _apply_no_leak_headers(resp)

        ok, pw_err = validate_password_strength(pw)
        if not ok:
            if is_json:
                return _apply_no_leak_headers(make_response(jsonify({"error": pw_err}), 400))
            resp = make_response(render_template(
                "invite_accept.html",
                valid=True,
                token=token,
                user=inv_preview["user"],
                purpose=inv_preview.get("purpose", "invite"),
                csrf_token=session.get("csrf_token"),
                error_message=pw_err,
            ), 400)
            return _apply_no_leak_headers(resp)

        accepted = storage.accept_invite_atomic(token, pw)
        if not accepted or not accepted.get("user"):
            invite_rate_limiter.record_failure(ip)
            if is_json:
                return _apply_no_leak_headers(make_response(jsonify({"error": _GENERIC_INVITE_ERR}), 400))
            resp = make_response(render_template("invite_accept.html", valid=False, error_message=_GENERIC_INVITE_ERR), 400)
            return _apply_no_leak_headers(resp)

        invite_rate_limiter.record_success(ip)
        user = accepted["user"]
        csrf_new = _issue_user_session(user, is_bootstrap=False)
        storage.record_audit(
            user["email"],
            "INVITE_ACCEPTED",
            str(user["id"]),
            f"Accepted {accepted['purpose']} for {user['email']}",
            ip=ip,
        )
        if is_json:
            return _apply_no_leak_headers(make_response(jsonify({"success": True, "user": user, "csrf_token": csrf_new}), 200))
        return _apply_no_leak_headers(redirect("/admin"))

def register_public_notice_routes(app):
    @app.route("/n/<notice_id>", methods=["GET"])
    def public_notice_view(notice_id):
        if not check_public_rate_limit(get_client_ip()):
            return Response("Too Many Requests", status=429, headers={"Retry-After": "60"})

        notice = storage.get_by_id(notice_id)
        if not notice or notice.get("deleted") == 1 or notice.get("is_active") == 0:
            return render_inactive_public_page()

        is_live = (notice.get("status") == "live")
        is_admin = check_admin_auth()
        if not is_live and not is_admin:
            return render_inactive_public_page()

        if is_live and not is_admin:
            storage.increment_scan_count(notice_id)

        enriched = format_notice_for_display(notice)
        body_text = str(enriched.get("body") or "").strip()
        og_desc = body_text[:120] if body_text else f"{enriched['display_dept']} notice on V Notice"

        if enriched.get("media") and enriched.get("type") in ("image", "video"):
            if str(enriched["media"]).startswith("http"):
                og_img = enriched["media"]
            else:
                og_img = f"{get_public_base_url()}/media/{enriched['media']}"
        else:
            og_img = f"{get_public_base_url()}/n/{notice_id}/og-image"

        return render_template(
            "notice_public.html",
            notice=enriched,
            is_active=True,
            is_admin_preview=is_admin and not is_live,
            public_base_url=get_public_base_url(),
            og_title=f"{enriched.get('title') or 'Notice'} — V Notice",
            og_description=og_desc,
            og_image=og_img
        ), 200

    @app.route("/n/<notice_id>/file", methods=["GET"])
    def public_notice_file(notice_id):
        if not check_public_rate_limit(get_client_ip()):
            return Response("Too Many Requests", status=429, headers={"Retry-After": "60"})

        notice = storage.get_by_id(notice_id)
        if not notice or notice.get("deleted") == 1 or notice.get("is_active") == 0:
            return render_inactive_public_page()

        is_live = (notice.get("status") == "live")
        is_admin = check_admin_auth()
        if not is_live and not is_admin:
            return render_inactive_public_page()

        notice_type = str(notice.get("type") or "text").lower()
        media_val = str(notice.get("media") or "").strip()

        # 1. Media Notice (image / video / voice): Must NEVER fall back to .txt
        if notice_type in ("image", "video", "voice"):
            if not media_val:
                resp = jsonify({"error": "Media file not found for this notice."})
                resp.status_code = 404
                resp.headers["Cache-Control"] = "private, no-store"
                return resp

            # Case A: Remote / Cloudinary URL
            if media_val.startswith("http://") or media_val.startswith("https://"):
                parsed_url = urllib.parse.urlparse(media_val)
                raw_ext = Path(parsed_url.path).suffix.lstrip(".").lower()
                if notice_type == "voice":
                    ext = raw_ext if raw_ext in ("mp3", "m4a", "wav", "webm", "ogg") else "mp3"
                elif notice_type == "video":
                    ext = raw_ext if raw_ext in ("mp4", "webm") else "mp4"
                else:
                    ext = raw_ext if raw_ext in ("jpg", "jpeg", "png", "webp", "gif") else "jpg"
                slug = generate_download_slug(notice, ext=ext)

                range_header = request.headers.get("Range")
                remote_headers = {"User-Agent": "VNotice/1.0"}
                if range_header:
                    remote_headers["Range"] = range_header

                remote_req = urllib.request.Request(media_val, headers=remote_headers)
                try:
                    remote_res = urllib.request.urlopen(remote_req, timeout=10)
                except Exception:
                    # For Cloudinary, redirect to fl_attachment URL
                    if "res.cloudinary.com" in media_val and "/upload/" in media_val:
                        att_slug = Path(slug).stem
                        att_url = media_val.replace("/upload/", f"/upload/fl_attachment:{att_slug}/", 1)
                        return redirect(att_url)
                    resp = jsonify({"error": "Remote media unavailable."})
                    resp.status_code = 502
                    resp.headers["Cache-Control"] = "private, no-store"
                    return resp

                def stream_remote():
                    try:
                        while True:
                            chunk = remote_res.read(65536)
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        remote_res.close()

                if notice_type == "voice":
                    if ext == "mp3":
                        mime = "audio/mpeg"
                    elif ext in ("wav", "ogg", "webm"):
                        mime = f"audio/{ext}"
                    elif ext in ("m4a", "mp4"):
                        mime = "audio/mp4"
                    else:
                        mime = f"audio/{ext}"
                elif notice_type == "video":
                    mime = "video/mp4" if ext != "webm" else "video/webm"
                else:
                    mime = remote_res.headers.get("Content-Type")
                    if not mime or mime == "application/octet-stream":
                        mime, _ = mimetypes.guess_type(slug)
                    if not mime:
                        mime = "image/jpeg"

                status_code = getattr(remote_res, "status", 200)
                resp = Response(stream_with_context(stream_remote()), status=status_code, mimetype=mime)
                resp.headers["Content-Disposition"] = f'attachment; filename="{slug}"'
                resp.headers["Cache-Control"] = "private, no-store"
                resp.headers["X-Content-Type-Options"] = "nosniff"
                resp.headers["Accept-Ranges"] = "bytes"
                if remote_res.headers.get("Content-Length"):
                    resp.headers["Content-Length"] = remote_res.headers.get("Content-Length")
                if remote_res.headers.get("Content-Range"):
                    resp.headers["Content-Range"] = remote_res.headers.get("Content-Range")
                return resp

            # Case B: Local Media
            media_path = None
            if hasattr(storage.media_storage, "get_path"):
                try:
                    media_path = storage.media_storage.get_path(media_val)
                except Exception:
                    media_path = None
            if not media_path or not Path(media_path).is_file():
                candidate = Path(MEDIA_FOLDER) / media_val
                if candidate.is_file():
                    media_path = candidate

            if not media_path or not Path(media_path).is_file():
                resp = jsonify({"error": "Media file not found on server."})
                resp.status_code = 404
                resp.headers["Cache-Control"] = "private, no-store"
                return resp

            media_path = Path(media_path)

            ext = media_path.suffix.lstrip(".").lower()
            slug = generate_download_slug(notice, ext=ext)
            if notice_type == "voice":
                if ext == "mp3":
                    mime = "audio/mpeg"
                elif ext in ("wav", "ogg", "webm"):
                    mime = f"audio/{ext}"
                elif ext in ("m4a", "mp4"):
                    mime = "audio/mp4"
                else:
                    mime = f"audio/{ext}"
            elif notice_type == "video":
                mime = "video/mp4" if ext != "webm" else "video/webm"
            else:
                mime, _ = mimetypes.guess_type(str(media_path))
                if not mime:
                    mime = "image/jpeg"

            file_size = media_path.stat().st_size
            resp = send_file(
                str(media_path),
                mimetype=mime,
                as_attachment=True,
                download_name=slug,
                conditional=True
            )
            resp.headers["Content-Length"] = str(file_size)
            resp.headers["Cache-Control"] = "private, no-store"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

        # 2. Text Notice (.txt announcement ONLY)
        slug = generate_download_slug(notice, ext="txt")
        title = notice.get("title", "Notice")
        dept_str = "College-wide" if str(notice.get("screen_id", "ALL")).strip().upper() == "ALL" else str(notice.get("screen_id", "ALL")).strip().upper()
        lines = [
            "====================================================",
            "  V NOTICE -- OFFICIAL CAMPUS ANNOUNCEMENT",
            "====================================================",
            "",
            f"TITLE:      {title}",
            f"DEPARTMENT: {dept_str}",
            f"PRIORITY:   {str(notice.get('priority', 'Normal')).upper()}",
            "",
            "DETAILS:",
            notice.get("body", "No additional details provided."),
            "",
            "====================================================",
            "Saved from V Notice Smart Display",
        ]
        content = "\n".join(lines).encode("utf-8")
        resp = Response(content, mimetype="text/plain; charset=utf-8")
        resp.headers["Content-Disposition"] = f'attachment; filename="{slug}"'
        resp.headers["Content-Length"] = str(len(content))
        resp.headers["Cache-Control"] = "private, no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/n/<notice_id>/og-image", methods=["GET"])
    def public_notice_og_image(notice_id):
        notice = storage.get_by_id(notice_id)
        if not notice or notice.get("status") != "live" or notice.get("deleted") == 1 or notice.get("is_active") == 0:
            return send_from_directory("static/brand", "og-image.png")

        if notice.get("media") and notice.get("type") == "image":
            m_filename = str(notice["media"])
            if m_filename.startswith("http://") or m_filename.startswith("https://"):
                return redirect(m_filename, code=302)
            media_path = Path(MEDIA_FOLDER) / m_filename
            if media_path.exists():
                return send_from_directory(MEDIA_FOLDER, m_filename)

        cache_file = Path(MEDIA_FOLDER) / f"og_text_{notice_id}.png"
        if cache_file.exists():
            resp = send_file(str(cache_file), mimetype="image/png")
            resp.headers["Cache-Control"] = "public, max-age=3600"
            return resp

        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (1200, 630), color="#131210")
            draw = ImageDraw.Draw(img)
            draw.rectangle([(24, 24), (1176, 606)], outline="#26241F", width=2)

            logo_path = Path("static/brand/mark-180.png")
            if logo_path.exists():
                try:
                    mark = Image.open(logo_path).convert("RGBA")
                    mark = mark.resize((64, 64), Image.Resampling.LANCZOS)
                    img.paste(mark, (64, 64), mark)
                except Exception:
                    pass

            dept = str(notice.get("screen_id") or "ALL").upper()
            draw.text((144, 76), "V NOTICE", fill="#EEEBDA")
            draw.text((144, 100), f"OFFICIAL CAMPUS ANNOUNCEMENT · {dept}", fill="#FBBF24")

            title = str(notice.get("title") or "Notice").strip()
            words = title.split()
            lines = []
            curr_line = []
            for w in words:
                curr_line.append(w)
                if len(" ".join(curr_line)) > 32:
                    lines.append(" ".join(curr_line))
                    curr_line = []
            if curr_line:
                lines.append(" ".join(curr_line))

            y = 200
            for line in lines[:3]:
                draw.text((64, y), line, fill="#EEEBDA")
                y += 50

            body = str(notice.get("body") or "").strip()
            if body:
                body_snippet = body[:180] + ("..." if len(body) > 180 else "")
                b_words = body_snippet.split()
                b_lines = []
                c_b = []
                for w in b_words:
                    c_b.append(w)
                    if len(" ".join(c_b)) > 55:
                        b_lines.append(" ".join(c_b))
                        c_b = []
                if c_b:
                    b_lines.append(" ".join(c_b))
                y += 20
                for line in b_lines[:3]:
                    draw.text((64, y), line, fill="#A9ABC4")
                    y += 36

            img.save(str(cache_file), format="PNG")
            resp = send_file(str(cache_file), mimetype="image/png")
            resp.headers["Cache-Control"] = "public, max-age=3600"
            return resp
        except Exception as e:
            return send_from_directory("static/brand", "og-image.png")

    @app.route("/notice/<notice_id>", methods=["GET"])
    def legacy_notice_redirect(notice_id):
        return redirect(f"/n/{notice_id}", code=301)

    @app.route("/notice/<notice_id>/download", methods=["GET"])
    def legacy_notice_download_redirect(notice_id):
        return redirect(f"/n/{notice_id}/file", code=301)

    @app.route("/n/<notice_id>/audio", methods=["GET", "HEAD"])
    def public_notice_audio(notice_id):
        if not check_public_rate_limit(get_client_ip()):
            return Response("Too Many Requests", status=429, headers={"Retry-After": "60"})

        notice = storage.get_by_id(notice_id)
        if not notice or notice.get("deleted") == 1 or notice.get("is_active") == 0:
            return Response("Not found", status=404)

        media_val = str(notice.get("media") or "").strip()
        if not media_val:
            return Response("Audio media not found", status=404)

        parsed_url = urllib.parse.urlparse(media_val)
        raw_ext = Path(parsed_url.path if media_val.startswith("http") else media_val).suffix.lstrip(".").lower()
        if raw_ext == "mp3":
            mime = "audio/mpeg"
        elif raw_ext in ("wav", "ogg", "webm"):
            mime = f"audio/{raw_ext}"
        elif raw_ext in ("m4a", "mp4"):
            mime = "audio/mp4"
        else:
            mime = "audio/webm"

        # Case A: Remote / Cloudinary URL
        if media_val.startswith("http://") or media_val.startswith("https://"):
            range_header = request.headers.get("Range")
            remote_headers = {"User-Agent": "VNotice/1.0"}
            if range_header:
                remote_headers["Range"] = range_header

            req = urllib.request.Request(media_val, headers=remote_headers)
            try:
                remote_res = urllib.request.urlopen(req, timeout=12)
            except Exception as e:
                logger.warning("Failed streaming remote audio for notice %s: %s", notice_id, e)
                return Response("Remote audio unavailable", status=502)

            def stream_remote():
                try:
                    while True:
                        chunk = remote_res.read(65536)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    remote_res.close()

            status_code = getattr(remote_res, "status", 200)
            resp = Response(stream_with_context(stream_remote()), status=status_code, mimetype=mime)
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Cache-Control"] = "public, max-age=86400"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            if remote_res.headers.get("Content-Length"):
                resp.headers["Content-Length"] = remote_res.headers.get("Content-Length")
            if remote_res.headers.get("Content-Range"):
                resp.headers["Content-Range"] = remote_res.headers.get("Content-Range")
            return resp

        # Case B: Local Media
        media_path = None
        if hasattr(storage.media_storage, "get_path"):
            try:
                media_path = storage.media_storage.get_path(media_val)
            except Exception:
                media_path = None
        if not media_path or not Path(media_path).is_file():
            candidate = Path(MEDIA_FOLDER) / media_val
            if candidate.is_file():
                media_path = candidate

        if not media_path or not Path(media_path).is_file():
            return Response("Local audio file not found", status=404)

        resp = send_file(str(media_path), mimetype=mime, conditional=True)
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Cache-Control"] = "public, max-age=86400"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.route("/media/thumb/w1200/<path:filename>", methods=["GET", "HEAD"])
    def public_media_thumb(filename):
        return serve_media_thumb_w1200(filename)

def serve_media_thumb_w1200(filename):
    if filename.startswith("http://") or filename.startswith("https://"):
        return redirect(filename)

    folder = getattr(storage, "media_folder", None) or Path(config.MEDIA_FOLDER)
    file_path = Path(folder) / filename
    if not file_path.is_file():
        file_path = Path(config.MEDIA_FOLDER) / filename

    if not file_path.is_file():
        return jsonify({"error": "Media file not found"}), 404

    ext = file_path.suffix.lstrip(".").lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        return serve_media_response(filename)

    cache_dir = Path(config.STORAGE_DIR) / ".cache" / "w1200"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    thumb_path = cache_dir / f"thumb_{safe_name}"

    if thumb_path.is_file() and thumb_path.stat().st_mtime >= file_path.stat().st_mtime:
        mimetype = "image/png" if ext == "png" else "image/jpeg"
        resp = send_file(str(thumb_path), mimetype=mimetype, conditional=True)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    try:
        from PIL import Image, ImageOps
        with Image.open(file_path) as im:
            im = ImageOps.exif_transpose(im)
            orig_w, orig_h = im.size
            if orig_w > 1200:
                new_h = int(round((orig_h * 1200) / orig_w))
                im = im.resize((1200, new_h), Image.Resampling.LANCZOS)
            
            save_format = "PNG" if ext == "png" else "JPEG"
            if save_format == "JPEG" and im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            im.save(str(thumb_path), format=save_format, quality=85, optimize=True)

        mimetype = "image/png" if ext == "png" else "image/jpeg"
        resp = send_file(str(thumb_path), mimetype=mimetype, conditional=True)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp
    except Exception as e:
        logger.warning("Thumbnail generation failed for %s: %s", filename, e)
        return serve_media_response(filename)

def serve_media_response(filename):
    if filename.startswith("http://") or filename.startswith("https://"):
        return redirect(filename)

    if request.args.get("w") == "1200":
        return serve_media_thumb_w1200(filename)

    folder = getattr(storage, "media_folder", None) or Path(config.MEDIA_FOLDER)
    file_path = Path(folder) / filename
    if not file_path.is_file():
        file_path = Path(config.MEDIA_FOLDER) / filename
        folder = config.MEDIA_FOLDER

    if not file_path.is_file():
        return jsonify({"error": "Media file not found"}), 404

    ext = file_path.suffix.lstrip(".").lower()
    is_voice = storage.is_voice_media(filename)
    if is_voice or ext in ("mp3", "wav", "ogg", "m4a"):
        if ext == "mp3":
            mimetype = "audio/mpeg"
        elif ext in ("wav", "ogg", "webm"):
            mimetype = f"audio/{ext}"
        elif ext in ("m4a", "mp4"):
            mimetype = "audio/mp4"
        else:
            mimetype = f"audio/{ext}"
    else:
        mimetype, _ = mimetypes.guess_type(str(file_path))

    response = send_from_directory(str(folder), filename, mimetype=mimetype, conditional=True)
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

# ==============================================================================
# DISPLAY APP (Port 5000)
# ==============================================================================
def create_display_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    configure_app_security(app)
    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            "sw.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/manifest.json")
    @app.route("/manifest.webmanifest")
    def manifest():
        filename = "manifest.webmanifest" if request.path.endswith(".webmanifest") else "manifest.json"
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            filename,
            mimetype="application/manifest+json",
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


    @app.teardown_appcontext
    def teardown_db(exception=None):
        storage.close_connection()

    @app.route("/")
    @app.route("/display")
    def index():
        screen = request.args.get("screen") or request.args.get("screen_id")
        if screen:
            target = screen.strip().upper()
            if target == "DEFAULT":
                target = "ALL"
            return redirect(f"/display/{target}", code=301)
        dept = storage.get_department("ALL")
        return render_template("display.html", screen_code="ALL", department=dept)

    @app.route("/display/<code>")
    def display_screen(code):
        if not code:
            return redirect("/display", code=301)
        upper_code = code.strip().upper()
        if code != upper_code:
            qs = request.query_string.decode("utf-8")
            url = f"/display/{upper_code}" + (f"?{qs}" if qs else "")
            return redirect(url, code=301)
        dept = storage.get_department(upper_code)
        if not dept or not dept.get("active"):
            active_depts = storage.get_departments(active_only=True)
            return render_template("screen_not_found.html", code=upper_code, departments=active_depts), 404
        return render_template("display.html", screen_code=upper_code, department=dept)

    @app.route("/<code>")
    def display_shortcut(code):
        if not code:
            return redirect("/display", code=301)
        if code.lower() in ("static", "api", "sw.js", "favicon.ico", "media", "display"):
            return "Not Found", 404
        canonical = code.strip().upper()
        dept = storage.get_department(canonical)
        if dept:
            return redirect(f"/display/{canonical}", code=301)
        return "Not Found", 404

    @app.route("/api/heartbeat", methods=["POST"])
    def display_heartbeat():
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = data.get("screen") or data.get("screen_id") or data.get("code") or "ALL"
        audio_ready = data.get("audio_ready")
        record_heartbeat(code, audio_ready)
        return jsonify({"success": True, "code": str(code).strip().upper(), "timestamp": int(time.time() * 1000)})

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.route("/admin")
    def to_admin():
        host = request.host.split(":")[0]
        return redirect(f"http://{host}:{ADMIN_PORT}/")

    @app.route("/api/notices", methods=["GET"])
    def get_active_notices():
        screen = request.args.get("screen") or request.args.get("screen_id")
        active = storage.get_active(screen_id=screen)
        data = [sanitize_public_notice(n) for n in active]
        return make_etag_response(data)

    @app.route("/api/events")
    def sse_events():
        import config
        if not getattr(config, "SSE_ENABLED", False):
            return jsonify({"error": "SSE is disabled; use conditional polling with ETag"}), 404
        screen = request.args.get("screen") or request.args.get("screen_id")
        return Response(
            sse_event_stream(screen),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        depts = storage.get_departments(active_only=True)
        screens = [{
            "code": d["code"],
            "name": d["name"],
            "id": d["code"],
            "accent_color": d.get("accent_color"),
            "sound_enabled": d.get("sound_enabled", False),
            "sound_volume": d.get("sound_volume", 70)
        } for d in depts]
        return jsonify({"success": True, "screens": screens})

    @app.route("/api/events/today", methods=["GET"])
    def get_events_today():
        screen = request.args.get("screen") or request.args.get("screen_id") or "ALL"
        sim_header = request.headers.get("X-Simulated-Now") or request.args.get("sim_now")
        now_dt = None
        if sim_header:
            try:
                now_dt = datetime.datetime.fromtimestamp(float(sim_header) / 1000.0, tz=KOLKATA_TZ)
            except Exception:
                pass
        data = storage.get_flag_event_today(screen_code=screen, now_dt=now_dt)
        return make_flag_event_response(data)

    @app.route("/api/events/flag/start", methods=["POST"])
    def flag_trigger_start():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        screens = data.get("screens", "ALL")
        duration = data.get("duration_seconds", 60)
        try:
            duration = max(5, min(86400, int(duration)))
        except Exception:
            duration = 60
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=False)
        storage.record_daily_event_run("flag", result=f"Triggered via external API for {duration}s on {screens}", actor="external_api", ip=get_client_ip())
        notify_flag_change(screens)
        res = jsonify({"success": True, "action": "flag_started", "duration_seconds": duration, "screens": screens})
        res.headers["Cache-Control"] = "no-store"
        return res

    @app.route("/api/events/flag/end", methods=["POST"])
    def flag_trigger_end():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        storage.clear_flag_manual_override(ended_early=True)
        storage.record_daily_event_run("flag", result="Ended via external API", actor="external_api", ip=get_client_ip())
        notify_flag_change("ALL")
        res = jsonify({"success": True, "action": "flag_ended"})
        res.headers["Cache-Control"] = "no-store"
        return res

    

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    register_public_notice_routes(app)

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        return serve_media_response(filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/api/health/details")
    @read_admin_required
    def health_details():
        data, code = get_health_payload("vnotice-display")
        return jsonify(data), code

    return app

# ==============================================================================
# ADMIN APP (Port 5001)
# ==============================================================================
def create_admin_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    configure_app_security(app)
    register_public_notice_routes(app)

    @app.teardown_appcontext
    def teardown_db(exception=None):
        storage.close_connection()

    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            "sw.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/admin-sw.js")
    def admin_service_worker():
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            "admin-sw.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/manifest.json")
    @app.route("/manifest.webmanifest")
    def manifest():
        filename = "manifest.webmanifest" if request.path.endswith(".webmanifest") else "manifest.json"
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            filename,
            mimetype="application/manifest+json",
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/")
    @app.route("/admin")
    def index():
        return render_template(
            "admin.html",
            version=getattr(config, "VERSION", "2.2.0"),
            is_cloud=getattr(storage.media_storage, "is_cloud", False),
            voice_notices_enabled=getattr(config, "VOICE_NOTICES_ENABLED", False),
            max_voice_duration=getattr(config, "MAX_VOICE_DURATION_SECONDS", 120),
            max_voice_upload_mb=getattr(config, "MAX_VOICE_UPLOAD_MB", 10),
        )

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.route("/display")
    @app.route("/display/<code>")
    def to_display(code=None):
        host = request.host.split(":")[0]
        sub = f"/{code}" if code else ""
        return redirect(f"http://{host}:{DISPLAY_PORT}/display{sub}")

    @app.route("/api/heartbeat", methods=["POST"])
    def admin_heartbeat():
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = data.get("screen") or data.get("screen_id") or data.get("code") or "ALL"
        audio_ready = data.get("audio_ready")
        record_heartbeat(code, audio_ready)
        return jsonify({"success": True, "code": str(code).strip().upper(), "timestamp": int(time.time() * 1000)})

    @app.route("/api/csrf-token", methods=["GET"])
    def get_csrf():
        token = session.get("csrf_token")
        if not token:
            token = generate_csrf_token()
            session["csrf_token"] = token
        return jsonify({"csrf_token": token})

    @app.route("/api/login", methods=["POST"])
    def login():
        return _handle_login()

    @app.route("/api/logout", methods=["POST"])
    def logout():
        return _handle_logout()

    # Test-only rate limit reset: strictly disabled in production & Render environments
    if os.environ.get("VNOTICE_TEST_MODE") == "1" and not os.environ.get("RENDER"):
        @app.route("/api/test-reset-rate-limit", methods=["POST"])
        def test_reset_rate_limit():
            ip = get_client_ip()
            login_rate_limiter.record_success(ip)
            login_rate_limiter.record_success("127.0.0.1")
            login_rate_limiter.record_success("::1")
            account_rate_limiter.record_success("admin")
            return jsonify({"success": True})

    @app.route("/api/screens", methods=["GET"])
    @read_admin_required
    def get_screens():
        depts = storage.get_departments(active_only=False)
        now_ms = int(time.time() * 1000)
        for d in depts:
            ls = get_screen_last_seen(d["code"])
            d["last_seen"] = ls
            d["online"] = (ls is not None) and ((now_ms - ls) < 60000)
            d["audio_ready"] = get_screen_audio_ready(d["code"])
        return jsonify({"success": True, "screens": depts})

    @app.route("/api/screens", methods=["POST"])
    @mutation_admin_required
    def create_screen():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = data.get("code")
        name = data.get("name")
        sort_order = data.get("sort_order", 0)
        active = data.get("active", True)
        if isinstance(active, str):
            active = active.lower() in ("true", "1", "yes")
        accent_color = data.get("accent_color")

        if not code or not isinstance(code, str):
            return jsonify({"error": "Screen code is required"}), 400
        code = code.strip()
        if not SCREEN_CODE_REGEX.match(code):
            return jsonify({"error": "Screen code must be 2-10 uppercase alphanumeric characters, underscores, or hyphens (lowercase, spaces, and symbols are rejected)"}), 400

        if not name or not str(name).strip():
            return jsonify({"error": "Screen name is required"}), 400

        try:
            created = storage.add_department(code=code, name=name, sort_order=sort_order, active=active, accent_color=accent_color)
            return jsonify({"success": True, "screen": created}), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/screens/<code>", methods=["PUT", "POST"])
    @mutation_admin_required
    def update_screen(code):
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = str(code).strip().upper()
        dept = storage.get_department(code)
        if not dept:
            return jsonify({"error": f"Screen '{code}' not found"}), 404

        try:
            updated = storage.update_department(code, data)
            return jsonify({"success": True, "screen": updated}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/screens/<code>", methods=["DELETE"])
    @mutation_admin_required
    def delete_screen(code):
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        code = str(code).strip().upper()
        if code == "ALL":
            return jsonify({"error": "The college-wide 'ALL' screen cannot be deleted"}), 400

        dept = storage.get_department(code)
        if not dept:
            return jsonify({"error": f"Screen '{code}' not found"}), 404

        try:
            res = storage.delete_department(code)
            return jsonify(res), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/notices", methods=["GET"])
    @read_admin_required
    def get_all_notices():
        screen = request.args.get("screen") or request.args.get("screen_id")
        notices = _filter_notices_for_user(get_current_user(), storage.get_all(screen_id=screen))
        return make_etag_response(notices)

    @app.route("/api/audit-logs", methods=["GET"])
    @read_admin_required
    def get_audit():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        action = request.args.get("action")
        actor = request.args.get("actor")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        if date_from:
            try: date_from = int(date_from)
            except (ValueError, TypeError): date_from = None
        if date_to:
            try: date_to = int(date_to)
            except (ValueError, TypeError): date_to = None

        res = storage.get_audit_logs(
            limit=limit,
            offset=offset,
            action=action,
            actor=actor,
            date_from=date_from,
            date_to=date_to
        )
        return jsonify({
            "success": True,
            "audit_logs": res["audit_logs"],
            "logs": res["logs"],
            "total": res["total"],
            "limit": limit,
            "offset": offset
        })

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": f"File exceeds the maximum upload limit."}), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"error": "An internal server error occurred. Please try again."}), 500

    @app.route("/api/notices", methods=["POST"])
    @mutation_admin_required
    def create_notice():
        form_data = request.form.to_dict()
        file_obj = request.files.get("media_file")
        if not form_data and request.is_json:
            form_data = request.get_json()

        raw_input = request.form.getlist("screens[]") or request.form.getlist("screens") or form_data.get("screens") or form_data.get("screen_id")
        screens = sanitize_screen_codes(raw_input)
        form_data["screens"] = screens
        form_data["screen_id"] = screens[0] if screens else "ALL"

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        user = get_current_user()
        target_candidates = screens or [form_data.get("screen_id") or "ALL"]
        ok, err = check_notice_permissions(user, target_candidates, priority=form_data.get("priority", "normal"), is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        try:
            creator_id = user.get("id") if user else None
            creator_name = (user.get("name") or user.get("email") or "Admin") if user else (form_data.get("created_by") or "Admin")
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator_id, created_by_name=creator_name)
            notify_notice_change(affected_screens=notice.get("screens"))
            return jsonify(notice), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to publish notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["PUT", "POST"])
    @mutation_admin_required
    def update_notice(notice_id):
        form_data = request.form.to_dict()
        file_obj = request.files.get("media_file")
        if not form_data and request.is_json:
            form_data = request.get_json()

        raw_input = request.form.getlist("screens[]") or request.form.getlist("screens") or form_data.get("screens") or form_data.get("screen_id")
        screens = sanitize_screen_codes(raw_input)
        form_data["screens"] = screens
        form_data["screen_id"] = screens[0] if screens else "ALL"

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        user = get_current_user()
        existing = storage.get_by_id(notice_id)
        if not existing:
            return jsonify({"error": "Notice not found"}), 404

        existing_screens = existing.get("screens") or [existing.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, existing_screens, priority=existing.get("priority", "normal"), existing_notice=existing, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        new_targets = screens or existing_screens
        new_priority = form_data.get("priority", existing.get("priority", "normal"))
        ok_new, err_new = check_notice_permissions(user, new_targets, priority=new_priority, existing_notice=existing, is_mutation=True)
        if not ok_new:
            return jsonify({"error": err_new}), 403

        try:
            updater = (user.get("username") if user else None) or form_data.get("created_by") or "admin"
            updated = storage.update(notice_id, form_data, file_obj=file_obj, updated_by=updater)
            if not updated:
                return jsonify({"error": "Notice not found"}), 404
            notify_notice_change(affected_screens=updated.get("screens"))
            return jsonify(updated), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to update notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @mutation_admin_required
    def delete_notice(notice_id):
        user = get_current_user()
        target = storage.get_by_id(notice_id)
        if not target:
            return jsonify({"error": "Notice not found"}), 404

        target_screens = target.get("screens") or [target.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, target_screens, priority=target.get("priority", "normal"), existing_notice=target, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        affected = target.get("screens") if target else None
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        success = storage.delete(notice_id, actor=actor, ip=get_client_ip())
        notify_notice_change(affected_screens=affected)
        if success:
            return jsonify({"success": True, "id": notice_id, "restorable": True})
        return jsonify({"error": "Notice not found"}), 404

    @app.route("/api/notices/<notice_id>/restore", methods=["POST"])
    @mutation_admin_required
    def restore_notice(notice_id):
        user = get_current_user()
        target = storage.get_by_id(notice_id)
        if not target:
            return jsonify({"error": "Notice not found or cannot be restored"}), 404
        target_screens = target.get("screens") or [target.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, target_screens, priority=target.get("priority", "normal"), existing_notice=target, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        restored = storage.restore(notice_id, actor=actor, ip=get_client_ip())
        if not restored:
            return jsonify({"error": "Notice not found or cannot be restored"}), 404
        notify_notice_change(affected_screens=restored.get("screens"))
        return jsonify({"success": True, "notice": restored})

    @app.route("/api/settings", methods=["POST", "PUT"])
    @mutation_admin_required
    def update_settings():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        theme = data.get("theme", "auto")
        storage.record_audit(actor, "SETTINGS_UPDATE", "theme", f"Theme updated to '{theme}'", ip=get_client_ip())
        return jsonify({"success": True, "theme": theme})

    @app.route("/api/media/clean-orphans", methods=["POST"])
    @mutation_admin_required
    def clean_orphaned_media_route():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        cleaned_count = storage.safe_garbage_collect_media(grace_period_seconds=60)
        storage.record_audit(actor, "CLEAN_MEDIA", "media", f"Cleaned {cleaned_count or 0} orphaned media files", ip=get_client_ip())
        return jsonify({"success": True, "cleaned_count": cleaned_count or 0})

    @app.route("/api/admin/events/flag", methods=["GET"])
    @read_admin_required
    def get_flag_settings():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        first_evt = events[0] if events else None
        import config
        return jsonify({
            "success": True,
            "events": events,
            "event": first_evt,
            "next_run": overall_next,
            "flag_event_enabled_config": getattr(config, "FLAG_EVENT_ENABLED", False),
            "flag_trigger_token_configured": bool(getattr(config, "FLAG_TRIGGER_TOKEN", ""))
        })

    @app.route("/api/admin/events/flag", methods=["POST"])
    @mutation_admin_required
    def create_flag_event():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        ev_id = data.get("id")
        try:
            if ev_id and storage.get_daily_event(ev_id):
                updated = storage.update_daily_event(ev_id, data, actor=actor, ip=get_client_ip())
            else:
                updated = storage.add_daily_event(data, actor=actor, ip=get_client_ip())
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag/<event_id>", methods=["PUT", "POST"])
    @mutation_admin_required
    def update_specific_flag_event(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        try:
            updated = storage.update_daily_event(event_id, data, actor=actor, ip=get_client_ip())
            if not updated:
                return jsonify({"error": f"Event '{event_id}' not found"}), 404
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag", methods=["PUT"])
    @mutation_admin_required
    def update_flag_settings():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or "flag"
        try:
            updated = storage.update_daily_event(event_id, data, actor=actor, ip=get_client_ip())
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag/<event_id>", methods=["DELETE"])
    @mutation_admin_required
    def delete_flag_event(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        events = storage.get_daily_events()
        if len(events) <= 1:
            return jsonify({"error": "Cannot delete the only remaining daily event"}), 400
        success = storage.delete_daily_event(event_id, actor=actor, ip=get_client_ip())
        if not success:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        notify_flag_change("ALL")
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        return jsonify({"success": True, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/<event_id>/skip-today", methods=["POST"])
    @mutation_admin_required
    def skip_specific_flag_today(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        updated = storage.skip_daily_event_today(event_id, actor=actor, ip=get_client_ip())
        if not updated:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
        return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/skip-today", methods=["POST"])
    @mutation_admin_required
    def skip_flag_today():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or "flag"
        updated = storage.skip_daily_event_today(event_id, actor=actor, ip=get_client_ip())
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
        return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/<event_id>/test-run", methods=["POST"])
    @mutation_admin_required
    def test_run_specific_flag(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        evt = storage.get_daily_event(event_id)
        if not evt:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        screens = data.get("screens", evt.get("screens", "ALL"))
        show_now = bool(data.get("show_now", False))
        if show_now:
            duration = 86400
        else:
            try:
                duration = int(data.get("duration_seconds", evt.get("duration_seconds", 60)))
                duration = max(5, min(86400, duration))
            except Exception:
                duration = evt.get("duration_seconds", 60)
        show_standup = bool(data.get("show_standup_text", evt.get("show_standup_text", False)))
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=show_standup, event_id=event_id)
        storage.record_daily_event_run(event_id, result=f"Manual run on {screens} ({duration}s)", actor=actor, ip=get_client_ip())
        notify_flag_change(screens)
        return jsonify({"success": True, "message": f"This will replace the display with the flag for {duration} seconds", "duration": duration, "screens": screens})

    @app.route("/api/admin/events/flag/test-run", methods=["POST"])
    @mutation_admin_required
    def test_run_flag():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or data.get("event_id") or "flag"
        evt = storage.get_daily_event(event_id)
        screens = data.get("screens", evt.get("screens", "ALL") if evt else "ALL")
        show_now = bool(data.get("show_now", False))
        if show_now:
            duration = 86400
        else:
            try:
                duration = int(data.get("duration_seconds", evt.get("duration_seconds", 60) if evt else 60))
                duration = max(5, min(86400, duration))
            except Exception:
                duration = 60
        show_standup = bool(data.get("show_standup_text", evt.get("show_standup_text", False) if evt else False))
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=show_standup, event_id=event_id)
        storage.record_daily_event_run(event_id, result=f"Manual run on {screens} ({duration}s)", actor=actor, ip=get_client_ip())
        notify_flag_change(screens)
        return jsonify({"success": True, "message": f"This will replace the display with the flag for {duration} seconds", "duration": duration, "screens": screens})

    @app.route("/api/admin/events/flag/stop", methods=["POST"])
    @mutation_admin_required
    def stop_flag_run():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        storage.clear_flag_manual_override(ended_early=True)
        notify_flag_change("ALL")
        return jsonify({"success": True, "message": "Flag display ended"})

    @app.route("/api/events/today", methods=["GET"])
    def admin_events_today():
        screen = request.args.get("screen") or request.args.get("screen_id") or "ALL"
        sim_header = request.headers.get("X-Simulated-Now") or request.args.get("sim_now")
        now_dt = None
        if sim_header:
            try:
                now_dt = datetime.datetime.fromtimestamp(float(sim_header) / 1000.0, tz=KOLKATA_TZ)
            except Exception:
                pass
        data = storage.get_flag_event_today(screen_code=screen, now_dt=now_dt)
        return make_flag_event_response(data)

    @app.route("/api/events/flag/start", methods=["POST"])
    def flag_trigger_start_admin():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        screens = data.get("screens", "ALL")
        duration = data.get("duration_seconds", 60)
        try:
            duration = max(5, min(86400, int(duration)))
        except Exception:
            duration = 60
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=False)
        storage.record_daily_event_run("flag", result=f"Triggered via external API for {duration}s on {screens}", actor="external_api", ip=get_client_ip())
        notify_flag_change(screens)
        res = jsonify({"success": True, "action": "flag_started", "duration_seconds": duration, "screens": screens})
        res.headers["Cache-Control"] = "no-store"
        return res

    @app.route("/api/events/flag/end", methods=["POST"])
    def flag_trigger_end_admin():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        storage.clear_flag_manual_override(ended_early=True)
        storage.record_daily_event_run("flag", result="Ended via external API", actor="external_api", ip=get_client_ip())
        notify_flag_change("ALL")
        res = jsonify({"success": True, "action": "flag_ended"})
        res.headers["Cache-Control"] = "no-store"
        return res

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        return serve_media_response(filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/api/health/details")
    @read_admin_required
    def health_details():
        data, code = get_health_payload("vnotice-admin")
        return jsonify(data), code

    
    register_admin_account_and_invite_routes(app)
    return app

# ==============================================================================
# UNIFIED CLOUD APP (Mode A: Render / Railway single $PORT)
# ==============================================================================
def create_unified_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    configure_app_security(app)
    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            "sw.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/admin-sw.js")
    def admin_service_worker():
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            "admin-sw.js",
            mimetype="application/javascript",
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/manifest.json")
    @app.route("/manifest.webmanifest")
    def manifest():
        filename = "manifest.webmanifest" if request.path.endswith(".webmanifest") else "manifest.json"
        response = send_from_directory(
            os.path.join(app.root_path, "static"),
            filename,
            mimetype="application/manifest+json",
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


    @app.teardown_appcontext
    def teardown_db(exception=None):
        storage.close_connection()

    # 1. Admin UI (Default Root and /admin)
    @app.route("/")
    @app.route("/admin")
    def admin_home():
        return render_template(
            "admin.html",
            version=getattr(config, "VERSION", "2.2.0"),
            is_cloud=getattr(storage.media_storage, "is_cloud", False),
            voice_notices_enabled=getattr(config, "VOICE_NOTICES_ENABLED", False),
            max_voice_duration=getattr(config, "MAX_VOICE_DURATION_SECONDS", 120),
            max_voice_upload_mb=getattr(config, "MAX_VOICE_UPLOAD_MB", 10),
        )

    # 2. Display Kiosk UI
    @app.route("/display")
    def display_home():
        screen = request.args.get("screen") or request.args.get("screen_id")
        if screen:
            target = screen.strip().upper()
            if target == "DEFAULT":
                target = "ALL"
            return redirect(f"/display/{target}", code=301)
        dept = storage.get_department("ALL")
        return render_template("display.html", screen_code="ALL", department=dept)

    @app.route("/display/<code>")
    def display_screen(code):
        if not code:
            return redirect("/display", code=301)
        upper_code = code.strip().upper()
        if code != upper_code:
            qs = request.query_string.decode("utf-8")
            url = f"/display/{upper_code}" + (f"?{qs}" if qs else "")
            return redirect(url, code=301)
        dept = storage.get_department(upper_code)
        if not dept or not dept.get("active"):
            active_depts = storage.get_departments(active_only=True)
            return render_template("screen_not_found.html", code=upper_code, departments=active_depts), 404
        return render_template("display.html", screen_code=upper_code, department=dept)

    @app.route("/<code>")
    def dept_shortcut(code):
        if not code:
            return redirect("/display", code=301)
        if code.lower() in ("static", "api", "sw.js", "favicon.ico", "media", "display", "notice", "admin", "invite"):
            return "Not Found", 404
        canonical = code.strip().upper()
        dept = storage.get_department(canonical)
        if dept:
            return redirect(f"/display/{canonical}", code=301)
        return "Not Found", 404

    @app.route("/api/heartbeat", methods=["POST"])
    def post_heartbeat():
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = data.get("screen") or data.get("screen_id") or data.get("code") or "ALL"
        audio_ready = data.get("audio_ready")
        record_heartbeat(code, audio_ready)
        return jsonify({"success": True, "code": str(code).strip().upper(), "timestamp": int(time.time() * 1000)})

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.route("/api/csrf-token", methods=["GET"])
    def get_csrf():
        token = session.get("csrf_token")
        if not token:
            token = generate_csrf_token()
            session["csrf_token"] = token
        return jsonify({"csrf_token": token})

    # Auth routes with rate limiting
    @app.route("/api/login", methods=["POST"])
    def login():
        return _handle_login()

    @app.route("/api/logout", methods=["POST"])
    def logout():
        return _handle_logout()

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        if check_admin_auth():
            depts = storage.get_departments(active_only=False)
            now_ms = int(time.time() * 1000)
            for d in depts:
                ls = get_screen_last_seen(d["code"])
                d["last_seen"] = ls
                d["online"] = (ls is not None) and ((now_ms - ls) < 60000)
                d["audio_ready"] = get_screen_audio_ready(d["code"])
            return jsonify({"success": True, "screens": depts})
        else:
            depts = storage.get_departments(active_only=True)
            screens = [{
                "code": d["code"],
                "name": d["name"],
                "id": d["code"],
                "accent_color": d.get("accent_color"),
                "sound_enabled": d.get("sound_enabled", False),
                "sound_volume": d.get("sound_volume", 70)
            } for d in depts]
            return jsonify({"success": True, "screens": screens})

    @app.route("/api/screens", methods=["POST"])
    @mutation_admin_required
    def create_screen():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = data.get("code")
        name = data.get("name")
        sort_order = data.get("sort_order", 0)
        active = data.get("active", True)
        if isinstance(active, str):
            active = active.lower() in ("true", "1", "yes")
        accent_color = data.get("accent_color")

        if not code or not isinstance(code, str):
            return jsonify({"error": "Screen code is required"}), 400
        code = code.strip()
        if not SCREEN_CODE_REGEX.match(code):
            return jsonify({"error": "Screen code must be 2-10 uppercase alphanumeric characters, underscores, or hyphens (lowercase, spaces, and symbols are rejected)"}), 400

        if not name or not str(name).strip():
            return jsonify({"error": "Screen name is required"}), 400

        try:
            created = storage.add_department(code=code, name=name, sort_order=sort_order, active=active, accent_color=accent_color)
            return jsonify({"success": True, "screen": created}), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/screens/<code>", methods=["PUT", "POST"])
    @mutation_admin_required
    def update_screen(code):
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        code = str(code).strip().upper()
        dept = storage.get_department(code)
        if not dept:
            return jsonify({"error": f"Screen '{code}' not found"}), 404

        try:
            updated = storage.update_department(code, data)
            return jsonify({"success": True, "screen": updated}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/screens/<code>", methods=["DELETE"])
    @mutation_admin_required
    def delete_screen(code):
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        code = str(code).strip().upper()
        if code == "ALL":
            return jsonify({"error": "The college-wide 'ALL' screen cannot be deleted"}), 400

        dept = storage.get_department(code)
        if not dept:
            return jsonify({"error": f"Screen '{code}' not found"}), 404

        try:
            res = storage.delete_department(code)
            return jsonify(res), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Smart Dual Notices API: Admin gets all notices; Public gets active only
    @app.route("/api/notices", methods=["GET"])
    def get_notices():
        screen = request.args.get("screen") or request.args.get("screen_id")
        is_admin_view = request.args.get("view") == "admin" or request.args.get("admin") == "1"
        api_status, _ = _check_api_key_header()
        if is_admin_view:
            if check_admin_auth():
                notices = _filter_notices_for_user(get_current_user(), storage.get_all(screen_id=screen))
                return make_etag_response(notices)
            return jsonify({"error": "Unauthorized. Authentication required."}), 401
        if api_status == "valid":
            return make_etag_response(storage.get_all(screen_id=screen))
        # Public kiosk view: active notices only with admin fields stripped
        active = storage.get_active(screen_id=screen)
        return make_etag_response([sanitize_public_notice(n) for n in active])

    @app.route("/api/events")
    def sse_events_unified():
        import config
        if not getattr(config, "SSE_ENABLED", False):
            return jsonify({"error": "SSE is disabled; use conditional polling with ETag"}), 404
        screen = request.args.get("screen") or request.args.get("screen_id")
        return Response(
            sse_event_stream(screen),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    @app.route("/api/audit-logs", methods=["GET"])
    @read_admin_required
    def get_audit():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        action = request.args.get("action")
        actor = request.args.get("actor")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        if date_from:
            try: date_from = int(date_from)
            except (ValueError, TypeError): date_from = None
        if date_to:
            try: date_to = int(date_to)
            except (ValueError, TypeError): date_to = None

        res = storage.get_audit_logs(
            limit=limit,
            offset=offset,
            action=action,
            actor=actor,
            date_from=date_from,
            date_to=date_to
        )
        return jsonify({
            "success": True,
            "audit_logs": res["audit_logs"],
            "logs": res["logs"],
            "total": res["total"],
            "limit": limit,
            "offset": offset
        })

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File exceeds the maximum upload limit."}), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"error": "An internal server error occurred. Please try again."}), 500

    @app.route("/api/notices", methods=["POST"])
    @mutation_admin_required
    def create_notice():
        form_data = request.form.to_dict()
        file_obj = request.files.get("media_file")
        if not form_data and request.is_json:
            form_data = request.get_json()

        raw_input = request.form.getlist("screens[]") or request.form.getlist("screens") or form_data.get("screens") or form_data.get("screen_id")
        screens = sanitize_screen_codes(raw_input)
        form_data["screens"] = screens
        form_data["screen_id"] = screens[0] if screens else "ALL"

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        user = get_current_user()
        target_candidates = screens or [form_data.get("screen_id") or "ALL"]
        ok, err = check_notice_permissions(user, target_candidates, priority=form_data.get("priority", "normal"), is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        try:
            creator_id = user.get("id") if user else None
            creator_name = (user.get("name") or user.get("email") or "Admin") if user else (form_data.get("created_by") or "Admin")
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator_id, created_by_name=creator_name)
            notify_notice_change(affected_screens=notice.get("screens"))
            return jsonify(notice), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to publish notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["PUT", "POST"])
    @mutation_admin_required
    def update_notice(notice_id):
        form_data = request.form.to_dict()
        file_obj = request.files.get("media_file")
        if not form_data and request.is_json:
            form_data = request.get_json()

        raw_input = request.form.getlist("screens[]") or request.form.getlist("screens") or form_data.get("screens") or form_data.get("screen_id")
        screens = sanitize_screen_codes(raw_input)
        form_data["screens"] = screens
        form_data["screen_id"] = screens[0] if screens else "ALL"

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        user = get_current_user()
        existing = storage.get_by_id(notice_id)
        if not existing:
            return jsonify({"error": "Notice not found"}), 404

        existing_screens = existing.get("screens") or [existing.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, existing_screens, priority=existing.get("priority", "normal"), existing_notice=existing, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        new_targets = screens or existing_screens
        new_priority = form_data.get("priority", existing.get("priority", "normal"))
        ok_new, err_new = check_notice_permissions(user, new_targets, priority=new_priority, existing_notice=existing, is_mutation=True)
        if not ok_new:
            return jsonify({"error": err_new}), 403

        try:
            updater = (user.get("username") if user else None) or form_data.get("created_by") or "admin"
            updated = storage.update(notice_id, form_data, file_obj=file_obj, updated_by=updater)
            if not updated:
                return jsonify({"error": "Notice not found"}), 404
            notify_notice_change(affected_screens=updated.get("screens"))
            return jsonify(updated), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to update notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @mutation_admin_required
    def delete_notice(notice_id):
        user = get_current_user()
        target = storage.get_by_id(notice_id)
        if not target:
            return jsonify({"error": "Notice not found"}), 404

        target_screens = target.get("screens") or [target.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, target_screens, priority=target.get("priority", "normal"), existing_notice=target, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403

        affected = target.get("screens") if target else None
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        success = storage.delete(notice_id, actor=actor, ip=get_client_ip())
        notify_notice_change(affected_screens=affected)
        if success:
            return jsonify({"success": True, "id": notice_id, "restorable": True})
        return jsonify({"error": "Notice not found"}), 404

    @app.route("/api/notices/<notice_id>/restore", methods=["POST"])
    @mutation_admin_required
    def restore_notice(notice_id):
        user = get_current_user()
        target = storage.get_by_id(notice_id)
        if not target:
            return jsonify({"error": "Notice not found or cannot be restored"}), 404
        target_screens = target.get("screens") or [target.get("screen_id", "ALL")]
        ok, err = check_notice_permissions(user, target_screens, priority=target.get("priority", "normal"), existing_notice=target, is_mutation=True)
        if not ok:
            return jsonify({"error": err}), 403
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        restored = storage.restore(notice_id, actor=actor, ip=get_client_ip())
        if not restored:
            return jsonify({"error": "Notice not found or cannot be restored"}), 404
        notify_notice_change(affected_screens=restored.get("screens"))
        return jsonify({"success": True, "notice": restored})

    @app.route("/api/settings", methods=["POST", "PUT"])
    @mutation_admin_required
    def update_settings():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        theme = data.get("theme", "auto")
        storage.record_audit(actor, "SETTINGS_UPDATE", "theme", f"Theme updated to '{theme}'", ip=get_client_ip())
        return jsonify({"success": True, "theme": theme})

    @app.route("/api/media/clean-orphans", methods=["POST"])
    @mutation_admin_required
    def clean_orphaned_media_route_unified():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        cleaned_count = storage.safe_garbage_collect_media(grace_period_seconds=60)
        storage.record_audit(actor, "CLEAN_MEDIA", "media", f"Cleaned {cleaned_count or 0} orphaned media files", ip=get_client_ip())
        return jsonify({"success": True, "cleaned_count": cleaned_count or 0})

    @app.route("/api/admin/events/flag", methods=["GET"])
    @read_admin_required
    def unified_flag_settings():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        first_evt = events[0] if events else None
        import config
        return jsonify({
            "success": True,
            "events": events,
            "event": first_evt,
            "next_run": overall_next,
            "flag_event_enabled_config": getattr(config, "FLAG_EVENT_ENABLED", False),
            "flag_trigger_token_configured": bool(getattr(config, "FLAG_TRIGGER_TOKEN", ""))
        })

    @app.route("/api/admin/events/flag", methods=["POST"])
    @mutation_admin_required
    def unified_create_flag_event():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        ev_id = data.get("id")
        try:
            if ev_id and storage.get_daily_event(ev_id):
                updated = storage.update_daily_event(ev_id, data, actor=actor, ip=get_client_ip())
            else:
                updated = storage.add_daily_event(data, actor=actor, ip=get_client_ip())
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag/<event_id>", methods=["PUT", "POST"])
    @mutation_admin_required
    def unified_update_specific_flag_event(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        try:
            updated = storage.update_daily_event(event_id, data, actor=actor, ip=get_client_ip())
            if not updated:
                return jsonify({"error": f"Event '{event_id}' not found"}), 404
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag", methods=["PUT"])
    @mutation_admin_required
    def unified_update_flag_settings():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or "flag"
        try:
            updated = storage.update_daily_event(event_id, data, actor=actor, ip=get_client_ip())
            events = storage.get_daily_events()
            for e in events:
                e["next_run"] = storage.compute_next_run_text(e)
            overall_next = storage.compute_overall_next_run_text()
            notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
            return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    @app.route("/api/admin/events/flag/<event_id>", methods=["DELETE"])
    @mutation_admin_required
    def unified_delete_flag_event(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        events = storage.get_daily_events()
        if len(events) <= 1:
            return jsonify({"error": "Cannot delete the only remaining daily event"}), 400
        success = storage.delete_daily_event(event_id, actor=actor, ip=get_client_ip())
        if not success:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        notify_flag_change("ALL")
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        return jsonify({"success": True, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/<event_id>/skip-today", methods=["POST"])
    @mutation_admin_required
    def unified_skip_specific_flag_today(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        updated = storage.skip_daily_event_today(event_id, actor=actor, ip=get_client_ip())
        if not updated:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
        return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/skip-today", methods=["POST"])
    @mutation_admin_required
    def unified_skip_flag_today():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or "flag"
        updated = storage.skip_daily_event_today(event_id, actor=actor, ip=get_client_ip())
        events = storage.get_daily_events()
        for e in events:
            e["next_run"] = storage.compute_next_run_text(e)
        overall_next = storage.compute_overall_next_run_text()
        notify_flag_change(updated.get("screens", "ALL") if updated else "ALL")
        return jsonify({"success": True, "event": updated, "events": events, "next_run": overall_next})

    @app.route("/api/admin/events/flag/<event_id>/test-run", methods=["POST"])
    @mutation_admin_required
    def unified_test_run_specific_flag(event_id):
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        evt = storage.get_daily_event(event_id)
        if not evt:
            return jsonify({"error": f"Event '{event_id}' not found"}), 404
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        screens = data.get("screens", evt.get("screens", "ALL"))
        show_now = bool(data.get("show_now", False))
        if show_now:
            duration = 86400
        else:
            try:
                duration = int(data.get("duration_seconds", evt.get("duration_seconds", 60)))
                duration = max(5, min(86400, duration))
            except Exception:
                duration = evt.get("duration_seconds", 60)
        show_standup = bool(data.get("show_standup_text", evt.get("show_standup_text", False)))
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=show_standup, event_id=event_id)
        storage.record_daily_event_run(event_id, result=f"Manual run on {screens} ({duration}s)", actor=actor, ip=get_client_ip())
        notify_flag_change(screens)
        return jsonify({"success": True, "message": f"This will replace the display with the flag for {duration} seconds", "duration": duration, "screens": screens})

    @app.route("/api/admin/events/flag/test-run", methods=["POST"])
    @mutation_admin_required
    def unified_test_run_flag():
        user, err_res = _require_admin_role()
        if err_res:
            return err_res
        actor = (user.get("email") or user.get("username") if user else None) or "admin"
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        event_id = data.get("id") or data.get("event_id") or "flag"
        evt = storage.get_daily_event(event_id)
        screens = data.get("screens", evt.get("screens", "ALL") if evt else "ALL")
        show_now = bool(data.get("show_now", False))
        if show_now:
            duration = 86400
        else:
            try:
                duration = int(data.get("duration_seconds", evt.get("duration_seconds", 60) if evt else 60))
                duration = max(5, min(86400, duration))
            except Exception:
                duration = 60
        show_standup = bool(data.get("show_standup_text", evt.get("show_standup_text", False) if evt else False))
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=show_standup, event_id=event_id)
        storage.record_daily_event_run(event_id, result=f"Manual run on {screens} ({duration}s)", actor=actor, ip=get_client_ip())
        notify_flag_change(screens)
        return jsonify({"success": True, "message": f"This will replace the display with the flag for {duration} seconds", "duration": duration, "screens": screens})

    @app.route("/api/admin/events/flag/stop", methods=["POST"])
    @mutation_admin_required
    def unified_stop_flag_run():
        _, err_res = _require_admin_role()
        if err_res:
            return err_res
        storage.clear_flag_manual_override(ended_early=True)
        notify_flag_change("ALL")
        return jsonify({"success": True, "message": "Flag display ended"})

    @app.route("/api/events/today", methods=["GET"])
    def unified_events_today():
        screen = request.args.get("screen") or request.args.get("screen_id") or "ALL"
        sim_header = request.headers.get("X-Simulated-Now") or request.args.get("sim_now")
        now_dt = None
        if sim_header:
            try:
                now_dt = datetime.datetime.fromtimestamp(float(sim_header) / 1000.0, tz=KOLKATA_TZ)
            except Exception:
                pass
        data = storage.get_flag_event_today(screen_code=screen, now_dt=now_dt)
        return make_flag_event_response(data)

    @app.route("/api/events/flag/start", methods=["POST"])
    def unified_flag_trigger_start():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        screens = data.get("screens", "ALL")
        duration = data.get("duration_seconds", 60)
        try:
            duration = max(5, min(86400, int(duration)))
        except Exception:
            duration = 60
        storage.set_flag_manual_override(screens=screens, duration_seconds=duration, show_standup_text=False)
        storage.record_daily_event_run("flag", result=f"Triggered via external API for {duration}s on {screens}", actor="external_api", ip=get_client_ip())
        notify_flag_change(screens)
        res = jsonify({"success": True, "action": "flag_started", "duration_seconds": duration, "screens": screens})
        res.headers["Cache-Control"] = "no-store"
        return res

    @app.route("/api/events/flag/end", methods=["POST"])
    def unified_flag_trigger_end():
        authorized, status_code, msg = check_flag_trigger_auth()
        if not authorized:
            return jsonify({"error": msg}), status_code
        storage.clear_flag_manual_override(ended_early=True)
        storage.record_daily_event_run("flag", result="Ended via external API", actor="external_api", ip=get_client_ip())
        notify_flag_change("ALL")
        res = jsonify({"success": True, "action": "flag_ended"})
        res.headers["Cache-Control"] = "no-store"
        return res

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    register_public_notice_routes(app)

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        return serve_media_response(filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/api/health/details")
    @read_admin_required
    def health_details():
        data, code = get_health_payload("vnotice-unified")
        return jsonify(data), code

    
    register_admin_account_and_invite_routes(app)
    return app

display_app = create_display_app()
admin_app = create_admin_app()
unified_app = create_unified_app()

def run_display_server():
    print(f"[*] Starting V Notice Display on http://0.0.0.0:{DISPLAY_PORT}")
    run_simple("0.0.0.0", DISPLAY_PORT, display_app, use_reloader=False, threaded=True)

def run_admin_server():
    print(f"[*] Starting V Notice Admin on http://0.0.0.0:{ADMIN_PORT}")
    run_simple("0.0.0.0", ADMIN_PORT, admin_app, use_reloader=False, threaded=True)

if __name__ == "__main__":
    port_env = os.environ.get("PORT")
    if port_env:
        port = int(port_env)
        print("=" * 60)
        print(f"       V NOTICE -- CLOUD UNIFIED SERVER (PORT {port})       ")
        print("=" * 60)
        print(f"Admin Portal:     http://0.0.0.0:{port}/ (or /admin)")
        print(f"Display Kiosk:    http://0.0.0.0:{port}/display")
        print("=" * 60)
        run_simple("0.0.0.0", port, unified_app, use_reloader=False, threaded=True)
    else:
        print("=" * 60)
        print("            V NOTICE - SMART DIGITAL NOTICE BOARD          ")
        print("=" * 60)
        print(f"Display Interface:  http://localhost:{DISPLAY_PORT}")
        print(f"Admin Interface:    http://localhost:{ADMIN_PORT}")
        print("=" * 60)

        admin_thread = threading.Thread(target=run_admin_server, daemon=True)
        admin_thread.start()

        try:
            run_display_server()
        except KeyboardInterrupt:
            print("[!] Shutting down V Notice servers...")
            sys.exit(0)
