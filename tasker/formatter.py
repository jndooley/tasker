"""Rich formatting helpers for Tasker output."""

from typing import List, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import CodeReview, Note, Priority, Project, Status, Task
from .utils import format_ts

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
        ts = note.created_at.strftime("%Y-%m-%d %H:%M")
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
        ts = cr.created_at.strftime("%Y-%m-%d %H:%M")
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


def print_stats(stats: dict):
    """Render simple stats table."""
    table = Table(title="Stats")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key in ["total", "todo", "in_progress", "review", "qa", "blocked", "done"]:
        table.add_row(key, str(stats.get(key, 0)))
    console.print(table)
