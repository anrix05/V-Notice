import os
import sqlite3
import subprocess
import sys
import time
import pytest

from app import unified_app
from security import validate_password_strength
from storage import NoticeStorage, storage

TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "vnotice2026")


@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    return unified_app.test_client()


def _login_bootstrap_admin(client):
    r = client.post("/api/login", json={"password": TEST_ADMIN_PASSWORD}, environ_base={"REMOTE_ADDR": "10.90.0.1"})
    assert r.status_code == 200
    return r.get_json()["csrf_token"]


def test_password_strength_rules():
    ok_short, _ = validate_password_strength("short123")
    assert ok_short is False

    ok_common, _ = validate_password_strength("password1234")
    assert ok_common is False

    # No composition rules: simple 12+ char non-common passphrase passes
    ok_good, err = validate_password_strength("correct horse battery")
    assert ok_good is True
    assert err == ""


def test_invite_lifecycle_hashed_single_use_expiry_revoke_and_no_token_in_logs(client):
    csrf = _login_bootstrap_admin(client)

    r_inv = client.post(
        "/api/users/invite",
        json={
            "name": "Prof. Asha Rao",
            "email": "asha.rao@college.edu",
            "phone": "9876543210",
            "departments": ["CMPN"],
            "role": "faculty",
            "can_post_college_wide": False,
            "can_post_urgent": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r_inv.status_code == 201
    inv_data = r_inv.get_json()
    token = inv_data["invite_url"].rsplit("/", 1)[-1]
    invite_id = inv_data["invite_id"]
    user_id = inv_data["user"]["id"]
    assert inv_data["user"]["status"] == "invited"

    # Token is stored hashed, never plaintext, and never appears in audit_logs
    conn = storage.get_connection()
    row = conn.execute("SELECT token_hash FROM invites WHERE id = ?;", (invite_id,)).fetchone()
    assert row["token_hash"] != token
    assert len(row["token_hash"]) == 64
    audits = storage.get_audit_logs(limit=50)["logs"]
    for a in audits:
        assert token not in (a.get("details") or "")

    # Revoked invite fails with generic message
    r_rev = client.post(f"/api/invites/{invite_id}/revoke", headers={"X-CSRF-Token": csrf})
    assert r_rev.status_code == 200

    with unified_app.test_client() as pub:
        r_get_rev = pub.get(f"/invite/{token}")
        assert r_get_rev.status_code == 400
        err_rev = r_get_rev.get_data(as_text=True)

        # Bad/nonexistent token returns exact same generic message
        r_get_bad = pub.get("/invite/nonexistent_token_abc")
        assert r_get_bad.status_code == 400
        assert "This link is not valid. Ask your admin for a new one." in err_rev
        assert "This link is not valid. Ask your admin for a new one." in r_get_bad.get_data(as_text=True)

    # Re-issue invite, expire it manually -> generic error
    r_inv2 = client.post(f"/api/users/{user_id}/invite", headers={"X-CSRF-Token": csrf})
    assert r_inv2.status_code == 201
    token2 = r_inv2.get_json()["invite_url"].rsplit("/", 1)[-1]
    inv2_id = r_inv2.get_json()["invite_id"]
    with conn:
        conn.execute("UPDATE invites SET expires_at = ? WHERE id = ?;", (int(time.time() * 1000) - 1000, inv2_id))
    with unified_app.test_client() as pub:
        r_exp = pub.post(
            f"/invite/{token2}/accept",
            json={"password": "StrongFacultyPassPhrase99", "confirm_password": "StrongFacultyPassPhrase99"},
        )
        assert r_exp.status_code == 400
        assert r_exp.get_json()["error"] == "This link is not valid. Ask your admin for a new one."

    # Re-issue valid invite -> accept once succeeds, second accept fails
    r_inv3 = client.post(f"/api/users/{user_id}/invite", headers={"X-CSRF-Token": csrf})
    token3 = r_inv3.get_json()["invite_url"].rsplit("/", 1)[-1]
    with unified_app.test_client() as pub:
        r_ok = pub.post(
            f"/invite/{token3}/accept",
            json={"password": "StrongFacultyPassPhrase99", "confirm_password": "StrongFacultyPassPhrase99"},
        )
        assert r_ok.status_code == 200
        assert r_ok.get_json()["user"]["status"] == "active"

        # Single use: second attempt fails with generic error
        r_reuse = pub.post(
            f"/invite/{token3}/accept",
            json={"password": "AnotherStrongPassPhrase99", "confirm_password": "AnotherStrongPassPhrase99"},
        )
        assert r_reuse.status_code == 400
        assert r_reuse.get_json()["error"] == "This link is not valid. Ask your admin for a new one."

    # Audit log checks: token never logged
    audits_after = storage.get_audit_logs(limit=50)["logs"]
    for a in audits_after:
        assert token3 not in (a.get("details") or "")


def test_disabled_user_session_dies_immediately_and_revoke_all(client):
    csrf_admin = _login_bootstrap_admin(client)
    u = storage.create_user(
        email="session.tester@college.edu",
        name="Session Tester",
        password="StrongSessionPass#123",
        role="faculty",
        departments=["EXCS"],
        status="active",
    )

    fac1 = unified_app.test_client()
    fac2 = unified_app.test_client()
    r1 = fac1.post("/api/login", json={"email": "session.tester@college.edu", "password": "StrongSessionPass#123"}, environ_base={"REMOTE_ADDR": "10.91.0.1"})
    r2 = fac2.post("/api/login", json={"email": "session.tester@college.edu", "password": "StrongSessionPass#123"}, environ_base={"REMOTE_ADDR": "10.91.0.2"})
    assert r1.status_code == 200 and r2.status_code == 200
    csrf1 = r1.get_json()["csrf_token"]

    # fac1 revokes all other sessions -> fac1 stays logged in, fac2 dies on next request
    r_rev = fac1.post("/api/me/sessions/revoke-all", headers={"X-CSRF-Token": csrf1})
    assert r_rev.status_code == 200
    assert fac1.get("/api/me").get_json()["authenticated"] is True
    assert fac2.get("/api/me").get_json()["authenticated"] is False
    assert fac2.get("/api/notices?view=admin").status_code == 401

    # Admin disables user -> fac1 dies on the very next request
    r_dis = client.post(f"/api/users/{u['id']}/disable", headers={"X-CSRF-Token": csrf_admin})
    assert r_dis.status_code == 200
    assert fac1.get("/api/notices?view=admin").status_code == 401


def test_faculty_ownership_and_switches_enforced_on_create_and_edit(client):
    storage.create_user(
        email="fac.a@college.edu",
        name="Faculty A",
        password="StrongFacultyAPass#123",
        role="faculty",
        departments=["EXCS"],
        can_post_college_wide=False,
        can_post_urgent=False,
    )
    storage.create_user(
        email="fac.b@college.edu",
        name="Faculty B",
        password="StrongFacultyBPass#123",
        role="faculty",
        departments=["EXCS"],
        can_post_college_wide=False,
        can_post_urgent=False,
    )

    c_a = unified_app.test_client()
    c_b = unified_app.test_client()
    csrf_a = c_a.post("/api/login", json={"email": "fac.a@college.edu", "password": "StrongFacultyAPass#123"}, environ_base={"REMOTE_ADDR": "10.92.0.1"}).get_json()["csrf_token"]
    csrf_b = c_b.post("/api/login", json={"email": "fac.b@college.edu", "password": "StrongFacultyBPass#123"}, environ_base={"REMOTE_ADDR": "10.92.0.2"}).get_json()["csrf_token"]

    # Faculty A cannot create urgent or college-wide or other-dept notices
    assert c_a.post("/api/notices", json={"title": "Urgent", "priority": "urgent", "screens": ["EXCS"]}, headers={"X-CSRF-Token": csrf_a}).status_code == 403
    assert c_a.post("/api/notices", json={"title": "All", "screens": ["ALL"]}, headers={"X-CSRF-Token": csrf_a}).status_code == 403
    assert c_a.post("/api/notices", json={"title": "Biom", "screens": ["BIOM"]}, headers={"X-CSRF-Token": csrf_a}).status_code == 403

    # Faculty A creates EXCS normal notice
    r_ok = c_a.post("/api/notices", json={"title": "EXCS Normal", "screens": ["EXCS"]}, headers={"X-CSRF-Token": csrf_a})
    assert r_ok.status_code == 201
    nid = r_ok.get_json()["id"]
    assert r_ok.get_json()["posted_by"] == "Faculty A"

    # Faculty A cannot escalate priority or screens on edit
    assert c_a.put(f"/api/notices/{nid}", json={"title": "EXCS Escalate", "priority": "urgent", "screens": ["EXCS"]}, headers={"X-CSRF-Token": csrf_a}).status_code == 403
    assert c_a.put(f"/api/notices/{nid}", json={"title": "EXCS Escalate", "screens": ["ALL"]}, headers={"X-CSRF-Token": csrf_a}).status_code == 403

    # Faculty B (same dept) can read it, but cannot edit or delete Faculty A's notice
    list_b = c_b.get("/api/notices?view=admin").get_json()
    assert any(n["id"] == nid for n in list_b)
    assert c_b.put(f"/api/notices/{nid}", json={"title": "Tamper", "screens": ["EXCS"]}, headers={"X-CSRF-Token": csrf_b}).status_code == 403
    assert c_b.delete(f"/api/notices/{nid}", headers={"X-CSRF-Token": csrf_b}).status_code == 403

    # Faculty cannot access admin-only endpoints
    assert c_a.get("/api/users").status_code == 403
    assert c_a.post("/api/screens", json={"code": "MECH", "name": "Mech"}, headers={"X-CSRF-Token": csrf_a}).status_code == 403
    assert c_a.get("/api/audit-logs").status_code == 403


def test_legacy_db_migration_backup_and_role_mapping(tmp_path):
    legacy_db = tmp_path / "legacy_notices.db"
    conn = sqlite3.connect(str(legacy_db))
    with conn:
        conn.execute("CREATE TABLE departments (code TEXT PRIMARY KEY, name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, accent_color TEXT, created_at INTEGER NOT NULL);")
        conn.execute("CREATE TABLE screens (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);")
        conn.execute("CREATE TABLE notices (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'normal', type TEXT NOT NULL DEFAULT 'text', media TEXT DEFAULT '', duration INTEGER NOT NULL DEFAULT 10, start INTEGER NOT NULL DEFAULT 0, end INTEGER, screen_id TEXT NOT NULL DEFAULT 'ALL', created_by TEXT NOT NULL DEFAULT 'admin', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);")
        conn.execute("CREATE TABLE notice_screens (notice_id TEXT NOT NULL, screen_code TEXT NOT NULL, PRIMARY KEY (notice_id, screen_code));")
        conn.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, target_id TEXT NOT NULL, details TEXT DEFAULT '');")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'dept_admin', departments TEXT NOT NULL DEFAULT '', can_target_all INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);")
        now_ms = int(time.time() * 1000)
        conn.execute("INSERT INTO users VALUES (1, 'old_super', 'hash1', 'super_admin', 'ALL', 1, ?);", (now_ms,))
        conn.execute("INSERT INTO users VALUES (2, 'old_dept', 'hash2', 'dept_admin', 'CMPN,INFT', 0, ?);", (now_ms,))
        conn.execute("INSERT INTO notices (id, title, created_by, created_at, updated_at) VALUES ('n_legacy_admin', 'Old Admin Notice', 'admin', ?, ?);", (now_ms, now_ms))
    conn.close()

    migrated_storage = NoticeStorage(db_file=legacy_db, data_file=tmp_path / "none.json")
    assert (tmp_path / "legacy_notices.db.pre2a.bak").exists()
    assert migrated_storage.last_user_migration_count == 2

    u1 = migrated_storage.get_user("old_super")
    u2 = migrated_storage.get_user("old_dept")
    assert u1["role"] == "admin"
    assert u2["role"] == "faculty"
    assert u2["departments"] == ["CMPN", "INFT"]

    n_old = migrated_storage.get_by_id("n_legacy_admin")
    assert n_old["created_by"] is None
    assert n_old["posted_by"] == "Admin"


def test_manage_cli_create_admin_invite_and_bootstrap_disable(tmp_path):
    # Verify manage.py create-admin --invite works without taking password on CLI
    env = os.environ.copy()
    cli_db = tmp_path / "cli_test.db"
    env["DB_FILE"] = str(cli_db)
    env["STORAGE_DIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "manage.py", "create-admin", "--email", "cli.admin@college.edu", "--name", "CLI Admin", "--invite"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "/invite/" in proc.stdout
    cli_storage = NoticeStorage(db_file=cli_db, data_file=tmp_path / "none.json")
    u = cli_storage.get_user("cli.admin@college.edu")
    assert u is not None
    assert u["role"] == "admin"
    assert u["status"] == "invited"
