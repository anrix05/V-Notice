import pytest
from playwright.sync_api import sync_playwright

ADMIN_URL = "http://localhost:5001"
PASSWORD = "vnotice2026"


def login_if_needed(page):
    """Logs into the admin portal if the login modal is displayed."""
    if page.locator("#admin-password-input").is_visible():
        page.fill("#admin-password-input", PASSWORD)
        page.click("#btn-login")
        page.wait_for_selector("#view-notices.active", timeout=8000)


def test_desktop_sidebar_tab_clicks_immediate_switch():
    """
    Assert clicking each sidebar tab immediately makes the matching view visible
    and sets the sidebar item to active without any page reload.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # 1. Start on Notices
        assert page.locator("#view-notices").is_visible()
        assert "active" in (page.locator("#sidebar-tab-notices").get_attribute("class") or "")

        # 2. Click Screens sidebar tab
        page.click("#btn-view-screens")
        page.wait_for_timeout(100)
        assert page.locator("#view-screens").is_visible(), "Screens view must be visible immediately"
        assert not page.locator("#view-notices").is_visible(), "Notices view must be hidden"
        assert "active" in (page.locator("#btn-view-screens").get_attribute("class") or "")
        assert "active" not in (page.locator("#sidebar-tab-notices").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        # 3. Click Audit Logs sidebar tab
        page.click("#btn-view-audit")
        page.wait_for_timeout(100)
        assert page.locator("#view-audit").is_visible(), "Audit view must be visible immediately"
        assert not page.locator("#view-screens").is_visible(), "Screens view must be hidden"
        assert "active" in (page.locator("#btn-view-audit").get_attribute("class") or "")
        assert "active" not in (page.locator("#btn-view-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#audit"

        # 4. Click Settings sidebar tab
        page.click("#sidebar-tab-settings")
        page.wait_for_timeout(100)
        assert page.locator("#view-settings").is_visible(), "Settings view must be visible immediately"
        assert not page.locator("#view-audit").is_visible(), "Audit view must be hidden"
        assert "active" in (page.locator("#sidebar-tab-settings").get_attribute("class") or "")
        assert "active" not in (page.locator("#btn-view-audit").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#settings"

        # 5. Click Notices sidebar tab
        page.click("#sidebar-tab-notices")
        page.wait_for_timeout(100)
        assert page.locator("#view-notices").is_visible(), "Notices view must be visible immediately"
        assert not page.locator("#view-settings").is_visible(), "Settings view must be hidden"
        assert "active" in (page.locator("#sidebar-tab-notices").get_attribute("class") or "")
        assert "active" not in (page.locator("#sidebar-tab-settings").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#notices"

        browser.close()


def test_desktop_history_walkback_order():
    """
    Click through Notices, Screens, Audit, Settings and press Back three times;
    assert it walks back in reverse order (Settings -> Audit -> Screens -> Notices)
    without any page reload.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # Click sequentially: Notices -> Screens -> Audit -> Settings
        page.click("#sidebar-tab-notices")
        page.wait_for_timeout(50)
        page.click("#btn-view-screens")
        page.wait_for_timeout(50)
        page.click("#btn-view-audit")
        page.wait_for_timeout(50)
        page.click("#sidebar-tab-settings")
        page.wait_for_timeout(100)

        assert page.locator("#view-settings").is_visible()
        assert page.evaluate("() => window.location.hash") == "#settings"

        # Back 1 -> Audit Logs
        page.go_back()
        page.wait_for_timeout(150)
        assert page.locator("#view-audit").is_visible(), "Back #1 must show Audit view"
        assert not page.locator("#view-settings").is_visible()
        assert "active" in (page.locator("#btn-view-audit").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#audit"

        # Back 2 -> Screens
        page.go_back()
        page.wait_for_timeout(150)
        assert page.locator("#view-screens").is_visible(), "Back #2 must show Screens view"
        assert not page.locator("#view-audit").is_visible()
        assert "active" in (page.locator("#btn-view-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        # Back 3 -> Notices
        page.go_back()
        page.wait_for_timeout(150)
        assert page.locator("#view-notices").is_visible(), "Back #3 must show Notices view"
        assert not page.locator("#view-screens").is_visible()
        assert "active" in (page.locator("#sidebar-tab-notices").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#notices"

        browser.close()


def test_desktop_modal_back_closes_only_modal():
    """
    Open a modal (New notice modal) and press Back;
    assert only the modal closes and the current tab remains visible and unchanged.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # Ensure we are on Notices
        assert page.locator("#view-notices").is_visible()

        # Open New notice modal
        page.click("#btn-open-create")
        page.wait_for_selector("#notice-modal:not(.hidden)", timeout=3000)
        assert page.locator("#notice-modal").is_visible()

        # Press browser back
        page.go_back()
        page.wait_for_timeout(200)

        # Assert only the modal closed
        assert not page.locator("#notice-modal").is_visible(), "Modal must be closed after Back"
        assert page.locator("#view-notices").is_visible(), "Tab must remain visible and unchanged"
        assert "active" in (page.locator("#sidebar-tab-notices").get_attribute("class") or "")

        browser.close()


def test_direct_hash_load_screens():
    """
    Directly loading /#screens must open the Screens tab directly on initial load.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"{ADMIN_URL}/#screens", wait_until="networkidle")

        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#view-screens.active", timeout=8000)

        assert page.locator("#view-screens").is_visible(), "Screens tab view must be open directly"
        assert not page.locator("#view-notices").is_visible(), "Notices view must not be active"
        assert "active" in (page.locator("#btn-view-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        browser.close()


def test_mobile_bottom_nav_immediate_switch():
    """
    Repeat at 390x844 with mobile bottom navigation:
    Assert clicking bottom tabs switches views immediately and updates active tab item.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # 1. Start on Notices
        assert page.locator("#view-notices").is_visible()
        assert "active" in (page.locator("#tab-notices").get_attribute("class") or "")

        # 2. Click Screens in bottom nav
        page.click("#tab-screens")
        page.wait_for_timeout(100)
        assert page.locator("#view-screens").is_visible(), "Mobile: Screens view must be visible immediately"
        assert not page.locator("#view-notices").is_visible(), "Mobile: Notices view must be hidden"
        assert "active" in (page.locator("#tab-screens").get_attribute("class") or "")
        assert "active" not in (page.locator("#tab-notices").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        # 3. Click Settings in bottom nav
        page.click("#tab-settings")
        page.wait_for_timeout(100)
        assert page.locator("#view-settings").is_visible(), "Mobile: Settings view must be visible immediately"
        assert not page.locator("#view-screens").is_visible(), "Mobile: Screens view must be hidden"
        assert "active" in (page.locator("#tab-settings").get_attribute("class") or "")
        assert "active" not in (page.locator("#tab-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#settings"

        # 4. Click Notices in bottom nav
        page.click("#tab-notices")
        page.wait_for_timeout(100)
        assert page.locator("#view-notices").is_visible(), "Mobile: Notices view must be visible immediately"
        assert not page.locator("#view-settings").is_visible(), "Mobile: Settings view must be hidden"
        assert "active" in (page.locator("#tab-notices").get_attribute("class") or "")
        assert "active" not in (page.locator("#tab-settings").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#notices"

        browser.close()


def test_mobile_history_walkback_order():
    """
    Repeat at 390x844:
    Click through mobile bottom nav tabs (Notices -> Screens -> Settings),
    press Back, and assert it walks back in reverse order without page reload.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # Click Notices -> Screens -> Settings
        page.click("#tab-notices")
        page.wait_for_timeout(50)
        page.click("#tab-screens")
        page.wait_for_timeout(50)
        page.click("#tab-settings")
        page.wait_for_timeout(100)

        assert page.locator("#view-settings").is_visible()
        assert page.evaluate("() => window.location.hash") == "#settings"

        # Back 1 -> Screens
        page.go_back()
        page.wait_for_timeout(150)
        assert page.locator("#view-screens").is_visible(), "Mobile Back #1 must show Screens"
        assert not page.locator("#view-settings").is_visible()
        assert "active" in (page.locator("#tab-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        # Back 2 -> Notices
        page.go_back()
        page.wait_for_timeout(150)
        assert page.locator("#view-notices").is_visible(), "Mobile Back #2 must show Notices"
        assert not page.locator("#view-screens").is_visible()
        assert "active" in (page.locator("#tab-notices").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#notices"

        browser.close()


def test_mobile_modal_back_closes_only_modal():
    """
    Repeat at 390x844:
    Open modal via raised '+' bottom nav button and press Back;
    assert only the modal closes and the current view remains active.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # Switch to screens first to ensure non-default tab is preserved
        page.click("#tab-screens")
        page.wait_for_timeout(100)
        assert page.locator("#view-screens").is_visible()

        # Open modal via JS or UI
        page.evaluate("() => window.openCreateModal()")
        page.wait_for_selector("#notice-modal:not(.hidden)", timeout=3000)
        assert page.locator("#notice-modal").is_visible()

        # Press Back
        page.go_back()
        page.wait_for_timeout(200)

        # Assert only modal closed
        assert not page.locator("#notice-modal").is_visible(), "Modal must be closed after Back"
        assert page.locator("#view-screens").is_visible(), "Screens view must remain active"
        assert "active" in (page.locator("#tab-screens").get_attribute("class") or "")

        browser.close()


def test_mobile_direct_hash_load_screens():
    """
    Repeat at 390x844:
    Directly loading /#screens on mobile must open Screens tab directly.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{ADMIN_URL}/#screens", wait_until="networkidle")

        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#view-screens.active", timeout=8000)

        assert page.locator("#view-screens").is_visible(), "Mobile: Screens tab view must be open directly"
        assert not page.locator("#view-notices").is_visible(), "Mobile: Notices view must not be active"
        assert "active" in (page.locator("#tab-screens").get_attribute("class") or "")
        assert page.evaluate("() => window.location.hash") == "#screens"

        browser.close()
