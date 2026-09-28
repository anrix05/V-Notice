import urllib.request
import urllib.error
import urllib.parse
import json
import time

BASE_DISPLAY = "http://127.0.0.1:5000"
BASE_ADMIN = "http://127.0.0.1:5001"
ADMIN_PASS = "vnotice2026"

def request_json(url, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    
    req_data = None
    if data is not None:
        if isinstance(data, (dict, list)):
            req_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, str):
            req_data = data.encode("utf-8")
        else:
            req_data = data

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
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

def test_suite():
    print("==================================================")
    print("       V NOTICE PRD AUTOMATED VERIFICATION       ")
    print("==================================================")

    # 1. Health checks
    status, res = request_json(f"{BASE_DISPLAY}/api/health")
    assert status == 200 and res.get("status") == "ok", f"Display health failed: {status} {res}"
    print("[OK] [1/9] Display Server Health (Port 5000): OK")

    status, res = request_json(f"{BASE_ADMIN}/api/health")
    assert status == 200 and res.get("status") == "ok", f"Admin health failed: {status} {res}"
    print("[OK] [2/9] Admin Server Health (Port 5001): OK")

    # 2. Display API active notices
    status, notices = request_json(f"{BASE_DISPLAY}/api/notices")
    assert status == 200 and isinstance(notices, list), f"Display notices failed: {status} {notices}"
    print(f"[OK] [3/9] Display GET /api/notices returns {len(notices)} active notices without auth: OK")

    # 3. Admin API auth check (401 without password)
    status, res = request_json(f"{BASE_ADMIN}/api/notices")
    assert status == 401, f"Expected 401 for unauthenticated admin access, got {status}"
    print("[OK] [4/9] Admin GET /api/notices blocks unauthorized requests (401): OK")

    # 4. Admin API login endpoint
    status, res = request_json(f"{BASE_ADMIN}/api/login", method="POST", data={"password": "wrongpassword"})
    assert status == 401, f"Expected 401 for wrong password, got {status}"
    status, res = request_json(f"{BASE_ADMIN}/api/login", method="POST", data={"password": ADMIN_PASS})
    assert status == 200 and res.get("success") is True, f"Admin login failed: {status} {res}"
    print("[OK] [5/9] Admin POST /api/login validates password correctly: OK")

    # 5. Admin GET /api/notices with X-Password header
    status, all_notices = request_json(f"{BASE_ADMIN}/api/notices", headers={"X-Password": ADMIN_PASS})
    assert status == 200 and isinstance(all_notices, list), f"Admin GET /api/notices failed: {status}"
    for n in all_notices:
        assert "status" in n, f"Notice missing status field: {n}"
        assert n["status"] in ("live", "scheduled", "expired"), f"Invalid status: {n['status']}"
    print(f"[OK] [6/9] Admin GET /api/notices returns all notices with computed status: OK")

    # 6. Admin POST /api/notices (Create notice)
    new_notice_data = {
        "title": "Automated MCA Test Announcement",
        "body": "Verification of instant notice publication to Raspberry Pi display.",
        "priority": "urgent",
        "type": "text",
        "duration": 15,
        "start": int(time.time() * 1000) - 1000,
        "end": int(time.time() * 1000) + 3600000
    }
    status, created = request_json(f"{BASE_ADMIN}/api/notices", method="POST", headers={"X-Password": ADMIN_PASS}, data=new_notice_data)
    assert status == 201 and "id" in created, f"Create notice failed: {status} {created}"
    created_id = created["id"]
    print(f"[OK] [7/9] Admin POST /api/notices creates notice id={created_id}: OK")

    # 7. Check if created notice appears in active display notices
    status, active_notices = request_json(f"{BASE_DISPLAY}/api/notices")
    found = any(n["id"] == created_id for n in active_notices)
    assert found, "Newly created notice not found in Display active notices list!"
    print(f"[OK] [8/9] Newly published notice immediately visible on Display site: OK")

    # 8. Delete notice
    status, del_res = request_json(f"{BASE_ADMIN}/api/notices/{created_id}", method="DELETE", headers={"X-Password": ADMIN_PASS})
    assert status == 200 and del_res.get("success") is True, f"Delete failed: {status} {del_res}"
    
    status, active_notices_after = request_json(f"{BASE_DISPLAY}/api/notices")
    assert not any(n["id"] == created_id for n in active_notices_after), "Deleted notice still present!"
    print(f"[OK] [9/9] Admin DELETE /api/notices/<id> successfully deletes notice: OK")

    print("\n==================================================")
    print("       ALL 9 PRD INTEGRATION TESTS PASSED!       ")
    print("==================================================")

if __name__ == "__main__":
    test_suite()
