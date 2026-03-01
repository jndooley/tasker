import pytest

from tasker import database


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tasker.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    database.close_connection()
    yield
    database.close_connection()
    if db_path.exists():
        db_path.unlink()
