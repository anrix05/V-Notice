import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from app import create_admin_app

def test_endpoint_404_when_test_mode_not_set(monkeypatch):
    monkeypatch.delenv("VNOTICE_TEST_MODE", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    app = create_admin_app()
    app.config["TESTING"] = True
    client = app.test_client()
    res = client.post("/api/test-reset-rate-limit")
    assert res.status_code == 404, f"Expected 404 when VNOTICE_TEST_MODE is not set, got {res.status_code}"

def test_endpoint_404_when_on_render(monkeypatch):
    monkeypatch.setenv("VNOTICE_TEST_MODE", "1")
    monkeypatch.setenv("RENDER", "true")
    app = create_admin_app()
    app.config["TESTING"] = True
    client = app.test_client()
    res = client.post("/api/test-reset-rate-limit")
    assert res.status_code == 404, f"Expected 404 when RENDER=true, got {res.status_code}"

def test_endpoint_200_only_when_test_mode_and_not_render(monkeypatch):
    monkeypatch.setenv("VNOTICE_TEST_MODE", "1")
    monkeypatch.delenv("RENDER", raising=False)
    app = create_admin_app()
    app.config["TESTING"] = True
    client = app.test_client()
    res = client.post("/api/test-reset-rate-limit")
    assert res.status_code == 200, f"Expected 200 when VNOTICE_TEST_MODE=1 and RENDER is unset, got {res.status_code}"
    data = res.get_json()
    assert data.get("success") is True
