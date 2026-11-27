import os
import io
import time
import pytest
from werkzeug.security import generate_password_hash
from security import (
    verify_admin_password,
    RateLimiter,
    sniff_media_type,
    generate_notice_id,
    generate_csrf_token,
    validate_csrf_token,
)
from app import unified_app
from storage import storage

TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "vnotice2026")

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_password_verification(monkeypatch):
    # Plaintext fallback check
    assert verify_admin_password(TEST_ADMIN_PASSWORD) is True
    assert verify_admin_password("wrongpass_random_xyz") is False

    # Hashed password check
    hashed = generate_password_hash("temp_hashed_secret_123")
    monkeypatch.setattr("security.ADMIN_PASSWORD_HASH", hashed)
    assert verify_admin_password("temp_hashed_secret_123") is True
    assert verify_admin_password(TEST_ADMIN_PASSWORD) is False

def test_rate_limiter_lockout():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    ip = "192.168.1.100"

    assert limiter.is_locked(ip)[0] is False
    limiter.record_failure(ip)
    limiter.record_failure(ip)
    assert limiter.is_locked(ip)[0] is False

    # 3rd failure triggers lockout
    limiter.record_failure(ip)
    locked, retry_after = limiter.is_locked(ip)
    assert locked is True
    assert retry_after > 0

    # Success clears lockout
    limiter.record_success(ip)
    assert limiter.is_locked(ip)[0] is False

def test_magic_byte_sniffing():
    # Valid PNG header
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert sniff_media_type(png_bytes) == ("png", "image")

    # Valid JPEG header
    jpg_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01"
    assert sniff_media_type(jpg_bytes) == ("jpg", "image")

    # Valid GIF header
    gif_bytes = b"GIF89a\x01\x00\x01\x00"
    assert sniff_media_type(gif_bytes) == ("gif", "image")

    # Spoofed file (text pretending to be image)
    spoofed = b"This is just plain text masquerading as PNG."
    assert sniff_media_type(spoofed) is None

def test_random_urlsafe_ids():
    id1 = generate_notice_id()
    id2 = generate_notice_id()
    assert id1 != id2
    assert len(id1) >= 8
    # URL-safe check
    for ch in id1:
        assert ch.isalnum() or ch in ("-", "_")

def test_login_rate_limiting_api(client):
    unique_ip = "10.99.88.77"
    for _ in range(5):
        r = client.post(
            "/api/login",
            json={"username": "rl_user_ip", "password": "badpassword"},
            environ_base={"REMOTE_ADDR": unique_ip}
        )
        assert r.status_code == 401

    # 6th attempt must return 429 Too Many Requests
    r_locked = client.post(
        "/api/login",
        json={"username": "rl_user_ip", "password": "badpassword"},
        environ_base={"REMOTE_ADDR": unique_ip}
    )
    assert r_locked.status_code == 429
    assert "Retry-After" in r_locked.headers
    assert r_locked.get_json()["retry_after"] > 0

def test_session_csrf_protection(client):
    # 1. Login with session
    r_login = client.post("/api/login", json={"password": TEST_ADMIN_PASSWORD})
    assert r_login.status_code == 200
    csrf_token = r_login.get_json()["csrf_token"]
    assert csrf_token is not None

    # 2. Mutation without CSRF token -> 403 Forbidden
    r_no_csrf = client.post("/api/notices", data={"title": "Should Fail Without CSRF"})
    assert r_no_csrf.status_code == 403
    assert "CSRF" in r_no_csrf.get_json()["error"]

    # 3. Mutation with valid CSRF token -> 201 Created
    r_valid_csrf = client.post(
        "/api/notices",
        data={"title": "Valid CSRF Notice", "screen_id": "default"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert r_valid_csrf.status_code == 201
    notice_id = r_valid_csrf.get_json()["id"]

    # 4. Mutation with X-Password -> 200/201 (CSRF exempt)
    r_api_key = client.post(
        "/api/notices",
        data={"title": "Exempt API Key Notice", "screen_id": "default"},
        headers={"X-Password": TEST_ADMIN_PASSWORD}
    )
    assert r_api_key.status_code == 201

def test_enumeration_protection(client):
    # Create expired notice directly in storage
    now = int(time.time() * 1000)
    expired = storage.add({
        "title": "Old Expired Notice",
        "start": now - 100000,
        "end": now - 50000,
    })
    n_id = expired["id"]

    # Unauthenticated viewer: /notice/<id> redirects (301) to /n/<id> which must return 404
    r_public = client.get(f"/notice/{n_id}", follow_redirects=True)
    assert r_public.status_code == 404

    # Authenticated admin: /notice/<id> redirects (301) to /n/<id> which returns 200
    r_admin = client.get(f"/notice/{n_id}", headers={"X-Password": TEST_ADMIN_PASSWORD}, follow_redirects=True)
    assert r_admin.status_code == 200

def test_spoofed_upload_rejected(client):
    # Upload file with .png extension but text content
    fake_png = io.BytesIO(b"Hello world, I am not a real image!")
    data = {
        "title": "Spoofed Upload Test",
        "media_file": (fake_png, "spoofed.png", "image/png")
    }
    r = client.post("/api/notices", data=data, headers={"X-Password": TEST_ADMIN_PASSWORD})
    assert r.status_code == 400
    assert "format" in r.get_json()["error"].lower()

def test_security_headers(client):
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in r.headers.get("Content-Security-Policy", "")
    assert r.headers.get("X-Frame-Options") == "DENY"

def test_public_notice_leak_prevention(client):
    r_public = client.get("/api/notices")
    assert r_public.status_code == 200
    items = r_public.get_json()
    assert isinstance(items, list)
    for item in items:
        assert "created_by" not in item
        assert "updated_at" not in item

def test_audit_log_recording(client):
    # Create notice
    r_create = client.post(
        "/api/notices",
        data={"title": "Audited Announcement", "created_by": "prof_rao"},
        headers={"X-Password": TEST_ADMIN_PASSWORD}
    )
    assert r_create.status_code == 201
    nid = r_create.get_json()["id"]

    # Delete notice
    r_del = client.delete(f"/api/notices/{nid}", headers={"X-Password": TEST_ADMIN_PASSWORD})
    assert r_del.status_code == 200

    # Fetch audit logs
    r_audit = client.get("/api/audit-logs", headers={"X-Password": TEST_ADMIN_PASSWORD})
    assert r_audit.status_code == 200
    logs = r_audit.get_json()["audit_logs"]
    actions = [l["action"] for l in logs if l["target_id"] == nid]
    assert "CREATE" in actions
    assert "DELETE" in actions


def test_spoofed_x_forwarded_for_does_not_reset_rate_limit(client):
    real_ip = "10.20.30.40"
    for i in range(5):
        r = client.post(
            "/api/login",
            json={"username": f"spoof_u_{i}", "password": "badpassword"},
            headers={"X-Forwarded-For": f"198.51.100.{i + 1}"},
            environ_base={"REMOTE_ADDR": real_ip},
        )
        assert r.status_code == 401

    # Spoofing a brand-new X-Forwarded-For must still hit 429 for the same REMOTE_ADDR
    r_locked = client.post(
        "/api/login",
        json={"username": "spoof_u_99", "password": "badpassword"},
        headers={"X-Forwarded-For": "203.0.113.250"},
        environ_base={"REMOTE_ADDR": real_ip},
    )
    assert r_locked.status_code == 429


def test_account_throttling_growing_delays_and_uniform_error(client):
    # Same error message for wrong admin password vs nonexistent user
    r_bad_admin = client.post(
        "/api/login",
        json={"username": "admin", "password": "wrong_password_1"},
        environ_base={"REMOTE_ADDR": "10.50.0.1"},
    )
    r_bad_user = client.post(
        "/api/login",
        json={"username": "nonexistent_user_xyz", "password": "wrong_password_1"},
        environ_base={"REMOTE_ADDR": "10.50.0.2"},
    )
    assert r_bad_admin.status_code == 401
    assert r_bad_user.status_code == 401
    assert r_bad_admin.get_json()["error"] == r_bad_user.get_json()["error"]

    # Account throttling across different IPs
    target_acct = "throttled_acct_test"
    for i in range(5):
        r = client.post(
            "/api/login",
            json={"username": target_acct, "password": "badpassword"},
            environ_base={"REMOTE_ADDR": f"10.51.0.{i + 10}"},
        )
        assert r.status_code == 401

    r_acct_locked = client.post(
        "/api/login",
        json={"username": target_acct, "password": "badpassword"},
        environ_base={"REMOTE_ADDR": "10.51.0.99"},
    )
    assert r_acct_locked.status_code == 429

    # Growing delays in RateLimiter
    limiter = RateLimiter(max_attempts=2, window_seconds=300, base_delay_seconds=10, max_delay_seconds=120)
    assert limiter.record_failure("k1") == 0
    d1 = limiter.record_failure("k1")
    d2 = limiter.record_failure("k1")
    d3 = limiter.record_failure("k1")
    assert d1 == 10
    assert d2 == 20
    assert d3 == 40


def test_invalid_x_password_falls_back_to_session_and_api_key_flag(client, monkeypatch):
    # Login via session
    r_login = client.post(
        "/api/login",
        json={"password": TEST_ADMIN_PASSWORD},
        environ_base={"REMOTE_ADDR": "10.60.0.1"},
    )
    assert r_login.status_code == 200
    csrf_token = r_login.get_json()["csrf_token"]

    # Invalid X-Password header present, but valid session exists -> falls back to session
    r_get = client.get(
        "/api/audit-logs",
        headers={"X-Password": "invalid_header_pw"},
        environ_base={"REMOTE_ADDR": "10.60.0.1"},
    )
    assert r_get.status_code == 200

    r_post = client.post(
        "/api/notices",
        data={"title": "Session Fallback Notice"},
        headers={"X-Password": "invalid_header_pw", "X-CSRF-Token": csrf_token},
        environ_base={"REMOTE_ADDR": "10.60.0.1"},
    )
    assert r_post.status_code == 201

    # When ALLOW_API_KEY_AUTH=False, X-Password alone is rejected
    monkeypatch.setattr("config.ALLOW_API_KEY_AUTH", False)
    with unified_app.test_client() as anon_client:
        r_rejected = anon_client.get(
            "/api/audit-logs",
            headers={"X-Password": TEST_ADMIN_PASSWORD},
            environ_base={"REMOTE_ADDR": "10.60.0.2"},
        )
        assert r_rejected.status_code == 401


def test_session_lifetime_fixation_and_logout_csrf(client):
    from datetime import timedelta
    assert unified_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert unified_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert unified_app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=30)

    with client.session_transaction() as sess:
        sess["stale_key"] = "should_be_cleared"

    r_login = client.post(
        "/api/login",
        json={"password": TEST_ADMIN_PASSWORD},
        environ_base={"REMOTE_ADDR": "10.70.0.1"},
    )
    assert r_login.status_code == 200
    csrf_token = r_login.get_json()["csrf_token"]

    with client.session_transaction() as sess:
        assert "stale_key" not in sess
        assert sess.permanent is True
        assert sess.get("is_admin") is True
        # Admin session lifetime is 8 hours
        now_ms = int(time.time() * 1000)
        ttl_hours = (sess["expires_at"] - now_ms) / (3600 * 1000)
        assert 7.9 <= ttl_hours <= 8.1

    # Logout without CSRF fails when authenticated
    r_logout_no_csrf = client.post("/api/logout")
    assert r_logout_no_csrf.status_code == 403

    # Logout with CSRF succeeds and clears session
    r_logout = client.post("/api/logout", headers={"X-CSRF-Token": csrf_token})
    assert r_logout.status_code == 200
    with client.session_transaction() as sess:
        assert len(sess) == 0


def test_production_startup_secret_validation(monkeypatch, capsys):
    import config
    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "shortpw")

    with pytest.raises(SystemExit):
        config.validate_production_secrets(is_prod=True, allow_weak=False)
    err = capsys.readouterr().err
    assert "shortpw" not in err
    assert "short" in err or "SECRET_KEY" in err

    # With ALLOW_WEAK_SECRETS=true, logs warning instead of exiting
    ok, issues = config.validate_production_secrets(is_prod=True, allow_weak=True)
    assert ok is False
    assert len(issues) == 2

    # Strong secrets pass
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("ADMIN_PASSWORD", "StrongCampusPass#2026")
    ok_strong, issues_strong = config.validate_production_secrets(is_prod=True, allow_weak=False)
    assert ok_strong is True
    assert issues_strong == []
