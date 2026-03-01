"""Utility helpers for path resolution and timestamp handling."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union


def resolve_db_path() -> Path:
    """Return the SQLite DB path, honoring TASKER_DB_PATH and XDG conventions.

    If TASKER_DB_PATH is a relative path (e.g., '.tasker/tasker.db'), searches
    up the directory tree from cwd to find an existing database before falling
    back to creating one in the current directory.
    """
    env_path = os.getenv("TASKER_DB_PATH")
    if env_path:
        path = Path(env_path).expanduser()

        # If it's a relative path, search up the directory tree
        if not path.is_absolute():
            current = Path.cwd()
            # Search up to root for existing database
            while current != current.parent:
                candidate = current / env_path
                if candidate.exists():
                    return candidate
                current = current.parent

            # Not found, use current directory
            path = Path.cwd() / env_path
    else:
        xdg_home = os.getenv("XDG_DATA_HOME")
        if xdg_home:
            base = Path(xdg_home)
        else:
            base = Path.home() / ".local" / "share"
        path = base / "tasker" / "tasker.db"

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_project_path(path: Optional[str]) -> Path:
    """Resolve an incoming path (or cwd) to an absolute project path."""
    target = Path(path) if path else Path.cwd()
    return target.expanduser().resolve()


def now_iso() -> str:
    """UTC timestamp string for DB writes."""
    return datetime.utcnow().isoformat(timespec="seconds")


def days_ago(days: int) -> datetime:
    """UTC datetime N days ago."""
    return datetime.utcnow() - timedelta(days=days)


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO-ish strings into datetimes; return None on failure."""
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", ""))
    except ValueError:
        return None


def format_ts(ts: Optional[Union[str, datetime]]) -> str:
    """Format datetimes or strings into human-readable short form."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        parsed = parse_ts(ts)
        if parsed is None:
            return ts
        ts = parsed
    return ts.strftime("%Y-%m-%d %H:%M")
