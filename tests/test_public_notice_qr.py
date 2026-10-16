import io
import time
import pytest
from pathlib import Path
from PIL import Image
import zxingcpp
from axe_core_python.sync_playwright import Axe
from playwright.sync_api import sync_playwright

from app import unified_app
from storage import storage

TEST_ADMIN_PASSWORD = "vnotice2026"

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

@pytest.fixture
def sample_media_image(tmp_path):
    # Create small valid test image in storage media folder
    img = Image.new("RGB", (200, 200), color="#1E3A8A")
    filename = "test_sample_poster.jpg"
    dest = Path(storage.media_storage.media_dir) / filename
    img.save(str(dest), format="JPEG")
    return filename

@pytest.fixture
def active_image_notice(sample_media_image):
    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Lab Exam Schedule",
        "body": "All students must bring their identity cards and lab journals.",
        "type": "image",
        "priority": "urgent",
        "screen_id": "EXCS",
        "screens": ["EXCS"],
        "start": now - 10000,
        "end": now + 86400000,
    })
    # Attach sample media file
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = ?, type = 'image' WHERE id = ?;", (sample_media_image, notice["id"]))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"])

@pytest.fixture
def active_text_notice():
    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Blood Donation Drive",
        "body": "Annual campus blood donation drive will be held in the auditorium.",
        "type": "text",
        "priority": "info",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000,
    })
    return storage.get_by_id(notice["id"])

@pytest.fixture
def active_video_notice():
    now = int(time.time() * 1000)
    notice = storage.add({
        "title": "Campus Cultural Fest Teaser",
        "body": "Watch the official teaser for Symphony 2026.",
        "type": "video",
        "priority": "normal",
        "screen_id": "ALL",
        "screens": ["ALL"],
        "start": now - 10000,
        "end": now + 86400000,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET media = 'teaser_2026.mp4', type = 'video' WHERE id = ?;", (notice["id"],))
    finally:
        storage.close_connection()
    return storage.get_by_id(notice["id"])

# ==============================================================================
# 1. Scanning /n/<id> returns HTML, not a file, and never sets Content-Disposition
# ==============================================================================
def test_public_route_returns_html_no_content_disposition(client, active_image_notice):
    n_id = active_image_notice["id"]
    res = client.get(f"/n/{n_id}")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("Content-Type", "")
    assert "Content-Disposition" not in res.headers
    # Verify title is displayed in the HTML
    html = res.data.decode("utf-8")
    assert "Lab Exam Schedule" in html
    assert "EXCS" in html

# ==============================================================================
# 2. Save button hits /n/<id>/file and returns right Content-Disposition and filename
# ==============================================================================
def test_file_route_attachment_slug_and_headers(client, active_image_notice, active_text_notice):
    # Test Image Notice File Download
    img_id = active_image_notice["id"]
    res_img = client.get(f"/n/{img_id}/file")
    assert res_img.status_code == 200
    cd = res_img.headers.get("Content-Disposition", "")
    assert cd.startswith("attachment; filename=")
    assert "EXCS-lab-exam-schedule.jpg" in cd
    assert res_img.headers.get("X-Content-Type-Options") == "nosniff"
    assert "private" in res_img.headers.get("Cache-Control", "")
    assert "no-store" in res_img.headers.get("Cache-Control", "")
    assert int(res_img.headers.get("Content-Length", 0)) > 0

    # Test Text Notice File Download
    txt_id = active_text_notice["id"]
    res_txt = client.get(f"/n/{txt_id}/file")
    assert res_txt.status_code == 200
    cd_txt = res_txt.headers.get("Content-Disposition", "")
    assert cd_txt.startswith("attachment; filename=")
    assert "ALL-blood-donation-drive.txt" in cd_txt
    assert res_txt.headers.get("Content-Type", "").startswith("text/plain")
    assert res_txt.headers.get("X-Content-Type-Options") == "nosniff"
    assert "private" in res_txt.headers.get("Cache-Control", "")
    assert "no-store" in res_txt.headers.get("Cache-Control", "")

# ==============================================================================
# 3. Inactive, expired, scheduled, deleted, unknown return identical generic 404 body
# ==============================================================================
def test_zero_leakage_diff_all_inactive_states(client):
    now = int(time.time() * 1000)

    # 1. Expired notice
    n_exp = storage.add({
        "title": "Secret Expired Midterm",
        "body": "Classified exam instructions.",
        "screen_id": "CMPN",
        "start": now - 100000,
        "end": now - 50000,
    })

    # 2. Scheduled notice
    n_sched = storage.add({
        "title": "Confidential Future Budget",
        "body": "Budget details for next semester.",
        "screen_id": "INFT",
        "start": now + 200000,
        "end": now + 500000,
    })

    # 3. Deleted notice
    n_del = storage.add({
        "title": "Deleted Grievance Notice",
        "body": "Private grievance report.",
        "screen_id": "BIOM",
        "start": now - 10000,
        "end": now + 50000,
    })
    storage.delete(n_del["id"])

    # 4. Unknown random ID
    unk_id = "vnot_unknown_9999"

    # Fetch all 4 public pages without authentication
    r_exp = client.get(f"/n/{n_exp['id']}")
    r_sched = client.get(f"/n/{n_sched['id']}")
    r_del = client.get(f"/n/{n_del['id']}")
    r_unk = client.get(f"/n/{unk_id}")

    # All must return HTTP 404
    assert r_exp.status_code == 404
    assert r_sched.status_code == 404
    assert r_del.status_code == 404
    assert r_unk.status_code == 404

    # All 4 responses must have 100% IDENTICAL body bytes (Diff test to prove no leakage)
    assert r_exp.data == r_sched.data, "Expired and Scheduled 404 bodies differ!"
    assert r_sched.data == r_del.data, "Scheduled and Deleted 404 bodies differ!"
    assert r_del.data == r_unk.data, "Deleted and Unknown ID 404 bodies differ!"

    # Verify zero leakage of sensitive notice metadata
    body_text = r_exp.data.decode("utf-8")
    assert "This notice is no longer active" in body_text
    assert "Secret Expired Midterm" not in body_text
    assert "Confidential Future Budget" not in body_text
    assert "Deleted Grievance Notice" not in body_text
    assert "CMPN" not in body_text
    assert "INFT" not in body_text
    assert "BIOM" not in body_text

    # File routes for inactive notices must also return identical 404
    rf_exp = client.get(f"/n/{n_exp['id']}/file")
    rf_unk = client.get(f"/n/{unk_id}/file")
    assert rf_exp.status_code == 404
    assert rf_unk.status_code == 404
    assert rf_exp.data == rf_unk.data

# ==============================================================================
# 4. Old /notice/<id> and ?download=1 URLs redirect to page and do not download
# ==============================================================================
def test_legacy_routes_redirect_and_do_not_download(client, active_image_notice):
    n_id = active_image_notice["id"]

    # Plain /notice/<id> 301 redirects to /n/<id>
    r1 = client.get(f"/notice/{n_id}")
    assert r1.status_code == 301
    assert r1.headers.get("Location", "").endswith(f"/n/{n_id}")
    assert "Content-Disposition" not in r1.headers

    # /notice/<id>?download=1 redirects to /n/<id>
    r2 = client.get(f"/notice/{n_id}?download=1")
    assert r2.status_code == 301
    assert r2.headers.get("Location", "").endswith(f"/n/{n_id}")
    assert "Content-Disposition" not in r2.headers

    # Following the redirect never forces a download
    r3 = client.get(f"/notice/{n_id}?download=1", follow_redirects=True)
    assert r3.status_code == 200
    assert "text/html" in r3.headers.get("Content-Type", "")
    assert "Content-Disposition" not in r3.headers

    # /notice/<id>/download 301 redirects to /n/<id>/file
    r4 = client.get(f"/notice/{n_id}/download")
    assert r4.status_code == 301
    assert r4.headers.get("Location", "").endswith(f"/n/{n_id}/file")

# ==============================================================================
# 5. Video notice: no autoplay, controls present, poster present
# ==============================================================================
def test_video_notice_properties(client, active_video_notice):
    v_id = active_video_notice["id"]
    res = client.get(f"/n/{v_id}")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    assert "<video" in html
    assert "controls" in html
    assert 'preload="metadata"' in html
    assert "muted" in html
    assert "playsinline" in html
    assert "poster=" in html
    # MUST NOT autoplay
    assert "autoplay" not in html

# ==============================================================================
# 6. OG tags present for active notice, generic for inactive, and noindex everywhere
# ==============================================================================
def test_og_tags_and_noindex(client, active_image_notice):
    # Active notice
    res_act = client.get(f"/n/{active_image_notice['id']}")
    html_act = res_act.data.decode("utf-8")
    assert '<meta name="robots" content="noindex, nofollow">' in html_act
    assert '<meta property="og:title" content="Lab Exam Schedule — V Notice">' in html_act
    assert '<meta property="og:description"' in html_act
    assert '<meta property="og:image"' in html_act
    assert '<meta name="theme-color" content="#0B1020">' in html_act

    # Inactive notice
    res_inact = client.get("/n/non-existent-notice-xyz")
    html_inact = res_inact.data.decode("utf-8")
    assert '<meta name="robots" content="noindex, nofollow">' in html_inact
    assert '<meta property="og:title" content="Notice not active — V Notice">' in html_inact

# ==============================================================================
# 7. Text notice shows Share but no Save; image notice shows file size
# ==============================================================================
def test_text_vs_image_action_buttons(client, active_image_notice, active_text_notice):
    # Image Notice
    res_img = client.get(f"/n/{active_image_notice['id']}")
    html_img = res_img.data.decode("utf-8")
    assert "Save image" in html_img
    assert "btn-save-media" in html_img

    # Text Notice
    res_txt = client.get(f"/n/{active_text_notice['id']}")
    html_txt = res_txt.data.decode("utf-8")
    assert "Save image" not in html_txt
    assert "Save video" not in html_txt
    assert "btn-save-media" not in html_txt
    assert "Share" in html_txt
    assert "Copy text" in html_txt

# ==============================================================================
# 8. Calendar generation only when start and end time are present
# ==============================================================================
def test_calendar_button_only_when_schedule_range(client, active_text_notice):
    # Notice with start & end ms
    res = client.get(f"/n/{active_text_notice['id']}")
    assert "Add to calendar" in res.data.decode("utf-8")

    # Notice with null end time
    now = int(time.time() * 1000)
    no_end_notice = storage.add({
        "title": "Ongoing Campus Maintenance",
        "body": "Library elevators will undergo inspection.",
        "start": now - 1000,
    })
    conn = storage.get_connection()
    try:
        with conn:
            conn.execute("UPDATE notices SET end = NULL WHERE id = ?;", (no_end_notice["id"],))
    finally:
        storage.close_connection()

    res_no_end = client.get(f"/n/{no_end_notice['id']}")
    assert "Add to calendar" not in res_no_end.data.decode("utf-8")

# ==============================================================================
# 9. Anonymous scan counter increments on public view
# ==============================================================================
def test_anonymous_scan_counter(client, active_text_notice):
    n_id = active_text_notice["id"]
    initial = storage.get_by_id(n_id).get("scan_count", 0)

    # First public visit
    client.get(f"/n/{n_id}")
    after1 = storage.get_by_id(n_id).get("scan_count", 0)
    assert after1 == initial + 1

    # Second public visit
    client.get(f"/n/{n_id}")
    after2 = storage.get_by_id(n_id).get("scan_count", 0)
    assert after2 == initial + 2

# ==============================================================================
# 10. Playwright QR Code Decode Test at 800x480 (Pi) and 1920x1080 (FHD)
# ==============================================================================
def test_display_qr_decodes_to_public_url(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        resolutions = [
            (800, 480, "pi_800x480"),
            (1920, 1080, "fhd_1920x1080")
        ]

        for width, height, label in resolutions:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto("http://localhost:5000/", wait_until="networkidle")

            # Wait for QR card to appear and render canvas
            qr_card = page.locator("#stage-qr-badge")
            qr_card.wait_for(state="visible", timeout=8000)
            page.wait_for_timeout(1000)

            # Check that new labels are displayed
            label_head = page.locator(".qr-label-head").inner_text()
            label_sub = page.locator(".qr-label-sub").inner_text()
            assert label_head == "Scan to view", f"Unexpected label head: {label_head}"
            assert label_sub == "Open this notice on your phone", f"Unexpected label sub: {label_sub}"

            # Capture QR canvas element screenshot
            qr_canvas = page.locator("#stage-qr-canvas")
            qr_canvas_shot = tmp_path / f"qr_{label}.png"
            qr_canvas.screenshot(path=str(qr_canvas_shot))

            # Decode the QR code using zxingcpp
            pil_img = Image.open(str(qr_canvas_shot))
            results = zxingcpp.read_barcodes(pil_img)
            assert len(results) > 0, f"Failed to decode QR code at {width}x{height}!"

            decoded_url = results[0].text
            assert "/n/" in decoded_url, f"QR code did not encode /n/<id>: {decoded_url}"
            assert "?download=1" not in decoded_url, f"QR code still contains download=1: {decoded_url}"
            context.close()
        browser.close()

# ==============================================================================
# 11. Axe-core Accessibility: Zero color-contrast violations in light and dark
# ==============================================================================
def test_axe_zero_color_contrast_violations(active_image_notice):
    n_id = active_image_notice["id"]
    target_url = f"http://localhost:5000/n/{n_id}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        axe = Axe()

        test_configs = [
            (360, 800, "light"),
            (360, 800, "dark"),
            (1440, 900, "light"),
            (1440, 900, "dark"),
        ]

        for width, height, color_scheme in test_configs:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme=color_scheme
            )
            page = context.new_page()
            page.goto(target_url, wait_until="networkidle")
            page.wait_for_timeout(500)

            results = axe.run(page)
            violations = results.get("violations", [])

            # Filter for color-contrast violations
            contrast_violations = [v for v in violations if v.get("id") == "color-contrast"]
            assert len(contrast_violations) == 0, (
                f"Color contrast violations found at {width}px ({color_scheme}): {contrast_violations}"
            )
            context.close()
        browser.close()
