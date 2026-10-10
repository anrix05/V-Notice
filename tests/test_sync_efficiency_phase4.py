import json
import pytest
from app import unified_app, display_app, admin_app
from storage import storage
import config

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_etag_header_presence(client):
    res = client.get("/api/notices")
    assert res.status_code == 200
    assert "ETag" in res.headers
    assert "no-cache" in res.headers.get("Cache-Control", "")
    etag = res.headers.get("ETag")
    assert etag.startswith('"') and etag.endswith('"')

def test_if_none_match_returns_304(client):
    res1 = client.get("/api/notices")
    assert res1.status_code == 200
    etag = res1.headers.get("ETag")
    assert etag is not None

    # Conditional GET with If-None-Match
    res2 = client.get("/api/notices", headers={"If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.data == b""
    assert res2.headers.get("ETag") == etag

def test_notice_mutation_changes_etag(client):
    res1 = client.get("/api/notices")
    etag1 = res1.headers.get("ETag")

    # Add a new notice
    nid = storage.add({
        "title": "Phase 4 ETag Test Notice",
        "body": "Testing dynamic ETag invalidation on storage mutation",
        "type": "text",
        "screen_id": "default",
        "priority": "normal",
        "duration": 10,
        "status": "live",
    })

    try:
        # Request with previous ETag must now return 200 with updated content
        res2 = client.get("/api/notices", headers={"If-None-Match": etag1})
        assert res2.status_code == 200
        etag2 = res2.headers.get("ETag")
        assert etag2 != etag1

        # Request with new ETag must return 304
        res3 = client.get("/api/notices", headers={"If-None-Match": etag2})
        assert res3.status_code == 304
    finally:
        storage.delete(nid["id"] if isinstance(nid, dict) else nid, actor="admin")

def test_screen_filtering_affects_etag(client):
    nid = storage.add({
        "title": "Screen Specific Notice",
        "body": "For Screen Alpha only",
        "type": "text",
        "screen_id": "screen_alpha",
        "status": "live",
    })
    try:
        res_alpha = client.get("/api/notices?screen=screen_alpha")
        res_beta = client.get("/api/notices?screen=screen_beta")

        etag_alpha = res_alpha.headers.get("ETag")
        etag_beta = res_beta.headers.get("ETag")
        assert etag_alpha != etag_beta
    finally:
        storage.delete(nid["id"] if isinstance(nid, dict) else nid, actor="admin")

def test_admin_notices_etag_and_304(client):
    headers = {"X-Password": config.ADMIN_PASSWORD}
    res1 = client.get("/api/notices", headers=headers)
    assert res1.status_code == 200
    etag = res1.headers.get("ETag")
    assert etag is not None

    res2 = client.get("/api/notices", headers={"X-Password": config.ADMIN_PASSWORD, "If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.data == b""

def test_sse_events_disabled_returns_404(client, monkeypatch):
    monkeypatch.setattr(config, "SSE_ENABLED", False)
    res = client.get("/api/events")
    assert res.status_code == 404

def test_sse_events_enabled_stream(client, monkeypatch):
    monkeypatch.setattr(config, "SSE_ENABLED", True)
    res = client.get("/api/events")
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type

def test_system_info_contains_sync_settings(client, monkeypatch):
    monkeypatch.setattr(config, "POLL_INTERVAL_SECONDS", 8)
    monkeypatch.setattr(config, "SSE_ENABLED", False)
    res = client.get("/api/system-info")
    assert res.status_code == 200
    data = res.get_json()
    assert data["poll_interval_seconds"] == 8
    assert data["sse_enabled"] is False
