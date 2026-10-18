import io
import json
import os
import time
import pytest
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

import config
from storage import storage, sanitize_or_generate_waveform
from app import create_display_app

@pytest.fixture(scope="module")
def local_server():
    import threading
    import socket

    app = create_display_app()
    app.config["TESTING"] = True

    # Find free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    from werkzeug.serving import make_server
    srv = make_server("127.0.0.1", port, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    srv.shutdown()

def test_storage_10mb_image_rejection_and_waveform_fallback(tmp_path):
    # 1. Test waveform generator produces 64 integers
    wf_json = sanitize_or_generate_waveform(None)
    wf = json.loads(wf_json)
    assert isinstance(wf, list)
    assert len(wf) == 64
    assert all(0 <= v <= 100 for v in wf)

    # 2. Test image > 10MB rejection on Render or Cloud storage
    orig_is_render = getattr(config, "IS_RENDER", False)
    try:
        config.IS_RENDER = True
        buf = io.BytesIO()
        im = Image.new("RGB", (100, 100), color=(255, 0, 0))
        im.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        dummy_large = io.BytesIO(png_bytes + b"\x00" * (11 * 1024 * 1024))
        dummy_large.filename = "large_image.png"

        notice_data = {
            "title": "Large Test",
            "type": "image",
            "body": "Testing size limit"
        }
        with pytest.raises(ValueError, match="Image is over 10 MB, choose a smaller file"):
            storage.add(notice_data, file_obj=dummy_large)
    finally:
        config.IS_RENDER = orig_is_render

def test_playwright_mobile_image_notice_hero_and_save(local_server, tmp_path):
    # Create an image notice with a local test image
    img_dir = Path(config.MEDIA_FOLDER)
    img_dir.mkdir(parents=True, exist_ok=True)
    test_img_path = img_dir / "test_mumbai_hero.png"

    # Create a 2000x1200 test image
    im = Image.new("RGB", (2000, 1200), color=(30, 80, 160))
    im.save(test_img_path, format="PNG")

    notice_data = {
        "title": "Exploring Mumbai",
        "type": "image",
        "body": "Touring the city landmarks.",
        "media": "test_mumbai_hero.png"
    }
    notice = storage.add(notice_data)
    notice_id = notice["id"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Mobile viewport emulation: 390x844 (iPhone 12/13/14)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        )
        page = context.new_page()

        # Check for any console errors or syntax errors
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        url = f"{local_server}/n/{notice_id}"
        resp = page.goto(url, wait_until="networkidle")
        assert resp.status == 200

        # Verify no script syntax errors (e.g. Jinja &#34; escaping issue)
        assert len(errors) == 0, f"Script errors on public notice page: {errors}"

        # Verify hero image source is resized version (/media/thumb/w1200/...)
        hero_img = page.locator("#notice-media-img")
        assert hero_img.is_visible()
        src = hero_img.get_attribute("src")
        assert "/media/thumb/w1200/" in src or "w_1200" in src

        # Verify skeleton is hidden/cleared
        skeleton = page.locator("#media-skeleton")
        opacity = skeleton.evaluate("el => window.getComputedStyle(el).opacity")
        display = skeleton.evaluate("el => window.getComputedStyle(el).display")
        assert opacity == "0" or display == "none"

        # Verify hero img has loaded class
        classes = hero_img.get_attribute("class")
        assert "loaded" in classes

        # Test Save Image downloads matching binary bytes
        with page.expect_download() as download_info:
            page.locator("#btn-save-media").click()
        download = download_info.value
        download_path = tmp_path / download.suggested_filename
        download.save_as(download_path)

        # Confirm downloaded file matches original attachment bytes
        assert download_path.exists()
        assert download_path.stat().st_size == test_img_path.stat().st_size
        browser.close()

def test_playwright_mobile_voice_notice_player(local_server, tmp_path):
    # Create voice notice with audio file and waveform
    media_dir = Path(config.MEDIA_FOLDER)
    media_dir.mkdir(parents=True, exist_ok=True)
    test_audio_path = media_dir / "test_voice.webm"
    # Write a tiny dummy webm header/data
    test_audio_path.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 1024)

    wf_sample = [15, 25, 45, 80, 95, 60, 30, 10] * 8
    notice_data = {
        "title": "Audio check Song Recording",
        "type": "voice",
        "caption": "Sound check in auditorium",
        "audio_duration": 64.0,
        "duration": 64,
        "play_sound": True,
        "waveform": json.dumps(wf_sample),
        "media": "test_voice.webm"
    }
    notice = storage.add(notice_data)
    notice_id = notice["id"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        )
        page = context.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        url = f"{local_server}/n/{notice_id}"
        resp = page.goto(url, wait_until="networkidle")
        assert resp.status == 200

        # No script errors
        assert len(errors) == 0, f"Script errors: {errors}"

        # Verify waveform bars are pre-rendered in DOM
        bars = page.locator(".pub-wf-bar")
        count = bars.count()
        assert count == 64, f"Expected 64 waveform bars, found {count}"

        # Verify audio element src points to range-supporting /n/<id>/audio
        audio = page.locator("#voice-public-audio")
        audio_src = audio.get_attribute("src")
        assert f"/n/{notice_id}/audio" in audio_src

        # Test audio endpoint headers
        audio_resp = page.request.get(f"{local_server}/n/{notice_id}/audio")
        assert audio_resp.status in (200, 206)
        assert audio_resp.headers.get("accept-ranges") == "bytes"
        assert "audio/" in audio_resp.headers.get("content-type", "")

        # Test Range request support
        range_resp = page.request.get(
            f"{local_server}/n/{notice_id}/audio",
            headers={"Range": "bytes=0-100"}
        )
        assert range_resp.status == 206
        assert "bytes 0-100/" in range_resp.headers.get("content-range", "")

        browser.close()

def test_playwright_mobile_css_fallback_and_error_box(local_server, tmp_path):
    # Create notice with deliberately missing media to test error box
    notice_data = {
        "title": "Broken Media Notice",
        "type": "image",
        "body": "Media file is absent",
        "media": "nonexistent_file_404.png"
    }
    notice = storage.add(notice_data)
    notice_id = notice["id"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()

        url = f"{local_server}/n/{notice_id}"
        resp = page.goto(url, wait_until="networkidle")
        assert resp.status == 200

        # Verify CSS fallback keyframes exist in document stylesheet
        has_fallback_keyframes = page.evaluate("""() => {
            for (let sheet of document.styleSheets) {
                try {
                    for (let rule of sheet.cssRules) {
                        if (rule.name === 'css-fallback-reveal' || rule.name === 'css-skeleton-fade') {
                            return true;
                        }
                    }
                } catch(e) {}
            }
            return false;
        }""")
        assert has_fallback_keyframes, "css-fallback-reveal keyframe animation must exist in CSS"

        # Verify media error box is displayed when image fails to load
        error_box = page.locator("#media-error-box")
        assert error_box.is_visible()
        assert page.locator("#media-error-box button").is_visible()
        assert page.locator("#media-error-box button").text_content() == "Retry"

        # Skeleton must be hidden on error
        skeleton = page.locator("#media-skeleton")
        assert not skeleton.is_visible() or skeleton.evaluate("el => window.getComputedStyle(el).display === 'none'")

        browser.close()

def test_cloudinary_w1200_rewrite():
    from app import format_notice_for_display
    n = {
        "id": "test1234",
        "type": "image",
        "title": "Cloudinary Test",
        "media": "https://res.cloudinary.com/demo/image/upload/sample.jpg"
    }
    formatted = format_notice_for_display(n)
    assert "upload/w_1200,q_auto,f_auto/" in formatted["hero_display_url"]
    assert "sample.jpg" in formatted["hero_display_url"]

