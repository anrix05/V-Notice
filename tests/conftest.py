import os
import shutil
import tempfile
import pytest

TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "vnotice2026")

@pytest.fixture(scope="session", autouse=True)
def isolated_test_environment(tmp_path_factory):
    """
    Ensures every test run uses an isolated test database and media directory,
    preventing any test pollution of the production/local notices.db.
    """
    from pathlib import Path
    test_dir = tmp_path_factory.mktemp("vnotice_test_data")
    test_db = Path(test_dir / "test_notices.db")
    test_media = Path(test_dir / "test_media")
    test_media.mkdir(parents=True, exist_ok=True)

    import config
    old_db = config.DB_FILE
    old_media = config.MEDIA_DIR
    old_storage_dir = config.STORAGE_DIR

    config.DB_FILE = test_db
    config.MEDIA_DIR = test_media
    config.MEDIA_FOLDER = test_media
    config.STORAGE_DIR = Path(test_dir)

    import storage
    storage.storage.db_file = test_db
    storage.storage.media_storage = storage.LocalMediaStorage(media_dir=test_media)
    storage.storage._init_db()

    # Also point app storage reference
    try:
        import app
        app.storage = storage.storage
        app.MEDIA_FOLDER = test_media
    except ImportError:
        pass

    yield test_dir

    # Teardown / cleanup
    config.DB_FILE = old_db
    config.MEDIA_DIR = old_media
    config.STORAGE_DIR = old_storage_dir
    storage.storage.db_file = old_db
    storage.storage.media_storage = storage.LocalMediaStorage(media_dir=old_media)
