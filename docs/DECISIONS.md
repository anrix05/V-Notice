# Architecture & Engineering Decisions (ADR)

## Decision 1: SQLite Storage with Write-Ahead Logging (WAL) Mode
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** The original storage engine read and wrote a single `notices.json` file under a threading Lock. This was prone to file corruption on sudden power loss (common on Raspberry Pi), prevented concurrent reads/writes, and did not scale cleanly with multi-worker/threaded Gunicorn servers.
- **Decision:** Transition from `notices.json` to standard library `sqlite3` using Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and `PRAGMA busy_timeout = 5000;`. Connections are managed per-request via Flask `g._db_conn` and automatically closed on `app.teardown_appcontext`.
- **Consequences:**
  - Zero added external dependencies (uses standard library `sqlite3`).
  - Concurrent readers do not block writers, and writers do not block readers.
  - Safe automatic migration from legacy `notices.json` with an atomic backup `notices.json.bak`.

## Decision 2: Pluggable MediaStorageBackend Interface
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** File uploads were saved directly to a local filesystem path. To prepare for cloud storage providers (such as Cloudflare R2 or AWS S3) without adding heavy SDK dependencies now, an abstraction was required.
- **Decision:** Define `MediaStorageBackend` with methods `save(file_obj, filename)`, `delete(filename)`, `exists(filename)`, `get_path(filename)`, and `url(filename)`. Implement `LocalMediaStorage(media_dir)` as the default.
- **Consequences:** Code in `storage.py` and `app.py` interacts only with the interface. An S3 or R2 backend can be dropped in later without modifying route or notice logic.

## Decision 3: Safe Media Garbage Collection with In-Flight Grace Period
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** Immediate deletion of unreferenced files on disk could delete files uploaded during in-flight form submissions or preview steps before the notice row is committed.
- **Decision:** Restrict garbage collection to files not referenced by any notice *and* whose file modification time is older than 10 minutes (`grace_period_seconds = 600`). Log every deleted unreferenced file at `INFO` level.
- **Consequences:** Protects concurrent or slow multi-part file uploads from race conditions while continuing to clean orphaned media.

## Decision 4: Multi-Screen Filtering Strategy
- **Date:** 2026-10-11
- **Status:** Accepted (Phase 1)
- **Context:** Institutional campuses need the ability to show different announcements in different corridors (e.g. `engineering-hall`, `library-lobby`, `canteen`).
- **Decision:** Add a `screens` table and `screen_id` column on `notices` defaulting to `'default'`. The display kiosk reads its target screen from `/display?screen=<id>`. The admin portal provides both a screen selector in the notice form and a filter in the feed header.
