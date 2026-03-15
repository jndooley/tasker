"""Rich formatting helpers for Tasker output."""

from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import CodeReview, HistoryEntry, Note, Priority, Project, Status, Task
from .utils import TIMESTAMP_FORMAT, format_ts

console = Console()


PRIORITY_LABELS = {
    Priority.NONE: "-",
    Priority.LOW: "low",
    Priority.MEDIUM: "med",
    Priority.HIGH: "high",
}

STATUS_COLORS = {
    Status.TODO: "cyan",
    Status.IN_PROGRESS: "yellow",
    Status.BLOCKED: "red",
    Status.REVIEW: "blue",
    Status.QA: "magenta",
    Status.DONE: "green",
}


def status_badge(status: Status) -> Text:
    """Colored label for task status."""
    color = STATUS_COLORS.get(status, "white")
    return Text(status.value, style=color)


def priority_badge(priority: Priority) -> Text:
    """Colored label for task priority."""
    label = PRIORITY_LABELS.get(priority, "-")
    color = {
        Priority.HIGH: "red",
        Priority.MEDIUM: "magenta",
        Priority.LOW: "blue",
    }.get(priority, "white")
    return Text(label, style=color)


def print_projects(projects: List[Project]):
    """Render project list table."""
    table = Table(title="Projects")
    table.add_column("ID", justify="right")
    table.add_column("Active")
    table.add_column("Name")
    table.add_column("Path")
    for p in projects:
        table.add_row(str(p.id), "*" if p.is_active else "", p.name, p.path)
    console.print(table)


def print_tasks(
    tasks: List[Task],
    group_by: bool = False,
    blocked_ids: Optional[set] = None,
):
    """Render tasks table, optionally grouped by group_id."""
    if group_by:
        _print_tasks_grouped(tasks, blocked_ids=blocked_ids)
        return
    blocked_ids = blocked_ids or set()
    table = Table(title="Tasks")
    table.add_column("ID", justify="right")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Group")
    table.add_column("Title")
    table.add_column("Updated")
    for t in tasks:
        badge = "[red]\\[B][/red] " if t.id in blocked_ids else ""
        table.add_row(
            str(t.id),
            status_badge(t.status),
            priority_badge(t.priority),
            t.group_id or "-",
            f"{badge}{t.title}",
            format_ts(t.updated_at),
        )
    console.print(table)


def _print_tasks_grouped(tasks: List[Task], blocked_ids: Optional[set] = None):
    """Render tasks grouped by group_id in separate tables."""
    from collections import OrderedDict

    blocked_ids = blocked_ids or set()
    groups: OrderedDict[Optional[str], List[Task]] = OrderedDict()
    for t in tasks:
        groups.setdefault(t.group_id, []).append(t)

    for group_id, group_tasks in groups.items():
        label = group_id if group_id else "Ungrouped"
        table = Table(title=f"Group: {label}")
        table.add_column("ID", justify="right")
        table.add_column("Status")
        table.add_column("Priority")
        table.add_column("Title")
        table.add_column("Updated")
        for t in group_tasks:
            badge = "[red]\\[B][/red] " if t.id in blocked_ids else ""
            table.add_row(
                str(t.id),
                status_badge(t.status),
                priority_badge(t.priority),
                f"{badge}{t.title}",
                format_ts(t.updated_at),
            )
        console.print(table)
        console.print()


def format_relations(relations: list) -> None:
    """Render a relations section for the show command."""
    if not relations:
        return
    console.print("[dim]Relations:[/dim]")
    for rel in relations:
        console.print(f"  [italic dim]{rel['label']}[/italic dim]: #{rel['task_id']}")


def print_task_detail(task: Task, relations: Optional[list] = None):
    """Render detailed view of a single task."""
    console.print(f"[bold]Task {task.id}[/bold]: {task.title}")
    group_str = f"  Group: {task.group_id}" if task.group_id else ""
    console.print(
        f"Status: {status_badge(task.status)}  Priority: {priority_badge(task.priority)}{group_str}"
    )
    if task.description:
        console.print(task.description)
    if task.acceptance_criteria:
        console.print("Acceptance criteria:")
        for item in task.acceptance_criteria:
            console.print(f"- {item}")
    if task.plan:
        console.print("[dim]Plan:[/dim]")
        console.print(task.plan)
    if relations:
        format_relations(relations)
    console.print(
        f"Created: {format_ts(task.created_at)} | Updated: {format_ts(task.updated_at)}"
        + (f" | Completed: {format_ts(task.completed_at)}" if task.completed_at else "")
    )


def print_focus(task: Optional[Task]):
    """Render the focus task (or none available)."""
    if not task:
        console.print("No tasks to focus on. ✅")
        return
    console.print("[bold green]Focus[/bold green]:")
    console.print(
        f"{status_badge(task.status)} {priority_badge(task.priority)} {task.title} (#{task.id})"
    )
    if task.description:
        console.print(task.description)
    if task.acceptance_criteria:
        console.print("Acceptance criteria:")
        for item in task.acceptance_criteria:
            console.print(f"- {item}")


def print_groups(groups: list):
    """Render groups table."""
    table = Table(title="Groups")
    table.add_column("Group ID")
    table.add_column("Tasks", justify="right")
    for g in groups:
        table.add_row(g["group_id"], str(g["task_count"]))
    console.print(table)


def format_notes(notes: List[Note]) -> None:
    """Render notes log section."""
    console.print("[bold]Notes[/bold]")
    console.print("─" * 41)
    if not notes:
        console.print("[dim](no notes)[/dim]")
        return
    for note in notes:
        ts = note.created_at.strftime(TIMESTAMP_FORMAT)
        console.print(f"[dim][{ts}][/dim]  {note.author}")
        console.print(note.content)
        console.print()


def format_reviews(reviews: List[CodeReview]) -> None:
    """Render code reviews section."""
    console.print("[bold]Code Reviews[/bold]")
    console.print("─" * 41)
    if not reviews:
        console.print("[dim](no reviews)[/dim]")
        return
    for cr in reviews:
        ts = cr.created_at.strftime(TIMESTAMP_FORMAT)
        reviewer_str = f"  Reviewer: {cr.reviewer}" if cr.reviewer else ""
        console.print(f"[bold]CR-{cr.cr_num}[/bold]  {ts}{reviewer_str}")
        console.print()
        if cr.recommendations:
            console.print("  [underline]Recommendations[/underline]")
            for line in cr.recommendations.splitlines():
                console.print(f"  {line}")
            console.print()
        if cr.devils_advocate:
            console.print("  [underline]Devil's Advocate[/underline]")
            for line in cr.devils_advocate.splitlines():
                console.print(f"  {line}")
            console.print()
        if cr.false_positives:
            console.print("  [underline]False Positives[/underline]")
            for line in cr.false_positives.splitlines():
                console.print(f"  {line}")
            console.print()


def format_history(history: List[HistoryEntry]) -> None:
    """Render history log section."""
    console.print("[bold]History[/bold]")
    console.print("─" * 41)
    if not history:
        console.print("[dim](no history)[/dim]")
        return
    for entry in history:
        ts = entry.changed_at.strftime(TIMESTAMP_FORMAT)
        old = entry.old_value or "(none)"
        new = entry.new_value or "(none)"
        console.print(
            f"[dim][{ts}][/dim]  {entry.agent}  {entry.field}: {old} → {new}"
        )


def print_stats(stats: dict):
    """Render simple stats table."""
    table = Table(title="Stats")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key in ["total", "todo", "in_progress", "review", "qa", "blocked", "done"]:
        table.add_row(key, str(stats.get(key, 0)))
    console.print(table)


def export_tasks_markdown(
    project: Project,
    tasks: List[Task],
    include_notes: bool = False,
    include_history: bool = False,
) -> str:
    """Render tasks as a Markdown document grouped by status."""
    from .queries import get_notes, get_reviews, get_task_history

    lines = [f"# Tasks for {project.name}", ""]
    by_status: Dict[Status, List[Task]] = {
        Status.TODO: [],
        Status.IN_PROGRESS: [],
        Status.REVIEW: [],
        Status.QA: [],
        Status.BLOCKED: [],
        Status.DONE: [],
    }
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
                        ts = n.created_at.strftime(TIMESTAMP_FORMAT)
                        lines.append(f"  - [{ts}] {n.author}: {n.content}")
                reviews = get_reviews(t.id)
                if reviews:
                    lines.append("  **Code Reviews:**")
                    for cr in reviews:
                        ts = cr.created_at.strftime(TIMESTAMP_FORMAT)
                        reviewer_str = f" — Reviewer: {cr.reviewer}" if cr.reviewer else ""
                        lines.append(f"  - CR-{cr.cr_num} ({ts}{reviewer_str})")
                        if cr.recommendations:
                            lines.append(f"    - Recommendations: {cr.recommendations}")
                        if cr.devils_advocate:
                            lines.append(f"    - Devil's Advocate: {cr.devils_advocate}")
                        if cr.false_positives:
                            lines.append(f"    - False Positives: {cr.false_positives}")
            if include_history:
                history = get_task_history(t.id)
                if history:
                    lines.append("  **History:**")
                    for h in history:
                        ts = h.changed_at.strftime(TIMESTAMP_FORMAT)
                        old = h.old_value or "(none)"
                        new = h.new_value or "(none)"
                        lines.append(f"  - [{ts}] {h.agent}  {h.field}: {old} → {new}")
        lines.append("")
    return "\n".join(lines)
