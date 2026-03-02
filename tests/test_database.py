import sqlite3

from tasker.database import close_connection, get_connection, transaction
from tasker import queries


def test_transaction_rolls_back_on_error():
    project = queries.create_project("/tmp/db_project", "DB Project")
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO tasks(project_id, title, status, priority) VALUES (?, ?, ?, ?)",
                (project.id, "Bad", "todo", 0),
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    tasks = queries.list_tasks(project.id, include_done=True)
    assert tasks == []


def test_connection_reused():
    conn1 = get_connection()
    conn2 = get_connection()
    assert conn1 is conn2


def test_migration_adds_acceptance_criteria_column(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','done')),
            priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
            order_index INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO metadata(key, value) VALUES ('schema_version', '1');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    close_connection()

    migrated = get_connection()
    columns = {
        row["name"] for row in migrated.execute("PRAGMA table_info(tasks)").fetchall()
    }
    assert "acceptance_criteria" in columns
    assert "group_id" in columns


def test_migration_v3_to_v4_creates_task_relations(tmp_path, monkeypatch):
    """Simulate a v3 database and verify migration to v4 creates task_relations."""
    db_path = tmp_path / "migration_v3.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            acceptance_criteria TEXT,
            status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','done')),
            priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
            order_index INTEGER DEFAULT 0,
            group_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO metadata(key, value) VALUES ('schema_version', '3');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    close_connection()

    migrated = get_connection()
    tables = {
        row[0]
        for row in migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "task_relations" in tables

    # Check columns exist
    columns = {
        row["name"]
        for row in migrated.execute("PRAGMA table_info(task_relations)").fetchall()
    }
    assert "source_task_id" in columns
    assert "target_task_id" in columns
    assert "relation_type" in columns


def test_migration_v8_creates_notes_and_reviews_tables(tmp_path, monkeypatch):
    """Simulate a v7 database and verify migration to v8 creates task_notes and task_reviews."""
    db_path = tmp_path / "migration_v7.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            acceptance_criteria TEXT,
            plan TEXT,
            status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','blocked','review','qa','done')),
            priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
            order_index INTEGER DEFAULT 0,
            group_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO metadata(key, value) VALUES ('schema_version', '7');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    close_connection()

    migrated = get_connection()
    tables = {
        row[0]
        for row in migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "task_notes" in tables
    assert "task_reviews" in tables

    note_cols = {row["name"] for row in migrated.execute("PRAGMA table_info(task_notes)").fetchall()}
    assert {"id", "task_id", "author", "content", "created_at"} <= note_cols

    review_cols = {row["name"] for row in migrated.execute("PRAGMA table_info(task_reviews)").fetchall()}
    assert {"id", "task_id", "cr_num", "reviewer", "recommendations", "devils_advocate", "false_positives", "created_at", "updated_at"} <= review_cols


def test_migration_adds_group_id_column(tmp_path, monkeypatch):
    """Simulate a v2 database and verify migration to v3 adds group_id."""
    db_path = tmp_path / "migration_v2.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            acceptance_criteria TEXT,
            status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in-progress','done')),
            priority INTEGER DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
            order_index INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO metadata(key, value) VALUES ('schema_version', '2');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    close_connection()

    migrated = get_connection()
    columns = {
        row["name"] for row in migrated.execute("PRAGMA table_info(tasks)").fetchall()
    }
    assert "group_id" in columns
