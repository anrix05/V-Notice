import os
from pathlib import Path
import pytest
from app import unified_app
import config

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_weather_disabled_api(client, monkeypatch):
    monkeypatch.setattr(config, "WEATHER_ENABLED", False)
    res = client.get("/api/system-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["weather_enabled"] is False
    assert data["temp"] is None
    assert data["icon"] is None

def test_weather_custom_location_api(client, monkeypatch):
    monkeypatch.setattr(config, "WEATHER_ENABLED", True)
    monkeypatch.setattr(config, "WEATHER_LABEL", "Delhi Campus")
    res = client.get("/api/system-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["city"] == "DELHI CAMPUS"

def test_public_base_url_in_system_info(client, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "https://v-notice.onrender.com")
    res = client.get("/api/system-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["public_base_url"] == "https://v-notice.onrender.com"

def test_urgent_chime_in_system_info(client, monkeypatch):
    monkeypatch.setattr(config, "URGENT_CHIME", True)
    res = client.get("/api/system-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["urgent_chime"] is True

    monkeypatch.setattr(config, "URGENT_CHIME", False)
    res2 = client.get("/api/system-info")
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["urgent_chime"] is False

def test_sw_route_served(client):
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.content_type
    assert res.headers.get("Service-Worker-Allowed") == "/"
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert b"SHELL_CACHE" in res.data

def test_self_hosted_fonts_and_font_face():
    base = Path(__file__).resolve().parent.parent
    fonts_dir = base / "static" / "fonts"
    expected_fonts = [
        "Inter-Regular.woff2",
        "Inter-Bold.woff2",
        "Outfit-Regular.woff2",
        "Outfit-Bold.woff2"
    ]
    for font_file in expected_fonts:
        p = fonts_dir / font_file
        assert p.exists(), f"Missing self-hosted font: {font_file}"
        assert p.stat().st_size > 5000, f"Font file appears empty or corrupt: {font_file}"

    css_path = base / "static" / "css" / "display.css"
    css_content = css_path.read_text(encoding="utf-8")
    assert "@font-face" in css_content
    assert "font-display: swap" in css_content
    assert "Inter-Regular.woff2" in css_content

def test_offline_qr_library_exists():
    base = Path(__file__).resolve().parent.parent
    qr_js = base / "static" / "js" / "qrcode.min.js"
    assert qr_js.exists()
    assert qr_js.stat().st_size > 10000

    html = (base / "templates" / "display.html").read_text(encoding="utf-8")
    assert "qrcode.min.js" in html

def test_kiosk_script_persistent_cache_flags():
    base = Path(__file__).resolve().parent.parent
    kiosk_sh = (base / "systemd" / "kiosk.sh").read_text(encoding="utf-8")
    assert "--user-data-dir=" in kiosk_sh
    assert "--autoplay-policy=no-user-gesture-required" in kiosk_sh
    assert "--noerrdialogs" in kiosk_sh
    assert "--disable-infobars" in kiosk_sh
    assert "--kiosk" in kiosk_sh
    assert "--incognito" not in kiosk_sh
