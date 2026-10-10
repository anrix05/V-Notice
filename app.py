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
from security import (
    verify_admin_password,
    login_rate_limiter,
    api_key_rate_limiter,
    generate_csrf_token,
    validate_csrf_token,
    check_password_config_warnings,
)
from storage import storage, compute_status
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

def get_system_weather():
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["timestamp"] < 600):
        return _weather_cache["data"]

    # Default to Mumbai campus location (coordinates 19.0760 N, 72.8777 E)
    city = os.environ.get("CAMPUS_CITY", "MUMBAI").strip() or "MUMBAI"
    lat = float(os.environ.get("CAMPUS_LAT", 19.0760) or 19.0760)
    lon = float(os.environ.get("CAMPUS_LON", 72.8777) or 72.8777)

    temp = "30\u00b0C"
    icon = "\u2600\ufe0f"
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
        req = urllib.request.Request(url, headers={"User-Agent": "VNotice/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            w_data = json.loads(r.read().decode("utf-8", "ignore"))
            if "current" in w_data:
                raw_temp = round(w_data["current"]["temperature_2m"])
                temp = f"{raw_temp}\u00b0C"
                code = w_data["current"]["weather_code"]
                icons = {
                    0: "\u2600\ufe0f",
                    1: "\U0001f324\ufe0f",
                    2: "\u26c5",
                    3: "\u2601\ufe0f",
                    45: "\U0001f32b\ufe0f",
                    48: "\U0001f32b\ufe0f",
                    51: "\U0001f326\ufe0f",
                    53: "\U0001f327\ufe0f",
                    55: "\U0001f327\ufe0f",
                    61: "\U0001f327\ufe0f",
                    63: "\U0001f327\ufe0f",
                    65: "\u26c8\ufe0f",
                    71: "\U0001f328\ufe0f",
                    80: "\U0001f326\ufe0f",
                    81: "\U0001f327\ufe0f",
                    82: "\u26c8\ufe0f",
                    95: "\u26a1"
                }
                icon = icons.get(code, "\u2600\ufe0f")
    except Exception:
        pass

    result = {
        "city": city.upper(),
        "temp": temp,
        "icon": icon,
        "lan_ip": get_lan_ip(),
        "display_port": DISPLAY_PORT
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
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "font-src 'self'; "
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

    @app.teardown_appcontext
    def teardown_db(exception=None):
        storage.close_connection()

    @app.route("/")
    def index():
        return render_template("display.html")

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
        return jsonify([sanitize_public_notice(n) for n in active])

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        return jsonify({"success": True, "screens": storage.get_screens()})

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
        return jsonify({"status": "ok", "app": "vnotice-display", "port": DISPLAY_PORT})

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

    @app.route("/")
    def index():
        return render_template("admin.html")

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.route("/display")
    def to_display():
        host = request.host.split(":")[0]
        return redirect(f"http://{host}:{DISPLAY_PORT}/")

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
        password = data.get("password", "")
        if verify_admin_password(password):
            login_rate_limiter.record_success(ip)
            session["is_admin"] = True
            token = generate_csrf_token()
            session["csrf_token"] = token
            return jsonify({"success": True, "message": "Authentication successful", "csrf_token": token})
        else:
            login_rate_limiter.record_failure(ip)
            return jsonify({"success": False, "error": "Invalid password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("is_admin", None)
        session.pop("csrf_token", None)
        return jsonify({"success": True})

    @app.route("/api/screens", methods=["GET"])
    @read_admin_required
    def get_screens():
        return jsonify({"success": True, "screens": storage.get_screens()})

    @app.route("/api/notices", methods=["GET"])
    @read_admin_required
    def get_all_notices():
        screen = request.args.get("screen") or request.args.get("screen_id")
        notices = storage.get_all(screen_id=screen)
        return jsonify(notices)

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

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        try:
            creator = form_data.get("created_by") or "admin"
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator)
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

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        try:
            updater = form_data.get("created_by") or "admin"
            updated = storage.update(notice_id, form_data, file_obj=file_obj, updated_by=updater)
            if not updated:
                return jsonify({"error": "Notice not found"}), 404
            return jsonify(updated), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to update notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @mutation_admin_required
    def delete_notice(notice_id):
        success = storage.delete(notice_id, actor="admin")
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
        return jsonify({"status": "ok", "app": "vnotice-admin", "port": ADMIN_PORT})

    return app

# ==============================================================================
# UNIFIED CLOUD APP (Mode A: Render / Railway single $PORT)
# ==============================================================================
def create_unified_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    configure_app_security(app)

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
        return render_template("display.html")

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
        password = data.get("password", "")
        if verify_admin_password(password):
            login_rate_limiter.record_success(ip)
            session["is_admin"] = True
            token = generate_csrf_token()
            session["csrf_token"] = token
            return jsonify({"success": True, "message": "Authentication successful", "csrf_token": token})
        else:
            login_rate_limiter.record_failure(ip)
            return jsonify({"success": False, "error": "Invalid password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("is_admin", None)
        session.pop("csrf_token", None)
        return jsonify({"success": True})

    @app.route("/api/screens", methods=["GET"])
    def get_screens():
        return jsonify({"success": True, "screens": storage.get_screens()})

    # Smart Dual Notices API: Admin gets all notices; Public gets active only
    @app.route("/api/notices", methods=["GET"])
    def get_notices():
        screen = request.args.get("screen") or request.args.get("screen_id")
        if check_admin_auth():
            return jsonify(storage.get_all(screen_id=screen))
        # Public kiosk view: active notices only with admin fields stripped
        active = storage.get_active(screen_id=screen)
        return jsonify([sanitize_public_notice(n) for n in active])

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

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        try:
            creator = form_data.get("created_by") or "admin"
            notice = storage.add(form_data, file_obj=file_obj, created_by=creator)
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

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        try:
            updater = form_data.get("created_by") or "admin"
            updated = storage.update(notice_id, form_data, file_obj=file_obj, updated_by=updater)
            if not updated:
                return jsonify({"error": "Notice not found"}), 404
            return jsonify(updated), 200
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to update notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @mutation_admin_required
    def delete_notice(notice_id):
        success = storage.delete(notice_id, actor="admin")
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
        return jsonify({"status": "ok", "app": "vnotice-unified", "notices_count": len(storage.get_all())})

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
