import os
import time
import json
import sqlite3
import pytest
from pathlib import Path
from storage import NoticeStorage, LocalMediaStorage

@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_notices.db"
    json_file = tmp_path / "notices.json"
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    
    # Pre-populate sample JSON file to test migration
    sample_notices = [
        {
            "id": "migr0001",
            "title": "Migrated Notice",
            "body": "Sample body",
            "priority": "normal",
            "type": "text",
            "media": "",
            "duration": 10,
            "start": int(time.time() * 1000) - 10000,
            "end": int(time.time() * 1000) + 100000
        }
    ]
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(sample_notices, f)

    storage = NoticeStorage(
        db_file=db_file,
        data_file=json_file,
        media_backend=LocalMediaStorage(media_dir=media_dir)
    )
    return {
        "storage": storage,
        "db_file": db_file,
        "json_file": json_file,
        "media_dir": media_dir,
    }

def test_sqlite_wal_mode(temp_env):
    conn = sqlite3.connect(str(temp_env["db_file"]))
    try:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"
    finally:
        conn.close()

def test_migration_and_backup(temp_env):
    storage = temp_env["storage"]
    notices = storage.get_all()
    assert len(notices) >= 1
    assert notices[0]["id"] == "migr0001"
    assert notices[0]["title"] == "Migrated Notice"
    assert notices[0]["screen_id"] == "default"
    assert notices[0]["created_by"] == "admin"
    
    # Verify backup file created
    bak_file = temp_env["json_file"].with_name("notices.json.bak")
    assert bak_file.exists()

def test_screen_filtering(temp_env):
    storage = temp_env["storage"]
    
    # Create notice for specific screen
    n1 = storage.add({
        "title": "Screen Library Notice",
        "body": "Silence please",
        "screen_id": "library",
        "created_by": "librarian"
    })
    assert n1["screen_id"] == "library"
    assert n1["created_by"] == "librarian"

    # Query by screen
    lib_notices = storage.get_all(screen_id="library")
    assert any(n["id"] == n1["id"] for n in lib_notices)

    default_notices = storage.get_all(screen_id="default")
    assert not any(n["id"] == n1["id"] for n in default_notices)

    all_notices = storage.get_all(screen_id="all")
    assert any(n["id"] == n1["id"] for n in all_notices)

def test_media_storage_backend(temp_env):
    media = temp_env["storage"].media_storage
    test_file_path = temp_env["media_dir"] / "test_dummy.txt"
    test_file_path.write_text("hello world", encoding="utf-8")
    
    assert media.exists("test_dummy.txt") is True
    assert media.url("test_dummy.txt") == "/media/test_dummy.txt"
    assert media.delete("test_dummy.txt") is True
    assert media.exists("test_dummy.txt") is False

def test_safe_garbage_collection(temp_env):
    storage = temp_env["storage"]
    media_dir = temp_env["media_dir"]
    
    # 1. File older than 10 mins (600s), unreferenced -> should be deleted
    old_orphan = media_dir / "old_orphan.jpg"
    old_orphan.write_text("old", encoding="utf-8")
    past_time = time.time() - 700  # 11+ minutes old
    os.utime(old_orphan, (past_time, past_time))

    # 2. File newer than 10 mins (in-flight), unreferenced -> should be SKIPPED
    new_inflight = media_dir / "in_flight.jpg"
    new_inflight.write_text("new", encoding="utf-8")  # current mtime

    # 3. Referenced file -> should be KEPT
    ref_file = media_dir / "active_poster.jpg"
    ref_file.write_text("poster", encoding="utf-8")
    storage.add({
        "title": "Notice with media",
        "media": "active_poster.jpg"
    })

    # Trigger safe GC
    storage.safe_garbage_collect_media(grace_period_seconds=600)

    assert not old_orphan.exists(), "Old orphan media should have been safely deleted"
    assert new_inflight.exists(), "In-flight young media should be protected from deletion"
    assert ref_file.exists(), "Referenced media must never be deleted"
