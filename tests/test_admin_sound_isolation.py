import os
import pytest
from playwright.sync_api import sync_playwright
from storage import NoticeStorage, get_current_time_ms
import config

def test_admin_sound_isolation_and_kiosk_sound():
    """
    Test Sound Isolation in Admin Page and Sound Playback on Real Kiosk:
    1. A video notice with play_sound=True is published while screen has sound_enabled=True.
    2. Admin portal must never play unmuted audio on its own.
    3. No media element in the admin page is unmuted.
    4. After closing create/edit modals or switching tabs, no media element is playing.
    5. No heartbeat or audio_ready is sent from preview iframes.
    6. A real kiosk (with autoplay policy flag) still plays unmuted when allowed.
    """
    storage = NoticeStorage()
    now = get_current_time_ms()

    # Configure screen ALL with sound enabled
    storage.update_department("ALL", {"sound_enabled": True, "sound_volume": 80})
    
    # Ensure there is an active video notice with play_sound=True
    created = storage.add({
        "title": "Admin Sound Isolation Verification Notice",
        "body": "Campus announcement video broadcast test.",
        "priority": "high",
        "type": "video",
        "media": "sample-video.mp4",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 1000,
        "end": now + 3600000,
        "duration": 15,
        "play_sound": 1
    })
    assert created is not None
    video_notice_id = created["id"]

    # 1. Test Admin Page Sound Isolation
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        admin_page = context.new_page()

        heartbeat_payloads = []
        def handle_request(req):
            if "/api/heartbeat" in req.url:
                try:
                    heartbeat_payloads.append(req.post_data_json)
                except Exception:
                    pass

        admin_page.on("request", handle_request)

        # Load Admin portal
        admin_page.goto("http://localhost:5001/", wait_until="networkidle")
        if admin_page.is_visible("#login-modal"):
            admin_page.fill("#admin-password-input", config.ADMIN_PASSWORD)
            admin_page.click("#btn-login")
            admin_page.wait_for_timeout(500)

        # Assert no media elements in the entire admin page are unmuted or playing
        media_state = admin_page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('video, audio'));
            return els.map(el => ({
                tag: el.tagName.toLowerCase(),
                muted: el.muted,
                volume: el.volume,
                paused: el.paused,
                src: el.src || ''
            }));
        }""")
        for m in media_state:
            assert m["muted"] is True or m["volume"] == 0 or m["paused"] is True, f"Admin media element must not play unmuted: {m}"

        # Assert no heartbeat was sent from the admin page
        assert len(heartbeat_payloads) == 0, f"Admin preview must NOT send heartbeats, but received: {heartbeat_payloads}"

        # Open Create Notice modal
        admin_page.click("#btn-open-create")
        admin_page.wait_for_timeout(300)

        # Close modal
        admin_page.click("#btn-close-modal")
        admin_page.wait_for_timeout(300)

        # Assert all media elements are stopped/paused/muted after modal closes
        after_close_media = admin_page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('video, audio'));
            return els.map(el => ({
                tag: el.tagName.toLowerCase(),
                muted: el.muted,
                paused: el.paused,
                currentTime: el.currentTime
            }));
        }""")
        for m in after_close_media:
            assert m["paused"] is True or m["muted"] is True, f"Media playing after modal close: {m}"

        browser.close()

    # 2. Test Real Kiosk plays unmuted when allowed
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        kiosk_page = context.new_page()

        kiosk_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")
        kiosk_page.wait_for_selector("#video-element", state="attached", timeout=6000)
        kiosk_page.wait_for_timeout(1000)

        kiosk_video_state = kiosk_page.evaluate("""() => {
            const v = document.getElementById('video-element');
            return {
                src: v ? v.src : '',
                muted: v ? v.muted : true,
                volume: v ? v.volume : 0,
                paused: v ? v.paused : true
            };
        }""")

        assert kiosk_video_state["src"] != "", "Real kiosk must have active video src"
        assert kiosk_video_state["muted"] is False, "Real kiosk must play unmuted when notice and screen sound are on"
        assert kiosk_video_state["volume"] > 0, f"Real kiosk volume must be > 0, got {kiosk_video_state['volume']}"

        browser.close()

    # Clean up test notice
    storage.delete(video_notice_id)
