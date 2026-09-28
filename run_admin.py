from app import admin_app
from config import ADMIN_PORT

if __name__ == "__main__":
    print(f"[*] Starting V Notice Admin on http://0.0.0.0:{ADMIN_PORT}")
    admin_app.run(host="0.0.0.0", port=ADMIN_PORT, debug=False, threaded=True)
