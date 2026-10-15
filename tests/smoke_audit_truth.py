import os
import sys
import time
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from playwright.sync_api import sync_playwright

BASE_URL_ADMIN = "http://localhost:5001"
BASE_URL_DISPLAY = "http://localhost:5000"
PASSWORD = os.environ.get("ADMIN_PASSWORD", "vnotice2026")

results = []

def record(test_num, name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    results.append({
        "num": test_num,
        "name": name,
        "status": status,
        "details": details
    })
    print(f"[{status}] Item {test_num}: {name} - {details}", flush=True)

def close_all_modals(page):
    try:
        page.evaluate("""() => {
            document.querySelectorAll('.modal-backdrop').forEach(m => {
                if (m.id !== 'login-modal') m.classList.add('hidden');
            });
        }""")
    except Exception:
        pass

def switch_to_tab(page, tab_name):
    close_all_modals(page)
    # Click sidebar item
    sidebar_item = page.locator(f"#desktop-sidebar a[data-tab='{tab_name}']")
    if sidebar_item.count() > 0:
        sidebar_item.click()
    else:
        page.locator(f"a[data-tab='{tab_name}']").first.click()
    time.sleep(0.5)
    close_all_modals(page)

def ensure_authenticated(page):
    try:
        close_all_modals(page)
        if page.is_visible("#login-modal:not(.hidden)"):
            page.fill("#admin-password-input", PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#login-modal", state="hidden", timeout=5000)
            page.wait_for_selector("#admin-app", timeout=5000)
    except Exception as e:
        print(f"Warning in ensure_authenticated: {e}", flush=True)

def run_truth_audit():
    print("=" * 70, flush=True)
    print("PART 0: TRUTH AUDIT - Running Playwright Smoke Tests on UNMODIFIED app", flush=True)
    print("=" * 70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        # Clean up any leftover smoke test notices from previous runs
        try:
            conn = sqlite3.connect("notices.db")
            conn.execute("DELETE FROM notices WHERE title LIKE 'Smoke Test%' OR title LIKE 'Exempt API Key%' OR title LIKE 'Valid CSRF%' OR title LIKE 'Permitted College Wide%';")
            conn.commit()
            conn.close()
        except Exception:
            pass

        # =========================================================================
        # 1. Login success and failure (error shown, rate limit message after repeated failures)
        # =========================================================================
        print("\n--- Testing Item 1: Login ---", flush=True)
        try:
            page.goto(f"{BASE_URL_ADMIN}/")
            page.wait_for_selector("#login-modal", timeout=5000)

            # 1a: Wrong password error
            page.fill("#admin-password-input", "wrongpassword123")
            page.click("#btn-login")
            page.wait_for_selector("#login-error:not(.hidden)", timeout=3000)
            err_text = page.inner_text("#login-error")
            wrong_pw_ok = "incorrect" in err_text.lower() or len(err_text) > 0

            # 1b: Rate limit in separate context (with distinct forwarded IP)
            rate_limit_triggered = False
            rate_ctx = browser.new_context(extra_http_headers={"X-Forwarded-For": "198.51.100.88"})
            rate_page = rate_ctx.new_page()
            rate_page.goto(f"{BASE_URL_ADMIN}/")
            rate_page.wait_for_selector("#login-modal", timeout=5000)
            for i in range(6):
                rate_page.fill("#admin-password-input", f"badpass_{i}")
                rate_page.click("#btn-login")
                time.sleep(0.3)
                err_text_rate = rate_page.inner_text("#login-error") if rate_page.is_visible("#login-error") else ""
                if "too many" in err_text_rate.lower() or "try again in" in err_text_rate.lower():
                    rate_limit_triggered = True
                    break
            rate_ctx.close()

            # 1c: Valid login on main context
            page.bring_to_front()
            page.evaluate("""async () => {
                try {
                    await fetch('/api/test-reset-rate-limit', { method: 'POST' });
                } catch(e) {}
                const p = document.getElementById('admin-password-input');
                if (p) p.disabled = false;
                const b = document.getElementById('btn-login');
                if (b) b.disabled = false;
                const err = document.getElementById('login-error');
                if (err) err.classList.add('hidden');
            }""")
            page.fill("#admin-password-input", PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#login-modal", state="hidden", timeout=6000)
            page.wait_for_selector("#admin-app", timeout=6000)
            login_success_ok = page.is_visible("#admin-app")

            item1_pass = wrong_pw_ok and rate_limit_triggered and login_success_ok
            details1 = f"Wrong PW error: {wrong_pw_ok}, Rate limit triggered: {rate_limit_triggered}, Login success: {login_success_ok}"
            record(1, "Login success and failure (rate limiting)", item1_pass, details1)
        except Exception as e:
            record(1, "Login success and failure (rate limiting)", False, f"Exception: {e}")

        # =========================================================================
        # 2. Create text notice targeting one dept, then ALL; confirm on displays
        # =========================================================================
        print("\n--- Testing Item 2: Create Notices (Targeted & ALL) ---", flush=True)
        try:
            ensure_authenticated(page)
            switch_to_tab(page, 'notices')

            # 2a: Create CMPN notice
            page.click("#btn-open-create")
            page.wait_for_selector("#notice-modal:not(.hidden)", timeout=4000)

            cmpn_chip = page.locator("#screen-chip-picker .chip", has_text="CMPN")
            if cmpn_chip.count() > 0:
                cmpn_chip.click()
                time.sleep(0.3)

            page.fill("#notice-title", "Smoke Test CMPN Target Notice")
            page.fill("#notice-body", "Details for CMPN only")
            page.click("#btn-submit-create")
            page.wait_for_selector("#notice-modal", state="hidden", timeout=6000)
            time.sleep(1)

            # 2b: Create ALL notice
            page.click("#btn-open-create")
            page.wait_for_selector("#notice-modal:not(.hidden)", timeout=4000)
            all_chip = page.locator("#screen-chip-picker .chip", has_text="ALL")
            all_chip.click()
            time.sleep(0.3)

            page.fill("#notice-title", "Smoke Test ALL Target Notice")
            page.fill("#notice-body", "Details for ALL departments")
            page.click("#btn-submit-create")
            page.wait_for_selector("#notice-modal", state="hidden", timeout=6000)
            time.sleep(1)

            # 2c: Check /display/CMPN
            display_page = context.new_page()
            display_page.goto(f"{BASE_URL_DISPLAY}/display/CMPN")
            display_page.wait_for_selector("#display-frame, #text-headline", timeout=8000)
            time.sleep(2)

            cmpn_notices = display_page.evaluate("() => typeof allNotices !== 'undefined' ? allNotices.map(n => n.title) : []")
            cmpn_content = display_page.content()
            cmpn_has_cmpn = ("Smoke Test CMPN Target Notice" in cmpn_notices) or ("Smoke Test CMPN Target Notice" in cmpn_content)
            cmpn_has_all = ("Smoke Test ALL Target Notice" in cmpn_notices) or ("Smoke Test ALL Target Notice" in cmpn_content)

            # 2d: Check /display/INFT (different department)
            display_page.goto(f"{BASE_URL_DISPLAY}/display/INFT")
            display_page.wait_for_selector("#display-frame, #text-headline", timeout=8000)
            time.sleep(2)

            inft_notices = display_page.evaluate("() => typeof allNotices !== 'undefined' ? allNotices.map(n => n.title) : []")
            inft_content = display_page.content()
            inft_has_all = ("Smoke Test ALL Target Notice" in inft_notices) or ("Smoke Test ALL Target Notice" in inft_content)
            inft_has_cmpn = ("Smoke Test CMPN Target Notice" in inft_notices) or ("Smoke Test CMPN Target Notice" in inft_content)

            display_page.close()

            item2_pass = cmpn_has_cmpn and cmpn_has_all and inft_has_all and (not inft_has_cmpn)
            details2 = (f"CMPN display has CMPN: {cmpn_has_cmpn}, has ALL: {cmpn_has_all}; "
                        f"INFT display has ALL: {inft_has_all}, omits CMPN: {not inft_has_cmpn}")
            record(2, "Create targeted notice & ALL notice, verify on displays", item2_pass, details2)
        except Exception as e:
            record(2, "Create targeted notice & ALL notice, verify on displays", False, f"Exception: {e}")

        # =========================================================================
        # 3. Edit, delete (with undo), and confirm they update the display
        # =========================================================================
        print("\n--- Testing Item 3: Edit, Delete (with Undo) ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'notices')
            time.sleep(1)

            card = page.locator(".notice-item-card", has_text="Smoke Test CMPN Target Notice").first
            card.wait_for(timeout=5000)

            overflow_btn = card.locator(".btn-card-overflow")
            if overflow_btn.count() > 0:
                overflow_btn.click()
                page.wait_for_selector("#action-sheet-modal:not(.hidden)", timeout=3000)
                page.click("#action-btn-edit")
            else:
                card.locator(".btn-edit-notice").click()

            page.wait_for_selector("#notice-modal:not(.hidden)", timeout=4000)
            page.fill("#notice-title", "Smoke Test CMPN Target Notice EDITED")
            page.click("#btn-submit-create")
            page.wait_for_selector("#notice-modal", state="hidden", timeout=6000)
            time.sleep(1)

            # Check update on display
            disp_check = context.new_page()
            disp_check.goto(f"{BASE_URL_DISPLAY}/display/CMPN")
            disp_check.wait_for_selector("#display-frame, #text-headline", timeout=8000)
            try:
                disp_check.wait_for_function("() => window.allNotices && window.allNotices.length > 0", timeout=5000)
            except Exception:
                pass
            time.sleep(1)
            cmpn_titles = disp_check.evaluate("() => (window.allNotices || []).map(n => n.title)")
            edit_on_display = ("Smoke Test CMPN Target Notice EDITED" in cmpn_titles) or ("Smoke Test CMPN Target Notice EDITED" in disp_check.content())

            # Now delete from Admin
            page.bring_to_front()
            card_edited = page.locator(".notice-item-card", has_text="Smoke Test CMPN Target Notice EDITED").first
            overflow_btn = card_edited.locator(".btn-card-overflow")
            if overflow_btn.count() > 0:
                overflow_btn.click()
                page.wait_for_selector("#action-sheet-modal:not(.hidden)", timeout=3000)
                page.click("#action-btn-delete")
            else:
                card_edited.locator(".btn-delete-notice").click()

            page.wait_for_selector("#delete-modal:not(.hidden)", timeout=3000)
            page.click("#btn-confirm-delete")
            page.wait_for_selector("#delete-modal", state="hidden", timeout=4000)
            time.sleep(1)

            # Check for undo mechanism in toast or UI
            undo_button = page.locator("#toast-container button, .toast-undo, [data-action='undo']")
            has_undo = undo_button.count() > 0

            # Confirm removal from display
            disp_check.reload()
            time.sleep(2)
            cmpn_titles_after_del = disp_check.evaluate("() => (window.allNotices || []).map(n => n.title)")
            deleted_from_display = "Smoke Test CMPN Target Notice EDITED" not in cmpn_titles_after_del
            disp_check.close()

            item3_pass = edit_on_display and deleted_from_display and has_undo
            details3 = f"Edit updated display: {edit_on_display}, Delete removed from display: {deleted_from_display}, Undo feature present: {has_undo}"
            record(3, "Edit, delete (with undo), update display", item3_pass, details3)
        except Exception as e:
            close_all_modals(page)
            record(3, "Edit, delete (with undo), update display", False, f"Exception: {e}")

        # =========================================================================
        # 4. Image and video upload (small files), including a rejected file type
        # =========================================================================
        print("\n--- Testing Item 4: Media Uploads & File Type Rejection ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'notices')
            page.click("#btn-open-create")
            page.wait_for_selector("#notice-modal:not(.hidden)", timeout=4000)

            # 4a: Test rejected file type (.txt)
            page.locator("label.type-opt:has(input[value='image'])").click()
            file_input = page.locator("#media-file-input")
            file_input.set_input_files("tests/fixtures/test_invalid.txt")
            time.sleep(0.5)
            err_media_visible = page.is_visible("#err-media:not(.hidden)")
            err_media_text = page.inner_text("#err-media") if err_media_visible else ""
            toast_text = page.inner_text("#toast-container") if page.is_visible("#toast-container") else ""
            rejection_ok = err_media_visible or "invalid" in toast_text.lower() or "not allowed" in toast_text.lower() or "allowed formats" in err_media_text.lower()

            # 4b: Test valid image (.png)
            file_input.set_input_files("tests/fixtures/test_image.png")
            time.sleep(1)
            image_preview_ok = page.is_visible("#media-live-preview:not(.hidden)")

            # 4c: Test valid video (.mp4)
            page.locator("label.type-opt:has(input[value='video'])").click()
            file_input.set_input_files("tests/fixtures/test_video.mp4")
            time.sleep(1)
            video_preview_ok = page.is_visible("#media-live-preview:not(.hidden)")

            # Close notice modal safely: click cancel, if discard modal appears click discard
            page.click("#btn-cancel-create")
            time.sleep(0.3)
            if page.is_visible("#discard-modal:not(.hidden)"):
                page.click("#btn-confirm-discard")
            close_all_modals(page)

            item4_pass = rejection_ok and image_preview_ok and video_preview_ok
            details4 = f"File rejection ok: {rejection_ok}, Image preview ok: {image_preview_ok}, Video preview ok: {video_preview_ok}"
            record(4, "Image & video upload with rejected file type check", item4_pass, details4)
        except Exception as e:
            close_all_modals(page)
            record(4, "Image & video upload with rejected file type check", False, f"Exception: {e}")

        # =========================================================================
        # 5. Screens tab: add, deactivate, reactivate, delete test dept; Copy link; Open kiosk
        # =========================================================================
        print("\n--- Testing Item 5: Screens Tab Management ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'screens')
            page.wait_for_selector("#view-screens:not(.hidden)", timeout=4000)

            # Open Add Screen form
            page.click("#btn-open-add-dept")
            page.wait_for_selector("#card-add-dept-inline:not(.hidden)", timeout=3000)

            # Add test department
            page.fill("#dept-code-input-inline", "TESTD")
            page.fill("#dept-name-input-inline", "Test Department Screen")
            page.click("#btn-save-dept-inline")
            time.sleep(1)

            testd_card = page.locator(".screen-item-card[data-code='TESTD']")
            testd_card.wait_for(timeout=5000)
            added_ok = testd_card.count() > 0

            # Deactivate
            toggle_btn = testd_card.locator(".btn-toggle-screen")
            toggle_btn.click()
            time.sleep(1)
            deactivated_ok = "inactive" in testd_card.inner_text().lower() or toggle_btn.inner_text().strip() == "Activate"

            # Reactivate
            toggle_btn.click()
            time.sleep(1)
            reactivated_ok = "active" in testd_card.inner_text().lower() or toggle_btn.inner_text().strip() == "Deactivate"

            # Copy link
            copy_btn = testd_card.locator(".btn-copy-screen-link")
            copy_btn.click()
            time.sleep(0.5)
            toast_text = page.inner_text("#toast-container") if page.is_visible("#toast-container") else ""
            copy_ok = "copied" in toast_text.lower() or "display/TESTD" in toast_text

            # Open kiosk opens /display/TESTD
            kiosk_btn = testd_card.locator(".btn-kiosk-open")
            kiosk_href = kiosk_btn.get_attribute("href") or ""
            kiosk_ok = "/display/TESTD" in kiosk_href

            # Delete
            overflow_btn = testd_card.locator(".btn-screen-overflow-trigger")
            if overflow_btn.count() > 0:
                overflow_btn.click()
                time.sleep(0.4)
            delete_btn = testd_card.locator(".btn-delete-screen")
            if delete_btn.count() > 0:
                delete_btn.click()
                time.sleep(1)
            deleted_ok = page.locator(".screen-item-card[data-code='TESTD']").count() == 0

            item5_pass = added_ok and deactivated_ok and reactivated_ok and copy_ok and kiosk_ok and deleted_ok
            details5 = (f"Added: {added_ok}, Deactivated: {deactivated_ok}, Reactivated: {reactivated_ok}, "
                        f"Copy link: {copy_ok}, Open kiosk href: {kiosk_ok}, Deleted: {deleted_ok}")
            record(5, "Screens tab (add, deactivate, reactivate, delete, copy, kiosk)", item5_pass, details5)
        except Exception as e:
            close_all_modals(page)
            record(5, "Screens tab (add, deactivate, reactivate, delete, copy, kiosk)", False, f"Exception: {e}")

        # =========================================================================
        # 6. Audit Logs: verify display of login, create, edit, delete, screen changes
        # =========================================================================
        print("\n--- Testing Item 6: Audit Logs ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'audit')
            page.wait_for_selector("#view-audit:not(.hidden)", timeout=4000)
            time.sleep(1)

            empty_row_visible = page.is_visible("#audit-tbody-page .audit-empty-row")
            table_text = page.inner_text("#view-audit")

            # Check backend API
            api_res = page.evaluate("""async () => {
                const res = await fetch('/api/audit-logs');
                return await res.json();
            }""")
            audit_logs_in_api = api_res.get("audit_logs", [])

            # Check root cause:
            ui_empty = empty_row_visible or "No administrative activity recorded yet" in table_text

            # Check DB for login, create, edit, delete, screen actions
            db_conn = sqlite3.connect("notices.db")
            db_c = db_conn.cursor()
            db_c.execute("SELECT DISTINCT action FROM audit_logs")
            actions_in_db = [r[0] for r in db_c.fetchall()]
            db_conn.close()

            has_login = "LOGIN" in actions_in_db or "LOGIN_SUCCESS" in actions_in_db or "login" in [a.lower() for a in actions_in_db]
            has_create = "CREATE" in actions_in_db
            has_edit = "UPDATE" in actions_in_db
            has_delete = "DELETE" in actions_in_db
            has_screen = "CREATE_SCREEN" in actions_in_db or "DEACTIVATE_SCREEN" in actions_in_db

            root_causes = []
            if ui_empty:
                root_causes.append("UI is EMPTY because loadAuditLogsPage() in admin.js checks data.logs instead of data.audit_logs")
            if not has_login:
                root_causes.append("Login/Logout events are never recorded to audit_logs table")
            root_causes.append("audit_logs table lacks ip_address column")

            item6_pass = (not ui_empty) and has_login and has_create and has_edit and has_delete and has_screen
            details6 = f"UI Empty: {ui_empty}; Actions in DB: {actions_in_db}; Root causes: {'; '.join(root_causes)}"
            record(6, "Audit Logs (shows login, create, edit, delete, screen changes)", item6_pass, details6)
        except Exception as e:
            close_all_modals(page)
            record(6, "Audit Logs (shows login, create, edit, delete, screen changes)", False, f"Exception: {e}")

        # =========================================================================
        # 7. Settings: theme Dark/Light/Auto, display preview buttons, PWA manifest, service worker
        # =========================================================================
        print("\n--- Testing Item 7: Settings ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'settings')
            page.wait_for_selector("#view-settings:not(.hidden)", timeout=4000)

            # 7a: Theme toggle & persistence
            page.click(".theme-btn[data-theme='light']")
            time.sleep(0.5)
            body_class_after_light = page.evaluate("() => document.body.className + ' ' + (document.documentElement.getAttribute('data-theme') || '')")
            body_bg_after_light = page.evaluate("() => window.getComputedStyle(document.body).backgroundColor")

            # Reload to check persistence
            page.reload()
            page.wait_for_selector("#admin-app", timeout=5000)
            switch_to_tab(page, 'settings')
            theme_btn_active = page.evaluate("() => document.querySelector('.theme-btn.active')?.getAttribute('data-theme')")
            theme_persisted = (theme_btn_active == "light") and ("light" in body_class_after_light.lower() or "rgb(255" in body_bg_after_light)

            # 7b: Preview buttons (800x480, 1366x768, 1920x1080, 3840x2160, 1080x1920)
            preview_buttons = page.locator(".btn-preview-size")
            btn_count = preview_buttons.count()
            has_5_buttons = (btn_count == 5)
            # Check if preview modal with scaled iframe exists in DOM
            preview_modal = page.locator("#preview-modal, .display-preview-modal, iframe#display-preview-iframe")
            has_preview_modal = preview_modal.count() > 0

            # 7c: PWA manifest and service worker
            manifest_ok = page.evaluate("""async () => {
                try {
                    const res = await fetch('/manifest.webmanifest');
                    return res.ok;
                } catch (e) { return false; }
            }""")

            sw_registered = page.evaluate("""async () => {
                if (!('serviceWorker' in navigator)) return false;
                const regs = await navigator.serviceWorker.getRegistrations();
                return regs.length > 0;
            }""")

            item7_pass = theme_persisted and has_5_buttons and has_preview_modal and manifest_ok and sw_registered
            details7 = (f"Theme persisted & applied: {theme_persisted}; Has 5 preview sizes: {has_5_buttons}; "
                        f"Preview modal with scaled iframe: {has_preview_modal}; Manifest 200: {manifest_ok}; "
                        f"Admin SW registered: {sw_registered}")
            record(7, "Settings (Theme persist, display preview modals, PWA SW)", item7_pass, details7)
        except Exception as e:
            close_all_modals(page)
            record(7, "Settings (Theme persist, display preview modals, PWA SW)", False, f"Exception: {e}")

        # =========================================================================
        # 8. Heartbeat: opening /display/<CODE> shows Online in Screens tab within 30s
        # =========================================================================
        print("\n--- Testing Item 8: Heartbeat ---", flush=True)
        try:
            page.bring_to_front()
            ensure_authenticated(page)
            switch_to_tab(page, 'screens')
            page.wait_for_selector("#view-screens:not(.hidden)", timeout=4000)

            # Open /display/EXTC in a separate page
            disp_extc = context.new_page()
            disp_extc.goto(f"{BASE_URL_DISPLAY}/display/EXTC")
            disp_extc.wait_for_selector("#display-frame, #text-headline", timeout=8000)

            # Wait for heartbeat to register in admin
            online_detected = False
            start_wait = time.time()
            while time.time() - start_wait < 30:
                page.bring_to_front()
                extc_card = page.locator(".screen-item-card[data-code='EXTC']")
                if extc_card.count() > 0:
                    text = extc_card.inner_text()
                    if "Online" in text:
                        online_detected = True
                        break
                page.evaluate("if (typeof loadScreens === 'function') loadScreens();")
                time.sleep(2)

            disp_extc.close()

            item8_pass = online_detected
            details8 = f"EXTC showed Online within 30s: {online_detected}"
            record(8, "Heartbeat (/display/<CODE> shows Online within 30s)", item8_pass, details8)
        except Exception as e:
            close_all_modals(page)
            record(8, "Heartbeat (/display/<CODE> shows Online within 30s)", False, f"Exception: {e}")

        context.close()
        browser.close()

    print("\n" + "=" * 70, flush=True)
    print("PART 0 AUDIT RESULTS SUMMARY TABLE", flush=True)
    print("=" * 70, flush=True)
    print("| Item | Requirement | Status | Details |", flush=True)
    print("| :--- | :--- | :--- | :--- |", flush=True)
    for r in results:
        print(f"| {r['num']} | {r['name']} | **{r['status']}** | {r['details']} |", flush=True)

if __name__ == "__main__":
    run_truth_audit()
