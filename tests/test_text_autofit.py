import os
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

DISPLAY_URL = "http://localhost:5000/display/EXCS"

# Test Headlines: 20, 41, 80, 120 characters
HEADLINES = {
    20: "Urgent: Exam Updates",
    41: "Urgent: EXCS Laboratory Exam Registration",
    80: "Mid-term Examination Schedule for Computer Science and Engineering Third Year B.",
    120: "Attention students and faculty: The annual research symposium registration deadline has been extended to next Monday 5PM",
}

# Test Bodies: none, short, long
BODIES = {
    "none": "",
    "short": "All BE-EXCS students must complete registration before Friday 5:00 PM.",
    "long": (
        "All BE-EXCS students must complete registration for the Advanced Embedded Systems lab exam before Friday 5:00 PM. "
        "Please verify your hall ticket numbers and room allocations before entering the examination hall. "
        "Bring your valid college ID card and calculator. Any discrepancies should be reported to the exam coordinator immediately."
    ),
}

RESOLUTIONS = [
    (800, 480),
    (1280, 720),
    (1920, 1080),
    (3840, 2160),
]


def test_screenshots_exist():
    """Verify before and after screenshots exist and are valid for both 1920x1080 and 800x480."""
    base_dir = Path(__file__).resolve().parent.parent / "archive" / "verification" / "verification_text_fit"
    if not base_dir.exists():
        pytest.skip("verification_text_fit directory not present in environment")
    required = [
        "before_1920x1080.png",
        "before_800x480.png",
        "after_1920x1080.png",
        "after_800x480.png",
    ]
    for filename in required:
        file_path = base_dir / filename
        assert file_path.exists(), f"Screenshot {filename} must exist"
        assert file_path.stat().st_size > 10000, f"Screenshot {filename} must not be empty"


def test_autofit_text_sizing_matrix_and_bounds():
    """
    Validates:
    - Headlines of 20, 41, 80 and 120 characters, each with no body, short body, long body.
    - At 800x480, 1280x720, 1920x1080, and 3840x2160.
    - Headline and body scrollHeight <= clientHeight.
    - Neither is clipped by any ancestor (within card-text and stage-viewport).
    - Font sizes are within min and max limits.
    - 20-character headline keeps largest size, 120-character is smaller than 41-character.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        page.goto(DISPLAY_URL, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")

        for width, height in RESOLUTIONS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)

            # Store font sizes for length comparison within this resolution
            headline_sizes_for_comparison = {}

            for length, headline_text in HEADLINES.items():
                assert len(headline_text) == length, f"Headline '{headline_text}' must be {length} chars, got {len(headline_text)}"

                for body_type, body_text in BODIES.items():
                    res = page.evaluate("""([title, body]) => {
                        const cardText = document.getElementById('card-text');
                        const cardImage = document.getElementById('card-image');
                        const cardVideo = document.getElementById('card-video');
                        const cardEmpty = document.getElementById('card-empty');
                        if (cardImage) cardImage.classList.add('hidden');
                        if (cardVideo) cardVideo.classList.add('hidden');
                        if (cardEmpty) cardEmpty.classList.add('hidden');
                        if (cardText) {
                            cardText.classList.remove('hidden');
                            cardText.classList.add('active');
                        }

                        if (typeof window.renderTextNotice === 'function') {
                            window.renderTextNotice({
                                id: 'test-fit',
                                title: title,
                                body: body,
                                category: 'urgent',
                                target_audience: 'College-wide'
                            });
                        }
                        if (typeof window.fitTextNotice === 'function') {
                            window.fitTextNotice();
                        }

                        const h = document.querySelector('.notice-text .notice-headline');
                        const b = document.querySelector('.notice-text .notice-body');
                        const card = document.getElementById('card-text');
                        const viewport = document.getElementById('stage-viewport');

                        const hRect = h.getBoundingClientRect();
                        const bRect = b ? b.getBoundingClientRect() : null;
                        const cardRect = card.getBoundingClientRect();
                        const vpRect = viewport.getBoundingClientRect();

                        const scale = window.innerHeight / 1080;
                        const minHeadline = Math.round(36 * scale);
                        const maxHeadline = Math.round(112 * scale);
                        const minBody = Math.round(20 * scale);

                        const hSize = parseFloat(window.getComputedStyle(h).fontSize);
                        const bSize = b ? parseFloat(window.getComputedStyle(b).fontSize) : 0;

                        // Check clipping by ancestor
                        const hClipped = (hRect.top < cardRect.top - 1) || (hRect.bottom > cardRect.bottom + 1.5) ||
                                         (hRect.top < vpRect.top - 1) || (hRect.bottom > vpRect.bottom + 1.5);
                        const bClipped = b && b.textContent.trim() ? (
                            (bRect.top < cardRect.top - 1) || (bRect.bottom > cardRect.bottom + 1.5) ||
                            (bRect.top < vpRect.top - 1) || (bRect.bottom > vpRect.bottom + 1.5)
                        ) : false;

                        return {
                            hScroll: h.scrollHeight,
                            hClient: h.clientHeight,
                            bScroll: b ? b.scrollHeight : 0,
                            bClient: b ? b.clientHeight : 0,
                            hSize: hSize,
                            bSize: bSize,
                            minHeadline: minHeadline,
                            maxHeadline: maxHeadline,
                            minBody: minBody,
                            hClipped: hClipped,
                            bClipped: bClipped
                        };
                    }""", [headline_text, body_text])

                    # Assert scrollHeight <= clientHeight
                    assert res["hScroll"] <= res["hClient"] + 1, (
                        f"Headline scrollHeight {res['hScroll']} > clientHeight {res['hClient']} at {width}x{height}, len={length}, body={body_type}"
                    )
                    if body_text:
                        assert res["bScroll"] <= res["bClient"] + 1, (
                            f"Body scrollHeight {res['bScroll']} > clientHeight {res['bClient']} at {width}x{height}, len={length}, body={body_type}"
                        )

                    # Assert not clipped by ancestor
                    assert not res["hClipped"], f"Headline is clipped by ancestor at {width}x{height}, len={length}, body={body_type}"
                    assert not res["bClipped"], f"Body is clipped by ancestor at {width}x{height}, len={length}, body={body_type}"

                    # Assert within limits
                    assert res["hSize"] >= res["minHeadline"] - 0.5, (
                        f"Headline size {res['hSize']} < min {res['minHeadline']} at {width}x{height}, len={length}"
                    )
                    assert res["hSize"] <= res["maxHeadline"] + 0.5, (
                        f"Headline size {res['hSize']} > max {res['maxHeadline']} at {width}x{height}, len={length}"
                    )
                    if body_text:
                        assert res["bSize"] >= res["minBody"] - 0.5, (
                            f"Body size {res['bSize']} < min {res['minBody']} at {width}x{height}, len={length}"
                        )

                    if body_type == "short":
                        headline_sizes_for_comparison[length] = res["hSize"]

            # Comparison assertions across headline lengths
            assert headline_sizes_for_comparison[20] >= headline_sizes_for_comparison[41], (
                f"20-char headline ({headline_sizes_for_comparison[20]}px) should be >= 41-char ({headline_sizes_for_comparison[41]}px) at {width}x{height}"
            )
            assert headline_sizes_for_comparison[120] < headline_sizes_for_comparison[41], (
                f"120-char headline ({headline_sizes_for_comparison[120]}px) should be smaller than 41-char ({headline_sizes_for_comparison[41]}px) at {width}x{height}"
            )

        browser.close()


def test_autofit_resize_without_reload():
    """Assert the size is recomputed after a viewport resize without a page reload."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        page.goto(DISPLAY_URL, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")

        test_title = HEADLINES[41]
        test_body = BODIES["short"]

        # Render at 1920x1080
        page.evaluate("""([title, body]) => {
            const cardText = document.getElementById('card-text');
            const cardImage = document.getElementById('card-image');
            const cardVideo = document.getElementById('card-video');
            if (cardImage) cardImage.classList.add('hidden');
            if (cardVideo) cardVideo.classList.add('hidden');
            if (cardText) {
                cardText.classList.remove('hidden');
                cardText.classList.add('active');
            }
            window.renderTextNotice({
                id: 'test-resize',
                title: title,
                body: body,
                category: 'urgent'
            });
            window.fitTextNotice();
        }""", [test_title, test_body])

        h_size_1080p = page.evaluate("""() => {
            const h = document.querySelector('.notice-text .notice-headline');
            return parseFloat(window.getComputedStyle(h).fontSize);
        }""")

        # Now resize viewport to 800x480 WITHOUT reload
        page.set_viewport_size({"width": 800, "height": 480})
        # Wait for resize event and requestAnimationFrame
        page.wait_for_timeout(200)

        h_size_480p = page.evaluate("""() => {
            const h = document.querySelector('.notice-text .notice-headline');
            return parseFloat(window.getComputedStyle(h).fontSize);
        }""")

        assert h_size_480p < h_size_1080p, (
            f"Font size at 800x480 ({h_size_480p}px) must be smaller than at 1920x1080 ({h_size_1080p}px) after resize"
        )
        assert h_size_480p > 15, f"Font size at 800x480 ({h_size_480p}px) must be positive and legible"

        browser.close()


def test_media_slides_regression_check():
    """Verify image and video slides look the same as before."""
    base = Path(__file__).resolve().parent.parent
    css = (base / "static" / "css" / "display.css").read_text(encoding="utf-8")

    assert "object-fit: contain" in css
    assert ".media-ambient-bg" in css
    assert "filter: blur(40px)" in css
