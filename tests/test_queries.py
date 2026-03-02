import sqlite3

import pytest

from tasker import queries
from tasker.database import transaction
from tasker.models import Priority, RelationType, Status


def test_project_creation_and_activation():
    project = queries.create_project("/tmp/projectA", "Project A")
    active = queries.get_active_project()
    assert active is not None
    assert active.id == project.id


def test_task_focus_prefers_in_progress():
    project = queries.create_project("/tmp/projectB", "Project B")
    t1 = queries.create_task(project.id, "First", priority=Priority.MEDIUM)
    t2 = queries.create_task(
        project.id, "Second", priority=Priority.HIGH, status=Status.IN_PROGRESS
    )

    focus = queries.get_focus_task(project.id)
    assert focus is not None
    assert focus.id == t2.id  # in-progress beats todo

    queries.complete_task(t2.id)
    focus_after = queries.get_focus_task(project.id)
    assert focus_after.id == t1.id


def test_reorder_changes_positions():
    project = queries.create_project("/tmp/projectC", "Project C")
    t1 = queries.create_task(project.id, "T1")
    t2 = queries.create_task(project.id, "T2")
    t3 = queries.create_task(project.id, "T3")

    queries.reorder_task(t3.id, 1)
    tasks = queries.list_tasks(project.id, include_done=True)
    assert [t.id for t in tasks][:2] == [t3.id, t1.id]


def test_update_and_delete_task():
    project = queries.create_project("/tmp/projectD", "Project D")
    task = queries.create_task(
        project.id, "Original", description="desc", priority=Priority.LOW
    )

    updated = queries.update_task(
        task.id, title="Updated", priority=Priority.HIGH, status=Status.IN_PROGRESS
    )
    assert updated is not None
    assert updated.title == "Updated"
    assert updated.priority == Priority.HIGH
    assert updated.status == Status.IN_PROGRESS

    queries.delete_task(task.id)
    assert queries.get_task(task.id) is None


def test_acceptance_criteria_persist_and_update():
    project = queries.create_project("/tmp/projectF", "Project F")
    task = queries.create_task(
        project.id,
        "Write tests",
        acceptance_criteria=["unit tests added", "docs updated"],
    )

    fetched = queries.get_task(task.id)
    assert fetched is not None
    assert fetched.acceptance_criteria == ["unit tests added", "docs updated"]

    updated = queries.update_task(task.id, acceptance_criteria=["tests pass"])
    assert updated is not None
    assert updated.acceptance_criteria == ["tests pass"]


def test_clean_completed_filters_by_age():
    project = queries.create_project("/tmp/projectE", "Project E")
    recent = queries.create_task(project.id, "Recent", status=Status.DONE)
    old = queries.create_task(project.id, "Old", status=Status.DONE)

    queries.update_task(old.id, status=Status.DONE)
    conn = queries.get_connection()
    conn.execute(
        "UPDATE tasks SET completed_at = datetime('now', '-10 days') WHERE id = ?",
        (old.id,),
    )
    conn.commit()

    removed = queries.clean_completed(project.id, older_than_days=7)
    assert removed == 1
    remaining = queries.list_tasks(project.id, include_done=True)
    assert {t.id for t in remaining} == {recent.id}


def test_group_id_create_and_filter():
    project = queries.create_project("/tmp/projectH", "Project H")
    t1 = queries.create_task(project.id, "Auth login", group_id="auth")
    t2 = queries.create_task(project.id, "Auth logout", group_id="auth")
    t3 = queries.create_task(project.id, "Dashboard widget", group_id="ui")
    t4 = queries.create_task(project.id, "No group task")

    # Filter by group
    auth_tasks = queries.list_tasks(project.id, group_id="auth")
    assert len(auth_tasks) == 2
    assert {t.id for t in auth_tasks} == {t1.id, t2.id}

    ui_tasks = queries.list_tasks(project.id, group_id="ui")
    assert len(ui_tasks) == 1
    assert ui_tasks[0].id == t3.id

    # All tasks returned without filter
    all_tasks = queries.list_tasks(project.id)
    assert len(all_tasks) == 4


def test_group_id_update_and_clear():
    project = queries.create_project("/tmp/projectI", "Project I")
    task = queries.create_task(project.id, "Some task")
    assert task.group_id is None

    updated = queries.update_task(task.id, group_id="backend")
    assert updated.group_id == "backend"

    cleared = queries.update_task(task.id, group_id=None)
    assert cleared.group_id is None


def test_list_groups():
    project = queries.create_project("/tmp/projectJ", "Project J")
    queries.create_task(project.id, "T1", group_id="api")
    queries.create_task(project.id, "T2", group_id="api")
    queries.create_task(project.id, "T3", group_id="ui")
    queries.create_task(project.id, "T4")  # ungrouped

    groups = queries.list_groups(project.id)
    assert len(groups) == 2
    by_id = {g["group_id"]: g["task_count"] for g in groups}
    assert by_id["api"] == 2
    assert by_id["ui"] == 1


def test_list_groups_excludes_done_by_default():
    project = queries.create_project("/tmp/projectK", "Project K")
    queries.create_task(project.id, "T1", group_id="old", status=Status.DONE)
    queries.create_task(project.id, "T2", group_id="active")

    groups = queries.list_groups(project.id, include_done=False)
    assert len(groups) == 1
    assert groups[0]["group_id"] == "active"

    groups_all = queries.list_groups(project.id, include_done=True)
    assert len(groups_all) == 2


def test_add_and_get_relations():
    project = queries.create_project("/tmp/projectR1", "Project R1")
    t1 = queries.create_task(project.id, "Design API")
    t2 = queries.create_task(project.id, "Implement API")

    rel = queries.add_relation(t2.id, t1.id, RelationType.BLOCKED_BY)
    assert rel.source_task_id == t2.id
    assert rel.target_task_id == t1.id
    assert rel.relation_type == RelationType.BLOCKED_BY

    # From t2's perspective: blocked-by #t1
    rels_t2 = queries.get_relations(t2.id)
    assert len(rels_t2) == 1
    assert rels_t2[0]["label"] == "blocked-by"
    assert rels_t2[0]["task_id"] == t1.id

    # From t1's perspective: blocks #t2
    rels_t1 = queries.get_relations(t1.id)
    assert len(rels_t1) == 1
    assert rels_t1[0]["label"] == "blocks"
    assert rels_t1[0]["task_id"] == t2.id


def test_remove_relation():
    project = queries.create_project("/tmp/projectR2", "Project R2")
    t1 = queries.create_task(project.id, "Task A")
    t2 = queries.create_task(project.id, "Task B")

    queries.add_relation(t1.id, t2.id, RelationType.RELATED_TO)
    assert len(queries.get_relations(t1.id)) == 1

    removed = queries.remove_relation(t1.id, t2.id, RelationType.RELATED_TO)
    assert removed is True
    assert len(queries.get_relations(t1.id)) == 0

    # Removing non-existent relation returns False
    assert queries.remove_relation(t1.id, t2.id, RelationType.RELATED_TO) is False


def test_self_relation_rejected():
    project = queries.create_project("/tmp/projectR3", "Project R3")
    t1 = queries.create_task(project.id, "Task A")
    with pytest.raises(ValueError, match="itself"):
        queries.add_relation(t1.id, t1.id, RelationType.RELATED_TO)


def test_cross_project_relation_rejected():
    p1 = queries.create_project("/tmp/projectR4a", "Project R4a")
    p2 = queries.create_project("/tmp/projectR4b", "Project R4b")
    t1 = queries.create_task(p1.id, "Task in P1")
    t2 = queries.create_task(p2.id, "Task in P2")
    with pytest.raises(ValueError, match="same project"):
        queries.add_relation(t1.id, t2.id, RelationType.RELATED_TO)


def test_is_blocked():
    project = queries.create_project("/tmp/projectR5", "Project R5")
    t1 = queries.create_task(project.id, "Blocker")
    t2 = queries.create_task(project.id, "Blocked")

    queries.add_relation(t2.id, t1.id, RelationType.BLOCKED_BY)
    assert queries.is_blocked(t2.id) is True
    assert queries.is_blocked(t1.id) is False

    # Complete the blocker -> no longer blocked
    queries.complete_task(t1.id)
    assert queries.is_blocked(t2.id) is False


def test_focus_skips_blocked_tasks():
    project = queries.create_project("/tmp/projectR6", "Project R6")
    t1 = queries.create_task(project.id, "Design", priority=Priority.LOW)
    t2 = queries.create_task(project.id, "Implement", priority=Priority.HIGH)

    queries.add_relation(t2.id, t1.id, RelationType.BLOCKED_BY)

    # Focus should pick t1 (t2 is blocked despite higher priority)
    focus = queries.get_focus_task(project.id)
    assert focus is not None
    assert focus.id == t1.id

    # Complete blocker, focus should now pick t2 (higher priority)
    queries.complete_task(t1.id)
    focus = queries.get_focus_task(project.id)
    assert focus is not None
    assert focus.id == t2.id


def test_delete_task_cascades_relations():
    project = queries.create_project("/tmp/projectR7", "Project R7")
    t1 = queries.create_task(project.id, "Task A")
    t2 = queries.create_task(project.id, "Task B")
    queries.add_relation(t1.id, t2.id, RelationType.CAUSED_BY)

    queries.delete_task(t2.id)
    assert queries.get_relations(t1.id) == []


def test_caused_by_inverse_label():
    project = queries.create_project("/tmp/projectR8", "Project R8")
    t1 = queries.create_task(project.id, "Bug")
    t2 = queries.create_task(project.id, "Root cause")
    queries.add_relation(t1.id, t2.id, RelationType.CAUSED_BY)

    rels_t2 = queries.get_relations(t2.id)
    assert len(rels_t2) == 1
    assert rels_t2[0]["label"] == "caused"


def test_block_task_sets_status_and_relation():
    project = queries.create_project("/tmp/projectBlock1", "Project Block1")
    t1 = queries.create_task(project.id, "Blocker task")
    t2 = queries.create_task(project.id, "Blocked task")

    result = queries.block_task(t2.id, t1.id)
    assert result.status == Status.BLOCKED

    # Relation should exist
    rels = queries.get_relations(t2.id)
    blocked_by_rels = [r for r in rels if r["label"] == "blocked-by"]
    assert len(blocked_by_rels) == 1
    assert blocked_by_rels[0]["task_id"] == t1.id


def test_block_task_idempotent_relation():
    """Calling block_task twice doesn't duplicate the relation."""
    project = queries.create_project("/tmp/projectBlock2", "Project Block2")
    t1 = queries.create_task(project.id, "Blocker")
    t2 = queries.create_task(project.id, "Blocked")

    queries.block_task(t2.id, t1.id)
    queries.block_task(t2.id, t1.id)

    rels = queries.get_relations(t2.id)
    blocked_by_rels = [r for r in rels if r["label"] == "blocked-by"]
    assert len(blocked_by_rels) == 1


def test_block_task_invalid_blocker():
    project = queries.create_project("/tmp/projectBlock3", "Project Block3")
    t1 = queries.create_task(project.id, "Real task")

    with pytest.raises(ValueError, match="not found"):
        queries.block_task(t1.id, 99999)


def test_block_task_self_block_rejected():
    project = queries.create_project("/tmp/projectBlock4", "Project Block4")
    t1 = queries.create_task(project.id, "Task")

    with pytest.raises(ValueError, match="itself"):
        queries.block_task(t1.id, t1.id)


def test_blocked_tasks_excluded_from_focus():
    project = queries.create_project("/tmp/projectBlock5", "Project Block5")
    t1 = queries.create_task(project.id, "Prereq", priority=Priority.LOW)
    t2 = queries.create_task(project.id, "Main work", priority=Priority.HIGH)

    queries.block_task(t2.id, t1.id)

    focus = queries.get_focus_task(project.id)
    assert focus is not None
    assert focus.id == t1.id  # blocked task skipped despite higher priority


def test_stats_include_blocked_count():
    project = queries.create_project("/tmp/projectBlock6", "Project Block6")
    t1 = queries.create_task(project.id, "Blocker")
    t2 = queries.create_task(project.id, "Blocked")
    queries.block_task(t2.id, t1.id)

    stats = queries.get_project_stats(project.id)
    assert stats["blocked"] == 1
    assert stats["todo"] == 1
    assert stats["total"] == 2


# Note tests


def test_add_and_get_notes():
    project = queries.create_project("/tmp/notesN1", "Notes N1")
    task = queries.create_task(project.id, "Task with notes")

    n1 = queries.add_note(task.id, "jason", "First note")
    n2 = queries.add_note(task.id, "agent", "Second note")

    notes = queries.get_notes(task.id)
    assert len(notes) == 2
    assert notes[0].id == n1.id
    assert notes[0].author == "jason"
    assert notes[0].content == "First note"
    assert notes[1].id == n2.id
    assert notes[1].author == "agent"


def test_notes_ordered_chronologically():
    project = queries.create_project("/tmp/notesN2", "Notes N2")
    task = queries.create_task(project.id, "Chrono task")

    n1 = queries.add_note(task.id, "jason", "Alpha")
    n2 = queries.add_note(task.id, "jason", "Beta")

    notes = queries.get_notes(task.id)
    assert notes[0].created_at <= notes[1].created_at
    assert notes[0].id == n1.id
    assert notes[1].id == n2.id


def test_notes_cascade_delete():
    project = queries.create_project("/tmp/notesN3", "Notes N3")
    task = queries.create_task(project.id, "Task to delete")
    queries.add_note(task.id, "jason", "Will be deleted")

    queries.delete_task(task.id)
    assert queries.get_task(task.id) is None
    # Notes should be gone (cascade), confirmed by direct query
    from tasker.database import get_connection
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as c FROM task_notes WHERE task_id = ?", (task.id,)).fetchone()
    assert row["c"] == 0


# Review tests


def test_create_and_get_review_stub():
    project = queries.create_project("/tmp/revR1", "Rev R1")
    task = queries.create_task(project.id, "Reviewable task")

    cr = queries.create_review_stub(task.id)
    assert cr.cr_num == 1
    assert cr.task_id == task.id
    assert cr.reviewer is None


def test_cr_num_auto_increments():
    project = queries.create_project("/tmp/revR2", "Rev R2")
    task = queries.create_task(project.id, "Task")

    cr1 = queries.create_review_stub(task.id)
    cr2 = queries.create_review_stub(task.id)
    cr3 = queries.create_review_stub(task.id)

    assert cr1.cr_num == 1
    assert cr2.cr_num == 2
    assert cr3.cr_num == 3


def test_task_has_reviews():
    project = queries.create_project("/tmp/revR3", "Rev R3")
    task = queries.create_task(project.id, "Task")

    assert queries.task_has_reviews(task.id) is False
    queries.create_review_stub(task.id)
    assert queries.task_has_reviews(task.id) is True


def test_update_review_fields():
    project = queries.create_project("/tmp/revR4", "Rev R4")
    task = queries.create_task(project.id, "Task")
    queries.create_review_stub(task.id)

    updated = queries.update_review(task.id, 1, reviewer="jason", recommendations="Fix the thing")
    assert updated is not None
    assert updated.reviewer == "jason"
    assert updated.recommendations == "Fix the thing"
    assert updated.devils_advocate is None


def test_get_review():
    project = queries.create_project("/tmp/revR5", "Rev R5")
    task = queries.create_task(project.id, "Task")
    queries.create_review_stub(task.id)

    cr = queries.get_review(task.id, 1)
    assert cr is not None
    assert cr.cr_num == 1

    missing = queries.get_review(task.id, 99)
    assert missing is None


def test_delete_review():
    project = queries.create_project("/tmp/revR6", "Rev R6")
    task = queries.create_task(project.id, "Task")
    queries.create_review_stub(task.id)

    assert queries.delete_review(task.id, 1) is True
    assert queries.get_review(task.id, 1) is None
    assert queries.delete_review(task.id, 1) is False


def test_review_task_auto_stubs_once():
    project = queries.create_project("/tmp/revR7", "Rev R7")
    task = queries.create_task(project.id, "Task")

    # First call creates stub
    queries.review_task(task.id)
    assert len(queries.get_reviews(task.id)) == 1

    # Second call does not create another stub
    queries.review_task(task.id)
    assert len(queries.get_reviews(task.id)) == 1


def test_reviews_cascade_delete():
    project = queries.create_project("/tmp/revR8", "Rev R8")
    task = queries.create_task(project.id, "Task")
    queries.create_review_stub(task.id)

    queries.delete_task(task.id)
    from tasker.database import get_connection
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as c FROM task_reviews WHERE task_id = ?", (task.id,)).fetchone()
    assert row["c"] == 0


def test_check_constraints_enforced():
    project = queries.create_project("/tmp/projectG", "Project G")
    with transaction() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tasks(project_id, title, status, priority) VALUES (?, ?, ?, ?)",
                (project.id, "Invalid status", "not-a-status", 0),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tasks(project_id, title, status, priority) VALUES (?, ?, ?, ?)",
                (project.id, "Bad priority", "todo", 9),
            )
