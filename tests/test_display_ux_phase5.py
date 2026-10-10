from pathlib import Path
import pytest
from app import unified_app, display_app

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_display_html_structure(client):
    res = client.get("/display")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Core layout structure
    assert 'id="display-frame"' in html
    assert 'id="stage-panel"' in html
    assert 'id="stage-viewport"' in html
    assert 'id="card-text"' in html
    assert 'id="card-image"' in html
    assert 'id="card-video"' in html
    assert 'id="card-empty"' in html
    assert 'id="stage-dots"' in html
    assert 'id="stage-qr-badge"' in html
    assert 'class="display-ticker"' in html

def test_display_css_transitions_and_typography():
    base = Path(__file__).resolve().parent.parent
    css = (base / "static" / "css" / "display.css").read_text(encoding="utf-8")

    # Hardware acceleration & transitions
    assert "will-change: opacity, transform" in css
    assert ".notice-view.card-entering" in css
    assert "will-change: transform" in css
    assert "animation: tickerMarquee 30s linear infinite" in css
    assert ".ticker-viewport:hover .ticker-track" in css

    # Urgent state visual priority
    assert ".stage-panel.urgent-state" in css
    assert ".display-ticker.urgent-ticker" in css

    # Empty state reconnecting pulse
    assert ".empty-icon.reconnecting" in css
    assert "@keyframes emptyPulse" in css

    # Responsive scaling for 18"-22" monitors
    assert "@media (min-width: 1200px)" in css
    assert "@media (min-width: 1600px)" in css
    assert "font-size: 64px" in css

def test_media_aspect_ratio_and_ambient_backdrop():
    base = Path(__file__).resolve().parent.parent
    css = (base / "static" / "css" / "display.css").read_text(encoding="utf-8")

    # Object-fit contain preserves native aspect ratio
    assert "object-fit: contain" in css
    # Apple TV style frosted ambient backdrop
    assert ".media-ambient-bg" in css
    assert "filter: blur(40px)" in css

def test_display_js_ux_logic():
    base = Path(__file__).resolve().parent.parent
    js = (base / "static" / "js" / "display.js").read_text(encoding="utf-8")

    # Card entrance animation trigger
    assert "card-entering" in js
    # Stage dots hidden on single or empty queue
    assert "displayQueue.length <= 1" in js
    # Clean Unicode bullet for continuous ticker
    assert "\u2022" in js
    # Urgent state class manipulation
    assert "urgent-state" in js
    assert "urgent-ticker" in js
