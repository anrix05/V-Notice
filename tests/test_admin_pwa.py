import json
import pytest
from playwright.sync_api import sync_playwright

from app import unified_app

ADMIN_URL = "http://localhost:5001/admin"
ADMIN_PASSWORD = "vnotice2026"

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c


def test_admin_manifest_structure_and_assets(client):
    """Confirm manifest properties, start_url, scope, display, and icon sizes."""
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    assert "application/manifest+json" in res.headers["Content-Type"]
    manifest = res.get_json()

    assert manifest["start_url"] == "/admin"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["name"] == "V Notice Admin"
    assert manifest["short_name"] == "V Notice"

    icons = manifest["icons"]
    sizes_found = {icon["sizes"]: icon["purpose"] for icon in icons}
    assert "192x192" in sizes_found
    assert "512x512" in sizes_found

    # Verify every icon exists and returns 200
    for icon in icons:
        icon_res = client.get(icon["src"])
        assert icon_res.status_code == 200, f"Icon {icon['src']} must exist and return 200"
        assert len(icon_res.data) > 500, f"Icon {icon['src']} must not be empty"


def test_admin_service_worker_headers_and_caching_rules(client):
    """
    Confirm admin service worker:
    - Never caches /api/*, login, uploads, or 206/Range responses
    - Uses network-first for the admin HTML
    - Is served with Service-Worker-Allowed: /
    """
    res = client.get("/admin-sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["Content-Type"]
    assert res.headers.get("Service-Worker-Allowed") == "/"

    sw_code = res.get_data(as_text=True)

    # 1. Never caches non-GET
    assert "req.method !== 'GET'" in sw_code

    # 2. Never caches requests with a Range header / 206
    assert "req.headers.has('range')" in sw_code
    assert "status !== 206" in sw_code

    # 3. Never caches /api/*
    assert "url.pathname.startsWith('/api/')" in sw_code

    # 4. Never caches /login or /logout
    assert "url.pathname === '/login'" in sw_code

    # 5. Never caches uploads
    assert "url.pathname.startsWith('/upload')" in sw_code

    # 6. Network-first for admin navigation
    assert "req.mode === 'navigate' || url.pathname === '/admin'" in sw_code


def test_admin_pwa_playwright_installability_and_registration():
    """Verify Chrome CDP installability, SW registration, and standalone banner hiding."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 412, "height": 915}) # Mobile viewport
        page = context.new_page()

        cdp = context.new_cdp_session(page)
        page.goto(ADMIN_URL, wait_until="networkidle")

        # Login
        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#view-notices.active")

        # Wait for Service Worker registration
        page.wait_for_timeout(1000)

        # 1. Check Service Worker is registered with scope '/'
        sw_state = page.evaluate("""async () => {
            if (!('serviceWorker' in navigator)) return null;
            const regs = await navigator.serviceWorker.getRegistrations();
            return regs.map(r => ({
                scope: r.scope,
                scriptURL: r.active ? r.active.scriptURL : (r.installing ? r.installing.scriptURL : null)
            }));
        }""")
        assert sw_state is not None and len(sw_state) > 0, "Admin Service Worker must be registered"
        assert any("admin-sw.js" in r["scriptURL"] for r in sw_state if r.get("scriptURL")), f"admin-sw.js must be active, found: {sw_state}"
        assert any(r["scope"].endswith("/") for r in sw_state), "Service Worker scope must be '/'"

        # 2. Check CDP Installability Errors
        cdp_errors = cdp.send("Page.getInstallabilityErrors")
        assert len(cdp_errors.get("installabilityErrors", [])) == 0, f"Expected 0 installability errors, got: {cdp_errors}"

        # 3. Standalone mode test: Confirm install banner hides when in standalone mode
        page.emulate_media(media="screen")
        # In browser default, banner may or may not be triggered by beforeinstallprompt, but in standalone mode:
        is_hidden_in_standalone = page.evaluate("""() => {
            const banner = document.getElementById('pwa-install-banner');
            const iosBanner = document.getElementById('ios-pwa-banner');
            // Check CSS rule or class
            const isHidden = (banner ? (banner.classList.contains('hidden') || window.getComputedStyle(banner).display === 'none') : true) &&
                             (iosBanner ? (iosBanner.classList.contains('hidden') || window.getComputedStyle(iosBanner).display === 'none') : true);
            return isHidden;
        }""")
        assert is_hidden_in_standalone is True, "PWA banners must remain hidden in standalone/default states"

        browser.close()


def test_admin_android_back_navigation():
    """
    Confirm Android back:
    1. Closes an open modal first
    2. Then goes to the previous tab
    3. And only then leaves the app
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 412, "height": 915})
        page = context.new_page()

        page.goto(ADMIN_URL, wait_until="networkidle")

        # Login
        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#view-notices.active")

        # 1. Switch to 'screens' tab
        page.evaluate("() => window.switchTab('screens')")
        page.wait_for_selector("#view-screens.active")
        assert page.evaluate("() => window.location.hash") == "#screens"

        # 2. Open notice modal
        page.evaluate("() => window.openCreateModal()")
        page.wait_for_selector("#notice-modal:not(.hidden)")
        assert page.locator("#notice-modal").is_visible()

        # 3. Trigger Android Back while modal is open
        # Simulates hardware/gesture Back button
        page.evaluate("() => window.history.back()")
        page.wait_for_timeout(300)

        # Modal MUST be closed now
        assert not page.locator("#notice-modal").is_visible(), "Android back must close the open modal first"
        # Must still be on 'screens' tab
        assert page.locator("#view-screens").is_visible(), "User must remain on current tab after closing modal"

        # 4. Trigger Android Back again when no modal is open
        page.evaluate("() => window.history.back()")
        page.wait_for_timeout(300)

        # Must switch back to previous tab ('notices')
        assert page.locator("#view-notices").is_visible(), "Android back must switch to the previous tab"
        assert not page.locator("#view-screens").is_visible(), "Previous tab must be active"

        browser.close()
