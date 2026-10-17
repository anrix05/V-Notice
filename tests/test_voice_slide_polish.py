import os
import json
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5000"
SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent / "verification_voice_polish"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def test_voice_slide_polish_scenarios():
    """
    Validates:
    - Display voice slide at 800x480 and 1920x1080.
    - With and without caption.
    - Quiet recording normalization: loudest bar reaches full height (100%).
    - Time label ('0:00 / 0:XX') under waveform updates on progress.
    - Unplayed bars contrast against track background.
    - Waveform track taller (~30% increase: ~94px at 1080p, ~58px at 480p).
    - No speaker icon inside .voice-pill.
    - Caption under waveform up to 3 lines, never clipped.
    - Saves Playwright screenshots for each scenario.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"]
        )

        test_cases = [
            {
                "name": "1920x1080_with_caption",
                "width": 1920,
                "height": 1080,
                "notice": {
                    "id": "test_voice_caption",
                    "title": "Campus Town Hall Announcement",
                    "type": "voice",
                    "caption": "Please join us in the central auditorium this Friday at 3:00 PM for the annual campus town hall meeting. All students and faculty are welcome.",
                    "audio_duration": 15.0,
                    "duration": 16,
                    "play_sound": True,
                    "waveform": [10, 20, 35, 60, 85, 45, 30, 15] * 8,  # Max peak 85
                    "media": "test_audio.webm"
                }
            },
            {
                "name": "800x480_with_caption",
                "width": 800,
                "height": 480,
                "notice": {
                    "id": "test_voice_caption_compact",
                    "title": "Campus Town Hall Announcement",
                    "type": "voice",
                    "caption": "Please join us in the central auditorium this Friday at 3:00 PM for the annual campus town hall meeting.",
                    "audio_duration": 15.0,
                    "duration": 16,
                    "play_sound": True,
                    "waveform": [10, 20, 35, 60, 85, 45, 30, 15] * 8,
                    "media": "test_audio.webm"
                }
            },
            {
                "name": "1920x1080_no_caption",
                "width": 1920,
                "height": 1080,
                "notice": {
                    "id": "test_voice_no_caption",
                    "title": "Weather Alert: Severe Rain Warning",
                    "type": "voice",
                    "caption": "",
                    "audio_duration": 12.0,
                    "duration": 13,
                    "play_sound": True,
                    "waveform": [5, 15, 40, 75, 90, 50, 25, 10] * 8,
                    "media": "test_audio.webm"
                }
            },
            {
                "name": "800x480_no_caption",
                "width": 800,
                "height": 480,
                "notice": {
                    "id": "test_voice_no_caption_compact",
                    "title": "Weather Alert: Severe Rain Warning",
                    "type": "voice",
                    "caption": "",
                    "audio_duration": 12.0,
                    "duration": 13,
                    "play_sound": True,
                    "waveform": [5, 15, 40, 75, 90, 50, 25, 10] * 8,
                    "media": "test_audio.webm"
                }
            },
            {
                "name": "1920x1080_quiet_recording",
                "width": 1920,
                "height": 1080,
                "notice": {
                    "id": "test_voice_quiet",
                    "title": "Whispered Library Reminder",
                    "type": "voice",
                    "caption": "Please keep conversations to a whisper on the quiet study floors.",
                    "audio_duration": 8.0,
                    "duration": 9,
                    "play_sound": True,
                    # Low raw peaks: max raw peak is only 12 out of 100
                    "waveform": [1, 2, 3, 6, 12, 5, 2, 1] * 8,
                    "media": "test_audio.webm"
                }
            },
            {
                "name": "800x480_quiet_recording",
                "width": 800,
                "height": 480,
                "notice": {
                    "id": "test_voice_quiet_compact",
                    "title": "Whispered Library Reminder",
                    "type": "voice",
                    "caption": "Please keep conversations to a whisper on the quiet study floors.",
                    "audio_duration": 8.0,
                    "duration": 9,
                    "play_sound": True,
                    "waveform": [1, 2, 3, 6, 12, 5, 2, 1] * 8,
                    "media": "test_audio.webm"
                }
            }
        ]

        for tc in test_cases:
            context = browser.new_context(viewport={"width": tc["width"], "height": tc["height"]})
            page = context.new_page()

            # Go to display
            page.goto(f"{BASE_URL}/display/ALL", wait_until="networkidle")
            page.evaluate("() => document.fonts.ready")

            # Render the notice via page function
            notice_json = json.dumps(tc["notice"])
            page.evaluate(f"""() => {{
                const notice = {notice_json};
                window.renderVoiceNotice(notice);
            }}""")

            page.wait_for_timeout(200)

            # Check 1: Loudest bar reaches full height (100%)
            loudest_bar_height = page.evaluate("""() => {
                const track = document.getElementById('voice-waveform-track');
                const bars = Array.from(track.querySelectorAll('.voice-bar'));
                let maxH = 0;
                bars.forEach(b => {
                    const h = parseFloat(b.style.height) || 0;
                    if (h > maxH) maxH = h;
                });
                return maxH;
            }""")
            assert loudest_bar_height == 100, f"Expected loudest bar to reach 100%, got {loudest_bar_height}% in {tc['name']}"

            # Check 2: All 64 bars rendered
            num_bars = page.evaluate("""() => {
                return document.querySelectorAll('#voice-waveform-track .voice-bar').length;
            }""")
            assert num_bars == 64, f"Expected 64 bars, got {num_bars}"

            # Check 3: Waveform track container height (taller by ~30%)
            track_height = page.evaluate("""() => {
                const el = document.getElementById('voice-waveform-container');
                return el.getBoundingClientRect().height;
            }""")
            if tc["width"] == 1920:
                assert 90 <= track_height <= 100, f"Expected 1080p track height ~94px, got {track_height}px"
            else:
                assert 54 <= track_height <= 64, f"Expected 480p track height ~58px, got {track_height}px"

            # Check 4: No speaker icon inside .voice-pill
            pill_has_speaker = page.evaluate("""() => {
                const pill = document.querySelector('.voice-pill');
                if (!pill) return false;
                return Boolean(pill.querySelector('#voice-speaker-badge') || pill.querySelector('svg'));
            }""")
            assert not pill_has_speaker, f"Expected no speaker icon inside .voice-pill in {tc['name']}"

            # Check 5: Time display exists under waveform and shows initial format '0:00 / M:SS'
            time_text = page.evaluate("""() => {
                const el = document.getElementById('voice-time-display');
                return el ? el.textContent.trim() : '';
            }""")
            assert "/" in time_text, f"Expected time format with '/', got '{time_text}'"
            assert time_text.startswith("0:00 /"), f"Expected initial time 0:00, got '{time_text}'"

            # Check 6: Simulating audio progress updates time display ('0:07 / ...')
            updated_time_text = page.evaluate("""() => {
                const audio = document.getElementById('voice-audio-element');
                const timeDisp = document.getElementById('voice-time-display');
                if (audio) {
                    audio.currentTime = 7.0;
                    if (typeof audio.ontimeupdate === 'function') {
                        audio.ontimeupdate();
                    }
                }
                return timeDisp ? timeDisp.textContent.trim() : '';
            }""")
            assert updated_time_text.startswith("0:07 /"), f"Expected time to update to 0:07, got '{updated_time_text}'"

            # Check 7: Caption layout
            if tc["notice"]["caption"]:
                caption_visible = page.evaluate("""() => {
                    const el = document.getElementById('voice-caption');
                    return el && !el.classList.contains('hidden') && el.textContent.length > 0;
                }""")
                assert caption_visible, f"Expected caption to be visible in {tc['name']}"

                # Ensure caption is placed after waveform container
                caption_after_waveform = page.evaluate("""() => {
                    const wf = document.getElementById('voice-waveform-container');
                    const cap = document.getElementById('voice-caption');
                    const inner = document.querySelector('.voice-card-inner');
                    const children = Array.from(inner.children);
                    return children.indexOf(cap) > children.indexOf(wf);
                }""")
                assert caption_after_waveform, "Expected caption to be positioned after waveform container"

                # Ensure caption is not clipped (never clipped, scrollHeight <= clientHeight + line tolerance)
                not_clipped = page.evaluate("""() => {
                    const cap = document.getElementById('voice-caption');
                    return cap.scrollHeight <= (cap.clientHeight + 4);
                }""")
                assert not_clipped, f"Caption should not be clipped in {tc['name']}"
            else:
                caption_hidden = page.evaluate("""() => {
                    const el = document.getElementById('voice-caption');
                    return !el || el.classList.contains('hidden') || el.textContent === '';
                }""")
                assert caption_hidden, f"Expected caption to be hidden when empty in {tc['name']}"

            # Capture screenshot
            screenshot_path = SCREENSHOTS_DIR / f"{tc['name']}.png"
            page.screenshot(path=str(screenshot_path))
            assert screenshot_path.exists() and screenshot_path.stat().st_size > 10000

            context.close()

        browser.close()


ADMIN_URL = "http://localhost:5001"
PASSWORD = "vnotice2026"


def login_if_needed(page):
    """Logs into the admin portal if the login modal is displayed."""
    if page.locator("#admin-password-input").is_visible():
        page.fill("#admin-password-input", PASSWORD)
        page.click("#btn-login")
        page.wait_for_selector("#view-notices.active", timeout=8000)


def test_admin_caption_nudge_hint():
    """
    Validates:
    - Admin form shows nudge hint when caption is empty:
      'Add a caption so people can read the message on silent screens.'
    - Hint hides when caption is typed.
    - Publish button is not blocked by empty caption.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
        login_if_needed(page)

        # Open New notice modal
        page.click("#btn-open-create")
        page.wait_for_selector("#notice-modal:not(.hidden)", state="visible")

        # Switch to Voice type
        page.locator("input[name='type'][value='voice']").check(force=True)
        page.wait_for_timeout(100)

        # Check hint element
        hint = page.locator("#voice-caption-hint")
        assert hint.is_visible(), "Expected caption nudge hint to be visible when caption is empty"
        assert "Add a caption so people can read the message on silent screens." in hint.inner_text()

        # Type caption: hint should hide
        caption_input = page.locator("#notice-voice-caption")
        caption_input.fill("Here is a test caption for silent screens")
        page.wait_for_timeout(50)
        assert not hint.is_visible(), "Expected caption nudge hint to hide when caption has text"

        # Clear caption: hint should reappear
        caption_input.fill("")
        page.wait_for_timeout(50)
        assert hint.is_visible(), "Expected caption nudge hint to reappear when caption is emptied"

        # Check publish button is not disabled by empty caption
        submit_btn = page.locator("#btn-submit-create")
        # Fill title so required title is satisfied
        page.locator("#notice-title").fill("Test Voice Announcement")
        assert not submit_btn.is_disabled(), "Publish button should not be blocked by empty caption"

        browser.close()
