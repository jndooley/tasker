import pytest

from tasker import queries
from tasker.database import get_db


@pytest.fixture
def project_with_tasks():
    project = queries.create_project("/tmp/order_test", "Order Test")
    t1 = queries.create_task(project.id, "T1")
    t2 = queries.create_task(project.id, "T2")
    t3 = queries.create_task(project.id, "T3")
    t4 = queries.create_task(project.id, "T4")
    t5 = queries.create_task(project.id, "T5")
    return project, [t1, t2, t3, t4, t5]


def test_set_order_linear(project_with_tasks):
    project, tasks = project_with_tasks
    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id], [tasks[2].id]], agent="alice")

    assert queries.get_task_order(project.id) == [[tasks[0].id], [tasks[1].id], [tasks[2].id]]
    t1 = queries.get_task(tasks[0].id)
    assert t1.order_number == 1
    assert t1.order_set_by == "alice"
    assert t1.order_set_at is not None


def test_set_order_branching(project_with_tasks):
    project, tasks = project_with_tasks
    queries.set_task_order(
        project.id,
        [[tasks[0].id], [tasks[1].id, tasks[3].id, tasks[2].id], [tasks[4].id]],
        agent="bob",
    )
    seq = queries.get_task_order(project.id)
    assert len(seq) == 3
    assert seq[0] == [tasks[0].id]
    assert sorted(seq[1]) == sorted([tasks[1].id, tasks[3].id, tasks[2].id])
    assert seq[2] == [tasks[4].id]


def test_set_order_replaces_prior(project_with_tasks):
    project, tasks = project_with_tasks
    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id]], agent="alice")
    queries.set_task_order(project.id, [[tasks[2].id], [tasks[3].id]], agent="bob")

    assert queries.get_task_order(project.id) == [[tasks[2].id], [tasks[3].id]]
    t1 = queries.get_task(tasks[0].id)
    assert t1.order_number is None
    assert t1.order_set_by is None


def test_clear_order(project_with_tasks):
    project, tasks = project_with_tasks
    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id]], agent="alice")
    cleared = queries.clear_task_order(project.id, agent="alice")
    assert cleared == 2
    assert queries.get_task_order(project.id) == []
    assert queries.get_task(tasks[0].id).order_number is None


def test_set_order_history_diff_aware(project_with_tasks):
    """Only tasks whose order_number actually changed should get history rows."""
    project, tasks = project_with_tasks
    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id], [tasks[2].id]], agent="alice")

    initial_hist = sum(
        len(queries.get_task_history(t.id)) for t in tasks
    )

    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id], [tasks[3].id]], agent="bob")

    t1_hist = queries.get_task_history(tasks[0].id)
    t2_hist = queries.get_task_history(tasks[1].id)
    t3_hist = queries.get_task_history(tasks[2].id)
    t4_hist = queries.get_task_history(tasks[3].id)

    t1_order = [h for h in t1_hist if h.field == "order_number"]
    t2_order = [h for h in t2_hist if h.field == "order_number"]
    t3_order = [h for h in t3_hist if h.field == "order_number"]
    t4_order = [h for h in t4_hist if h.field == "order_number"]

    assert len(t1_order) == 1
    assert len(t2_order) == 1
    assert len(t3_order) == 2
    assert t3_order[-1].new_value is None
    assert t3_order[-1].agent == "bob"
    assert len(t4_order) == 1
    assert t4_order[0].new_value == "3"


def test_duplicate_id_in_sequence_rejected(project_with_tasks):
    project, tasks = project_with_tasks
    with pytest.raises(ValueError, match="more than one step"):
        queries.set_task_order(
            project.id, [[tasks[0].id], [tasks[0].id]], agent="alice"
        )


def test_unknown_task_rejected(project_with_tasks):
    project, _ = project_with_tasks
    with pytest.raises(ValueError, match="not found"):
        queries.set_task_order(project.id, [[99999]], agent="alice")


def test_cross_project_task_rejected(project_with_tasks):
    project, _ = project_with_tasks
    other = queries.create_project("/tmp/order_other", "Other")
    other_task = queries.create_task(other.id, "Foreign")
    with pytest.raises(ValueError, match="not in active project"):
        queries.set_task_order(project.id, [[other_task.id]], agent="alice")


def test_get_order_empty(project_with_tasks):
    project, _ = project_with_tasks
    assert queries.get_task_order(project.id) == []


def test_set_order_partial_clears_omitted(project_with_tasks):
    """Tasks not present in new sequence should have order_number cleared."""
    project, tasks = project_with_tasks
    queries.set_task_order(project.id, [[tasks[0].id], [tasks[1].id], [tasks[2].id]], agent="alice")
    queries.set_task_order(project.id, [[tasks[0].id]], agent="bob")
    assert queries.get_task(tasks[1].id).order_number is None
    assert queries.get_task(tasks[2].id).order_number is None
    assert queries.get_task(tasks[0].id).order_number == 1
