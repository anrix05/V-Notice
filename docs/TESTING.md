# V Notice Testing & Verification Guide

## 1. Automated Test Suite (pytest)

Run the backend automated test suite:
```bash
pytest -v
```

### Coverage by Phase:
- **Phase 1 (Data Integrity & Storage):** `tests/test_storage_phase1.py`
  - Tests SQLite database initialization and WAL journal mode.
  - Tests one-time automatic migration from `notices.json` to SQLite with backup creation.
  - Tests `MediaStorageBackend` interface and `LocalMediaStorage` save/delete operations.
  - Tests Safe Media Garbage Collection (10-minute in-flight grace period).
  - Tests multi-screen filtering (`screen_id`) and creator tracking (`created_by`).

---

## 2. Manual Verification Checklist (Frontend & End-to-End)

### Phase 1: Data Integrity & Storage
- [ ] **One-Time Migration Verification:**
  1. Verify that `notices.db` exists in the project root/storage directory.
  2. Verify that `notices.json.bak` exists as an intact backup of the original notices.
  3. Start the application (`python app.py`) and confirm existing notices appear on `/` and `/display`.
- [ ] **Multi-Screen Filtering:**
  1. Open the Admin Portal at `/` (or `http://localhost:5001/`).
  2. Click **"+ New notice"**.
  3. Verify the **Target Screen** dropdown is present with "Default Screen".
  4. Type a new screen name or select default, fill headline, and submit.
  5. In the notices feed, use the **Screen:** dropdown to switch between "All Screens" and specific screens. Confirm filtering works immediately.
  6. Open `/display?screen=default` on another tab and confirm only notices targeted to `default` appear.
- [ ] **Safe Media Garbage Collection:**
  1. Upload a notice with an image attachment.
  2. Delete the notice.
  3. Verify that the media file is removed if it is no longer referenced by any notice.
  4. Create a dummy file in `media/test_inflight.png` with current timestamp; confirm GC skips it because age is < 10 minutes.
- [ ] **Render Ephemeral Warning:**
  1. Run `RENDER=true python -c "import config"` in a terminal.
  2. Confirm the visible warning message is printed to `stderr` detailing that data will be lost on container redeploy unless a persistent disk is attached.
