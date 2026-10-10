import pytest
from app import unified_app

@pytest.fixture
def client():
    unified_app.config["TESTING"] = True
    with unified_app.test_client() as c:
        yield c

def test_admin_screens_html_elements_present(client):
    res = client.get("/admin")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. Multi-select Chip Picker in Publish Modal
    assert 'id="screen-chip-picker"' in html
    assert 'id="screen-picker-error"' in html
    assert 'id="screen-picker-label"' in html

    # 2. Feed Screen Filter
    assert 'id="feed-screen-filter"' in html

    # 3. Screens Management Panel
    assert 'id="screens-modal"' in html
    assert 'id="btn-view-screens"' in html
    assert 'id="dept-table-body"' in html
    assert 'id="add-dept-form"' in html
    assert 'id="dept-code-input"' in html
    assert 'id="dept-name-input"' in html

    # 4. Preview on Display button
    assert 'id="btn-preview-display"' in html

    # 5. User-facing "Default Screen" renamed to "All Departments (college-wide)"
    assert "Default Screen" not in html
    assert "All Departments (college-wide)" in html

def test_admin_css_phase4_rules():
    with open("static/css/admin.css", "r", encoding="utf-8") as f:
        css = f.read()

    assert ".chip-picker" in css
    assert ".chip" in css
    assert ".chip.selected" in css
    assert ".badge-dept-chip" in css
    assert ".badge-dept-chip.badge-all" in css
    assert ".badge-dept-chip.badge-overflow" in css
    assert ".btn-preview-display" in css
    assert ".dept-table" in css
    assert ".hb-online" in css

def test_admin_js_phase4_logic():
    with open("static/js/admin.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "renderChipPicker" in js
    assert "validateScreenPicker" in js
    assert "selectedScreenCodes" in js
    assert "loadAndRenderScreensTable" in js
    assert "btnPreviewDisplay" in js
    assert "btn-copy-screen-link" in js
