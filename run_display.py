from app import display_app
from config import DISPLAY_PORT

if __name__ == "__main__":
    print(f"[*] Starting V Notice Display on http://0.0.0.0:{DISPLAY_PORT}")
    display_app.run(host="0.0.0.0", port=DISPLAY_PORT, debug=False, threaded=True)
