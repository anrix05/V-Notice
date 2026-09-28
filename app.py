import os
import sys
import threading
from functools import wraps
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory,
    session,
    redirect,
    url_for,
)
from werkzeug.serving import run_simple
from config import (
    ADMIN_PASSWORD,
    DISPLAY_PORT,
    ADMIN_PORT,
    MEDIA_FOLDER,
    MAX_CONTENT_LENGTH,
)
from storage import storage

def create_display_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.urandom(24)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

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
        active_notices = storage.get_active()
        return jsonify(active_notices)

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        return send_from_directory(MEDIA_FOLDER, filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "app": "vnotice-display", "port": DISPLAY_PORT})

    return app

def check_admin_auth():
    # Check X-Password header or session
    auth_header = request.headers.get("X-Password")
    if auth_header and auth_header == ADMIN_PASSWORD:
        return True
    if session.get("is_admin") is True:
        return True
    return False

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not check_admin_auth():
            return jsonify({"error": "Unauthorized. Invalid or missing admin password."}), 401
        return f(*args, **kwargs)
    return decorated_function

def create_admin_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.urandom(24)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["TEMPLATES_AUTO_RELOAD"] = True

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

    @app.route("/api/login", methods=["POST"])
    def login():
        data = request.get_json(silent=True) or request.form
        password = data.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return jsonify({"success": True, "message": "Authentication successful"})
        return jsonify({"success": False, "error": "Invalid password"}), 401

    @app.route("/api/logout", methods=["POST"])
    def logout():
        session.pop("is_admin", None)
        return jsonify({"success": True})

    @app.route("/api/notices", methods=["GET"])
    @admin_required
    def get_all_notices():
        notices = storage.get_all()
        return jsonify(notices)

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File exceeds the 200 MB maximum upload limit."}), 413

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({"error": "An internal server error occurred. Please try again."}), 500

    @app.route("/api/notices", methods=["POST"])
    @admin_required
    def create_notice():
        form_data = request.form.to_dict()
        file_obj = request.files.get("media_file")
        
        # In case client sends json without file
        if not form_data and request.is_json:
            form_data = request.get_json()

        title = form_data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Notice title/headline is required"}), 400

        try:
            notice = storage.add(form_data, file_obj=file_obj)
            return jsonify(notice), 201
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to publish notice: {str(e)}"}), 500

    @app.route("/api/notices/<notice_id>", methods=["DELETE"])
    @admin_required
    def delete_notice(notice_id):
        success = storage.delete(notice_id)
        if success:
            return jsonify({"success": True, "id": notice_id})
        return jsonify({"error": "Notice not found"}), 404

    @app.route("/media/<path:filename>")
    def serve_media(filename):
        return send_from_directory(MEDIA_FOLDER, filename)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok", "app": "vnotice-admin", "port": ADMIN_PORT})

    return app

display_app = create_display_app()
admin_app = create_admin_app()

def run_display_server():
    print(f"[*] Starting V Notice Display on http://0.0.0.0:{DISPLAY_PORT}")
    run_simple("0.0.0.0", DISPLAY_PORT, display_app, use_reloader=False, threaded=True)

def run_admin_server():
    print(f"[*] Starting V Notice Admin on http://0.0.0.0:{ADMIN_PORT}")
    run_simple("0.0.0.0", ADMIN_PORT, admin_app, use_reloader=False, threaded=True)

if __name__ == "__main__":
    print("=" * 60)
    print("            V NOTICE - SMART DIGITAL NOTICE BOARD          ")
    print("=" * 60)
    print(f"Display Interface:  http://localhost:{DISPLAY_PORT}")
    print(f"Admin Interface:    http://localhost:{ADMIN_PORT}")
    print(f"Default Admin Pass: {ADMIN_PASSWORD}")
    print("=" * 60)

    # Start admin server in background thread
    admin_thread = threading.Thread(target=run_admin_server, daemon=True)
    admin_thread.start()

    # Start display server in main thread
    try:
        run_display_server()
    except KeyboardInterrupt:
        print("\n[!] Shutting down V Notice servers...")
        sys.exit(0)
