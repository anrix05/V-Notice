import pytest
from app import unified_app, display_app, admin_app
from storage import storage
import config

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_healthcheck_endpoint_structure(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()

    assert data["status"] == "healthy"
    assert data["version"] == config.VERSION
    assert "uptime_seconds" in data
    assert "memory_rss_mb" in data

    # Database health check
    assert data["database"]["connected"] is True
    assert data["database"]["journal_mode"].lower() == "wal"
    assert "notices_count" in data["database"]
    assert "screens_count" in data["database"]

    # Storage health check
    assert data["storage"]["writable"] is True
    assert data["storage"]["free_space_mb"] > 0

def test_healthcheck_unhealthy_on_db_failure(client, monkeypatch):
    monkeypatch.setattr(storage, "check_health", lambda: {"connected": False, "error": "Disk I/O error"})
    res = client.get("/api/health")
    assert res.status_code == 503
    data = res.get_json()
    assert data["status"] == "unhealthy"
    assert data["database"]["connected"] is False

def test_ram_budget_under_60mb(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    mem = data.get("memory_rss_mb")
    if mem is not None:
        # Strictly verify process memory stays well within Raspberry Pi 3B+ budget (~60MB)
        assert mem < 60.0, f"RAM usage ({mem} MB) exceeds Raspberry Pi target limit of 60MB"

def test_dual_mode_healthcheck_coverage():
    # Both Mode A and Mode B display/admin instances report healthy status
    for app in [display_app, admin_app, unified_app]:
        with app.test_client() as c:
            res = c.get("/api/health")
            assert res.status_code == 200
            assert res.get_json()["status"] == "healthy"
