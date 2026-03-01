"""Click CLI definition for Tasker."""

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__
from .formatter import (
    console,
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
    add_relation,
    block_task,
    clean_completed,
    complete_task,
    create_project,
    create_task,
    delete_task,
    export_tasks,
    export_tasks_markdown,
    get_active_project,
    get_focus_task,
    get_project_by_path,
    get_project_stats,
    get_relations,
    get_task,
    is_blocked,
    list_groups,
    list_projects,
    list_tasks,
    qa_task,
    remove_relation,
    reorder_task,
    review_task,
    set_active_project,
    start_task,
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
        click.echo("No active project. Run `tasker init` first.")
        raise click.Abort()
    return project


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
@click.argument("task_id", type=int)
def show(task_id: int):
    """Show task details."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    relations = get_relations(task_id)
    print_task_detail(task, relations=relations)


@cli.command()
@click.argument("task_id", type=int)
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
):
    """Update a task."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    acceptance_criteria_value = _parse_acceptance_criteria(
        acceptance_criteria, acceptance_criteria_json
    )
    if plan == "-":
        plan = sys.stdin.read()
    # Convert empty string to None to clear group assignment
    from .queries import _UNSET

    group_val = _UNSET
    if group_id is not None:
        group_val = group_id if group_id != "" else None
    updated = update_task(
        task_id,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria_value,
        priority=_parse_priority(priority),
        status=_parse_status(status),
        group_id=group_val,
        plan=plan,
    )
    if updated:
        console.print(f"Updated task #{updated.id}")


@cli.command()
@click.argument("task_id", type=int)
def start(task_id: int):
    """Mark a task as in-progress."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    updated = start_task(task_id)
    if updated:
        console.print(f"Task #{task_id} started")


@cli.command()
@click.argument("task_id", type=int)
def review(task_id: int):
    """Mark a task as in review."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    updated = review_task(task_id)
    if updated:
        console.print(f"Task #{task_id} in review")


@cli.command()
@click.argument("task_id", type=int)
def qa(task_id: int):
    """Mark a task as in QA."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    updated = qa_task(task_id)
    if updated:
        console.print(f"Task #{task_id} in QA")


@cli.command()
@click.argument("task_id", type=int)
def done(task_id: int):
    """Mark a task as done."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    updated = complete_task(task_id)
    if updated:
        console.print(f"Task #{task_id} completed")


@cli.command()
@click.argument("task_id", type=int)
@click.argument("blocker_id", type=int)
def block(task_id: int, blocker_id: int):
    """Mark a task as blocked by another task."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    blocker = get_task(blocker_id)
    if not blocker or blocker.project_id != project.id:
        console.print(f"Task {blocker_id} not found in active project.")
        return
    try:
        block_task(task_id, blocker_id)
        console.print(f"Task #{task_id} blocked by #{blocker_id}")
    except ValueError as exc:
        console.print(f"Error: {exc}")


@cli.command()
@click.argument("task_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(task_id: int, yes: bool):
    """Delete a task."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
    if not yes and not click.confirm(f"Delete task #{task_id}?"):
        return
    delete_task(task_id)
    console.print(f"Deleted task #{task_id}")


@cli.command()
@click.argument("task_id", type=int)
@click.argument("position", type=int)
def reorder(task_id: int, position: int):
    """Move a task to POSITION (1-based)."""
    project = _require_project()
    task = get_task(task_id)
    if not task or task.project_id != project.id:
        console.print(f"Task {task_id} not found in active project.")
        return
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
@click.argument("source_id", type=int)
@click.argument("target_id", type=int)
@click.option(
    "--type", "-t", "relation_type",
    type=click.Choice(RELATION_TYPE_CHOICES),
    default=RelationType.RELATED_TO.value,
    help="Relation type (default: related-to)",
)
def link(source_id: int, target_id: int, relation_type: str):
    """Link two tasks with a relation."""
    project = _require_project()
    source = get_task(source_id)
    if not source or source.project_id != project.id:
        console.print(f"Task {source_id} not found in active project.")
        return
    target = get_task(target_id)
    if not target or target.project_id != project.id:
        console.print(f"Task {target_id} not found in active project.")
        return
    try:
        rt = RelationType.from_value(relation_type)
        rel = add_relation(source_id, target_id, rt)
        console.print(f"Linked #{source_id} --{rel.relation_type.value}--> #{target_id}")
    except (ValueError, Exception) as exc:
        console.print(f"Error: {exc}")


@cli.command()
@click.argument("source_id", type=int)
@click.argument("target_id", type=int)
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
def export(file: Optional[Path], fmt: str):
    """Export tasks to FILE (default stdout)."""
    project = _require_project()
    tasks = list_tasks(project.id, include_done=True)
    if fmt == "json":
        payload = json.dumps(export_tasks(project.id), indent=2)
    else:
        payload = export_tasks_markdown(project, tasks)

    if file:
        file.write_text(payload)
        console.print(f"Exported to {file}")
    else:
        click.echo(payload)


if __name__ == "__main__":
    cli()
