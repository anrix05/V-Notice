import os
import threading
import time
from pathlib import Path
import pytest
from werkzeug.serving import run_simple
from playwright.sync_api import sync_playwright

import config
from app import unified_app
from storage import storage

TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "vnotice2026")


def test_show_posted_by_on_display_default_false_and_public_sanitized():
    assert getattr(config, "SHOW_POSTED_BY_ON_DISPLAY", False) is False
    u = storage.create_user(
        email="author.hidden@college.edu",
        name="Prof. Hidden",
        password="StrongAuthorPass#123",
        role="faculty",
        departments=["EXCS"],
    )
    n = storage.add(
        {"title": "Public Sanitization Check", "screens": ["EXCS"]},
        created_by=u["id"],
        created_by_name="Prof. Hidden",
    )
    assert n["posted_by"] == "Prof. Hidden"

    c = unified_app.test_client()
    r_pub = c.get("/api/notices?screen=EXCS")
    assert r_pub.status_code == 200
    items = r_pub.get_json()
    matched = [i for i in items if i["id"] == n["id"]]
    assert len(matched) == 1
    assert "created_by" not in matched[0]
    assert "created_by_name" not in matched[0]
    assert "posted_by" not in matched[0]

    r_page = c.get(f"/n/{n['id']}")
    assert r_page.status_code == 200
    assert "Prof. Hidden" not in r_page.get_data(as_text=True)


def test_admin_cannot_disable_or_demote_self_and_session_revoke_endpoint():
    admin_u = storage.create_user(
        email="self.admin@college.edu",
        name="Self Admin",
        password="StrongSelfAdminPass#123",
        role="admin",
        departments=["ALL"],
    )
    fac_u = storage.create_user(
        email="target.fac@college.edu",
        name="Target Faculty",
        password="StrongTargetFacPass#123",
        role="faculty",
        departments=["CMPN"],
    )

    c_admin = unified_app.test_client()
    r_login = c_admin.post("/api/login", json={"email": "self.admin@college.edu", "password": "StrongSelfAdminPass#123"}, environ_base={"REMOTE_ADDR": "10.95.0.1"})
    assert r_login.status_code == 200
    csrf = r_login.get_json()["csrf_token"]

    # Self-disable and self-demote rejected with 400
    r_dis = c_admin.patch(f"/api/users/{admin_u['id']}", json={"status": "disabled"}, headers={"X-CSRF-Token": csrf})
    assert r_dis.status_code == 400
    assert "own account" in r_dis.get_json()["error"]

    r_dem = c_admin.patch(f"/api/users/{admin_u['id']}", json={"role": "faculty"}, headers={"X-CSRF-Token": csrf})
    assert r_dem.status_code == 400
    assert "own account" in r_dem.get_json()["error"]

    # Admin revokes target faculty's sessions
    c_fac = unified_app.test_client()
    assert c_fac.post("/api/login", json={"email": "target.fac@college.edu", "password": "StrongTargetFacPass#123"}, environ_base={"REMOTE_ADDR": "10.95.0.2"}).status_code == 200
    assert c_fac.get("/api/me").get_json()["authenticated"] is True

    r_rev = c_admin.post(f"/api/users/{fac_u['id']}/sessions/revoke", headers={"X-CSRF-Token": csrf})
    assert r_rev.status_code == 200
    assert c_fac.get("/api/me").get_json()["authenticated"] is False

    # Pending invite metadata appears in GET /api/users
    r_inv = c_admin.post(
        "/api/users/invite",
        json={"name": "Pending Invitee", "email": "pending.inv@college.edu", "role": "faculty", "departments": ["INFT"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r_inv.status_code == 201
    users = c_admin.get("/api/users").get_json()["users"]
    matched = [x for x in users if x["email"] == "pending.inv@college.edu"]
    assert len(matched) == 1
    assert matched[0]["pending_invite_id"] == r_inv.get_json()["invite_id"]


def test_phase2b1_ui_playwright_and_screenshots(tmp_path):
    unified_app.config["TESTING"] = True
    threading.Thread(target=lambda: run_simple("127.0.0.1", 5598, unified_app, threaded=True), daemon=True).start()
    time.sleep(1.0)

    # Seed an admin and a faculty user + notices
    if not storage.get_user("ui.admin@college.edu"):
        storage.create_user(email="ui.admin@college.edu", name="Dr. UI Admin", password="StrongUIAdminPass#123", role="admin", departments=["ALL"])
    fac = storage.get_user("ui.faculty@college.edu") or storage.create_user(
        email="ui.faculty@college.edu",
        name="Prof. Maya Nair",
        password="StrongUIFacultyPass#123",
        role="faculty",
        departments=["EXCS"],
        can_post_college_wide=False,
        can_post_urgent=False,
    )
    admin_u = storage.get_user("ui.admin@college.edu")
    storage.add({"title": "Admin EXCS Notice (Read-Only for Faculty)", "screens": ["EXCS"]}, created_by=admin_u["id"], created_by_name="Dr. UI Admin")
    storage.add({"title": "Maya EXCS Lab Notice", "screens": ["EXCS"]}, created_by=fac["id"], created_by_name="Prof. Maya Nair")

    art_dir = Path(r"C:\Users\pbclu\.gemini\antigravity\brain\c723e1b6-5acf-40ff-bf89-8e8651b77b90")
    art_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for theme in ("dark", "light"):
            for width, height, vp_label in [(1440, 900, "1440"), (390, 844, "390")]:
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()
                page.add_init_script(f"localStorage.setItem('vnotice_theme', '{theme}');")
                page.goto("http://127.0.0.1:5598/admin", wait_until="networkidle")
                page.fill("#admin-username-input", "ui.admin@college.edu")
                page.fill("#admin-password-input", "StrongUIAdminPass#123")
                page.click("#btn-login")
                page.wait_for_selector("#login-modal", state="hidden")
                page.evaluate(f"window.applyTheme && window.applyTheme('{theme}', false);")

                # 1. People list
                assert page.locator('meta[name="description"]').count() == 1
                page.evaluate("window.switchTab('people');")
                page.wait_for_selector("#view-people:not(.hidden)", state="visible")
                assert page.title() == "V Notice — People"
                people_sel = "#people-table-wrap:not(.hidden)" if width >= 768 else "#people-cards-grid:not(.hidden)"
                page.wait_for_selector(people_sel, state="visible")
                page.wait_for_timeout(200)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(art_dir / f"p2b1_people_{vp_label}_{theme}.png"))

                # 2. Invite result panel (only once per viewport/theme on first pass or unique email)
                page.click("#btn-open-invite")
                page.wait_for_selector("#invite-person-modal:not(.hidden)", state="visible")
                inv_email = f"invited.{vp_label}.{theme}@college.edu"
                page.fill("#invite-name-input", "Dr. Invited User")
                page.fill("#invite-email-input", inv_email)
                page.click("#btn-submit-invite")
                page.wait_for_selector("#invite-result-panel:not(.hidden)", state="visible")
                assert "This link is shown only once." in page.inner_text("#invite-result-panel")
                page.screenshot(path=str(art_dir / f"p2b1_invite_result_{vp_label}_{theme}.png"))
                page.click("#btn-done-invite")

                # 3. My account
                page.evaluate("window.switchTab('account');")
                page.wait_for_selector("#view-account:not(.hidden)", state="visible")
                assert page.title() == "V Notice — My account"
                page.wait_for_timeout(200)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(art_dir / f"p2b1_account_{vp_label}_{theme}.png"))
                if width < 1024:
                    for tab_name in ("notices", "screens", "audit", "settings", "people", "account"):
                        page.evaluate(f"window.switchTab('{tab_name}');")
                        page.wait_for_selector(f"#view-{tab_name}:not(.hidden)", state="visible")
                        page.wait_for_timeout(120)
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Mobile overflow on {tab_name}"
                    page.click("#btn-mobile-menu")
                    page.wait_for_selector("#mobile-nav-drawer:not(.hidden)", state="visible")
                    page.click("#btn-close-mobile-menu")
                brand_sel = "#sidebar-brand-link" if width >= 1024 else "#navbar-brand-link"
                page.click(brand_sel)
                page.wait_for_selector("#view-notices:not(.hidden)", state="visible")
                ctx.close()

                # 4. Faculty view of Notices
                ctx_f = browser.new_context(viewport={"width": width, "height": height})
                page_f = ctx_f.new_page()
                page_f.add_init_script(f"localStorage.setItem('vnotice_theme', '{theme}');")
                page_f.goto("http://127.0.0.1:5598/admin", wait_until="networkidle")
                page_f.fill("#admin-username-input", "ui.faculty@college.edu")
                page_f.fill("#admin-password-input", "StrongUIFacultyPass#123")
                page_f.click("#btn-login")
                page_f.wait_for_selector("#login-modal", state="hidden")
                page_f.evaluate(f"window.applyTheme && window.applyTheme('{theme}', false);")
                page_f.wait_for_timeout(400)

                # Verify faculty nav hides admin-only tabs and redirects #people -> #notices
                assert page_f.locator("#sidebar-tab-people").evaluate("el => el.classList.contains('hidden')")
                page_f.evaluate("window.location.hash = '#people';")
                page_f.wait_for_timeout(150)
                assert page_f.locator("#view-notices").evaluate("el => !el.classList.contains('hidden')")
                page_f.screenshot(path=str(art_dir / f"p2b1_faculty_notices_{vp_label}_{theme}.png"))
                ctx_f.close()

        browser.close()

