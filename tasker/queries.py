"""Data access layer: CRUD operations, ordering, stats, and exports."""

from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional, Sequence

from .database import get_connection, transaction
from .models import INVERSE_LABELS, CodeReview, Note, Priority, Project, RelationType, Status, Task, TaskRelation
from .utils import days_ago, now_iso

ORDER_STEP = 1000


# Project operations


def create_project(path: str, name: str, activate: bool = True) -> Project:
    """Create a project if missing and optionally mark it active."""
    with transaction() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO projects(path, name, is_active) VALUES (?, ?, 0)",
            (path, name),
        )
        if cur.rowcount == 0:
            # Already exists, just update name if changed
            conn.execute(
                "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (name, path),
            )
        project = get_project_by_path(path)
        if project is None:
            raise RuntimeError("Failed to create project")
        if activate:
            set_active_project(path)
            project = get_project_by_path(path)
        return project  # type: ignore


def get_project(project_id: int) -> Optional[Project]:
    """Fetch a project by id."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return Project.from_row(row) if row else None


def get_project_by_path(path: str) -> Optional[Project]:
    """Fetch a project by filesystem path."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE path = ?", (path,)).fetchone()
    return Project.from_row(row) if row else None


def list_projects() -> List[Project]:
    """List all projects sorted by creation date."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
    return [Project.from_row(r) for r in rows]


def set_active_project(path: str) -> Optional[Project]:
    """Mark the given project as active (only one active)."""
    project = get_project_by_path(path)
    if project is None:
        return None
    with transaction() as conn:
        conn.execute("UPDATE projects SET is_active = 0")
        conn.execute(
            "UPDATE projects SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
            (path,),
        )
        return get_project_by_path(path)


def get_active_project() -> Optional[Project]:
    """Return the currently active project if any."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM projects WHERE is_active = 1 LIMIT 1").fetchone()
    return Project.from_row(row) if row else None


# Task operations


def _serialize_acceptance_criteria(
    acceptance_criteria: Optional[Sequence[str]],
) -> Optional[str]:
    if acceptance_criteria is None:
        return None
    return json.dumps([str(item) for item in acceptance_criteria])


def _next_order_index(conn: sqlite3.Connection, project_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(order_index), 0) as max_idx FROM tasks WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    max_idx = row["max_idx"] if row else 0
    return int(max_idx) + ORDER_STEP


def create_task(
    project_id: int,
    title: str,
    description: Optional[str] = None,
    acceptance_criteria: Optional[Sequence[str]] = None,
    priority: Priority = Priority.NONE,
    status: Status = Status.TODO,
    order_index: Optional[int] = None,
    group_id: Optional[str] = None,
    plan: Optional[str] = None,
) -> Task:
    """Insert a task with optional status/priority, ordering, and group."""
    with transaction() as conn:
        idx = (
            order_index
            if order_index is not None
            else _next_order_index(conn, project_id)
        )
        completed_at = now_iso() if status == Status.DONE else None
        cur = conn.execute(
            """
            INSERT INTO tasks(
                project_id,
                title,
                description,
                acceptance_criteria,
                plan,
                status,
                priority,
                order_index,
                group_id,
                completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                title,
                description,
                _serialize_acceptance_criteria(acceptance_criteria),
                plan,
                status.value,
                int(priority),
                idx,
                group_id,
                completed_at,
            ),
        )
        return get_task(cur.lastrowid)  # type: ignore


def get_task(task_id: int) -> Optional[Task]:
    """Fetch a task by id."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return Task.from_row(row) if row else None


def list_tasks(
    project_id: int,
    status: Optional[Sequence[Status]] = None,
    priority: Optional[Priority] = None,
    include_done: bool = True,
    group_id: Optional[str] = None,
) -> List[Task]:
    """List tasks for a project with optional filters and ordering."""
    conn = get_connection()
    conditions = ["project_id = ?"]
    params: List = [project_id]

    if status:
        placeholders = ",".join(["?" for _ in status])
        conditions.append(f"status IN ({placeholders})")
        params.extend([s.value for s in status])
    elif not include_done:
        conditions.append("status != 'done'")

    if priority is not None:
        conditions.append("priority = ?")
        params.append(int(priority))

    if group_id is not None:
        conditions.append("group_id = ?")
        params.append(group_id)

    where_clause = " AND ".join(conditions)
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {where_clause} ORDER BY group_id ASC, order_index ASC",
        params,
    ).fetchall()
    return [Task.from_row(r) for r in rows]


_UNSET = object()


def update_task(
    task_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    acceptance_criteria: Optional[Sequence[str]] = None,
    priority: Optional[Priority] = None,
    status: Optional[Status] = None,
    group_id: object = _UNSET,
    plan: Optional[str] = None,
) -> Optional[Task]:
    """Update mutable task fields; returns updated task or None."""
    sets = []
    params: List = []
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    if description is not None:
        sets.append("description = ?")
        params.append(description)
    if acceptance_criteria is not None:
        sets.append("acceptance_criteria = ?")
        params.append(_serialize_acceptance_criteria(acceptance_criteria))
    if priority is not None:
        sets.append("priority = ?")
        params.append(int(priority))
    if status is not None:
        sets.append("status = ?")
        params.append(status.value)
        if status == Status.DONE:
            sets.append("completed_at = ?")
            params.append(now_iso())
        else:
            sets.append("completed_at = NULL")
    if group_id is not _UNSET:
        sets.append("group_id = ?")
        params.append(group_id)
    if plan is not None:
        sets.append("plan = ?")
        params.append(plan)
    if not sets:
        return get_task(task_id)

    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(task_id)

    with transaction() as conn:
        conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        return get_task(task_id)


def delete_task(task_id: int) -> None:
    """Delete a task by id."""
    with transaction() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def reorder_task(task_id: int, position: int) -> Optional[Task]:
    """Reorder a task to a 1-based position within its project."""
    task = get_task(task_id)
    if not task:
        return None

    with transaction() as conn:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE project_id = ? ORDER BY order_index ASC",
            (task.project_id,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if task_id not in ids:
            return None

        ids.remove(task_id)
        position = max(1, min(position, len(ids) + 1))
        ids.insert(position - 1, task_id)

        new_index = ORDER_STEP
        for tid in ids:
            conn.execute(
                "UPDATE tasks SET order_index = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_index, tid),
            )
            new_index += ORDER_STEP
        return get_task(task_id)


def start_task(task_id: int) -> Optional[Task]:
    """Set task status to in-progress."""
    return update_task(task_id, status=Status.IN_PROGRESS)


def complete_task(task_id: int) -> Optional[Task]:
    """Set task status to done and mark completion time."""
    return update_task(task_id, status=Status.DONE)


def review_task(task_id: int) -> Optional[Task]:
    """Set task status to review and auto-create CR-1 stub on first call."""
    updated = update_task(task_id, status=Status.REVIEW)
    if updated and not task_has_reviews(task_id):
        create_review_stub(task_id)
    return updated


def qa_task(task_id: int) -> Optional[Task]:
    """Set task status to qa."""
    return update_task(task_id, status=Status.QA)


def block_task(task_id: int, blocker_id: int) -> Task:
    """Set task to blocked status and create a blocked-by relation to the blocker."""
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found.")
    blocker = get_task(blocker_id)
    if blocker is None:
        raise ValueError(f"Blocker task {blocker_id} not found.")
    if task.project_id != blocker.project_id:
        raise ValueError("Tasks must belong to the same project.")
    if task_id == blocker_id:
        raise ValueError("A task cannot block itself.")

    updated = update_task(task_id, status=Status.BLOCKED)

    # Add blocked-by relation if not already present
    conn = get_connection()
    existing = conn.execute(
        "SELECT 1 FROM task_relations WHERE source_task_id = ? AND target_task_id = ? AND relation_type = ?",
        (task_id, blocker_id, RelationType.BLOCKED_BY.value),
    ).fetchone()
    if not existing:
        add_relation(task_id, blocker_id, RelationType.BLOCKED_BY)

    return updated  # type: ignore


def get_focus_task(project_id: int) -> Optional[Task]:
    """Return the next task to focus on, skipping blocked tasks."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM tasks t
        WHERE t.project_id = ? AND t.status IN ('in-progress', 'review', 'qa', 'todo')
          AND NOT EXISTS (
            SELECT 1 FROM task_relations tr
            JOIN tasks blocker ON blocker.id = tr.target_task_id
            WHERE tr.source_task_id = t.id
              AND tr.relation_type = 'blocked-by'
              AND blocker.status != 'done'
          )
        ORDER BY CASE
            WHEN t.status = 'in-progress' THEN 0
            WHEN t.status = 'review' THEN 1
            WHEN t.status = 'qa' THEN 2
            ELSE 3
        END, t.priority DESC, t.order_index ASC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    return Task.from_row(row) if row else None


def get_project_stats(project_id: int) -> dict:
    """Return basic counts of tasks by status for a project."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END) as todo,
            SUM(CASE WHEN status = 'in-progress' THEN 1 ELSE 0 END) as in_progress,
            SUM(CASE WHEN status = 'review' THEN 1 ELSE 0 END) as review,
            SUM(CASE WHEN status = 'qa' THEN 1 ELSE 0 END) as qa,
            SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked,
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done
        FROM tasks WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    return {k: row[k] for k in row.keys()} if row else {}


def clean_completed(project_id: int, older_than_days: Optional[int] = None) -> int:
    """Delete completed tasks; optionally only those older than N days."""
    with transaction() as conn:
        if older_than_days is None:
            cur = conn.execute(
                "DELETE FROM tasks WHERE project_id = ? AND status = 'done'",
                (project_id,),
            )
        else:
            cutoff = days_ago(older_than_days).isoformat(timespec="seconds")
            cur = conn.execute(
                "DELETE FROM tasks WHERE project_id = ? AND status = 'done' AND completed_at < ?",
                (project_id, cutoff),
            )
        return cur.rowcount if cur else 0


def list_groups(project_id: int, include_done: bool = False) -> List[dict]:
    """List distinct groups for a project with task counts."""
    conn = get_connection()
    done_filter = "" if include_done else "AND status != 'done'"
    rows = conn.execute(
        f"""
        SELECT group_id, COUNT(*) as task_count
        FROM tasks
        WHERE project_id = ? AND group_id IS NOT NULL {done_filter}
        GROUP BY group_id
        ORDER BY group_id ASC
        """,
        (project_id,),
    ).fetchall()
    return [{"group_id": r["group_id"], "task_count": r["task_count"]} for r in rows]


def export_tasks(project_id: int) -> List[dict]:
    """Export all tasks for a project to dictionaries."""
    tasks = list_tasks(project_id, include_done=True)
    return [t.to_dict() for t in tasks]


# Relation operations


def add_relation(
    source_task_id: int, target_task_id: int, relation_type: RelationType
) -> TaskRelation:
    """Add a relation between two tasks. Both must exist in the same project."""
    if source_task_id == target_task_id:
        raise ValueError("A task cannot have a relation to itself.")
    source = get_task(source_task_id)
    target = get_task(target_task_id)
    if source is None:
        raise ValueError(f"Task {source_task_id} not found.")
    if target is None:
        raise ValueError(f"Task {target_task_id} not found.")
    if source.project_id != target.project_id:
        raise ValueError("Tasks must belong to the same project.")
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO task_relations(source_task_id, target_task_id, relation_type) VALUES (?, ?, ?)",
            (source_task_id, target_task_id, relation_type.value),
        )
        row = conn.execute(
            "SELECT * FROM task_relations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return TaskRelation.from_row(row)


def remove_relation(
    source_task_id: int, target_task_id: int, relation_type: RelationType
) -> bool:
    """Remove a specific relation. Returns True if a row was deleted."""
    with transaction() as conn:
        cur = conn.execute(
            "DELETE FROM task_relations WHERE source_task_id = ? AND target_task_id = ? AND relation_type = ?",
            (source_task_id, target_task_id, relation_type.value),
        )
        return cur.rowcount > 0


def get_relations(task_id: int) -> List[dict]:
    """Return all relations involving task_id, with display labels.

    Each dict has: relation_id, task_id (the other task), label (e.g. 'blocked-by' or 'blocks').
    """
    conn = get_connection()
    results = []

    # Relations where this task is the source (label = relation_type value)
    rows = conn.execute(
        "SELECT * FROM task_relations WHERE source_task_id = ?", (task_id,)
    ).fetchall()
    for row in rows:
        rt = RelationType.from_value(row["relation_type"])
        results.append({
            "relation_id": row["id"],
            "task_id": row["target_task_id"],
            "label": rt.value,
        })

    # Relations where this task is the target (label = inverse)
    rows = conn.execute(
        "SELECT * FROM task_relations WHERE target_task_id = ?", (task_id,)
    ).fetchall()
    for row in rows:
        rt = RelationType.from_value(row["relation_type"])
        results.append({
            "relation_id": row["id"],
            "task_id": row["source_task_id"],
            "label": INVERSE_LABELS[rt],
        })

    return results


def is_blocked(task_id: int) -> bool:
    """Return True if the task has a blocked-by relation pointing to an incomplete task."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT 1 FROM task_relations tr
        JOIN tasks t ON t.id = tr.target_task_id
        WHERE tr.source_task_id = ?
          AND tr.relation_type = 'blocked-by'
          AND t.status != 'done'
        LIMIT 1
        """,
        (task_id,),
    ).fetchone()
    return row is not None


# Note operations


def add_note(task_id: int, author: str, content: str) -> Note:
    """Append an immutable note to a task."""
    with transaction() as conn:
        cur = conn.execute(
            "INSERT INTO task_notes(task_id, author, content) VALUES (?, ?, ?)",
            (task_id, author, content),
        )
        row = conn.execute(
            "SELECT * FROM task_notes WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return Note.from_row(row)


def get_notes(task_id: int) -> List[Note]:
    """Return all notes for a task, ordered by creation time."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task_notes WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    return [Note.from_row(r) for r in rows]


# Review operations


def task_has_reviews(task_id: int) -> bool:
    """Return True if the task has at least one code review."""
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM task_reviews WHERE task_id = ? LIMIT 1", (task_id,)
    ).fetchone()
    return row is not None


def create_review_stub(task_id: int) -> CodeReview:
    """Create a new CR stub with auto-incremented cr_num (within a transaction)."""
    with transaction() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(cr_num), 0) + 1 AS next_num FROM task_reviews WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        cr_num = row["next_num"]
        cur = conn.execute(
            "INSERT INTO task_reviews(task_id, cr_num) VALUES (?, ?)",
            (task_id, cr_num),
        )
        row = conn.execute(
            "SELECT * FROM task_reviews WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return CodeReview.from_row(row)


def get_reviews(task_id: int) -> List[CodeReview]:
    """Return all code reviews for a task ordered by cr_num."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM task_reviews WHERE task_id = ? ORDER BY cr_num ASC",
        (task_id,),
    ).fetchall()
    return [CodeReview.from_row(r) for r in rows]


def get_review(task_id: int, cr_num: int) -> Optional[CodeReview]:
    """Fetch a single code review by task_id and cr_num."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM task_reviews WHERE task_id = ? AND cr_num = ?",
        (task_id, cr_num),
    ).fetchone()
    return CodeReview.from_row(row) if row else None


def update_review(task_id: int, cr_num: int, **fields) -> Optional[CodeReview]:
    """Update one or more fields of a code review. Returns updated CR or None."""
    allowed = {"reviewer", "recommendations", "devils_advocate", "false_positives"}
    sets = []
    params: List = []
    for key, value in fields.items():
        if key in allowed and value is not None:
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return get_review(task_id, cr_num)
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.extend([task_id, cr_num])
    with transaction() as conn:
        conn.execute(
            f"UPDATE task_reviews SET {', '.join(sets)} WHERE task_id = ? AND cr_num = ?",
            params,
        )
    return get_review(task_id, cr_num)


def delete_review(task_id: int, cr_num: int) -> bool:
    """Delete a code review. Returns True if a row was deleted."""
    with transaction() as conn:
        cur = conn.execute(
            "DELETE FROM task_reviews WHERE task_id = ? AND cr_num = ?",
            (task_id, cr_num),
        )
        return cur.rowcount > 0


def export_tasks_markdown(project: Project, tasks: List[Task], include_notes: bool = False) -> str:
    """Render tasks as a Markdown document grouped by status."""
    lines = [f"# Tasks for {project.name}", ""]
    by_status: Dict[Status, List[Task]] = {Status.TODO: [], Status.IN_PROGRESS: [], Status.REVIEW: [], Status.QA: [], Status.BLOCKED: [], Status.DONE: []}
    for t in tasks:
        by_status[t.status].append(t)
    for status, title in [
        (Status.IN_PROGRESS, "In Progress"),
        (Status.REVIEW, "Review"),
        (Status.QA, "QA"),
        (Status.BLOCKED, "Blocked"),
        (Status.TODO, "Todo"),
        (Status.DONE, "Done"),
    ]:
        lines.append(f"## {title}")
        if not by_status[status]:
            lines.append("(none)\n")
            continue
        for t in by_status[status]:
            pr = ["", "(low)", "(medium)", "(high)"][int(t.priority)]
            grp = f" [{t.group_id}]" if t.group_id else ""
            lines.append(
                f"- [ {'x' if status == Status.DONE else ' '} ] {t.title} {pr}{grp}\n  {t.description or ''}"
            )
            if include_notes:
                notes = get_notes(t.id)
                if notes:
                    lines.append("  **Notes:**")
                    for n in notes:
                        ts = n.created_at.strftime("%Y-%m-%d %H:%M")
                        lines.append(f"  - [{ts}] {n.author}: {n.content}")
                reviews = get_reviews(t.id)
                if reviews:
                    lines.append("  **Code Reviews:**")
                    for cr in reviews:
                        ts = cr.created_at.strftime("%Y-%m-%d %H:%M")
                        reviewer_str = f" — Reviewer: {cr.reviewer}" if cr.reviewer else ""
                        lines.append(f"  - CR-{cr.cr_num} ({ts}{reviewer_str})")
                        if cr.recommendations:
                            lines.append(f"    - Recommendations: {cr.recommendations}")
                        if cr.devils_advocate:
                            lines.append(f"    - Devil's Advocate: {cr.devils_advocate}")
                        if cr.false_positives:
                            lines.append(f"    - False Positives: {cr.false_positives}")
        lines.append("")
    return "\n".join(lines)
