"""Database connection, migrations, and transaction helpers."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .utils import resolve_db_path


class Database:
    """SQLite database singleton wrapper with schema migrations and transactions."""

    SCHEMA_VERSION = 9

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or resolve_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Return shared connection, initializing schema and migrations once."""
        if self._conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.executescript(self._schema())
            self._conn = conn
            self._ensure_metadata()
            self._run_migrations()
        return self._conn

    def close(self):
        """Close the shared connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager that commits on success and rolls back on failure."""
        conn = self.connect()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()

    @staticmethod
    def _schema() -> str:
        return """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            acceptance_criteria TEXT,
            status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','blocked','review','qa','done')),
            priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
            order_index INTEGER DEFAULT 0,
            group_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
        CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
        """

    def _ensure_metadata(self):
        conn = self._conn
        if conn is None:
            raise RuntimeError("No database connection")
        conn.execute(
            "INSERT OR IGNORE INTO metadata(key, value, updated_at) VALUES ('schema_version', '0', CURRENT_TIMESTAMP)"
        )
        conn.commit()

    def _current_version(self) -> int:
        conn = self._conn
        if conn is None:
            raise RuntimeError("No database connection")
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def _set_version(self, version: int) -> None:
        conn = self._conn
        if conn is None:
            raise RuntimeError("No database connection")
        conn.execute(
            "UPDATE metadata SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'schema_version'",
            (str(version),),
        )
        conn.commit()

    def _run_migrations(self) -> None:
        """Run forward migrations based on schema version."""
        current = self._current_version()
        conn = self._conn
        if conn is None:
            raise RuntimeError("No database connection")

        if current < 2:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "acceptance_criteria" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN acceptance_criteria TEXT")

        if current < 3:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "group_id" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN group_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(group_id)"
            )

        if current < 4:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_task_id INTEGER NOT NULL,
                    target_task_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL CHECK (relation_type IN ('blocked-by','caused-by','related-to')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                    UNIQUE (source_task_id, target_task_id, relation_type)
                );
                CREATE INDEX IF NOT EXISTS idx_task_relations_source ON task_relations(source_task_id);
                CREATE INDEX IF NOT EXISTS idx_task_relations_target ON task_relations(target_task_id);
            """)

        if current < 5:
            # Recreate tasks table with updated CHECK constraint to include 'blocked'
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    acceptance_criteria TEXT,
                    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','blocked','done')),
                    priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
                    order_index INTEGER DEFAULT 0,
                    group_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                );

                INSERT INTO tasks_new (id, project_id, title, description, acceptance_criteria, status, priority, order_index, group_id, created_at, updated_at, completed_at)
                SELECT id, project_id, title, description, acceptance_criteria, status, priority, order_index, group_id, created_at, updated_at, completed_at FROM tasks;

                DROP TABLE tasks;

                ALTER TABLE tasks_new RENAME TO tasks;

                CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
                CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(group_id);
            """)

        if current < 6:
            # Recreate tasks table with updated CHECK constraint to include 'review' and 'qa'
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    acceptance_criteria TEXT,
                    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','blocked','review','qa','done')),
                    priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
                    order_index INTEGER DEFAULT 0,
                    group_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                );

                INSERT INTO tasks_new (id, project_id, title, description, acceptance_criteria, status, priority, order_index, group_id, created_at, updated_at, completed_at)
                SELECT id, project_id, title, description, acceptance_criteria, status, priority, order_index, group_id, created_at, updated_at, completed_at FROM tasks;

                DROP TABLE tasks;

                ALTER TABLE tasks_new RENAME TO tasks;

                CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
                CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(group_id);
            """)

        if current < 7:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "plan" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN plan TEXT")

        if current < 8:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    cr_num INTEGER NOT NULL,
                    reviewer TEXT,
                    recommendations TEXT,
                    devils_advocate TEXT,
                    false_positives TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (task_id, cr_num)
                );
            """)

        if current < 9:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    agent TEXT NOT NULL,
                    field TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    changed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id);
            """)

        if current < self.SCHEMA_VERSION:
            self._set_version(self.SCHEMA_VERSION)


_db_instance: Optional[Database] = None


def get_db(db_path: Optional[Path] = None) -> Database:
    """Return the singleton Database instance, creating it if needed."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance


def close_connection():
    """Close and reset the singleton connection (used in tests)."""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
        _db_instance = None
