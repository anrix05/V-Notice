from pathlib import Path
import pytest
from app import unified_app, admin_app
from storage import storage
import config

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_admin_html_elements_present(client):
    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Core login and dashboard elements
    assert 'id="login-modal"' in html
    assert 'id="admin-password-input"' in html
    assert 'id="btn-login"' in html
    assert 'id="btn-open-create"' in html

    # Expiration presets
    assert 'data-preset="today"' in html
    assert 'data-preset="3days"' in html
    assert 'data-preset="7days"' in html
    assert 'data-preset="30days"' in html

    # Dropzone and live preview
    assert 'id="file-drop-area"' in html
    assert 'id="media-file-input"' in html
    assert 'id="media-live-preview"' in html

    # Screen management
    assert 'id="feed-screen-filter"' in html
    assert 'id="notice-screen"' in html

    # Delete modal
    assert 'id="delete-modal"' in html
    assert 'id="btn-confirm-delete"' in html

    # Audit logs viewer UI
    assert 'id="btn-view-audit"' in html
    assert 'id="audit-modal"' in html
    assert 'id="audit-tbody"' in html

def test_audit_logs_api_and_admin_integration(client):
    # Unauthenticated audit request is blocked
    unauth = client.get("/api/audit-logs")
    assert unauth.status_code == 401

    # Log test audit event directly or via action
    storage.record_audit("admin", "notice_created", "test_phase6_notice")
    auth_res = client.get("/api/audit-logs", headers={"X-Password": config.ADMIN_PASSWORD})
    assert auth_res.status_code == 200
    data = auth_res.get_json()
    logs = data.get("audit_logs", data) if isinstance(data, dict) else data
    assert isinstance(logs, list)
    actions = [l.get("action") for l in logs]
    assert "notice_created" in actions

def test_admin_css_modal_and_audit_rules():
    base = Path(__file__).resolve().parent.parent
    css = (base / "static" / "css" / "admin.css").read_text(encoding="utf-8")

    assert ".modal-dialog-wide" in css
    assert ".audit-table" in css
    assert ".audit-action-badge" in css

def test_admin_js_validation_and_audit_handlers():
    base = Path(__file__).resolve().parent.parent
    js = (base / "static" / "js" / "admin.js").read_text(encoding="utf-8")

    # Client-side file validation
    assert "MAX_FILE_SIZE_MB = 200" in js
    assert "ALLOWED_EXTS" in js
    # Rate limit 429 countdown
    assert "_loginCountdown" in js
    # Audit log viewer
    assert "loadAuditLogs" in js
    assert "btnViewAudit" in js
