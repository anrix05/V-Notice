import io
import time
import pytest
from pathlib import Path
from PIL import Image
from unittest.mock import patch, MagicMock
from axe_core_python.sync_playwright import Axe
from playwright.sync_api import sync_playwright

from app import unified_app
from storage import storage

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

@pytest.fixture
def local_image_notice():
    # Create test image in media folder
    img = Image.new("RGB", (320, 240), color="#1E40AF")
    filename = "test_redesign_poster.png"
    dest = Path(storage.media_storage.media_dir) / filename
    img.save(str(dest), format="PNG")

    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Robotics Competition 2026",
        "body": "Annual inter-college robotics hackathon and exhibition.",
        "type": "image",
        "priority": "urgent",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000 * 29,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = ?, type = 'image' WHERE id = ?;", (filename, notice["id"]))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"]), dest.read_bytes()

@pytest.fixture
def remote_cloudinary_notice():
    now = int(time.time() * 1000)
    cloudinary_url = "https://res.cloudinary.com/vnotice-demo/image/upload/v12345/campus_flyer.jpg"
    notice = storage.add({
        "title": "Guest Lecture On Artificial Intelligence",
        "body": "Keynote lecture by Dr. Alan Turing in Auditorium Hall 1.",
        "type": "image",
        "priority": "info",
        "screen_id": "CS",
        "screens": ["CS"],
        "start": now - 10000,
        "end": now + 86400000 * 5,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = ?, type = 'image' WHERE id = ?;", (cloudinary_url, notice["id"]))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"]), cloudinary_url

@pytest.fixture
def video_notice():
    # Create test dummy mp4 file
    dummy_mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free"
    filename = "test_teaser_video.mp4"
    dest = Path(storage.media_storage.media_dir) / filename
    dest.write_bytes(dummy_mp4_bytes)

    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Spring Fest Teaser",
        "body": "Catch a glimpse of Spring Fest celebrations.",
        "type": "video",
        "priority": "normal",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000 * 10,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = ?, type = 'video' WHERE id = ?;", (filename, notice["id"]))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"]), dummy_mp4_bytes

@pytest.fixture
def text_notice():
    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Library Book Return Deadline",
        "body": "All overdue books must be returned without penalty before Friday.",
        "type": "text",
        "priority": "urgent",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000 * 3,
    })
    return storage.get_by_id(notice["id"])

@pytest.fixture
def missing_media_notice():
    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Lost and Found Wallet",
        "body": "A brown leather wallet was found in the cafeteria.",
        "type": "image",
        "priority": "normal",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = 'missing_ghost_file.png', type = 'image' WHERE id = ?;", (notice["id"],))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"])

# ==============================================================================
# TEST 1: Image notice downloads real image matching bytes, extension, MIME (local)
# ==============================================================================
def test_image_notice_downloads_matching_bytes_local(client, local_image_notice):
    notice, expected_bytes = local_image_notice
    res = client.get(f"/n/{notice['id']}/file")
    assert res.status_code == 200
    assert "image/png" in res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    assert cd.startswith("attachment; filename=")
    assert cd.endswith(".png")
    assert ".txt" not in cd
    assert res.headers.get("Cache-Control") == "private, no-store"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.data == expected_bytes

# ==============================================================================
# TEST 2: Image notice downloads matching bytes from remote Cloudinary URL (mocked)
# ==============================================================================
def test_image_notice_downloads_remote_cloudinary_stream(client, remote_cloudinary_notice):
    notice, _ = remote_cloudinary_notice
    mock_remote_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00mocked_jpeg_bytes"

    class MockRemoteResponse:
        def __init__(self):
            self.status = 200
            self.headers = {
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(mock_remote_bytes)),
                "Accept-Ranges": "bytes"
            }
            self._stream = io.BytesIO(mock_remote_bytes)
        def read(self, chunk_size=65536):
            return self._stream.read(chunk_size)
        def close(self):
            self._stream.close()

    with patch("urllib.request.urlopen", return_value=MockRemoteResponse()):
        res = client.get(f"/n/{notice['id']}/file")
        assert res.status_code == 200
        assert "image/jpeg" in res.headers.get("Content-Type", "")
        cd = res.headers.get("Content-Disposition", "")
        assert cd.startswith("attachment; filename=")
        assert "CS-guest-lecture-on-artificial-intelligence.jpg" in cd
        assert ".txt" not in cd
        assert res.headers.get("Cache-Control") == "private, no-store"
        assert res.data == mock_remote_bytes

# ==============================================================================
# TEST 3: Video notice downloads video with Range support and video Content-Type
# ==============================================================================
def test_video_notice_downloads_video(client, video_notice):
    notice, expected_bytes = video_notice
    res = client.get(f"/n/{notice['id']}/file")
    assert res.status_code == 200
    assert "video/mp4" in res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    assert cd.startswith("attachment; filename=")
    assert cd.endswith(".mp4")
    assert ".txt" not in cd
    assert res.headers.get("Accept-Ranges") == "bytes"
    assert res.headers.get("Cache-Control") == "private, no-store"
    assert res.data == expected_bytes

# ==============================================================================
# TEST 4: Text notice downloads .txt with campus announcement format
# ==============================================================================
def test_text_notice_downloads_txt_only(client, text_notice):
    res = client.get(f"/n/{text_notice['id']}/file")
    assert res.status_code == 200
    assert "text/plain" in res.headers.get("Content-Type", "")
    cd = res.headers.get("Content-Disposition", "")
    assert cd.startswith("attachment; filename=")
    assert "ALL-library-book-return-deadline.txt" in cd
    assert res.headers.get("Cache-Control") == "private, no-store"
    content = res.data.decode("utf-8")
    assert "OFFICIAL CAMPUS ANNOUNCEMENT" in content
    assert "Library Book Return Deadline" in content
    assert "College-wide" in content
    assert "DEPARTMENT: ALL" not in content

# ==============================================================================
# TEST 5: Missing media file shows error with Retry and NEVER downloads .txt
# ==============================================================================
def test_missing_media_returns_error_and_never_txt(client, missing_media_notice):
    res = client.get(f"/n/{missing_media_notice['id']}/file")
    assert res.status_code in (404, 502)
    cd = res.headers.get("Content-Disposition", "")
    assert not cd.startswith("attachment; filename=")
    assert "OFFICIAL CAMPUS ANNOUNCEMENT" not in res.data.decode("utf-8", errors="ignore")
    assert res.headers.get("Cache-Control") == "private, no-store"

# ==============================================================================
# TEST 6: Inactive, expired, and unknown IDs return identical 404
# ==============================================================================
def test_zero_leakage_byte_identical_404(client):
    now = int(time.time() * 1000)
    exp_notice = storage.add({
        "title": "Expired Notice 101",
        "body": "Should not leak",
        "start": now - 50000,
        "end": now - 10000,
    })
    r_exp = client.get(f"/n/{exp_notice['id']}")
    r_unk = client.get("/n/random_unknown_id_xyz999")

    assert r_exp.status_code == 404
    assert r_unk.status_code == 404
    assert r_exp.data == r_unk.data, "Expired notice 404 differs from unknown notice 404!"

# ==============================================================================
# TEST 7: Playwright Layout checks at 360, 390, 768px (no horizontal scroll, sticky bar)
# ==============================================================================
def test_playwright_responsive_layout_and_zoom_viewer(local_image_notice):
    url = "http://localhost:5000/n/vert_demo_01"

    viewports = [
        {"width": 360, "height": 800},
        {"width": 390, "height": 844},
        {"width": 768, "height": 1024},
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp in viewports:
            context = browser.new_context(viewport=vp)
            page = context.new_page()
            page.goto(url, wait_until="networkidle")

            # 1. No horizontal scroll
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("document.documentElement.clientWidth")
            assert scroll_width <= client_width + 1, f"Horizontal scroll detected at {vp['width']}px: scroll={scroll_width}, client={client_width}"

            # 2. Check sticky bottom action bar (wait for 200ms rise animation)
            bottom_bar = page.locator(".bottom-action-bar")
            bottom_bar.wait_for(state="visible", timeout=3000)
            assert bottom_bar.is_visible()
            box = bottom_bar.bounding_box()
            assert box is not None
            assert box["y"] + box["height"] >= vp["height"] - 5

            # 3. Save button height >= 48px
            save_btn = page.locator("#btn-save-media")
            assert save_btn.is_visible()
            save_box = save_btn.bounding_box()
            assert save_box["height"] >= 48, f"Button height {save_box['height']} < 48px target"

            # 4. Check "College-wide" instead of "ALL"
            page_text = page.locator(".dept-chip").inner_text()
            assert "College-wide" in page_text
            assert "ALL" not in page_text

            # 5. Tap-to-zoom viewer opens and closes
            hero_img = page.locator("#notice-media-img")
            hero_img.click()
            page.wait_for_timeout(300)

            zoom_viewer = page.locator("#zoom-viewer")
            assert zoom_viewer.is_visible()

            # Close via ESC key
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            assert not zoom_viewer.is_visible()

            context.close()
        browser.close()

# ==============================================================================
# TEST 8: Playwright Save Button Download: bytes match stored image & image MIME
# ==============================================================================
def test_playwright_save_image_downloads_matching_bytes():
    url = "http://localhost:5000/n/vert_demo_01"
    stored_path = Path("media/sample_vertical_poster.png")
    expected_bytes = stored_path.read_bytes()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.goto(url, wait_until="networkidle")

        with page.expect_download() as download_info:
            page.locator("#btn-save-media").click()
        download = download_info.value

        assert download.suggested_filename == "ALL-annual-cultural-fest-2026.png"
        assert download.suggested_filename.endswith(".png")
        assert not download.suggested_filename.endswith(".txt")

        dl_path = download.path()
        with open(dl_path, "rb") as f:
            downloaded_bytes = f.read()

        assert len(downloaded_bytes) == len(expected_bytes)
        assert downloaded_bytes == expected_bytes
        context.close()
        browser.close()

# ==============================================================================
# TEST 9: Axe-core Accessibility: Zero color-contrast violations in light & dark
# ==============================================================================
def test_axe_zero_contrast_violations_dark_light():
    url = "http://localhost:5000/n/vert_demo_01"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        axe = Axe()

        for theme in ("dark", "light"):
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                color_scheme=theme
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(300)

            results = axe.run(page)
            violations = [v for v in results.get("violations", []) if v.get("id") == "color-contrast"]
            assert len(violations) == 0, f"Contrast violations in {theme} theme: {violations}"
            context.close()
        browser.close()
