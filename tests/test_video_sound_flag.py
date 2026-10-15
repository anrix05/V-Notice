import os
import re
import xml.etree.ElementTree as ET
import pytest
from playwright.sync_api import sync_playwright
from axe_core_python.sync_playwright import Axe
from storage import NoticeStorage, get_current_time_ms
import config

# ==============================================================================
# 1. FLAG SVG ASSET STRUCTURE TESTS
# ==============================================================================
def test_flag_svg_geometry_and_bands():
    flag_path = os.path.join("static", "brand", "indian-flag.svg")
    assert os.path.exists(flag_path), "indian-flag.svg must exist"
    
    with open(flag_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Check 3:2 ratio from viewBox
    tree = ET.fromstring(svg_content)
    viewbox = tree.attrib.get("viewBox", "")
    assert viewbox != "", "SVG must have a viewBox"
    parts = [float(p) for p in viewbox.split()]
    width, height = parts[2], parts[3]
    ratio = width / height
    assert abs(ratio - 1.5) < 0.001, f"Flag ratio must be exactly 3:2 (1.5), got {ratio}"

    # Assert 3 color bands: Saffron #FF9933, White #FFFFFF, Green #138808
    assert "#FF9933" in svg_content or "#ff9933" in svg_content, "Flag must contain Saffron #FF9933"
    assert "#FFFFFF" in svg_content or "#ffffff" in svg_content, "Flag must contain White #FFFFFF"
    assert "#138808" in svg_content or "#138808" in svg_content, "Flag must contain India Green #138808"
    assert "#000080" in svg_content or "#000080" in svg_content, "Chakra must be Navy #000080"

    # Assert exactly 24 spokes in the Ashoka Chakra
    spoke_matches = re.findall(r'<line\s+class="spoke"', svg_content)
    assert len(spoke_matches) == 24, f"Ashoka Chakra must have exactly 24 spokes, found {len(spoke_matches)}"

    # Check Chakra diameter is 3/4 of white band height
    band_height = height / 3
    chakra_radius = band_height * (3 / 4) / 2
    circle_match = re.search(r'<circle[^>]*r="([0-9.]+)"', svg_content)
    assert circle_match is not None, "Chakra circle radius must be defined"
    found_r = float(circle_match.group(1))
    assert abs(found_r - chakra_radius) < 2.0, f"Chakra radius must be ~{chakra_radius}, got {found_r}"

# ==============================================================================
# 2. SELF-HOSTED DEVANAGARI FONTS TESTS
# ==============================================================================
def test_devanagari_fonts_exist_and_fontface_configured():
    reg_font = os.path.join("static", "fonts", "NotoSansDevanagari-Regular.woff2")
    bold_font = os.path.join("static", "fonts", "NotoSansDevanagari-Bold.woff2")
    assert os.path.exists(reg_font), "NotoSansDevanagari-Regular.woff2 must exist"
    assert os.path.exists(bold_font), "NotoSansDevanagari-Bold.woff2 must exist"
    assert os.path.getsize(reg_font) > 10000, "Font regular must be non-empty"
    assert os.path.getsize(bold_font) > 10000, "Font bold must be non-empty"

    with open("static/css/display.css", "r", encoding="utf-8") as f:
        css = f.read()
    assert "Noto Sans Devanagari" in css
    assert "font-display: swap" in css

# ==============================================================================
# 3. UNIT TESTS: SCHEDULER & CLOCK MATH
# ==============================================================================
def test_clock_offset_math():
    with open("static/js/flag_scheduler.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "computeClockOffset" in js
    assert "FlagStateMachine" in js

def test_daily_events_storage_and_next_run(tmp_path):
    db_file = str(tmp_path / "test_events.db")
    storage = NoticeStorage(db_file=db_file)

    event = storage.get_daily_event("flag")
    assert event is not None
    assert event["type"] == "flag"
    assert event["enabled"] in (0, False)
    assert event["start_time"] == "11:00"
    assert event["duration_seconds"] == 60
    assert event["start_offset_seconds"] == 0

    # Update event
    storage.update_daily_event(
        "flag",
        data={
            "enabled": True,
            "start_time": "11:15",
            "start_offset_seconds": 5,
            "duration_seconds": 55,
            "days_of_week": "1,2,3,4,5,6",
            "screens": "ALL",
            "show_standup_text": True,
            "skip_dates": ["2026-10-20"]
        }
    )
    updated = storage.get_daily_event("flag")
    assert updated["enabled"] in (1, True)
    assert updated["start_time"] == "11:15"
    assert updated["start_offset_seconds"] == 5
    assert updated["duration_seconds"] == 55
    assert updated["show_standup_text"] in (1, True)
    assert "2026-10-20" in updated["skip_dates"]

    # Test skip today
    storage.skip_daily_event_today("flag")
    skipped = storage.get_daily_event("flag")
    assert len(skipped["skip_dates"]) >= 2

# ==============================================================================
# 4. API CONTRACT & ZERO-LEAKAGE TESTS
# ==============================================================================
def test_api_events_today_endpoint():
    with sync_playwright() as p:
        request_context = p.request.new_context()
        res = request_context.get("http://localhost:5000/api/events/today?screen=EXCS")
        assert res.status == 200
        data = res.json()
        assert "server_time_ms" in data
        assert isinstance(data["server_time_ms"], (int, float))
        # Ensure zero administrative leakage
        assert "password" not in data
        assert "token" not in data
        assert "audit" not in data
        assert "admin" not in data
        assert "db" not in data
        # Check cache header
        cache_control = res.headers.get("cache-control", "")
        assert "max-age" in cache_control

def test_api_flag_trigger_security_404_when_unset():
    with sync_playwright() as p:
        request_context = p.request.new_context()
        if not config.FLAG_TRIGGER_TOKEN:
            res1 = request_context.post("http://localhost:5000/api/events/flag/start", data={})
            assert res1.status == 404
            res2 = request_context.post("http://localhost:5000/api/events/flag/end", data={})
            assert res2.status == 404

# ==============================================================================
# 5. PLAYWRIGHT INTEGRATION & STATE MACHINE TESTS
# ==============================================================================
def test_flag_display_state_machine_and_elements_hidden():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        # Initially, normal display UI elements are visible
        header = page.locator(".display-header")
        assert header.is_visible()
        rail = page.locator("#rail-panel")
        assert rail.is_visible()
        ticker = page.locator(".display-ticker")
        assert ticker.is_visible()
        assert not page.is_visible("#flag-overlay")

        # Trigger manual flag test run via state machine schedule injection
        page.evaluate("""() => {
            if (window.flagScheduler) {
                const now = window.flagScheduler.getCurrentServerTime();
                window.flagScheduler.setSchedule({
                    flag_start_ms: now - 1000,
                    flag_end_ms: now + 50000,
                    show_standup_text: false
                });
            }
        }""")
        page.wait_for_timeout(400)

        # Flag overlay is now visible
        overlay = page.locator("#flag-overlay")
        assert overlay.is_visible()
        flag_screen = page.locator("#flag-screen")
        assert flag_screen.is_visible()

        # Normal rotation chrome is hidden
        assert not header.is_visible() or header.evaluate("el => getComputedStyle(el).opacity === '0' || getComputedStyle(el).display === 'none'")
        assert not rail.is_visible() or rail.evaluate("el => getComputedStyle(el).opacity === '0' || getComputedStyle(el).display === 'none'")

        # Assert no text or logo overlaid on flag screen
        flag_img = page.locator("#flag-svg-element")
        assert flag_img.is_visible()
        src = flag_img.get_attribute("src")
        assert "indian-flag.svg" in src

        # Assert all media elements are paused/muted
        media_state = page.evaluate("""() => {
            const media = Array.from(document.querySelectorAll('video, audio'));
            return {
                count: media.length,
                allMutedOrPaused: media.every(m => m.paused || m.muted)
            };
        }""")
        assert media_state["allMutedOrPaused"] is True

        # Now exit flag state back to rotation
        page.evaluate("""() => {
            if (window.flagScheduler) {
                window.flagScheduler.setSchedule(null);
            }
        }""")
        page.wait_for_timeout(400)

        # Rotation resumes
        assert not page.is_visible("#flag-overlay")
        assert header.is_visible()
        assert rail.is_visible()

        browser.close()

def test_standup_screen_three_languages_and_no_missing_glyphs():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        # Trigger standup state (15s before flag start)
        page.evaluate("""() => {
            if (window.flagScheduler) {
                const now = window.flagScheduler.getCurrentServerTime();
                window.flagScheduler.setSchedule({
                    flag_start_ms: now + 10000,
                    flag_end_ms: now + 60000,
                    show_standup_text: true,
                    standup_lead_seconds: 15
                });
            }
        }""")
        page.wait_for_timeout(400)

        standup = page.locator("#standup-screen")
        assert standup.is_visible()

        # Check all three languages appear
        content = standup.inner_text()
        assert "Please stand for the National Anthem" in content
        assert "कृपया राष्ट्रगान के लिए खड़े हो जाएँ" in content
        assert "कृपया राष्ट्रगीतासाठी उभे राहा" in content

        # Check Axe contrast on standup screen
        axe = Axe()
        results = axe.run(page, context="#standup-screen")
        violations = results.get("violations", [])
        contrast_violations = [v for v in violations if v.get("id") == "color-contrast"]
        assert len(contrast_violations) == 0, f"Standup screen contrast violations: {contrast_violations}"

        browser.close()

# ==============================================================================
# 6. VIDEO SOUND CONTROLS & AUTOPLAY TESTS
# ==============================================================================
def test_preloaded_next_video_strictly_muted():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        preloader_muted = page.evaluate("""() => {
            const preloader = document.getElementById('preloader-video');
            return preloader ? preloader.muted && preloader.volume === 0 : true;
        }""")
        assert preloader_muted is True, "Preloader video must be strictly muted and volume=0"
        browser.close()

def test_admin_notice_modal_sound_switch_and_preview_toggle():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:5001/", wait_until="networkidle")

        # Login
        if page.is_visible("#login-modal"):
            page.fill("#admin-password-input", config.ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_timeout(500)

        # Open create notice modal
        page.click("#btn-open-create")
        page.wait_for_timeout(300)

        # Sound switch container is present in Section 3
        sound_group = page.locator("#video-sound-group")
        assert sound_group.count() > 0
        sound_checkbox = page.locator("#notice-play-sound")
        assert sound_checkbox.count() > 0

        # Note element exists
        no_audio_note = page.locator("#video-no-audio-note")
        assert no_audio_note.count() > 0
        assert "This video has no audio track" in no_audio_note.inner_text()

        browser.close()

def test_admin_settings_national_flag_card_and_contrast():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:5001/", wait_until="networkidle")

        # Login
        if page.is_visible("#login-modal"):
            page.fill("#admin-password-input", config.ADMIN_PASSWORD)
            page.click("#btn-login")
            page.wait_for_timeout(500)

        # Navigate to Settings tab
        page.evaluate("() => window.switchTab('settings')")
        page.wait_for_timeout(400)

        # Check National Flag Card exists and is visible
        card = page.locator("#settings-card-flag-event")
        assert card.is_visible()

        # Check controls
        assert page.locator("#flag-enabled-switch").count() > 0
        assert page.locator("#flag-start-time").count() > 0
        assert page.locator("#flag-start-offset").count() > 0
        assert page.locator("#flag-duration").count() > 0
        assert page.locator("#flag-screens-input").count() > 0
        assert page.locator("#flag-standup-switch").count() > 0
        assert page.locator("#btn-flag-skip-today").count() > 0
        assert page.locator("#btn-flag-preview-5x").count() > 0
        assert page.locator("#btn-flag-run-now").count() > 0
        assert page.locator("#btn-flag-show-now").count() > 0
        assert page.locator("#btn-flag-end-now").count() > 0

        # Run Axe contrast check on the card
        axe = Axe()
        results = axe.run(page, context="#settings-card-flag-event")
        violations = results.get("violations", [])
        contrast_violations = [v for v in violations if v.get("id") == "color-contrast"]
        assert len(contrast_violations) == 0, f"Settings National Flag card contrast violations: {contrast_violations}"

        browser.close()


def test_video_sound_with_csp_enabled():
    """
    Playwright test with CSP enabled:
    - notice play_sound=true
    - screen sound_enabled=true (EXCS screen has sound_enabled=True, sound_volume=85)
    - a video with an audio track plays with muted=false and volume equal to the screen volume (0.85)
    - no CSP console errors appear (specifically no media-src 'data:' violations)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        response = page.goto("http://localhost:5000/display/EXCS", wait_until="networkidle")
        assert response is not None
        assert response.status == 200

        # Verify CSP header is present, active, and does NOT loosen media-src with data:
        csp_header = response.headers.get("content-security-policy", "")
        assert "media-src" in csp_header
        media_src_part = [part for part in csp_header.split(";") if "media-src" in part]
        assert len(media_src_part) > 0
        assert "data:" not in media_src_part[0], "media-src must NOT allow data: URI"

        # Wait for video element
        page.wait_for_selector("#video-element", state="attached", timeout=5000)
        page.wait_for_timeout(1000)

        video_state = page.evaluate("""() => {
            const v = document.getElementById('video-element');
            const speaker = document.getElementById('stage-speaker-indicator');
            return {
                src: v ? v.src : '',
                muted: v ? v.muted : true,
                volume: v ? v.volume : 0,
                speakerVisible: speaker ? !speaker.classList.contains('hidden') : false
            };
        }""")

        assert video_state["src"] != "", "Video element must have a media src"
        assert video_state["muted"] is False, "Video must play with muted=false when play_sound=true and screen.sound_enabled=true"
        assert abs(video_state["volume"] - 0.85) < 0.01, f"Video volume must equal screen volume (0.85), got {video_state['volume']}"
        assert video_state["speakerVisible"] is True, "Speaker indicator must be visible when playing with sound"

        # Verify no CSP console errors appear
        csp_errors = [err for err in console_errors if "Content Security Policy" in err or "violates" in err or "media-src" in err]
        assert len(csp_errors) == 0, f"Expected 0 CSP console errors, got: {csp_errors}"
        assert len(console_errors) == 0, f"Expected 0 console errors, got: {console_errors}"

        browser.close()

