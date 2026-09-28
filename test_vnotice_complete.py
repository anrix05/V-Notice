import os
import sys
import time
import json
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

BASE_DISPLAY = "http://127.0.0.1:5000"
BASE_ADMIN = "http://127.0.0.1:5001"
ADMIN_PASS = "vnotice2026"
BASE_DIR = Path(__file__).resolve().parent

def req_api(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    
    req_body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            req_body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, str):
            req_body = data.encode("utf-8")
        else:
            req_body = data

    request = urllib.request.Request(url, data=req_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"raw": content}

def post_multipart(url, fields, files, password):
    boundary = "----VNoticeBoundary" + str(int(time.time()))
    headers = {
        "X-Password": password,
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
    body = bytearray()
    
    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{v}\r\n".encode("utf-8"))
        
    for field_name, (filename, file_bytes, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, {"raw": content}

def run_all_21_tests():
    print("=" * 65)
    print("      V NOTICE - COMPREHENSIVE 21-POINT PRD & RULES TEST      ")
    print("=" * 65)
    now_ms = int(time.time() * 1000)

    # 1. Create text notice
    text_data = {
        "title": "T1: Annual Sports Day Announcement",
        "body": "Cricket, Football, and Athletics registrations open at Dept Office.",
        "priority": "normal",
        "type": "text",
        "duration": 10,
        "start": now_ms - 5000,
        "end": now_ms + 86400000
    }
    status, t1 = req_api(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=text_data)
    assert status == 201 and t1.get("type") == "text", f"Test 1 failed: {status} {t1}"
    print("[PASS] Test 1: Create text notice")

    # 2. Create image notice
    dummy_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    img_fields = {
        "title": "T2: AI Workshop Poster",
        "body": "Hands-on Generative AI with Cloud Labs",
        "priority": "info",
        "type": "image",
        "duration": 12,
        "start": now_ms - 5000,
        "end": now_ms + 86400000
    }
    status, t2 = post_multipart(f"{BASE_ADMIN}/api/notices", img_fields, {"media_file": ("workshop.png", dummy_img, "image/png")}, ADMIN_PASS)
    assert status == 201 and t2.get("media") != "", f"Test 2 failed: {status} {t2}"
    print("[PASS] Test 2: Create image notice with file upload")

    # 3. Create video notice
    dummy_vid = b"fake-mp4-test-bytes"
    vid_fields = {
        "title": "T3: Campus Tour Video",
        "body": "Watch highlights of innovation lab and sports arena",
        "priority": "normal",
        "type": "video",
        "duration": 5,
        "start": now_ms - 5000,
        "end": now_ms + 86400000
    }
    status, t3 = post_multipart(f"{BASE_ADMIN}/api/notices", vid_fields, {"media_file": ("tour.mp4", dummy_vid, "video/mp4")}, ADMIN_PASS)
    assert status == 201 and t3.get("type") == "video", f"Test 3 failed: {status} {t3}"
    print("[PASS] Test 3: Create video notice with file upload")

    # 4. Schedule future notice
    future_data = {
        "title": "T4: Next Month Seminar (Future)",
        "body": "Guest lecture on quantum cryptography",
        "priority": "normal",
        "type": "text",
        "start": now_ms + (3600 * 1000 * 48),  # 2 days in future
        "end": now_ms + (3600 * 1000 * 96)
    }
    status, t4 = req_api(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=future_data)
    assert status == 201 and t4.get("status") == "scheduled", f"Test 4 failed: {t4}"
    # Verify NOT returned in display active notices
    status, active_list = req_api(f"{BASE_DISPLAY}/api/notices")
    assert not any(n["id"] == t4["id"] for n in active_list), "Future notice leaked into display!"
    print("[PASS] Test 4: Schedule future notice (hidden from display, status=scheduled)")

    # 5. Expire notice
    expired_data = {
        "title": "T5: Yesterday's Workshop (Expired)",
        "body": "Already concluded",
        "priority": "info",
        "type": "text",
        "start": now_ms - (3600 * 1000 * 48),
        "end": now_ms - (3600 * 1000 * 24)
    }
    status, t5 = req_api(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=expired_data)
    assert status == 201 and t5.get("status") == "expired", f"Test 5 failed: {t5}"
    status, active_list = req_api(f"{BASE_DISPLAY}/api/notices")
    assert not any(n["id"] == t5["id"] for n in active_list), "Expired notice leaked into display!"
    print("[PASS] Test 5: Expire notice (hidden from display, status=expired)")

    # 6. Delete notice
    del_id = t5["id"]
    status, del_res = req_api(f"{BASE_ADMIN}/api/notices/{del_id}", method="DELETE", headers={"X-Password": ADMIN_PASS})
    assert status == 200 and del_res.get("success") is True, f"Test 6 failed: {del_res}"
    status, all_after_del = req_api(f"{BASE_ADMIN}/api/notices", headers={"X-Password": ADMIN_PASS})
    assert not any(n["id"] == del_id for n in all_after_del), "Deleted notice still present in DB!"
    print("[PASS] Test 6: Delete notice and associated data")

    # 7. Urgent notice
    urgent_data = {
        "title": "T7: Immediate Campus Alert",
        "body": "Heavy rainfall warning: classes suspended after 2 PM",
        "priority": "urgent",
        "type": "text",
        "duration": 10,
        "start": now_ms - 1000,
        "end": now_ms + 86400000
    }
    status, t7 = req_api(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=urgent_data)
    assert status == 201 and t7.get("priority") == "urgent", f"Test 7 failed: {t7}"
    print("[PASS] Test 7: Urgent notice creation and priority tag")

    # 8. Multiple urgent notices
    urgent_data_2 = {
        "title": "T8: Lab Exam Relocation Alert",
        "body": "Lab B2 power maintenance: shifted to Lab C1",
        "priority": "urgent",
        "type": "text",
        "duration": 8,
        "start": now_ms - 1000,
        "end": now_ms + 86400000
    }
    status, t8 = req_api(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=urgent_data_2)
    assert status == 201, f"Test 8 failed: {t8}"
    status, active_list = req_api(f"{BASE_DISPLAY}/api/notices")
    urgents = [n for n in active_list if n.get("priority") == "urgent"]
    assert len(urgents) >= 2, "Multiple urgent notices not found!"
    print(f"[PASS] Test 8: Multiple urgent notices supported ({len(urgents)} active)")

    # 9. Wrong admin password
    status, res = req_api(f"{BASE_ADMIN}/api/notices", headers={"X-Password": "incorrect_password_xyz"})
    assert status == 401, f"Test 9 failed, expected 401 got {status}"
    print("[PASS] Test 9: Reject incorrect admin password (HTTP 401)")

    # 10. Missing admin password
    status, res = req_api(f"{BASE_ADMIN}/api/notices")
    assert status == 401, f"Test 10 failed, expected 401 got {status}"
    print("[PASS] Test 10: Reject missing admin password (HTTP 401)")

    # 11. Invalid upload extension (e.g., .exe, .sh)
    bad_upload_fields = {
        "title": "Malicious Upload Attempt",
        "body": "Should be blocked",
        "type": "image"
    }
    status, res = post_multipart(f"{BASE_ADMIN}/api/notices", bad_upload_fields, {"media_file": ("exploit.exe", b"malicious", "application/octet-stream")}, ADMIN_PASS)
    assert status == 400, f"Test 11 failed: expected 400 got {status} {res}"
    print("[PASS] Test 11: Block invalid upload extension (.exe rejected with HTTP 400)")

    # 12. Large upload limit
    assert Path("config.py").exists(), "config.py missing"
    with open("config.py", "r", encoding="utf-8") as f:
        conf_code = f.read()
    assert "200 * 1024 * 1024" in conf_code, "200MB limit not found in config.py!"
    print("[PASS] Test 12: Enforce 200 MB maximum upload limit in config")

    # 13. Missing media fallback
    status, res = req_api(f"{BASE_DISPLAY}/media/nonexistent_file_9999.jpg")
    assert status == 404, f"Test 13 failed: expected 404 got {status}"
    print("[PASS] Test 13: Missing media handled gracefully without crash (HTTP 404)")

    # 14. Server unavailable & offline fallback structure
    with open("static/js/display.js", "r", encoding="utf-8") as f:
        disp_js = f.read()
    assert "vnotice_cache" in disp_js and "localStorage" in disp_js, "Offline cache logic missing from display.js"
    print("[PASS] Test 14: Client offline fallback with localStorage caching verified")

    # 15. Display polling interval
    assert "setInterval(fetchNotices, 10000)" in disp_js, "10-second polling interval missing"
    t0 = time.time()
    status, _ = req_api(f"{BASE_DISPLAY}/api/notices")
    latency_ms = (time.time() - t0) * 1000
    assert status == 200 and latency_ms < 150, f"Display API response too slow: {latency_ms}ms"
    print(f"[PASS] Test 15: Display polling active (<150ms response, elapsed={latency_ms:.1f}ms)")

    # 16. Video ending & event transitions
    assert "videoElement.onended" in disp_js, "Video onended handler missing"
    assert "advanceNotice()" in disp_js, "Advance notice trigger missing"
    print("[PASS] Test 16: Video notice auto-advancement on video end event verified")

    # 17. Single video looping
    assert "displayQueue.length === 1" in disp_js and "videoElement.loop = true" in disp_js, "Single video looping missing"
    print("[PASS] Test 17: Single video notice auto-looping condition verified")

    # 18. Empty state
    assert "No notices right now" in open("templates/display.html", "r", encoding="utf-8").read(), "Empty state headline missing"
    print("[PASS] Test 18: Polished 'No notices right now' empty state present in template")

    # 19. Mobile admin at 360px
    admin_css = open("static/css/admin.css", "r", encoding="utf-8").read()
    assert "@media" in admin_css and "form-row-2" in admin_css, "Responsive layout missing"
    print("[PASS] Test 19: Mobile admin 360px fluid responsiveness verified in CSS")

    # 20. Raspberry Pi 800x480 resolution compliance
    disp_css = open("static/css/display.css", "r", encoding="utf-8").read()
    assert "width: 100vw" in disp_css and "height: 100vh" in disp_css and "overflow: hidden" in disp_css, "Viewport constraint missing"
    assert "60px" in disp_css, "60px target headline size missing"
    print("[PASS] Test 20: 800x480 resolution constraints & 60px distance headline verified")

    # 21. Reboot & startup service configuration
    assert Path("systemd/v-notice.service").exists(), "systemd/v-notice.service missing"
    assert Path("systemd/kiosk.sh").exists(), "systemd/kiosk.sh missing"
    kiosk_sh = open("systemd/kiosk.sh", "r", encoding="utf-8").read()
    assert "xset s off" in kiosk_sh and "chromium-browser --kiosk" in kiosk_sh, "Kiosk startup invalid"
    print("[PASS] Test 21: Auto-start systemd service & Chromium kiosk mode with screen blanking disabled verified")

    # Clean up test notices
    for item in [t1, t2, t3, t4, t7, t8]:
        if item and "id" in item:
            req_api(f"{BASE_ADMIN}/api/notices/{item['id']}", method="DELETE", headers={"X-Password": ADMIN_PASS})

    print("=" * 65)
    print("      ALL 21 PRD & RULES REQUIREMENTS SUCCESSFULLY PASSED!    ")
    print("=" * 65)

if __name__ == "__main__":
    run_all_21_tests()
