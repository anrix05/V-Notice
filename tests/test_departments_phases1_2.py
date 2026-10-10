import os
import time
import json
import sqlite3
import pytest
from app import unified_app, display_app, admin_app
from storage import NoticeStorage, LocalMediaStorage, storage

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def get_auth_headers(client):
    res = client.post("/api/login", json={"password": "vnotice2026"})
    assert res.status_code == 200
    token = res.get_json()["csrf_token"]
    return {"X-CSRF-Token": token}

def test_seeded_departments(client):
    res = client.get("/api/screens")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    screens = data["screens"]
    codes = [s["code"] for s in screens]
    assert "ALL" in codes
    assert "CMPN" in codes
    assert "INFT" in codes
    assert "EXTC" in codes
    assert "EXCS" in codes
    assert "BIOM" in codes

def test_screen_code_validation_rejects_invalid(client):
    headers = get_auth_headers(client)

    # Reject lowercase
    res = client.post("/api/screens", json={"code": "excs_low", "name": "Invalid Lower"}, headers=headers)
    assert res.status_code == 400

    # Reject spaces
    res = client.post("/api/screens", json={"code": "EX CS", "name": "Space Code"}, headers=headers)
    assert res.status_code == 400

    # Reject symbols
    res = client.post("/api/screens", json={"code": "EX@CS", "name": "Symbol Code"}, headers=headers)
    assert res.status_code == 400

    # Reject too short (<2 chars)
    res = client.post("/api/screens", json={"code": "E", "name": "Short Code"}, headers=headers)
    assert res.status_code == 400

    # Reject too long (>10 chars)
    res = client.post("/api/screens", json={"code": "VERYLONGCODE", "name": "Long Code"}, headers=headers)
    assert res.status_code == 400

    # Reject duplicates
    res = client.post("/api/screens", json={"code": "CMPN", "name": "Duplicate Computer"}, headers=headers)
    assert res.status_code == 400

def test_screen_crud_and_deactivation_protection(client):
    headers = get_auth_headers(client)

    # Create new department
    res = client.post("/api/screens", json={"code": "TEST_D1", "name": "Test Department 1", "sort_order": 99}, headers=headers)
    assert res.status_code == 201
    assert res.get_json()["screen"]["code"] == "TEST_D1"

    # Update department
    res = client.put("/api/screens/TEST_D1", json={"name": "Updated Dept 1", "accent_color": "#123456"}, headers=headers)
    assert res.status_code == 200
    assert res.get_json()["screen"]["name"] == "Updated Dept 1"

    # Add notice targeting TEST_D1
    notice_res = client.post("/api/notices", data={"title": "Notice for D1", "screens": ["TEST_D1"]}, headers=headers)
    assert notice_res.status_code == 201
    notice_id = notice_res.get_json()["id"]

    # Attempt to delete TEST_D1 -> Must DEACTIVATE, not hard delete
    del_res = client.delete("/api/screens/TEST_D1", headers=headers)
    assert del_res.status_code == 200
    data = del_res.get_json()
    assert data.get("deactivated") is True

    # Department is now inactive: unauthenticated API should not list it
    # Log out to test public API
    client.post("/api/logout")
    pub_res = client.get("/api/screens")
    pub_codes = [s["code"] for s in pub_res.get_json()["screens"]]
    assert "TEST_D1" not in pub_codes

    # Re-login to clean up notice and department
    headers2 = get_auth_headers(client)
    client.delete(f"/api/notices/{notice_id}", headers=headers2)

    # Now that notices are gone, deleting should hard-delete
    del_res2 = client.delete("/api/screens/TEST_D1", headers=headers2)
    assert del_res2.status_code == 200
    assert del_res2.get_json().get("deleted") is True

def test_cannot_delete_all_screen(client):
    headers = get_auth_headers(client)
    res = client.delete("/api/screens/ALL", headers=headers)
    assert res.status_code == 400

def test_display_routing_case_redirect(client):
    # Lowercase code redirects 301 to uppercase
    res = client.get("/display/excs")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/display/EXCS")

def test_display_routing_unknown_code_404(client):
    # Unknown screen code returns 404 with friendly page
    res = client.get("/display/UNKNOWN99")
    assert res.status_code == 404
    html = res.get_data(as_text=True)
    assert "Screen Not Found" in html
    assert "UNKNOWN99" in html
    assert "CMPN" in html

def test_display_root_and_legacy_query_redirect(client):
    # /display without code shows ALL board
    res = client.get("/display")
    assert res.status_code == 200
    assert "display.html" in res.get_data(as_text=True) or "<html" in res.get_data(as_text=True)

    # Legacy /display?screen=excs redirects 301 to /display/EXCS
    res = client.get("/display?screen=excs")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/display/EXCS")

    # Legacy /display?screen=default redirects 301 to /display/ALL
    res = client.get("/display?screen=default")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/display/ALL")

def test_api_notices_screen_filtering_and_multi_target(client):
    headers = get_auth_headers(client)

    # 1. Create College-wide notice
    n_all = client.post("/api/notices", data={"title": "College Wide Notice", "screens": ["ALL"]}, headers=headers).get_json()

    # 2. Create EXCS-only notice
    n_excs = client.post("/api/notices", data={"title": "EXCS Only Notice", "screens": ["EXCS"]}, headers=headers).get_json()

    # 3. Create BIOM-only notice
    n_biom = client.post("/api/notices", data={"title": "BIOM Only Notice", "screens": ["BIOM"]}, headers=headers).get_json()

    # 4. Create Multi-target notice (CMPN + INFT)
    n_multi = client.post("/api/notices", data={"title": "Multi Notice", "screens": ["CMPN", "INFT"]}, headers=headers).get_json()

    # Public client (logout) fetches EXCS:
    client.post("/api/logout")
    res = client.get("/api/notices?screen=EXCS")
    assert res.status_code == 200
    excs_notices = res.get_json()
    excs_ids = [n["id"] for n in excs_notices]

    # Must contain EXCS and ALL
    assert n_excs["id"] in excs_ids
    assert n_all["id"] in excs_ids

    # Must NEVER contain BIOM-only notice or CMPN/INFT multi notice
    assert n_biom["id"] not in excs_ids
    assert n_multi["id"] not in excs_ids

    # Public client fetches CMPN:
    res_cmpn = client.get("/api/notices?screen=CMPN")
    cmpn_ids = [n["id"] for n in res_cmpn.get_json()]
    assert n_multi["id"] in cmpn_ids
    assert n_all["id"] in cmpn_ids
    assert n_excs["id"] not in cmpn_ids
    assert n_biom["id"] not in cmpn_ids

    # Public client fetches INFT:
    res_inft = client.get("/api/notices?screen=INFT")
    inft_ids = [n["id"] for n in res_inft.get_json()]
    assert n_multi["id"] in inft_ids
    assert n_all["id"] in inft_ids

    # Clean up notices
    headers2 = get_auth_headers(client)
    for nid in [n_all["id"], n_excs["id"], n_biom["id"], n_multi["id"]]:
        client.delete(f"/api/notices/{nid}", headers=headers2)

def test_unauthenticated_callers_never_see_scheduled_or_expired(client):
    headers = get_auth_headers(client)
    now = int(time.time() * 1000)

    # Scheduled notice (starts tomorrow)
    n_sched = client.post("/api/notices", data={
        "title": "Future Notice",
        "screens": ["EXCS"],
        "start": now + 86400000,
        "end": now + 172800000
    }, headers=headers).get_json()

    # Expired notice (ended yesterday)
    n_exp = client.post("/api/notices", data={
        "title": "Past Notice",
        "screens": ["EXCS"],
        "start": now - 172800000,
        "end": now - 86400000
    }, headers=headers).get_json()

    # Public client (logout) checks EXCS notices
    client.post("/api/logout")
    res = client.get("/api/notices?screen=EXCS")
    assert res.status_code == 200
    pub_ids = [n["id"] for n in res.get_json()]

    assert n_sched["id"] not in pub_ids
    assert n_exp["id"] not in pub_ids

    # Clean up
    headers2 = get_auth_headers(client)
    client.delete(f"/api/notices/{n_sched['id']}", headers=headers2)
    client.delete(f"/api/notices/{n_exp['id']}", headers=headers2)

def test_etag_isolation_between_departments(client):
    # Initial ETag for BIOM (public)
    res_biom1 = client.get("/api/notices?screen=BIOM")
    etag_biom1 = res_biom1.headers.get("ETag")
    assert etag_biom1 is not None

    # Mutate an EXCS-only notice as admin
    headers = get_auth_headers(client)
    n_excs = client.post("/api/notices", data={"title": "EXCS Mutation", "screens": ["EXCS"]}, headers=headers).get_json()

    # Logout to query public BIOM display
    client.post("/api/logout")
    # BIOM display should still return 304 with its previous ETag
    res_biom2 = client.get("/api/notices?screen=BIOM", headers={"If-None-Match": etag_biom1})
    assert res_biom2.status_code == 304, "BIOM ETag should NOT be invalidated by EXCS notice mutation"

    # Clean up
    headers2 = get_auth_headers(client)
    client.delete(f"/api/notices/{n_excs['id']}", headers=headers2)

def test_heartbeat_and_last_seen_tracking(client):
    # Post heartbeat for EXCS
    res = client.post("/api/heartbeat", json={"screen": "EXCS"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["code"] == "EXCS"

    # Authenticated admin checking /api/screens sees last_seen and online=True
    headers = get_auth_headers(client)
    res_screens = client.get("/api/screens")
    assert res_screens.status_code == 200
    screens = res_screens.get_json()["screens"]
    excs_screen = next(s for s in screens if s["code"] == "EXCS")
    assert excs_screen.get("last_seen") is not None
    assert excs_screen.get("online") is True
