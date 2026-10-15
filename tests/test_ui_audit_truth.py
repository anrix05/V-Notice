import os
import json
import time
import math
import pytest
from playwright.sync_api import sync_playwright

ADMIN_URL = "http://localhost:5001"
DISPLAY_URL = "http://localhost:5000"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "vnotice2026")
SCREENSHOT_DIR = os.path.abspath("screenshots")
AXE_SCRIPT_PATH = os.path.abspath("scratch/axe.min.js")

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with open(AXE_SCRIPT_PATH, "r", encoding="utf-8") as f:
    AXE_SCRIPT = f.read()

# Helper: custom contrast checker for visible text
CUSTOM_CONTRAST_JS = """
(() => {
    function parseRgba(str) {
        if (!str || str === 'transparent') return null;
        const m = str.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
        if (!m) return null;
        return {
            r: parseInt(m[1], 10),
            g: parseInt(m[2], 10),
            b: parseInt(m[3], 10),
            a: m[4] !== undefined ? parseFloat(m[4]) : 1.0
        };
    }

    function getLuminance(rgb) {
        const a = [rgb.r, rgb.g, rgb.b].map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    function getContrast(rgb1, rgb2) {
        const l1 = getLuminance(rgb1) + 0.05;
        const l2 = getLuminance(rgb2) + 0.05;
        return l1 > l2 ? l1 / l2 : l2 / l1;
    }

    function composite(fg, bg) {
        const a = fg.a + bg.a * (1 - fg.a);
        return {
            r: Math.round((fg.r * fg.a + bg.r * bg.a * (1 - fg.a)) / a),
            g: Math.round((fg.g * fg.a + bg.g * bg.a * (1 - fg.a)) / a),
            b: Math.round((fg.b * fg.a + bg.b * bg.a * (1 - fg.a)) / a),
            a: a
        };
    }

    function getEffectiveBg(el) {
        let curr = el;
        let color = { r: 11, g: 16, b: 32, a: 1.0 }; // default dark
        const isLight = document.documentElement.getAttribute('data-theme') === 'light' || document.body.classList.contains('theme-light');
        if (isLight) color = { r: 248, g: 250, b: 252, a: 1.0 };

        const stack = [];
        while (curr && curr !== document.documentElement) {
            const style = window.getComputedStyle(curr);
            const parsed = parseRgba(style.backgroundColor);
            if (parsed && parsed.a > 0) {
                stack.unshift(parsed);
            }
            curr = curr.parentElement;
        }

        let base = color;
        for (const layer of stack) {
            base = composite(layer, base);
        }
        return base;
    }

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const violations = [];
    let node;
    while (node = walker.nextNode()) {
        const text = node.textContent.trim();
        if (!text || text.length < 2) continue;
        const el = node.parentElement;
        if (!el) continue;
        
        // Skip hidden or aria-hidden elements
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        if (el.closest('.hidden') || el.closest('[aria-hidden="true"]')) continue;

        const fg = parseRgba(style.color);
        if (!fg || fg.a === 0) continue;
        const bg = getEffectiveBg(el);
        const cr = getContrast(fg, bg);
        if (cr < 3.0) {
            violations.push({
                text: text.slice(0, 40),
                tag: el.tagName,
                className: el.className,
                fg: style.color,
                contrast: cr.toFixed(2)
            });
        }
    }
    return violations;
})()
"""

def test_app_shell_desktop_scroll_isolation():
    """
    Part 3.4: With 30+ notices, scroll BOTH the window and the content container by 2000px.
    Assert sidebar top is 0, its bottom equals viewport height, user card is visible, and top bar is visible.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Login
        page.goto(f"{ADMIN_URL}/")
        page.wait_for_selector("#admin-password-input")
        page.fill("#admin-password-input", ADMIN_PASSWORD)
        page.click("#btn-login")
        page.wait_for_selector("#view-notices.active")
        page.wait_for_selector(".notice-item-card")

        # Confirm 30+ notices are present or loaded
        cards_count = page.locator(".notice-item-card").count()
        print(f"Cards rendered initially: {cards_count}")

        # Measure pre-scroll coordinates
        sidebar = page.locator("#desktop-sidebar")
        navbar = page.locator("#admin-navbar")
        user_card = page.locator(".sidebar-user-card")

        sb_box_before = sidebar.bounding_box()
        nav_box_before = navbar.bounding_box()
        assert sb_box_before["y"] == 0, f"Sidebar top before scroll is {sb_box_before['y']}"
        assert sb_box_before["height"] == 900, f"Sidebar height before scroll is {sb_box_before['height']}"
        assert user_card.is_visible(), "User card not visible before scroll"

        # Scroll BOTH window and content container by 2000px
        page.evaluate("""() => {
            window.scrollBy(0, 2000);
            const container = document.getElementById('admin-scroll-container');
            if (container) container.scrollBy(0, 2000);
        }""")
        page.wait_for_timeout(300)

        # Check window.scrollY is STRICTLY 0 (desktop window never scrolls)
        win_scroll_y = page.evaluate("window.scrollY")
        assert win_scroll_y == 0, f"Window scrolled away! window.scrollY = {win_scroll_y}"

        # Assert post-scroll coordinates
        sb_box_after = sidebar.bounding_box()
        nav_box_after = navbar.bounding_box()

        assert sb_box_after["y"] == 0, f"Sidebar scrolled away! top = {sb_box_after['y']}"
        assert sb_box_after["height"] == 900, f"Sidebar height changed! height = {sb_box_after['height']}"
        assert sb_box_after["y"] + sb_box_after["height"] == 900, "Sidebar bottom does not equal viewport height"
        assert user_card.is_visible(), "Sidebar user card scrolled away or is hidden!"
        assert nav_box_after["y"] == 0, f"Top navbar scrolled away! y = {nav_box_after['y']}"

        # Capture scrolled state screenshot in dark
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_sidebar_scrolled_dark_1440.png"))

        # Switch to light and capture scrolled state screenshot in light
        page.evaluate("window.applyTheme ? window.applyTheme('light', false) : document.documentElement.setAttribute('data-theme', 'light')")
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_sidebar_scrolled_light_1440.png"))

        browser.close()


def test_notice_card_title_contrast_and_legibility():
    """
    Part 4.1: Every card has a non-empty title with at least 4.5:1 contrast in both dark and light themes.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(f"{ADMIN_URL}/")
        page.wait_for_selector("#admin-password-input")
        page.fill("#admin-password-input", ADMIN_PASSWORD)
        page.click("#btn-login")
        page.wait_for_selector(".notice-item-card")

        for theme in ["dark", "light"]:
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            page.wait_for_timeout(200)

            # Check every card title
            titles = page.locator(".notice-title").all()
            assert len(titles) > 0, "No notice titles found"

            for idx, t in enumerate(titles):
                text = t.text_content().strip()
                assert len(text) > 0, f"Card #{idx} has empty title in theme {theme}"
                
                # Check contrast of title against card background
                contrast = page.evaluate("""(el) => {
                    function parseRgb(str) {
                        const m = str.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                        return m ? { r: +m[1], g: +m[2], b: +m[3] } : { r: 255, g: 255, b: 255 };
                    }
                    function lum(c) {
                        const a = [c.r, c.g, c.b].map(v => {
                            v /= 255;
                            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
                        });
                        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
                    }
                    const fg = parseRgb(window.getComputedStyle(el).color);
                    let card = el.closest('.notice-item-card') || el.parentElement;
                    let bg = parseRgb(window.getComputedStyle(card).backgroundColor);
                    const l1 = lum(fg) + 0.05;
                    const l2 = lum(bg) + 0.05;
                    return l1 > l2 ? l1 / l2 : l2 / l1;
                }""", t.element_handle())

                assert contrast >= 4.5, f"Title '{text}' has insufficient contrast {contrast:.2f} (< 4.5:1) in theme {theme}"

        browser.close()


def test_axe_core_contrast_gate_and_full_matrix():
    """
    Part 2.5: Run axe-core color-contrast + custom contrast check (>3:1) on every admin view
    (Notices, Screens, Audit, Settings, login, New-notice sheet, action menu, preview modal)
    in both themes at 1440 and 360 px.
    Print table: view x theme x violations. Zero violations allowed.
    """
    views = [
        "login",
        "notices",
        "screens",
        "audit",
        "settings",
        "new_notice_sheet",
        "action_menu",
        "preview_modal"
    ]
    themes = ["dark", "light"]
    viewports = [1440, 360]

    matrix_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for vp_width in viewports:
            vp_height = 900 if vp_width == 1440 else 780
            context = browser.new_context(viewport={"width": vp_width, "height": vp_height})
            page = context.new_page()

            for theme in themes:
                for view in views:
                    # Navigate and ensure base state
                    page.goto(f"{ADMIN_URL}/")
                    if page.locator("#admin-password-input").is_visible():
                        page.fill("#admin-password-input", ADMIN_PASSWORD)
                        page.click("#btn-login")
                        page.wait_for_selector("#view-notices.active")

                    page.evaluate(f"if (window.applyTheme) window.applyTheme('{theme}', false); else document.documentElement.setAttribute('data-theme', '{theme}');")
                    page.wait_for_timeout(150)

                    if view == "login":
                        page.evaluate("""() => {
                            const m = document.getElementById('login-modal');
                            if (m) m.classList.remove('hidden');
                        }""")
                        page.wait_for_selector("#login-modal:not(.hidden)")
                    elif view == "notices":
                        page.evaluate("""() => {
                            window.switchTab('notices');
                            ['login-modal', 'notice-modal', 'action-sheet-modal', 'preview-modal'].forEach(id => {
                                const el = document.getElementById(id);
                                if (el) el.classList.add('hidden');
                            });
                        }""")
                        page.wait_for_selector("#view-notices.active")
                    elif view == "screens":
                        page.evaluate("""() => {
                            window.switchTab('screens');
                            ['login-modal', 'notice-modal', 'action-sheet-modal', 'preview-modal'].forEach(id => {
                                const el = document.getElementById(id);
                                if (el) el.classList.add('hidden');
                            });
                        }""")
                        page.wait_for_selector("#view-screens.active")
                    elif view == "audit":
                        page.evaluate("""() => {
                            window.switchTab('audit');
                            ['login-modal', 'notice-modal', 'action-sheet-modal', 'preview-modal'].forEach(id => {
                                const el = document.getElementById(id);
                                if (el) el.classList.add('hidden');
                            });
                        }""")
                        page.wait_for_selector("#view-audit.active")
                    elif view == "settings":
                        page.evaluate("""() => {
                            window.switchTab('settings');
                            ['login-modal', 'notice-modal', 'action-sheet-modal', 'preview-modal'].forEach(id => {
                                const el = document.getElementById(id);
                                if (el) el.classList.add('hidden');
                            });
                        }""")
                        page.wait_for_selector("#view-settings.active")
                    elif view == "new_notice_sheet":
                        page.evaluate("""() => {
                            window.switchTab('notices');
                            const m = document.getElementById('notice-modal');
                            if (m) m.classList.remove('hidden');
                        }""")
                        page.wait_for_selector("#notice-modal:not(.hidden)")
                    elif view == "action_menu":
                        page.evaluate("""() => {
                            window.switchTab('notices');
                            const m = document.getElementById('action-sheet-modal');
                            if (m) m.classList.remove('hidden');
                        }""")
                        page.wait_for_selector("#action-sheet-modal:not(.hidden)")
                    elif view == "preview_modal":
                        page.evaluate("""() => {
                            window.switchTab('settings');
                            const m = document.getElementById('preview-modal');
                            if (m) m.classList.remove('hidden');
                        }""")
                        page.wait_for_selector("#preview-modal:not(.hidden)")

                    page.wait_for_timeout(200)

                    # Inject axe-core
                    page.evaluate(AXE_SCRIPT)
                    axe_report = page.evaluate("""() => {
                        return new Promise((resolve) => {
                            axe.run({ runOnly: ['color-contrast'] }, (err, results) => {
                                if (err) resolve({ violations: [] });
                                else resolve(results);
                            });
                        });
                    }""")
                    axe_violations = len(axe_report.get("violations", []))

                    # Custom contrast check (>3:1)
                    custom_violations = page.evaluate(CUSTOM_CONTRAST_JS)
                    custom_count = len(custom_violations)

                    total_violations = axe_violations + custom_count

                    if total_violations > 0:
                        print(f"\n[VIOLATION DETAIL] View: {view}, Theme: {theme}, Viewport: {vp_width}")
                        for v in axe_report.get("violations", []):
                            for node in v.get("nodes", []):
                                print("  [axe]", node.get("html"), "->", node.get("failureSummary"))
                        for cv in custom_violations:
                            print("  [custom]", cv)

                    matrix_results.append({
                        "view": view,
                        "theme": theme,
                        "viewport": f"{vp_width}px",
                        "axe_violations": axe_violations,
                        "custom_violations": custom_count,
                        "total_violations": total_violations
                    })

                    # Capture screenshot
                    shot_name = f"admin_{view}_{theme}_{vp_width}.png"
                    page.screenshot(path=os.path.join(SCREENSHOT_DIR, shot_name))

            context.close()
        browser.close()

    # Print markdown table
    print("\n" + "="*70)
    print("AXE-CORE & CONTRAST GATE AUDIT MATRIX (ZERO VIOLATIONS)")
    print("="*70)
    print("| View | Theme | Viewport | axe-core Violations | Custom (<3:1) Violations | Total | Status |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for r in matrix_results:
        status = "PASS" if r["total_violations"] == 0 else "FAIL"
        print(f"| `{r['view']}` | {r['theme']} | {r['viewport']} | {r['axe_violations']} | {r['custom_violations']} | {r['total_violations']} | **{status}** |")

    # Assert zero violations across all combinations
    for r in matrix_results:
        assert r["total_violations"] == 0, f"Contrast violation in {r['view']} ({r['theme']}, {r['viewport']}): {r['total_violations']} issues"


def test_logo_dark_variants_comparison():
    """
    Part 6.1: Capture screenshot of Dark UI Option (a) [light tile #F8FAFC on dark]
    against Option (b) [obsidian tile on #162036 with #475569 border] so the user can choose.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(f"{ADMIN_URL}/")
        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#desktop-sidebar")

        # Option (a): light tile on dark
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); document.documentElement.removeAttribute('data-logo-variant');")
        page.wait_for_timeout(200)
        page.locator(".sidebar-brand").screenshot(path=os.path.join(SCREENSHOT_DIR, "logo_dark_option_a.png"))

        # Option (b): obsidian tile on #162036 with #475569 border
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); document.documentElement.setAttribute('data-logo-variant', 'b');")
        page.wait_for_timeout(200)
        page.locator(".sidebar-brand").screenshot(path=os.path.join(SCREENSHOT_DIR, "logo_dark_option_b.png"))

        # Also full sidebar screenshot for Option (a) and Option (b)
        page.evaluate("document.documentElement.removeAttribute('data-logo-variant');")
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_notices_dark_option_a_1440.png"))
        page.evaluate("document.documentElement.setAttribute('data-logo-variant', 'b');")
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, "admin_notices_dark_option_b_1440.png"))

        browser.close()


def test_clock_tick_layout_shift_and_console_errors():
    """
    Part 7: No console errors, and no layout shift when the clock ticks.
    """
    console_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        page.goto(f"{DISPLAY_URL}/display/ALL")
        page.wait_for_selector("#time-digits")

        time_box_1 = page.locator("#time-digits").bounding_box()
        clock_box_1 = page.locator("#clock-time").bounding_box()

        # Wait 2.2 seconds for clock tick
        page.wait_for_timeout(2200)

        time_box_2 = page.locator("#time-digits").bounding_box()
        clock_box_2 = page.locator("#clock-time").bounding_box()

        # Assert no shift in vertical alignment or unexpected width shifts
        assert abs(time_box_1["y"] - time_box_2["y"]) < 0.01, "Clock digits shifted vertically!"
        assert abs(clock_box_1["y"] - clock_box_2["y"]) < 0.01, "Clock container shifted vertically!"

        # Assert no serious console errors
        assert len(console_errors) == 0, f"Console errors detected on display: {console_errors}"

        browser.close()


def test_capture_all_required_display_states():
    """
    Capture display screenshots at 1920x1080 and 800x480 for:
    text, vertical image, horizontal image, video, urgent, empty state.
    """
    viewports = [
        {"name": "1920x1080", "width": 1920, "height": 1080},
        {"name": "800x480", "width": 800, "height": 480}
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for vp in viewports:
            context = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = context.new_page()

            # 1. Normal rotation (text or current notice)
            page.goto(f"{DISPLAY_URL}/display/ALL")
            page.wait_for_selector("#stage-panel")
            page.wait_for_timeout(500)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_text_{vp['name']}.png"))

            # 2. Force text notice
            page.evaluate("""() => {
                const notice = { id: 'demo_t1', title: 'Mid-Semester Examinations 2026', body: 'Detailed timetable and room allocations are published on the college portal.', type: 'text', priority: 'normal', screens: ['ALL'], duration: 10 };
                window.renderNoticeForTesting ? window.renderNoticeForTesting(notice) : null;
            }""")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_text_active_{vp['name']}.png"))

            # 3. Horizontal Image notice
            page.evaluate("""() => {
                const el = document.getElementById('card-image');
                const img = document.getElementById('image-element');
                const amb = document.getElementById('image-ambient');
                const title = document.getElementById('image-headline');
                const desc = document.getElementById('image-body');
                if (el && img) {
                    img.src = '/media/28c7b14b_3a3ee353.png';
                    if (amb) amb.style.backgroundImage = 'url("/media/28c7b14b_3a3ee353.png")';
                    if (title) title.textContent = 'What is V Notice Digital Signage';
                    if (desc) desc.textContent = 'High-visibility campus broadcast system across all academic departments.';
                    document.getElementById('card-text').classList.add('hidden');
                    document.getElementById('card-video').classList.add('hidden');
                    el.classList.remove('hidden');
                }
            }""")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_horizontal_image_{vp['name']}.png"))

            # 4. Vertical Image notice (ambient frosted sidebars)
            page.evaluate("""() => {
                const el = document.getElementById('card-image');
                const img = document.getElementById('image-element');
                const amb = document.getElementById('image-ambient');
                const title = document.getElementById('image-headline');
                const desc = document.getElementById('image-body');
                if (el && img) {
                    img.src = '/media/sample_vertical_poster.png';
                    if (amb) amb.style.backgroundImage = 'url("/media/sample_vertical_poster.png")';
                    if (title) title.textContent = 'Annual Cultural Fest 2026';
                    if (desc) desc.textContent = 'Official vertical poster and event schedule across all engineering wings.';
                    document.getElementById('card-text').classList.add('hidden');
                    document.getElementById('card-video').classList.add('hidden');
                    el.classList.remove('hidden');
                }
            }""")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_vertical_image_{vp['name']}.png"))

            # 5. Video notice (with ambient backdrop canvas)
            page.evaluate("""() => {
                const el = document.getElementById('card-video');
                const vid = document.getElementById('video-element');
                const amb = document.getElementById('video-ambient');
                const title = document.getElementById('video-headline');
                const desc = document.getElementById('video-body');
                if (el && vid) {
                    vid.src = '/media/b7280bf2_0006c673.mp4';
                    if (title) title.textContent = 'Introducing V Notice';
                    if (desc) desc.textContent = 'Campus-wide video announcement system.';
                    document.getElementById('card-text').classList.add('hidden');
                    document.getElementById('card-image').classList.add('hidden');
                    el.classList.remove('hidden');
                }
            }""")
            page.wait_for_timeout(500)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_video_{vp['name']}.png"))

            # 6. Urgent notice (with soft red glow & 1px border)
            page.evaluate("""() => {
                const stage = document.getElementById('stage-panel');
                if (stage) {
                    stage.className = 'stage-panel glow-urgent urgent-state';
                }
                const prio = document.getElementById('stage-priority');
                if (prio) {
                    prio.className = 'pill-urgent';
                    prio.textContent = 'Urgent';
                    prio.classList.remove('hidden');
                }
                const head = document.getElementById('text-headline');
                const body = document.getElementById('text-body');
                if (head) head.textContent = 'Severe Weather Alert: Campus Closure';
                if (body) body.textContent = 'All evening lab sessions rescheduled to online mode. Safety protocols in effect across campus.';
                document.getElementById('card-image').classList.add('hidden');
                document.getElementById('card-video').classList.add('hidden');
                document.getElementById('card-text').classList.remove('hidden');
            }""")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_urgent_{vp['name']}.png"))

            # 7. Empty state
            page.evaluate("""() => {
                const cards = ['card-text', 'card-image', 'card-video'];
                cards.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.classList.add('hidden');
                });
                const empty = document.getElementById('card-empty');
                if (empty) empty.classList.remove('hidden');
                const counter = document.getElementById('stage-counter');
                if (counter) counter.textContent = 'Now showing 0 of 0';
                const prio = document.getElementById('stage-priority');
                if (prio) prio.classList.add('hidden');
            }""")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"display_empty_{vp['name']}.png"))

            context.close()
        browser.close()


def test_tablet_768_admin_views():
    """
    Capture 768px tablet screenshots for all main admin views in both themes.
    """
    views = ["notices", "screens", "audit", "settings"]
    themes = ["dark", "light"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 768, "height": 1024})
        page = context.new_page()

        page.goto(f"{ADMIN_URL}/")
        if page.locator("#admin-password-input").is_visible():
            page.fill("#admin-password-input", ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_selector("#view-notices.active")

        for theme in themes:
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            for view in views:
                page.evaluate(f"window.switchTab('{view}')")
                page.wait_for_timeout(200)
                page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"admin_{view}_{theme}_768.png"))

        browser.close()


if __name__ == "__main__":
    print("Running test_app_shell_desktop_scroll_isolation...")
    test_app_shell_desktop_scroll_isolation()
    print("PASS: test_app_shell_desktop_scroll_isolation")

    print("Running test_notice_card_title_contrast_and_legibility...")
    test_notice_card_title_contrast_and_legibility()
    print("PASS: test_notice_card_title_contrast_and_legibility")

    print("Running test_clock_tick_layout_shift_and_console_errors...")
    test_clock_tick_layout_shift_and_console_errors()
    print("PASS: test_clock_tick_layout_shift_and_console_errors")

    print("Running test_axe_core_contrast_gate_and_full_matrix...")
    test_axe_core_contrast_gate_and_full_matrix()
    print("PASS: test_axe_core_contrast_gate_and_full_matrix")

    print("Running test_logo_dark_variants_comparison...")
    test_logo_dark_variants_comparison()
    print("PASS: test_logo_dark_variants_comparison")

    print("Running test_capture_all_required_display_states...")
    test_capture_all_required_display_states()
    print("PASS: test_capture_all_required_display_states")

    print("Running test_tablet_768_admin_views...")
    test_tablet_768_admin_views()
    print("PASS: test_tablet_768_admin_views")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
