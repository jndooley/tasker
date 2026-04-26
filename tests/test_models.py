from datetime import datetime
import json

from tasker.models import Priority, Project, Status, Task


def test_project_to_dict_and_from_row_roundtrip():
    now = datetime.utcnow().replace(microsecond=0)
    row = {
        "id": 1,
        "path": "/tmp/p",
        "name": "P",
        "is_active": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    project = Project.from_row(row)
    assert isinstance(project.created_at, datetime)
    data = project.to_dict()
    assert data["name"] == "P"
    assert data["is_active"] is True


def test_task_to_dict_and_from_row_roundtrip():
    now = datetime.utcnow().replace(microsecond=0)
    row = {
        "id": 2,
        "project_id": 1,
        "title": "T",
        "description": "d",
        "acceptance_criteria": json.dumps(["criterion one", "criterion two"]),
        "plan": None,
        "status": "in-progress",
        "priority": 2,
        "order_index": 1000,
        "group_id": "backend",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "completed_at": None,
        "order_number": None,
        "order_set_at": None,
        "order_set_by": None,
    }
    task = Task.from_row(row)
    assert task.status == Status.IN_PROGRESS
    assert task.priority == Priority.MEDIUM
    assert task.group_id == "backend"
    data = task.to_dict()
    assert data["status"] == "in-progress"
    assert data["priority"] == 2
    assert data["acceptance_criteria"] == ["criterion one", "criterion two"]
    assert data["group_id"] == "backend"
