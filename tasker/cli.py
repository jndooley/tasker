"""Click CLI definition for Tasker."""

import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__
from .formatter import (
    console,
    export_tasks_markdown,
    format_history,
    format_notes,
    format_reviews,
    print_focus,
    print_groups,
    print_projects,
    print_stats,
    print_task_detail,
    print_tasks,
)
from .models import RelationType
from .models import Priority, Status
from .queries import (
    add_note,
    add_relation,
    block_task,
    clean_completed,
    clear_task_order,
    create_project,
    create_review_stub,
    create_task,
    delete_review,
    delete_task,
    get_active_project,
    get_focus_task,
    get_notes,
    get_project_by_path,
    get_project_stats,
    get_relations,
    get_review,
    get_reviews,
    get_task,
    get_task_history,
    get_task_order,
    is_blocked,
    list_groups,
    list_projects,
    list_tasks,
    remove_relation,
    reorder_task,
    review_task,
    set_active_project,
    set_task_order,
    task_has_reviews,
    update_review,
    update_task,
)
from .utils import resolve_project_path


PRIORITY_CHOICES = ["none", "low", "med", "medium", "high"]
STATUS_CHOICES = [s.value for s in Status]


@click.group()
@click.version_option(__version__)
def cli():
    """Tasker - lightweight task tracker for agents."""


def _parse_priority(priority: Optional[str]) -> Optional[Priority]:
    if priority is None:
        return None
    mapping = {
        "none": Priority.NONE,
        "low": Priority.LOW,
        "med": Priority.MEDIUM,
        "medium": Priority.MEDIUM,
        "high": Priority.HIGH,
    }
    if priority not in mapping:
        raise click.BadParameter("Priority must be one of: none, low, medium, high")
    return mapping[priority]


def _parse_status(status: Optional[str]) -> Optional[Status]:
    if status is None:
        return None
    try:
        return Status(status)
    except ValueError as exc:  # noqa: BLE001
        raise click.BadParameter("Status must be todo, in-progress, blocked, review, qa, or done") from exc


def _require_project():
    project = get_active_project()
    if not project:
        raise click.ClickException("No active project. Run `tasker init` first.")
    return project


def _require_task(task_id: int):
    """Fetch task in the active project, raising ClickException if not found."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        raise click.ClickException(f"Task {task_id} not found in active project.")
    return task


def _get_agent(agent: Optional[str]) -> str:
    """Resolve agent name: explicit arg → $TASKER_AGENT env → 'unknown'."""
    if agent:
        return agent
    return os.environ.get("TASKER_AGENT", "unknown")


def _parse_acceptance_criteria(
    acceptance_criteria: Tuple[str, ...],
    acceptance_criteria_json: Optional[str],
) -> Optional[list[str]]:
    if acceptance_criteria and acceptance_criteria_json:
        raise click.BadParameter(
            "Use either --acceptance-criteria (repeatable) or --acceptance-criteria-json, not both."
        )
    if acceptance_criteria_json is not None:
        try:
            parsed = json.loads(acceptance_criteria_json)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                "--acceptance-criteria-json must be a valid JSON array of strings."
            ) from exc
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise click.BadParameter(
                "--acceptance-criteria-json must be a JSON array of strings."
            )
        return parsed
    if acceptance_criteria:
        return list(acceptance_criteria)
    return None


# Project commands


@cli.command()
@click.argument("path", required=False)
def init(path: Optional[str]):
    """Initialize a project at PATH (defaults to current directory)."""
    target = resolve_project_path(path)
    name = target.name
    project = create_project(str(target), name, activate=True)
    console.print(f"Initialized project '{project.name}' at {project.path}")


@cli.command()
@click.argument("path", required=False)
def switch(path: Optional[str]):
    """Switch active project."""
    target = resolve_project_path(path)
    project = get_project_by_path(str(target))
    if project is None:
        console.print("Project not found; creating new and activating it.")
        project = create_project(str(target), target.name, activate=True)
    else:
        project = set_active_project(str(target))
    if project is None:
        raise click.ClickException("Failed to activate project.")
    console.print(f"Active project: {project.name} ({project.path})")


@cli.command()
def project():
    """Show active project."""
    project = get_active_project()
    if not project:
        console.print("No active project. Run `tasker init`.")
    else:
        console.print(f"Active project: {project.name} ({project.path})")


@cli.command()
def projects():
    """List all projects."""
    projs = list_projects()
    if not projs:
        console.print("No projects found. Run `tasker init`.")
        return
    print_projects(projs)


# Task commands


@cli.command()
@click.argument("title")
@click.option("--description", "-d", help="Task description")
@click.option(
    "--acceptance-criteria",
    "acceptance_criteria",
    multiple=True,
    help="Acceptance criteria item (repeatable)",
)
@click.option(
    "--acceptance-criteria-json",
    help="JSON array of acceptance criteria strings",
)
@click.option("--priority", "-p", type=click.Choice(PRIORITY_CHOICES), default="none")
@click.option(
    "--status", "-s", type=click.Choice(STATUS_CHOICES), default=Status.TODO.value
)
@click.option("--group", "-g", "group_id", help="Group ID to assign this task to")
@click.option("--plan", help="Implementation plan (use '-' to read from stdin)")
def add(
    title: str,
    description: Optional[str],
    acceptance_criteria: Tuple[str, ...],
    acceptance_criteria_json: Optional[str],
    priority: str,
    status: str,
    group_id: Optional[str],
    plan: Optional[str],
):
    """Add a task to the active project."""
    if not title.strip():
        raise click.BadParameter("Title cannot be blank.", param_hint="'TITLE'")
    project = _require_project()
    acceptance_criteria_value = _parse_acceptance_criteria(
        acceptance_criteria, acceptance_criteria_json
    )
    if plan == "-":
        plan = sys.stdin.read()
    task = create_task(
        project_id=project.id,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria_value,
        priority=_parse_priority(priority) or Priority.NONE,
        status=_parse_status(status) or Status.TODO,
        group_id=group_id,
        plan=plan,
    )
    console.print(f"Created task #{task.id}: {task.title}")


@cli.command(name="list")
@click.option(
    "--status", "-s", type=click.Choice(STATUS_CHOICES), help="Filter by status"
)
@click.option(
    "--priority", "-p", type=click.Choice(PRIORITY_CHOICES), help="Filter by priority"
)
@click.option("--all", "-a", "show_all", is_flag=True, help="Include completed tasks")
@click.option("--group", "-g", "group_id", help="Filter by group ID")
@click.option(
    "--group-by", "group_by", is_flag=True, help="Display tasks grouped by group ID"
)
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def list_cmd(
    status: Optional[str],
    priority: Optional[str],
    show_all: bool,
    group_id: Optional[str],
    group_by: bool,
    json_output: bool,
):
    """List tasks."""
    project = _require_project()
    status_val = _parse_status(status) if status else None
    if status and status_val is None:
        raise click.BadParameter("Invalid status filter")
    status_filter = [status_val] if status_val else None

    priority_filter = _parse_priority(priority) if priority else None
    tasks = list_tasks(
        project.id,
        status=status_filter,
        priority=priority_filter,
        include_done=show_all,
        group_id=group_id,
    )
    if json_output:
        click.echo(json.dumps([t.to_dict() for t in tasks], indent=2))
    else:
        blocked_ids = {t.id for t in tasks if is_blocked(t.id)}
        print_tasks(tasks, group_by=group_by, blocked_ids=blocked_ids)


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--notes", "show_notes", is_flag=True, help="Also show notes and code reviews")
@click.option("--history", "show_history", is_flag=True, help="Show history log")
def show(task_id: int, show_notes: bool, show_history: bool):
    """Show task details."""
    task = _require_task(task_id)
    relations = get_relations(task_id)
    print_task_detail(task, relations=relations)
    if show_notes:
        console.print()
        format_notes(get_notes(task_id))
        console.print()
        format_reviews(get_reviews(task_id))
    if show_history:
        console.print()
        format_history(get_task_history(task_id))


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--title", "-t", help="New title")
@click.option("--description", "-d", help="New description")
@click.option(
    "--acceptance-criteria",
    "acceptance_criteria",
    multiple=True,
    help="Acceptance criteria item (repeatable)",
)
@click.option(
    "--acceptance-criteria-json",
    help="JSON array of acceptance criteria strings",
)
@click.option("--priority", "-p", type=click.Choice(PRIORITY_CHOICES))
@click.option("--status", "-s", type=click.Choice(STATUS_CHOICES))
@click.option("--group", "-g", "group_id", help="Group ID (use '' to clear)")
@click.option("--plan", help="Implementation plan (use '-' to read from stdin)")
@click.option("--agent", default=None, help="Agent or user performing this action")
def update(
    task_id: int,
    title: Optional[str],
    description: Optional[str],
    acceptance_criteria: Tuple[str, ...],
    acceptance_criteria_json: Optional[str],
    priority: Optional[str],
    status: Optional[str],
    group_id: Optional[str],
    plan: Optional[str],
    agent: Optional[str],
):
    """Update a task."""
    task = _require_task(task_id)
    acceptance_criteria_value = _parse_acceptance_criteria(
        acceptance_criteria, acceptance_criteria_json
    )
    if plan == "-":
        plan = sys.stdin.read()
    clear_group = False
    new_group_id = None
    if group_id is not None:
        if group_id == "":
            clear_group = True
        else:
            new_group_id = group_id
    status_agent = _get_agent(agent) if status else None
    updated = update_task(
        task_id,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria_value,
        priority=_parse_priority(priority),
        status=_parse_status(status),
        group_id=new_group_id,
        clear_group=clear_group,
        plan=plan,
        agent=status_agent,
    )
    if updated:
        console.print(f"Updated task #{updated.id}")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--agent", default=None, help="Agent or user performing this action")
def start(task_id: int, agent: Optional[str]):
    """Mark a task as in-progress."""
    _require_task(task_id)
    updated = update_task(task_id, status=Status.IN_PROGRESS, agent=_get_agent(agent))
    if updated:
        console.print(f"Task #{task_id} started")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--agent", default=None, help="Agent or user performing this action")
@click.option("--no-stub", "no_stub", is_flag=True, help="Do not auto-create a CR stub")
def review(task_id: int, agent: Optional[str], no_stub: bool):
    """Mark a task as in review."""
    _require_task(task_id)
    had_reviews = task_has_reviews(task_id)
    updated = review_task(task_id, agent=_get_agent(agent), create_stub=not no_stub)
    if updated:
        console.print(f"Task #{task_id} in review")
        if not no_stub and not had_reviews:
            console.print(f"Created CR-1. Use 'tasker cr update {task_id} 1' to fill in details.")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--agent", default=None, help="Agent or user performing this action")
def qa(task_id: int, agent: Optional[str]):
    """Mark a task as in QA."""
    _require_task(task_id)
    updated = update_task(task_id, status=Status.QA, agent=_get_agent(agent))
    if updated:
        console.print(f"Task #{task_id} in QA")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--agent", default=None, help="Agent or user performing this action")
def done(task_id: int, agent: Optional[str]):
    """Mark a task as done."""
    _require_task(task_id)
    updated = update_task(task_id, status=Status.DONE, agent=_get_agent(agent))
    if updated:
        console.print(f"Task #{task_id} completed")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("blocker_id", type=click.IntRange(min=1))
@click.option("--agent", default=None, help="Agent or user performing this action")
def block(task_id: int, blocker_id: int, agent: Optional[str]):
    """Mark a task as blocked by another task."""
    _require_task(task_id)
    _require_task(blocker_id)
    try:
        block_task(task_id, blocker_id, agent=_get_agent(agent))
        console.print(f"Task #{task_id} blocked by #{blocker_id}")
    except ValueError as exc:
        raise click.ClickException(str(exc))


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(task_id: int, yes: bool):
    """Delete a task."""
    task = _require_task(task_id)
    if not yes:
        notes = get_notes(task_id)
        reviews = get_reviews(task_id)
        history = get_task_history(task_id)
        relations = get_relations(task_id)
        cascades = []
        if notes:
            cascades.append(f"{len(notes)} note(s)")
        if reviews:
            cascades.append(f"{len(reviews)} code review(s)")
        if history:
            cascades.append(f"{len(history)} history entry/entries")
        if relations:
            cascades.append(f"{len(relations)} relation(s)")
        prompt = f"Delete task #{task_id} '{task.title}'?"
        if cascades:
            prompt += f" Also deletes: {', '.join(cascades)}."
        if not click.confirm(prompt):
            return
    delete_task(task_id)
    console.print(f"Deleted task #{task_id}")


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("position", type=click.IntRange(min=1))
def reorder(task_id: int, position: int):
    """Move a task to POSITION (1-based)."""
    _require_task(task_id)
    updated = reorder_task(task_id, position)
    if updated:
        console.print(f"Task #{task_id} moved to position {position}")


@cli.command()
@click.option("--all", "-a", "show_all", is_flag=True, help="Include groups with only done tasks")
def groups(show_all: bool):
    """List task groups."""
    project = _require_project()
    grps = list_groups(project.id, include_done=show_all)
    if not grps:
        console.print("No groups found.")
        return
    print_groups(grps)


RELATION_TYPE_CHOICES = [rt.value for rt in RelationType]


@cli.command()
@click.argument("source_id", type=click.IntRange(min=1))
@click.argument("target_id", type=click.IntRange(min=1))
@click.option(
    "--type", "-t", "relation_type",
    type=click.Choice(RELATION_TYPE_CHOICES),
    default=RelationType.RELATED_TO.value,
    help="Relation type (default: related-to)",
)
def link(source_id: int, target_id: int, relation_type: str):
    """Link two tasks with a relation."""
    _require_task(source_id)
    _require_task(target_id)
    try:
        rt = RelationType.from_value(relation_type)
        rel = add_relation(source_id, target_id, rt)
        console.print(f"Linked #{source_id} --{rel.relation_type.value}--> #{target_id}")
    except Exception as exc:
        raise click.ClickException(str(exc))


@cli.command()
@click.argument("source_id", type=click.IntRange(min=1))
@click.argument("target_id", type=click.IntRange(min=1))
@click.option(
    "--type", "-t", "relation_type",
    type=click.Choice(RELATION_TYPE_CHOICES),
    default=RelationType.RELATED_TO.value,
    help="Relation type (default: related-to)",
)
def unlink(source_id: int, target_id: int, relation_type: str):
    """Remove a relation between two tasks."""
    _require_project()
    rt = RelationType.from_value(relation_type)
    removed = remove_relation(source_id, target_id, rt)
    if removed:
        console.print(f"Removed {rt.value} link between #{source_id} and #{target_id}")
    else:
        console.print("No matching relation found.")


# Order commands


@cli.group()
def order():
    """Manage the recommended task completion order."""


def _parse_order_steps(steps: Tuple[str, ...]) -> list:
    """Parse positional step args like '1' '2,7,9' '5' into [[1],[2,7,9],[5]]."""
    parsed: list = []
    for step in steps:
        ids: list = []
        for token in step.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                ids.append(int(token))
            except ValueError:
                raise click.BadParameter(f"Invalid task id: {token!r}")
        if not ids:
            raise click.BadParameter(f"Empty step: {step!r}")
        parsed.append(ids)
    return parsed


@order.command(name="set")
@click.argument("steps", nargs=-1)
@click.option("--json", "json_input", help="JSON array of arrays, e.g. '[[1],[2,7,9],[5]]'")
@click.option("--agent", default=None, help="Agent or user performing this action")
def order_set(steps: Tuple[str, ...], json_input: Optional[str], agent: Optional[str]):
    """Set the recommended completion order. Use positional 'STEP STEP ...' (commas for parallel) or --json."""
    project = _require_project()
    if json_input is not None and steps:
        raise click.BadParameter("Use either positional steps or --json, not both.")
    if json_input is not None:
        try:
            sequence = json.loads(json_input)
        except json.JSONDecodeError as exc:
            raise click.BadParameter("--json must be a valid JSON array.") from exc
        if not isinstance(sequence, list) or not all(
            isinstance(step, list) and all(isinstance(t, int) for t in step)
            for step in sequence
        ):
            raise click.BadParameter("--json must be an array of arrays of integers.")
    elif steps:
        sequence = _parse_order_steps(steps)
    else:
        raise click.BadParameter("Provide step arguments or --json.")
    try:
        changed = set_task_order(project.id, sequence, agent=_get_agent(agent))
    except ValueError as exc:
        raise click.ClickException(str(exc))
    console.print(f"Order set ({len(sequence)} step(s); {changed} task(s) changed).")


@order.command(name="clear")
@click.option("--agent", default=None, help="Agent or user performing this action")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def order_clear(agent: Optional[str], yes: bool):
    """Clear the recommended completion order."""
    project = _require_project()
    if not yes and not click.confirm("Clear the current task ordering?"):
        return
    cleared = clear_task_order(project.id, agent=_get_agent(agent))
    console.print(f"Cleared ordering for {cleared} task(s).")


@order.command(name="show")
def order_show():
    """Show the current recommended completion order."""
    project = _require_project()
    sequence = get_task_order(project.id)
    if not sequence:
        console.print("No order set.")
        return
    for i, step in enumerate(sequence, start=1):
        ids = ", ".join(f"#{tid}" for tid in step)
        console.print(f"Step {i}: {ids}")


# Note command


@cli.command()
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("content")
@click.option("--author", "-a", required=True, help="Note author (required)")
def note(task_id: int, content: str, author: str):
    """Append a note to a task."""
    _require_task(task_id)
    if not author.strip():
        raise click.BadParameter("Author cannot be empty.", param_hint="'--author'")
    n = add_note(task_id, author.strip(), content)
    console.print(f"Note added to task #{task_id} (id={n.id})")


# Code review commands


@cli.group()
def cr():
    """Manage code reviews for a task."""


@cr.command(name="list")
@click.argument("task_id", type=click.IntRange(min=1))
def cr_list(task_id: int):
    """List all code reviews for a task."""
    _require_task(task_id)
    reviews = get_reviews(task_id)
    if not reviews:
        console.print("No code reviews found.")
        return
    from rich.table import Table
    table = Table(title=f"Code Reviews — Task #{task_id}")
    table.add_column("CR#", justify="right")
    table.add_column("Reviewer")
    table.add_column("Created")
    table.add_column("Fields set", justify="right")
    for cr_obj in reviews:
        filled = sum(1 for f in [cr_obj.reviewer, cr_obj.recommendations, cr_obj.devils_advocate, cr_obj.false_positives] if f)
        table.add_row(
            str(cr_obj.cr_num),
            cr_obj.reviewer or "-",
            cr_obj.created_at.strftime("%Y-%m-%d %H:%M"),
            str(filled),
        )
    console.print(table)


@cr.command(name="show")
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("cr_num", type=click.IntRange(min=1))
def cr_show(task_id: int, cr_num: int):
    """Show full detail of one code review."""
    _require_task(task_id)
    cr_obj = get_review(task_id, cr_num)
    if not cr_obj:
        console.print(f"CR-{cr_num} not found for task #{task_id}.")
        return
    format_reviews([cr_obj])


@cr.command(name="add")
@click.argument("task_id", type=click.IntRange(min=1))
def cr_add(task_id: int):
    """Create a new code review stub for a task."""
    _require_task(task_id)
    cr_obj = create_review_stub(task_id)
    console.print(f"Created CR-{cr_obj.cr_num} for task #{task_id}.")
    console.print(f"Use 'tasker cr update {task_id} {cr_obj.cr_num}' to fill in details.")


@cr.command(name="update")
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("cr_num", type=click.IntRange(min=1))
@click.option("--reviewer", "-r", help="Name of reviewer")
@click.option("--recommendations", "-R", help="Core findings and suggested changes (or - for stdin)")
@click.option("--devils-advocate", "-d", "devils_advocate", help="Reviewer's self-critique (or - for stdin)")
@click.option("--false-positives", "-f", "false_positives", help="Issues raised but ruled out (or - for stdin)")
def cr_update(task_id: int, cr_num: int, reviewer: Optional[str], recommendations: Optional[str], devils_advocate: Optional[str], false_positives: Optional[str]):
    """Update fields of a code review."""
    _require_task(task_id)
    cr_obj = get_review(task_id, cr_num)
    if not cr_obj:
        console.print(f"CR-{cr_num} not found for task #{task_id}.")
        return
    if recommendations == "-":
        recommendations = sys.stdin.read()
    if devils_advocate == "-":
        devils_advocate = sys.stdin.read()
    if false_positives == "-":
        false_positives = sys.stdin.read()
    updated = update_review(task_id, cr_num, reviewer=reviewer, recommendations=recommendations, devils_advocate=devils_advocate, false_positives=false_positives)
    if updated:
        console.print(f"Updated CR-{cr_num} for task #{task_id}.")


@cr.command(name="delete")
@click.argument("task_id", type=click.IntRange(min=1))
@click.argument("cr_num", type=click.IntRange(min=1))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def cr_delete(task_id: int, cr_num: int, yes: bool):
    """Delete a code review."""
    _require_task(task_id)
    if not yes and not click.confirm(f"Delete CR-{cr_num} for task {task_id}?"):
        return
    deleted = delete_review(task_id, cr_num)
    if deleted:
        console.print(f"Deleted CR-{cr_num} for task #{task_id}.")
    else:
        console.print(f"CR-{cr_num} not found for task #{task_id}.")


# Utility commands


@cli.command()
def focus():
    """Show what to work on next."""
    project = _require_project()
    task = get_focus_task(project.id)
    print_focus(task)


@cli.command()
def stats():
    """Show task statistics for the active project."""
    project = _require_project()
    data = get_project_stats(project.id)
    print_stats(data)


@cli.command()
@click.option("--days", type=int, help="Remove completed tasks older than DAYS")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def clean(days: Optional[int], yes: bool):
    """Clean up completed tasks."""
    project = _require_project()
    if not yes:
        prompt = (
            "Delete all completed tasks?"
            if days is None
            else f"Delete tasks completed more than {days} days ago?"
        )
        if not click.confirm(prompt):
            return
    removed = clean_completed(project.id, older_than_days=days)
    console.print(f"Removed {removed} tasks")


@cli.command()
@click.argument("file", required=False, type=click.Path(path_type=Path))
@click.option(
    "--format", "-f", "fmt", type=click.Choice(["json", "md"]), default="json"
)
@click.option("--include-notes", "include_notes", is_flag=True, help="Include notes and code reviews in export")
@click.option("--include-history", "include_history", is_flag=True, help="Include history log in export")
def export(file: Optional[Path], fmt: str, include_notes: bool, include_history: bool):
    """Export tasks to FILE (default stdout)."""
    project = _require_project()
    tasks = list_tasks(project.id, include_done=True)
    if fmt == "json":
        task_dicts = [t.to_dict() for t in tasks]
        if include_notes:
            for td in task_dicts:
                td["notes"] = [n.to_dict() for n in get_notes(td["id"])]
                td["reviews"] = [r.to_dict() for r in get_reviews(td["id"])]
        if include_history:
            for td in task_dicts:
                td["history"] = [h.to_dict() for h in get_task_history(td["id"])]
        payload = json.dumps(task_dicts, indent=2)
    else:
        payload = export_tasks_markdown(
            project, tasks, include_notes=include_notes, include_history=include_history
        )

    if file:
        file.write_text(payload)
        console.print(f"Exported to {file}")
    else:
        click.echo(payload)


if __name__ == "__main__":
    cli()
