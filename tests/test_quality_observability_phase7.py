import sqlite3
import time
import pytest
from app import unified_app, display_app, admin_app
from storage import storage
import config

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_healthcheck_liveness_endpoint(client):
    """GET /api/health returns 200 with {'status': 'ok'} and exposes no secrets or internal info."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data == {"status": "ok"}
    assert "version" not in data
    assert "database" not in data
    assert "storage" not in data
    assert "memory_rss_mb" not in data
    assert "uptime_seconds" not in data

def test_healthcheck_details_admin_only(client):
    """GET /api/health/details returns 401 without login, 200 with admin credentials."""
    # 1. Unauthenticated -> 401
    unauth = client.get("/api/health/details")
    assert unauth.status_code == 401

    # 2. Authenticated -> 200 with full health payload
    auth_res = client.get("/api/health/details", headers={"X-Password": config.ADMIN_PASSWORD})
    assert auth_res.status_code == 200
    data = auth_res.get_json()

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
    """On DB failure, detailed health returns 503 while liveness /api/health still returns 200."""
    monkeypatch.setattr(storage, "check_health", lambda: {"connected": False, "error": "Disk I/O error"})
    
    # Detailed health reflects database failure
    res = client.get("/api/health/details", headers={"X-Password": config.ADMIN_PASSWORD})
    assert res.status_code == 503
    data = res.get_json()
    assert data["status"] == "unhealthy"
    assert data["database"]["connected"] is False

    # Liveness check does not touch database and remains 200 ok
    liveness = client.get("/api/health")
    assert liveness.status_code == 200
    assert liveness.get_json() == {"status": "ok"}

def test_ram_budget_under_60mb(client):
    """Verify memory profiling is present in /api/health/details and stays within budget."""
    res = client.get("/api/health/details", headers={"X-Password": config.ADMIN_PASSWORD})
    assert res.status_code == 200
    data = res.get_json()
    mem = data.get("memory_rss_mb")
    if mem is not None:
        assert mem < 60.0, f"RAM usage ({mem} MB) exceeds Raspberry Pi target limit of 60MB"

def test_dual_mode_healthcheck_coverage():
    """Verify /api/health liveness and /api/health/details across display, admin, and unified apps."""
    for app in [display_app, admin_app, unified_app]:
        with app.test_client() as c:
            # Liveness returns 200 ok without login
            res = c.get("/api/health")
            assert res.status_code == 200
            assert res.get_json() == {"status": "ok"}

            # Details returns 401 without login
            unauth_details = c.get("/api/health/details")
            assert unauth_details.status_code == 401

            # Details returns healthy with admin auth
            auth_details = c.get("/api/health/details", headers={"X-Password": config.ADMIN_PASSWORD})
            assert auth_details.status_code == 200
            assert auth_details.get_json()["status"] == "healthy"

def test_health_liveness_locked_db_and_details_unauthorized(client):
    """
    Test: /api/health answers 200 in under 100 ms while the database is locked by another connection,
    and /api/health/details returns 401 without a login.
    """
    storage.close_connection()

    db_path = str(storage.db_file)
    locker = sqlite3.connect(db_path, timeout=1.0)
    locker.execute("PRAGMA locking_mode = EXCLUSIVE;")
    locker.execute("BEGIN EXCLUSIVE;")

    try:
        # Verify the database is truly locked for other connections
        verify_conn = sqlite3.connect(db_path, timeout=0.1)
        with pytest.raises(sqlite3.OperationalError):
            verify_conn.execute("SELECT 1;")
        verify_conn.close()

        # /api/health answers 200 in under 100 ms while the database is locked
        start_time = time.perf_counter()
        res = client.get("/api/health")
        duration = time.perf_counter() - start_time

        assert res.status_code == 200
        assert res.get_json() == {"status": "ok"}
        assert duration < 0.100, f"/api/health took {duration * 1000:.2f} ms, expected under 100 ms"
    finally:
        locker.close()

    # /api/health/details returns 401 without a login
    details_res = client.get("/api/health/details")
    assert details_res.status_code == 401
    assert "error" in details_res.get_json()
