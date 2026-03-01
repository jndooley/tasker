from datetime import datetime
from pathlib import Path

from tasker import utils


def test_resolve_project_path_defaults_to_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert utils.resolve_project_path(None) == tmp_path.resolve()


def test_format_ts_handles_datetime_and_string():
    now = datetime(2024, 1, 1, 12, 30)
    assert utils.format_ts(now) == "2024-01-01 12:30"
    assert utils.format_ts(now.isoformat()) == "2024-01-01 12:30"
    assert utils.format_ts("bad") == "bad"


def test_resolve_db_path_env(monkeypatch, tmp_path):
    target = tmp_path / "db.sqlite"
    monkeypatch.setenv("TASKER_DB_PATH", str(target))
    resolved = utils.resolve_db_path()
    assert resolved == target
    assert resolved.parent.exists()


def test_resolve_db_path_searches_up_tree(monkeypatch, tmp_path):
    """Test that relative TASKER_DB_PATH searches up directory tree."""
    # Create parent/.tasker/tasker.db
    parent = tmp_path / "parent"
    subdir = parent / "subdir" / "nested"
    subdir.mkdir(parents=True)

    db_path = parent / ".tasker" / "tasker.db"
    db_path.parent.mkdir(parents=True)
    db_path.touch()

    # Set env to relative path and change to subdirectory
    monkeypatch.setenv("TASKER_DB_PATH", ".tasker/tasker.db")
    monkeypatch.chdir(subdir)

    # Should find the database in parent directory
    resolved = utils.resolve_db_path()
    assert resolved == db_path
    assert resolved.exists()


def test_resolve_db_path_fallback_to_cwd(monkeypatch, tmp_path):
    """Test that when no database is found, it falls back to cwd."""
    subdir = tmp_path / "project" / "subdir"
    subdir.mkdir(parents=True)

    monkeypatch.setenv("TASKER_DB_PATH", ".tasker/tasker.db")
    monkeypatch.chdir(subdir)

    # Should create in current directory since none found above
    resolved = utils.resolve_db_path()
    assert resolved == subdir / ".tasker" / "tasker.db"
    assert resolved.parent.exists()
