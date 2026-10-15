import os
import pytest
from app import unified_app
from storage import storage

TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "vnotice2026")

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def get_csrf(client):
    res = client.get("/api/csrf-token")
    return res.get_json()["csrf_token"]

def test_user_creation_and_credential_verification():
    # Clean up test user if exists
    storage.delete_user("excs_tester")
    user = storage.create_user(
        username="excs_tester",
        password="securepassword123",
        role="dept_admin",
        departments=["EXCS"],
        can_target_all=False
    )
    assert user["username"] == "excs_tester"
    assert user["role"] == "dept_admin"
    assert "EXCS" in user["departments"]
    assert user["can_target_all"] is False

    # Check credential verification with hashed password
    verified = storage.verify_user_credentials("excs_tester", "securepassword123")
    assert verified is not None
    assert verified["username"] == "excs_tester"
    assert "password_hash" not in verified

    # Invalid password returns None
    invalid = storage.verify_user_credentials("excs_tester", "wrongpassword")
    assert invalid is None

def test_login_shared_password_as_super_admin(client):
    res = client.post("/api/login", json={"password": TEST_ADMIN_PASSWORD})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["user"]["role"] == "super_admin"

    # Verify /api/me
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.get_json()["role"] == "super_admin"

def test_login_per_user_dept_admin(client):
    storage.delete_user("excs_login_user")
    storage.create_user("excs_login_user", "mypassword456", role="dept_admin", departments=["EXCS"])

    # Attempt with bad password
    bad_res = client.post("/api/login", json={"username": "excs_login_user", "password": "wrong"})
    assert bad_res.status_code == 401

    # Attempt with good password
    good_res = client.post("/api/login", json={"username": "excs_login_user", "password": "mypassword456"})
    assert good_res.status_code == 200
    data = good_res.get_json()
    assert data["success"] is True
    assert data["user"]["username"] == "excs_login_user"
    assert data["user"]["role"] == "dept_admin"
    assert data["user"]["departments"] == ["EXCS"]

    # Verify /api/me
    me = client.get("/api/me")
    assert me.status_code == 200
    me_data = me.get_json()
    assert me_data["username"] == "excs_login_user"
    assert me_data["role"] == "dept_admin"

def test_dept_admin_cannot_target_all_without_permission(client):
    storage.delete_user("excs_author")
    storage.create_user("excs_author", "pass123", role="dept_admin", departments=["EXCS"], can_target_all=False)

    # Login as excs_author
    client.post("/api/login", json={"username": "excs_author", "password": "pass123"})
    csrf = get_csrf(client)

    # Attempt to broadcast to ALL
    res = client.post(
        "/api/notices",
        json={"title": "College-Wide Notice Attempt", "body": "Test", "screens": ["ALL"]},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 403
    assert "Permission denied" in res.get_json()["error"]

def test_dept_admin_cannot_target_other_departments(client):
    storage.delete_user("excs_author2")
    storage.create_user("excs_author2", "pass123", role="dept_admin", departments=["EXCS"], can_target_all=False)

    client.post("/api/login", json={"username": "excs_author2", "password": "pass123"})
    csrf = get_csrf(client)

    # Attempt to broadcast to BIOM
    res = client.post(
        "/api/notices",
        json={"title": "BIOM Notice Attempt", "body": "Test", "screens": ["BIOM"]},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 403
    assert "Permission denied" in res.get_json()["error"]

def test_dept_admin_can_target_own_department_and_records_created_by(client):
    storage.delete_user("excs_author3")
    storage.create_user("excs_author3", "pass123", role="dept_admin", departments=["EXCS"], can_target_all=False)

    client.post("/api/login", json={"username": "excs_author3", "password": "pass123"})
    csrf = get_csrf(client)

    res = client.post(
        "/api/notices",
        json={"title": "EXCS Lab Exam Notice", "body": "Lab exam details", "screens": ["EXCS"]},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 201
    notice = res.get_json()
    assert notice["title"] == "EXCS Lab Exam Notice"
    assert notice["created_by"] == "excs_author3"
    assert "EXCS" in notice["screens"]

def test_dept_admin_granted_all_can_broadcast_college_wide(client):
    storage.delete_user("trusted_dept_admin")
    storage.create_user("trusted_dept_admin", "pass123", role="dept_admin", departments=["EXCS"], can_target_all=True)

    client.post("/api/login", json={"username": "trusted_dept_admin", "password": "pass123"})
    csrf = get_csrf(client)

    res = client.post(
        "/api/notices",
        json={"title": "Permitted College Wide Notice", "body": "Approved", "screens": ["ALL"]},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 201
    notice = res.get_json()
    assert notice["created_by"] == "trusted_dept_admin"
    assert "ALL" in notice["screens"]

def test_dept_admin_cannot_edit_or_delete_outside_department(client):
    # Create a BIOM notice as super_admin
    client.post("/api/login", json={"password": TEST_ADMIN_PASSWORD})
    csrf = get_csrf(client)
    res_biom = client.post(
        "/api/notices",
        json={"title": "Biomedical Department Exclusive", "body": "Bio", "screens": ["BIOM"]},
        headers={"X-CSRF-Token": csrf}
    )
    biom_notice = res_biom.get_json()
    biom_id = biom_notice["id"]

    # Now login as an EXCS-only dept_admin
    storage.delete_user("excs_strict")
    storage.create_user("excs_strict", "pass123", role="dept_admin", departments=["EXCS"], can_target_all=False)
    client.post("/api/login", json={"username": "excs_strict", "password": "pass123"})
    csrf2 = get_csrf(client)

    # Attempt to edit the BIOM notice
    res_edit = client.put(
        f"/api/notices/{biom_id}",
        json={"title": "Tampered Title", "screens": ["BIOM"]},
        headers={"X-CSRF-Token": csrf2}
    )
    assert res_edit.status_code == 403
    assert "Permission denied" in res_edit.get_json()["error"]

    # Attempt to delete the BIOM notice
    res_del = client.delete(
        f"/api/notices/{biom_id}",
        headers={"X-CSRF-Token": csrf2}
    )
    assert res_del.status_code == 403
    assert "Permission denied" in res_del.get_json()["error"]

def test_dept_admin_cannot_manage_screens(client):
    storage.delete_user("excs_screen_test")
    storage.create_user("excs_screen_test", "pass123", role="dept_admin", departments=["EXCS"])
    client.post("/api/login", json={"username": "excs_screen_test", "password": "pass123"})
    csrf = get_csrf(client)

    # Attempt POST /api/screens
    res = client.post(
        "/api/screens",
        json={"code": "MECH", "name": "Mechanical Engineering"},
        headers={"X-CSRF-Token": csrf}
    )
    assert res.status_code == 403
    assert "Permission denied" in res.get_json()["error"]
