"""Tests for the lift (scope estimate) field: migration, queries, and CLI."""

import json
import sqlite3

import pytest
from click.testing import CliRunner

from tasker import cli
from tasker.database import close_connection, get_db
from tasker.models import Lift
from tasker.queries import (
    create_project,
    create_task,
    get_task,
    get_task_history,
    list_tasks,
    update_task,
)


def _make_project():
    return create_project("/tmp/lift-test", "lift-test")


def test_migration_v11_adds_lift_and_preserves_child_rows(tmp_path, monkeypatch):
    """Simulate a v11 database and verify migration to v12 adds lift while
    preserving task rows, the AUTOINCREMENT sequence, and every row in tables
    that reference tasks."""
    db_path = tmp_path / "migration_v11.db"
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
            order_number INTEGER,
            order_set_at TIMESTAMP,
            order_set_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );

        CREATE TABLE task_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_task_id INTEGER NOT NULL,
            target_task_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL CHECK (relation_type IN ('blocked-by','caused-by','related-to')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            FOREIGN KEY (target_task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            UNIQUE (source_task_id, target_task_id, relation_type)
        );

        CREATE TABLE task_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE task_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            cr_num INTEGER NOT NULL,
            reviewer TEXT,
            recommendations TEXT,
            devils_advocate TEXT,
            false_positives TEXT,
            kind TEXT NOT NULL DEFAULT 'standard',
            model TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (task_id, cr_num)
        );

        CREATE TABLE task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            agent TEXT NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_at TEXT NOT NULL
        );

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO metadata(key, value) VALUES ('schema_version', '11');

        INSERT INTO projects(path, name, is_active) VALUES ('/tmp/p', 'p', 1);
        INSERT INTO tasks(project_id, title, priority) VALUES (1, 'Existing task', 2);
        INSERT INTO tasks(project_id, title) VALUES (1, 'Second task');
        INSERT INTO task_relations(source_task_id, target_task_id, relation_type) VALUES (1, 2, 'blocked-by');
        INSERT INTO task_notes(task_id, author, content) VALUES (1, 'claude', 'a note');
        INSERT INTO task_reviews(task_id, cr_num) VALUES (1, 1);
        INSERT INTO task_history(task_id, agent, field, old_value, new_value, changed_at)
            VALUES (1, 'claude', 'status', 'todo', 'in-progress', '2026-07-01T00:00:00');
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    close_connection()

    migrated = get_db().connect()
    columns = {
        row["name"]
        for row in migrated.execute("PRAGMA table_info(tasks)").fetchall()
    }
    assert "lift" in columns

    # Existing rows preserved with lift defaulting to unset (0)
    rows = migrated.execute(
        "SELECT id, title, priority, lift FROM tasks ORDER BY id"
    ).fetchall()
    assert [(r["id"], r["title"], r["priority"], r["lift"]) for r in rows] == [
        (1, "Existing task", 2, 0),
        (2, "Second task", 0, 0),
    ]

    # Child rows referencing tasks must survive the migration
    assert migrated.execute("SELECT COUNT(*) FROM task_relations").fetchone()[0] == 1
    assert migrated.execute("SELECT COUNT(*) FROM task_notes").fetchone()[0] == 1
    assert migrated.execute("SELECT COUNT(*) FROM task_reviews").fetchone()[0] == 1
    assert migrated.execute("SELECT COUNT(*) FROM task_history").fetchone()[0] == 1

    # AUTOINCREMENT high-water-mark must survive (id reuse after delete is
    # forbidden; a copy-table rebuild would reset this)
    seq = migrated.execute(
        "SELECT seq FROM sqlite_sequence WHERE name='tasks'"
    ).fetchone()
    assert seq is not None and seq[0] == 2

    # CHECK constraint rejects out-of-range lift
    with pytest.raises(sqlite3.IntegrityError):
        migrated.execute("UPDATE tasks SET lift = 4 WHERE id = 1")

    close_connection()


def test_create_task_defaults_to_unset():
    project = _make_project()
    task = create_task(project_id=project.id, title="No lift given")
    assert task.lift == Lift.UNSET
    assert task.to_dict()["lift"] == 0


def test_create_update_and_history():
    project = _make_project()
    task = create_task(project_id=project.id, title="Sized task", lift=Lift.SMALL)
    assert task.lift == Lift.SMALL

    updated = update_task(task.id, lift=Lift.LARGE, agent="claude")
    assert updated is not None
    assert updated.lift == Lift.LARGE
    assert get_task(task.id).lift == Lift.LARGE

    history = get_task_history(task.id)
    lift_entries = [h for h in history if h.field == "lift"]
    assert len(lift_entries) == 1
    assert (lift_entries[0].old_value, lift_entries[0].new_value) == ("1", "3")


def test_list_tasks_lift_filter():
    project = _make_project()
    small = create_task(project_id=project.id, title="Small", lift=Lift.SMALL)
    create_task(project_id=project.id, title="Large", lift=Lift.LARGE)
    unsized = create_task(project_id=project.id, title="Unsized")

    smalls = list_tasks(project.id, lift=Lift.SMALL)
    assert [t.id for t in smalls] == [small.id]

    unset = list_tasks(project.id, lift=Lift.UNSET)
    assert [t.id for t in unset] == [unsized.id]

    everything = list_tasks(project.id)
    assert len(everything) == 3


def test_cli_lift_workflow(tmp_path, monkeypatch):
    db_path = tmp_path / "cli_lift.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    assert runner.invoke(cli.cli, ["init", str(tmp_path)]).exit_code == 0

    # add with --lift, and one without
    assert runner.invoke(cli.cli, ["add", "Big feature", "--lift", "large"]).exit_code == 0
    assert runner.invoke(cli.cli, ["add", "Tiny fix", "--lift", "small"]).exit_code == 0
    assert runner.invoke(cli.cli, ["add", "Unsized"]).exit_code == 0

    # list --lift filter
    res = runner.invoke(cli.cli, ["list", "--lift", "large", "--json"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    assert [t["title"] for t in payload] == ["Big feature"]
    assert payload[0]["lift"] == 3

    res = runner.invoke(cli.cli, ["list", "--lift", "unset", "--json"])
    assert res.exit_code == 0
    assert [t["title"] for t in json.loads(res.output)] == ["Unsized"]

    # update --lift
    task_id = payload[0]["id"]
    assert runner.invoke(cli.cli, ["update", str(task_id), "--lift", "medium"]).exit_code == 0
    res = runner.invoke(cli.cli, ["list", "--lift", "medium", "--json"])
    assert [t["id"] for t in json.loads(res.output)] == [task_id]

    # show displays lift
    res = runner.invoke(cli.cli, ["show", str(task_id)])
    assert res.exit_code == 0
    assert "Lift: med" in res.output

    # lift-only update with explicit --agent records history
    assert (
        runner.invoke(
            cli.cli, ["update", str(task_id), "--lift", "large", "--agent", "claude"]
        ).exit_code
        == 0
    )
    res = runner.invoke(cli.cli, ["show", str(task_id), "--history"])
    assert res.exit_code == 0
    assert "lift: 2" in res.output and "3" in res.output

    # invalid choice rejected
    res = runner.invoke(cli.cli, ["add", "Bad", "--lift", "huge"])
    assert res.exit_code != 0
