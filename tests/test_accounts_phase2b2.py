import io
import logging
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from werkzeug.serving import run_simple

from app import unified_app
from storage import storage


def _login_admin(client, email="import.admin@college.edu", password="StrongImportAdmin#123"):
    if not storage.get_user(email):
        storage.create_user(
            email=email,
            name="Import Admin",
            password=password,
            role="admin",
            departments=["ALL"],
        )
    res = client.post("/api/login", json={"username": email, "password": password})
    assert res.status_code == 200
    return res.get_json()["csrf_token"]


def test_import_preview_flags_duplicates_bad_emails_unknown_depts_and_csv_injection():
    client = unified_app.test_client()
    csrf = _login_admin(client)

    existing_email = "existing.faculty@college.edu"
    if not storage.get_user(existing_email):
        storage.create_user(
            email=existing_email,
            name="Existing Faculty",
            password="StrongExistingPass#123",
            role="faculty",
            departments=["EXCS"],
        )

    csv_content = (
        "\ufeffname,email,phone,departments,role\r\n"
        "\"Nair, Maya\",maya.ready@college.edu,9876543210,EXCS;CMPN,faculty\r\n"
        f"Dup Existing,{existing_email},,EXCS,faculty\r\n"
        "Dup In File,maya.ready@college.edu,,EXCS,faculty\r\n"
        "Bad Email,not-an-email,,EXCS,faculty\r\n"
        "Unknown Dept,unknown.dept@college.edu,,NOPE,faculty\r\n"
        "Bad Role,bad.role@college.edu,,EXCS,superhero\r\n"
        "=cmd('calc'),inj1@college.edu,,EXCS,faculty\r\n"
        "Plus Cell,inj2@college.edu,+123456,EXCS,faculty\r\n"
        "Minus Cell,inj3@college.edu,-1+1,EXCS,faculty\r\n"
        "At Cell,inj4@college.edu,@SUM(A1),EXCS,faculty\r\n"
    ).encode("utf-8")

    res = client.post(
        "/api/users/import/preview",
        data={"file": (io.BytesIO(csv_content), "faculty.csv")},
        headers={"X-CSRF-Token": csrf},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    body = res.get_json()
    counts = body["counts"]
    assert counts["total"] == 10
    assert counts["ready"] == 1
    assert counts["duplicate_email"] == 2
    assert counts["invalid_email"] == 1
    assert counts["unknown_department"] == 1
    assert counts["invalid_role"] == 1
    assert counts["csv_injection"] == 4

    statuses = [r["status"] for r in body["rows"]]
    assert statuses[0] == "Ready"
    assert body["rows"][0]["name"] == "Nair, Maya"
    assert body["rows"][0]["departments"] == ["EXCS", "CMPN"]


def test_import_commit_all_or_nothing_idempotent_and_links_available_once(caplog):
    caplog.set_level(logging.INFO)
    client = unified_app.test_client()
    csrf = _login_admin(client)

    csv_ok = (
        "name,email,phone,departments,role\r\n"
        "Batch One,batch1.fac@college.edu,,EXCS,faculty\r\n"
        "Batch Two,batch2.fac@college.edu,,CMPN,faculty\r\n"
    ).encode("utf-8")

    prev = client.post(
        "/api/users/import/preview",
        data={"file": (io.BytesIO(csv_ok), "batch.csv")},
        headers={"X-CSRF-Token": csrf},
        content_type="multipart/form-data",
    )
    assert prev.status_code == 200
    batch_id = prev.get_json()["batch_id"]

    # First commit creates both users
    c1 = client.post(
        "/api/users/import/commit",
        json={"batch_id": batch_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert c1.status_code == 200
    d1 = c1.get_json()
    assert d1["created_count"] == 2
    assert d1["links_available"] is True
    assert len(d1["whatsapp_messages"]) == 2

    # Idempotent repeat commit for same batch_id does NOT create duplicates
    c2 = client.post(
        "/api/users/import/commit",
        json={"batch_id": batch_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert c2.status_code == 200
    d2 = c2.get_json()
    assert d2["already_committed"] is True
    assert d2["created_count"] == 2

    # Links CSV available ONCE
    dl1 = client.get(f"/api/users/import/{batch_id}/links.csv")
    assert dl1.status_code == 200
    csv_text = dl1.get_data(as_text=True)
    assert "batch1.fac@college.edu" in csv_text
    assert "/invite/" in csv_text

    dl2 = client.get(f"/api/users/import/{batch_id}/links.csv")
    assert dl2.status_code == 410

    # Extract tokens to verify none appear in logs or audit logs
    tokens = []
    for msg in d1["whatsapp_messages"]:
        tokens.append(msg.split("/invite/")[1].split(" ")[0])

    logs = storage.get_audit_logs(limit=20)["logs"]
    for log_row in logs:
        for tok in tokens:
            assert tok not in (log_row.get("details") or "")
            assert tok not in (log_row.get("target_id") or "")
    for tok in tokens:
        assert tok not in caplog.text

    # All-or-nothing rollback test: preview two new emails, insert one out-of-band, then commit
    csv_race = (
        "name,email,phone,departments,role\r\n"
        "Race A,race.a@college.edu,,EXCS,faculty\r\n"
        "Race B,race.b@college.edu,,EXCS,faculty\r\n"
    ).encode("utf-8")
    prev_race = client.post(
        "/api/users/import/preview",
        data={"file": (io.BytesIO(csv_race), "race.csv")},
        headers={"X-CSRF-Token": csrf},
        content_type="multipart/form-data",
    )
    race_batch = prev_race.get_json()["batch_id"]
    storage.create_user(email="race.b@college.edu", name="Race B Pre", status="invited", role="faculty")

    c_fail = client.post(
        "/api/users/import/commit",
        json={"batch_id": race_batch},
        headers={"X-CSRF-Token": csrf},
    )
    assert c_fail.status_code == 409
    assert storage.get_user("race.a@college.edu") is None


def test_accept_page_generic_card_for_bad_links_and_no_leak_headers():
    client = unified_app.test_client()
    user = storage.create_user(
        email="accept.check@college.edu",
        name="Accept Check",
        status="invited",
        role="faculty",
        departments=["EXCS"],
    )

    # 1. Nonexistent token
    r_missing = client.get("/invite/totally-bogus-token-123")
    assert r_missing.status_code == 400
    html_missing = r_missing.get_data(as_text=True)
    assert "This link is not valid. Ask your admin for a new one." in html_missing
    assert r_missing.headers.get("Referrer-Policy") == "no-referrer"
    assert "no-store" in (r_missing.headers.get("Cache-Control") or "")
    assert "noindex" in (r_missing.headers.get("X-Robots-Tag") or "")

    # 2. Revoked token
    tok_rev, _ = storage.create_invite(user["id"], purpose="invite", expires_hours=72)
    tok_valid, _ = storage.create_invite(user["id"], purpose="invite", expires_hours=72, revoke_existing=True)
    r_rev = client.get(f"/invite/{tok_rev}")
    assert r_rev.status_code == 400
    assert "This link is not valid. Ask your admin for a new one." in r_rev.get_data(as_text=True)

    # 3. Valid token renders welcome + chips, never echoes token in visible text
    r_ok = client.get(f"/invite/{tok_valid}")
    assert r_ok.status_code == 200
    html_ok = r_ok.get_data(as_text=True)
    assert "Welcome, Accept Check" in html_ok
    assert "EXCS" in html_ok
    assert "Set password and sign in" in html_ok
    assert f">{tok_valid}<" not in html_ok


def test_phase2b2_playwright_390px_screenshots():
    unified_app.config["TESTING"] = True
    threading.Thread(target=lambda: run_simple("127.0.0.1", 5597, unified_app, threaded=True), daemon=True).start()
    time.sleep(1.0)

    _login_admin(unified_app.test_client(), email="ui2b2.admin@college.edu", password="StrongUI2B2Admin#123")
    u_acc = storage.create_user(
        email="accept.ui@college.edu",
        name="Prof. Arjun Mehta",
        status="invited",
        role="faculty",
        departments=["EXCS", "CMPN"],
    )
    tok_ui, _ = storage.create_invite(u_acc["id"], purpose="invite", expires_hours=72)

    art_dir = Path(r"C:\Users\pbclu\.gemini\antigravity\brain\c723e1b6-5acf-40ff-bf89-8e8651b77b90")
    art_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
        page = ctx.new_page()

        # 1. Valid accept page at 390px
        page.goto(f"http://127.0.0.1:5597/invite/{tok_ui}", wait_until="networkidle")
        page.fill("#password", "MyStrongFacultyPass#99")
        page.fill("#confirm_password", "MyStrongFacultyPass#99")
        page.screenshot(path=str(art_dir / "p2b2_accept_valid_390.png"))

        # 2. Invalid accept page at 390px
        page.goto("http://127.0.0.1:5597/invite/invalid-link-token", wait_until="networkidle")
        page.screenshot(path=str(art_dir / "p2b2_accept_invalid_390.png"))

        # 3. Bulk CSV import modal steps at 390px
        page.goto("http://127.0.0.1:5597/admin", wait_until="networkidle")
        page.fill("#admin-username-input", "ui2b2.admin@college.edu")
        page.fill("#admin-password-input", "StrongUI2B2Admin#123")
        page.click("#btn-login")
        page.wait_for_selector("#login-modal", state="hidden")

        page.evaluate("window.switchTab('people');")
        page.wait_for_selector("#view-people:not(.hidden)", state="visible")
        page.click("#btn-open-csv-import")
        page.wait_for_selector("#csv-import-modal:not(.hidden)", state="visible")
        page.wait_for_timeout(250)
        page.screenshot(path=str(art_dir / "p2b2_import_upload_390.png"))

        csv_payload = (
            "name,email,phone,departments,role\r\n"
            "Dr. Kavita Rao,kavita.ui@college.edu,,EXCS;CMPN,faculty\r\n"
            "Bad Row,bad-email,,NOPE,faculty\r\n"
        ).encode("utf-8")
        page.set_input_files("#csv-file-input", files=[{"name": "faculty.csv", "mimeType": "text/csv", "buffer": csv_payload}])
        page.click("#btn-csv-preview")
        page.wait_for_selector("#csv-step-preview:not(.hidden)", state="visible")
        page.screenshot(path=str(art_dir / "p2b2_import_preview_390.png"))

        page.click("#btn-csv-commit")
        page.wait_for_selector("#csv-step-result:not(.hidden)", state="visible")
        page.screenshot(path=str(art_dir / "p2b2_import_result_390.png"))

        ctx.close()
        browser.close()
