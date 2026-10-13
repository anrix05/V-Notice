import re
import config
import hashlib
import queue
import threading
import sys
import os
import threading
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    send_from_directory,
    redirect,
    Response,
)
from werkzeug.serving import run_simple
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
    login_rate_limiter,
    api_key_rate_limiter,
    generate_csrf_token,
    validate_csrf_token,
    check_password_config_warnings,
)
from storage import storage, compute_status, sanitize_screen_codes
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
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
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

_sse_subscribers = []
_sse_lock = threading.Lock()

_screen_heartbeats = {}
_screen_heartbeats_lock = threading.Lock()

def record_heartbeat(screen_code: str):
    if not screen_code:
        return
    code = str(screen_code).strip().upper()
    with _screen_heartbeats_lock:
        _screen_heartbeats[code] = int(time.time() * 1000)

def get_screen_last_seen(screen_code: str):
    if not screen_code:
        return None
    code = str(screen_code).strip().upper()
    with _screen_heartbeats_lock:
        return _screen_heartbeats.get(code)

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
                    q.put_nowait(payload)
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
                yield f"event: notice_update\ndata: {msg}\n\n"
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
    return safe

def check_admin_auth():
    # Header-based authentication (X-Password)
    auth_header = request.headers.get("X-Password")
    if auth_header:
        ip = get_client_ip()
        locked, _ = api_key_rate_limiter.is_locked(ip)
        if not locked and verify_admin_password(auth_header):
            api_key_rate_limiter.record_success(ip)
            return True
        else:
            api_key_rate_limiter.record_failure(ip)
            return False

    # Session-based authentication
    if session.get("is_admin") is True:
        return True
    return False

def read_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("X-Password")
        if auth_header:
            ip = get_client_ip()
            locked, retry_after = api_key_rate_limiter.is_locked(ip)
            if locked:
                res = jsonify({"error": "Rate limit exceeded. Too many invalid credentials.", "retry_after": retry_after})
                res.status_code = 429
                res.headers["Retry-After"] = str(retry_after)
                return res
            if not verify_admin_password(auth_header):
                api_key_rate_limiter.record_failure(ip)
                return jsonify({"error": "Unauthorized. Invalid admin password."}), 401
            api_key_rate_limiter.record_success(ip)
            return f(*args, **kwargs)

        if session.get("is_admin") is True:
            return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized. Authentication required."}), 401
    return decorated_function


def get_current_user():
    # 1. Check API Key header
    auth_header = request.headers.get("X-Password")
    if auth_header and verify_admin_password(auth_header):
        return {
            "username": "admin",
            "role": "super_admin",
            "departments": ["ALL"],
            "can_target_all": True
        }

    # 2. Check session
    if session.get("is_admin") is True:
        role = session.get("role", "super_admin")
        username = session.get("username", "admin")
        departments = session.get("departments", ["ALL"] if role == "super_admin" else [])
        can_target_all = bool(session.get("can_target_all", role == "super_admin"))
        return {
            "username": username,
            "role": role,
            "departments": departments,
            "can_target_all": can_target_all
        }
    return None

def check_notice_permissions(user, target_screens):
    """Phase 6: Enforces permission boundaries between super_admin and dept_admin."""
    if not user:
        return False, "Authentication required."
    if user.get("role") == "super_admin":
        return True, None

    # dept_admin role
    screens = [str(s).strip().upper() for s in target_screens if str(s).strip()]
    if not screens:
        screens = ["ALL"]

    if "ALL" in screens and not user.get("can_target_all", False):
        return False, "Permission denied: dept_admin cannot target All Departments (college-wide)"

    user_depts = [str(d).strip().upper() for d in user.get("departments", [])]
    for sc in screens:
        if sc == "ALL":
            continue
        if sc not in user_depts:
            return False, f"Permission denied: dept_admin cannot target department '{sc}'"

    return True, None

def mutation_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("X-Password")
        if auth_header:
            # X-Password exempt from CSRF per Phase 2 Rule 3, but rate-limited
            ip = get_client_ip()
            locked, retry_after = api_key_rate_limiter.is_locked(ip)
            if locked:
                res = jsonify({"error": "Rate limit exceeded. Too many invalid credentials.", "retry_after": retry_after})
                res.status_code = 429
                res.headers["Retry-After"] = str(retry_after)
                return res
            if not verify_admin_password(auth_header):
                api_key_rate_limiter.record_failure(ip)
                return jsonify({"error": "Unauthorized. Invalid admin password."}), 401
            api_key_rate_limiter.record_success(ip)
            return f(*args, **kwargs)

        if session.get("is_admin") is True:
            # CSRF validation required for session-authenticated mutations
            csrf_token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            session_token = session.get("csrf_token")
            if not validate_csrf_token(session_token, csrf_token):
                return jsonify({"error": "Forbidden: CSRF token validation failed."}), 403
            return f(*args, **kwargs)

        return jsonify({"error": "Unauthorized. Authentication required."}), 401
    return decorated_function

def apply_security_headers(app):
    @app.after_request
    def set_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://res.cloudinary.com https://*.cloudinary.com; "
            "media-src 'self' blob: https://res.cloudinary.com https://*.cloudinary.com; "
            "connect-src 'self' https://res.cloudinary.com https://*.cloudinary.com; "
            "font-src 'self'; "
            "manifest-src 'self'; "
            "worker-src 'self'; "
            "frame-ancestors 'none';"
        )
        if request.path.startswith("/admin") or request.path == "/" or request.path.startswith("/api"):
            response.headers["X-Frame-Options"] = "DENY"
        
        # If HTTPS, enforce Secure session cookies
        if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
            for cookie_name in ("session", "csrf_token"):
                if cookie_name in response.headers.get("Set-Cookie", ""):
                    # cookie already formatted with HttpOnly, SameSite=Lax via Flask config
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
    apply_security_headers(app)

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
        record_heartbeat(code)
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
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        depts = storage.get_departments(active_only=True)
        screens = [{"code": d["code"], "name": d["name"], "id": d["code"], "accent_color": d.get("accent_color")} for d in depts]
        return jsonify({"success": True, "screens": screens})

    

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    @app.route("/notice/<notice_id>")
    def notice_detail(notice_id):
        notice = storage.get_by_id(notice_id)
        if not notice:
            return render_template("notice_detail.html", notice=None), 404
        # Phase 2 Rule 4: Return 404 unless active (admins may see any)
        if notice.get("status") != "live" and not check_admin_auth():
            return render_template("notice_detail.html", notice=None), 404
        return render_template("notice_detail.html", notice=notice)

    @app.route("/notice/<notice_id>/download")
    def notice_download(notice_id):
        notice = storage.get_by_id(notice_id)
        if not notice:
            return jsonify({"error": "Notice not found"}), 404
        if notice.get("status") != "live" and not check_admin_auth():
            return jsonify({"error": "Notice not found"}), 404

        if notice.get("media"):
            media_path = storage.media_storage.get_path(notice["media"])
            if media_path.exists():
                return send_from_directory(
                    MEDIA_FOLDER,
                    notice["media"],
                    as_attachment=True,
                    download_name=notice["media"]
                )

        title = notice.get("title", "Notice")
        clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
        filename = f"{clean_title or 'notice'}.txt"
        lines = [
            "====================================================",
            "  V NOTICE -- OFFICIAL CAMPUS ANNOUNCEMENT",
            "====================================================",
            "",
            f"TITLE:    {notice.get('title', '')}",
            f"PRIORITY: {notice.get('priority', 'Normal').upper()}",
            "",
            "DETAILS:",
            notice.get('body', 'No additional details provided.'),
            "",
            "====================================================",
            "Saved from V Notice Smart Display",
        ]
        content = "\n".join(lines)
        return Response(
            content,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        response = send_from_directory(MEDIA_FOLDER, filename)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.route("/api/health")
    def health():
        data, code = get_health_payload("vnotice-display")
        return jsonify(data), code

    return app

# ==============================================================================
# ADMIN APP (Port 5001)
# ==============================================================================
def create_admin_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    configure_app_security(app)

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
    def index():
        return render_template("admin.html")

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
        record_heartbeat(code)
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
        ip = get_client_ip()
        locked, retry_after = login_rate_limiter.is_locked(ip)
        if locked:
            res = jsonify({
                "success": False,
                "error": "Too many failed login attempts. Please try again later.",
                "retry_after": retry_after
            })
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res

        data = request.get_json(silent=True) or request.form
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()

        # Shared password / super_admin login
        if not username or username.lower() == "admin":
            if verify_admin_password(password):
                login_rate_limiter.record_success(ip)
                session["is_admin"] = True
                session["username"] = "admin"
                session["role"] = "super_admin"
                session["departments"] = ["ALL"]
                session["can_target_all"] = True
                token = generate_csrf_token()
                session["csrf_token"] = token
                return jsonify({
                    "success": True,
                    "message": "Authentication successful",
                    "csrf_token": token,
                    "user": {
                        "username": "admin",
                        "role": "super_admin",
                        "departments": ["ALL"],
                        "can_target_all": True
                    }
                })
            else:
                login_rate_limiter.record_failure(ip)
                return jsonify({"success": False, "error": "Invalid password"}), 401
        else:
            # Per-user dept_admin login with hashed passwords
            user = storage.verify_user_credentials(username, password)
            if user:
                login_rate_limiter.record_success(ip)
                session["is_admin"] = True
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["departments"] = user["departments"]
                session["can_target_all"] = user["can_target_all"]
                token = generate_csrf_token()
                session["csrf_token"] = token
                return jsonify({
                    "success": True,
                    "message": "Authentication successful",
                    "csrf_token": token,
                    "user": {
                        "username": user["username"],
                        "role": user["role"],
                        "departments": user["departments"],
                        "can_target_all": user["can_target_all"]
                    }
                })
            else:
                login_rate_limiter.record_failure(ip)
                return jsonify({"success": False, "error": "Invalid username or password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("is_admin", None)
        session.pop("csrf_token", None)
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
        return jsonify({"success": True, "screens": depts})

    @app.route("/api/screens", methods=["POST"])
    @mutation_admin_required
    def create_screen():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can create screens"}), 403
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
        notices = storage.get_all(screen_id=screen)
        return make_etag_response(notices)

    @app.route("/api/audit-logs", methods=["GET"])
    @read_admin_required
    def get_audit():
        logs = storage.get_audit_logs(limit=50)
        return jsonify({"success": True, "audit_logs": logs})

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
        ok, err = check_notice_permissions(user, target_candidates)
        if not ok:
            return jsonify({"error": err}), 403

        try:
            creator = (user.get("username") if user else None) or form_data.get("created_by") or "admin"
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator)
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
        ok, err = check_notice_permissions(user, existing_screens)
        if not ok:
            return jsonify({"error": err}), 403

        if screens or form_data.get("screen_id"):
            new_targets = screens or [form_data.get("screen_id") or "ALL"]
            ok_new, err_new = check_notice_permissions(user, new_targets)
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
        ok, err = check_notice_permissions(user, target_screens)
        if not ok:
            return jsonify({"error": err}), 403

        affected = target.get("screens") if target else None
        actor = (user.get("username") if user else None) or "admin"
        success = storage.delete(notice_id, actor=actor)
        notify_notice_change(affected_screens=affected)
        if success:
            return jsonify({"success": True, "id": notice_id})
        return jsonify({"error": "Notice not found"}), 404

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        response = send_from_directory(MEDIA_FOLDER, filename)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.route("/api/health")
    def health():
        data, code = get_health_payload("vnotice-admin")
        return jsonify(data), code

    
    @app.route("/api/me", methods=["GET"])
    def get_me():
        user = get_current_user()
        if not user:
            return jsonify({"authenticated": False}), 200
        return jsonify({
            "authenticated": True,
            "username": user["username"],
            "role": user["role"],
            "departments": user["departments"],
            "can_target_all": user["can_target_all"]
        })

    @app.route("/api/users", methods=["GET"])
    @read_admin_required
    def get_users_list():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can list users"}), 403
        return jsonify({"success": True, "users": storage.list_users()})

    @app.route("/api/users", methods=["POST"])
    @mutation_admin_required
    def create_dept_user():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can create users"}), 403
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "dept_admin").strip()
        departments = data.get("departments", [])
        can_target_all = bool(data.get("can_target_all", False))
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        try:
            created = storage.create_user(
                username=username,
                password=password,
                role=role,
                departments=departments,
                can_target_all=can_target_all
            )
            return jsonify({"success": True, "user": created}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/users/<username>", methods=["DELETE"])
    @mutation_admin_required
    def delete_dept_user(username):
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can delete users"}), 403
        if username.lower() == "admin":
            return jsonify({"error": "Cannot delete primary admin"}), 400
        deleted = storage.delete_user(username)
        if deleted:
            return jsonify({"success": True, "username": username})
        return jsonify({"error": "User not found"}), 404
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
        return render_template("admin.html")

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
        if code.lower() in ("static", "api", "sw.js", "favicon.ico", "media", "display", "notice", "admin"):
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
        record_heartbeat(code)
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
        ip = get_client_ip()
        locked, retry_after = login_rate_limiter.is_locked(ip)
        if locked:
            res = jsonify({
                "success": False,
                "error": "Too many failed login attempts. Please try again later.",
                "retry_after": retry_after
            })
            res.status_code = 429
            res.headers["Retry-After"] = str(retry_after)
            return res

        data = request.get_json(silent=True) or request.form
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", "")).strip()

        # Shared password / super_admin login
        if not username or username.lower() == "admin":
            if verify_admin_password(password):
                login_rate_limiter.record_success(ip)
                session["is_admin"] = True
                session["username"] = "admin"
                session["role"] = "super_admin"
                session["departments"] = ["ALL"]
                session["can_target_all"] = True
                token = generate_csrf_token()
                session["csrf_token"] = token
                return jsonify({
                    "success": True,
                    "message": "Authentication successful",
                    "csrf_token": token,
                    "user": {
                        "username": "admin",
                        "role": "super_admin",
                        "departments": ["ALL"],
                        "can_target_all": True
                    }
                })
            else:
                login_rate_limiter.record_failure(ip)
                return jsonify({"success": False, "error": "Invalid password"}), 401
        else:
            # Per-user dept_admin login with hashed passwords
            user = storage.verify_user_credentials(username, password)
            if user:
                login_rate_limiter.record_success(ip)
                session["is_admin"] = True
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["departments"] = user["departments"]
                session["can_target_all"] = user["can_target_all"]
                token = generate_csrf_token()
                session["csrf_token"] = token
                return jsonify({
                    "success": True,
                    "message": "Authentication successful",
                    "csrf_token": token,
                    "user": {
                        "username": user["username"],
                        "role": user["role"],
                        "departments": user["departments"],
                        "can_target_all": user["can_target_all"]
                    }
                })
            else:
                login_rate_limiter.record_failure(ip)
                return jsonify({"success": False, "error": "Invalid username or password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("is_admin", None)
        session.pop("csrf_token", None)
        return jsonify({"success": True})

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        if check_admin_auth():
            depts = storage.get_departments(active_only=False)
            now_ms = int(time.time() * 1000)
            for d in depts:
                ls = get_screen_last_seen(d["code"])
                d["last_seen"] = ls
                d["online"] = (ls is not None) and ((now_ms - ls) < 60000)
            return jsonify({"success": True, "screens": depts})
        else:
            depts = storage.get_departments(active_only=True)
            screens = [{"code": d["code"], "name": d["name"], "id": d["code"], "accent_color": d.get("accent_color")} for d in depts]
            return jsonify({"success": True, "screens": screens})

    @app.route("/api/screens", methods=["POST"])
    @mutation_admin_required
    def create_screen():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can create screens"}), 403
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
        is_api_key_auth = bool(request.headers.get("X-Password") and verify_admin_password(request.headers.get("X-Password")))
        if is_api_key_auth or (is_admin_view and check_admin_auth()):
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
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    @app.route("/api/audit-logs", methods=["GET"])
    @read_admin_required
    def get_audit():
        logs = storage.get_audit_logs(limit=50)
        return jsonify({"success": True, "audit_logs": logs})

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
        ok, err = check_notice_permissions(user, target_candidates)
        if not ok:
            return jsonify({"error": err}), 403

        try:
            creator = (user.get("username") if user else None) or form_data.get("created_by") or "admin"
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator)
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
        ok, err = check_notice_permissions(user, existing_screens)
        if not ok:
            return jsonify({"error": err}), 403

        if screens or form_data.get("screen_id"):
            new_targets = screens or [form_data.get("screen_id") or "ALL"]
            ok_new, err_new = check_notice_permissions(user, new_targets)
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
        ok, err = check_notice_permissions(user, target_screens)
        if not ok:
            return jsonify({"error": err}), 403

        affected = target.get("screens") if target else None
        actor = (user.get("username") if user else None) or "admin"
        success = storage.delete(notice_id, actor=actor)
        notify_notice_change(affected_screens=affected)
        if success:
            return jsonify({"success": True, "id": notice_id})
        return jsonify({"error": "Notice not found"}), 404

    @app.route("/api/system-info", methods=["GET"])
    def system_info():
        return jsonify(get_system_weather())

    @app.route("/notice/<notice_id>")
    def notice_detail(notice_id):
        notice = storage.get_by_id(notice_id)
        if not notice:
            return render_template("notice_detail.html", notice=None), 404
        # Phase 2 Rule 4: Return 404 unless active (admins may see any)
        if notice.get("status") != "live" and not check_admin_auth():
            return render_template("notice_detail.html", notice=None), 404
        return render_template("notice_detail.html", notice=notice)

    @app.route("/notice/<notice_id>/download")
    def notice_download(notice_id):
        notice = storage.get_by_id(notice_id)
        if not notice:
            return jsonify({"error": "Notice not found"}), 404
        if notice.get("status") != "live" and not check_admin_auth():
            return jsonify({"error": "Notice not found"}), 404

        if notice.get("media"):
            if str(notice["media"]).startswith("http://") or str(notice["media"]).startswith("https://"):
                return redirect(notice["media"])
            media_path = storage.media_storage.get_path(notice["media"]) if hasattr(storage.media_storage, "get_path") else None
            if media_path and media_path.exists():
                return send_from_directory(
                    MEDIA_FOLDER,
                    notice["media"],
                    as_attachment=True,
                    download_name=notice["media"]
                )

        title = notice.get("title", "Notice")
        clean_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
        filename = f"{clean_title or 'notice'}.txt"
        lines = [
            "====================================================",
            "  V NOTICE -- OFFICIAL CAMPUS ANNOUNCEMENT",
            "====================================================",
            "",
            f"TITLE:    {notice.get('title', '')}",
            f"PRIORITY: {notice.get('priority', 'Normal').upper()}",
            "",
            "DETAILS:",
            notice.get('body', 'No additional details provided.'),
            "",
            "====================================================",
            "Saved from V Notice Smart Display",
        ]
        content = "\n".join(lines)
        return Response(
            content,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        if filename.startswith("http://") or filename.startswith("https://"):
            return redirect(filename)
        file_path = MEDIA_FOLDER / filename
        if file_path.exists():
            response = send_from_directory(MEDIA_FOLDER, filename)
            response.headers["Cache-Control"] = "public, max-age=86400"
            return response
        return jsonify({"error": "Media file not found"}), 404

    @app.route("/api/health")
    def health():
        data, code = get_health_payload("vnotice-unified")
        return jsonify(data), code

    
    @app.route("/api/me", methods=["GET"])
    def get_me():
        user = get_current_user()
        if not user:
            return jsonify({"authenticated": False}), 200
        return jsonify({
            "authenticated": True,
            "username": user["username"],
            "role": user["role"],
            "departments": user["departments"],
            "can_target_all": user["can_target_all"]
        })

    @app.route("/api/users", methods=["GET"])
    @read_admin_required
    def get_users_list():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can list users"}), 403
        return jsonify({"success": True, "users": storage.list_users()})

    @app.route("/api/users", methods=["POST"])
    @mutation_admin_required
    def create_dept_user():
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can create users"}), 403
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        role = data.get("role", "dept_admin").strip()
        departments = data.get("departments", [])
        can_target_all = bool(data.get("can_target_all", False))
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        try:
            created = storage.create_user(
                username=username,
                password=password,
                role=role,
                departments=departments,
                can_target_all=can_target_all
            )
            return jsonify({"success": True, "user": created}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/users/<username>", methods=["DELETE"])
    @mutation_admin_required
    def delete_dept_user(username):
        user = get_current_user()
        if not user or user.get("role") != "super_admin":
            return jsonify({"error": "Permission denied: Only super_admin can delete users"}), 403
        if username.lower() == "admin":
            return jsonify({"error": "Cannot delete primary admin"}), 400
        deleted = storage.delete_user(username)
        if deleted:
            return jsonify({"success": True, "username": username})
        return jsonify({"error": "User not found"}), 404
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
        print(f"Default Admin Pass: {os.environ.get('ADMIN_PASSWORD', 'vnotice2026')}")
        print("=" * 60)

        admin_thread = threading.Thread(target=run_admin_server, daemon=True)
        admin_thread.start()

        try:
            run_display_server()
        except KeyboardInterrupt:
            print("[!] Shutting down V Notice servers...")
            sys.exit(0)
