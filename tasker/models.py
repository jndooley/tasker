"""Domain models and enums for Tasker."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
import json
from typing import List, Optional
import sqlite3


class RelationType(str, Enum):
    """Types of relationships between tasks."""

    BLOCKED_BY = "blocked-by"
    CAUSED_BY = "caused-by"
    RELATED_TO = "related-to"

    @classmethod
    def from_value(cls, value: str) -> "RelationType":
        """Create a RelationType from its string value, raising if invalid."""
        for rt in cls:
            if rt.value == value:
                return rt
        raise ValueError(f"Invalid relation type: {value}")


INVERSE_LABELS = {
    RelationType.BLOCKED_BY: "blocks",
    RelationType.CAUSED_BY: "caused",
    RelationType.RELATED_TO: "related-to",
}


@dataclass
class TaskRelation:
    """Task relation row model."""

    id: int
    source_task_id: int
    target_task_id: int
    relation_type: RelationType
    created_at: datetime

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "TaskRelation":
        """Hydrate a TaskRelation from a sqlite Row."""
        return cls(
            id=row["id"],
            source_task_id=row["source_task_id"],
            target_task_id=row["target_task_id"],
            relation_type=RelationType.from_value(row["relation_type"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class Status(str, Enum):
    """Lifecycle status for tasks."""

    TODO = "todo"
    IN_PROGRESS = "in-progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    QA = "qa"
    DONE = "done"

    @classmethod
    def from_value(cls, value: str) -> "Status":
        """Create a Status from its string value, raising if invalid."""
        for status in cls:
            if status.value == value:
                return status
        raise ValueError(f"Invalid status: {value}")


class Priority(IntEnum):
    """Priority levels ordered from none to high."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_value(cls, value: int) -> "Priority":
        """Create a Priority from its integer value, raising if invalid."""
        try:
            return cls(int(value))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid priority: {value}") from exc


@dataclass
class Project:
    """Project row model."""

    id: int
    path: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "Project":
        """Hydrate a Project from a sqlite Row."""
        return cls(
            id=row["id"],
            path=row["path"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def to_dict(self) -> dict:
        """Serialize the project for JSON output."""
        return {
            "id": self.id,
            "path": self.path,
            "name": self.name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Task:
    """Task row model."""

    id: int
    project_id: int
    title: str
    description: Optional[str]
    acceptance_criteria: List[str]
    plan: Optional[str]
    status: Status
    priority: Priority
    order_index: int
    group_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    order_number: Optional[int] = None
    order_set_at: Optional[datetime] = None
    order_set_by: Optional[str] = None

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "Task":
        """Hydrate a Task from a sqlite Row."""
        raw_acceptance_criteria = row["acceptance_criteria"]
        acceptance_criteria: List[str] = []
        if raw_acceptance_criteria:
            try:
                parsed = json.loads(raw_acceptance_criteria)
                if isinstance(parsed, list):
                    acceptance_criteria = [str(item) for item in parsed]
            except json.JSONDecodeError:
                acceptance_criteria = []
        order_set_at_raw = row["order_set_at"]
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            description=row["description"],
            acceptance_criteria=acceptance_criteria,
            plan=row["plan"],
            status=Status.from_value(row["status"]),
            priority=Priority.from_value(row["priority"]),
            order_index=row["order_index"],
            group_id=row["group_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"])
            if row["completed_at"]
            else None,
            order_number=row["order_number"],
            order_set_at=datetime.fromisoformat(order_set_at_raw) if order_set_at_raw else None,
            order_set_by=row["order_set_by"],
        )

    def to_dict(self) -> dict:
        """Serialize the task for JSON or export."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "plan": self.plan,
            "status": self.status.value,
            "priority": int(self.priority),
            "order_index": self.order_index,
            "group_id": self.group_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "order_number": self.order_number,
            "order_set_at": self.order_set_at.isoformat() if self.order_set_at else None,
            "order_set_by": self.order_set_by,
        }


@dataclass
class Note:
    """Task note row model (immutable, append-only)."""

    id: int
    task_id: int
    author: str
    content: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "Note":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            author=row["author"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CodeReview:
    """Code review row model."""

    id: int
    task_id: int
    cr_num: int
    reviewer: Optional[str]
    recommendations: Optional[str]
    devils_advocate: Optional[str]
    false_positives: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "CodeReview":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            cr_num=row["cr_num"],
            reviewer=row["reviewer"],
            recommendations=row["recommendations"],
            devils_advocate=row["devils_advocate"],
            false_positives=row["false_positives"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "cr_num": self.cr_num,
            "reviewer": self.reviewer,
            "recommendations": self.recommendations,
            "devils_advocate": self.devils_advocate,
            "false_positives": self.false_positives,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class HistoryEntry:
    """Task history row model — records every field change with agent attribution."""

    id: int
    task_id: int
    agent: str
    field: str
    old_value: Optional[str]
    new_value: Optional[str]
    changed_at: datetime

    @classmethod
    def from_row(cls, row: "sqlite3.Row") -> "HistoryEntry":
        return cls(
            id=row["id"],
            task_id=row["task_id"],
            agent=row["agent"],
            field=row["field"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            changed_at=datetime.fromisoformat(row["changed_at"]),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "changed_at": self.changed_at.isoformat(),
        }
