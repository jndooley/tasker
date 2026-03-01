import json
from pathlib import Path

from click.testing import CliRunner

from tasker import cli


def test_cli_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()

    # init project
    result = runner.invoke(cli.cli, ["init", str(tmp_path)])
    assert result.exit_code == 0

    # add and list
    runner.invoke(cli.cli, ["add", "Do work", "-p", "high"])
    list_res = runner.invoke(cli.cli, ["list", "--json"])
    assert list_res.exit_code == 0
    assert "Do work" in list_res.output

    # focus should show same task
    focus_res = runner.invoke(cli.cli, ["focus"])
    assert "Do work" in focus_res.output


def test_cli_group_workflow(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])

    # Add tasks with groups
    runner.invoke(cli.cli, ["add", "Login page", "-g", "auth"])
    runner.invoke(cli.cli, ["add", "Signup page", "-g", "auth"])
    runner.invoke(cli.cli, ["add", "Dashboard", "-g", "ui"])
    runner.invoke(cli.cli, ["add", "Ungrouped task"])

    # List with group filter
    list_res = runner.invoke(cli.cli, ["list", "--json", "-g", "auth"])
    assert list_res.exit_code == 0
    payload = json.loads(list_res.output)
    assert len(payload) == 2
    assert all(t["group_id"] == "auth" for t in payload)

    # Groups command
    groups_res = runner.invoke(cli.cli, ["groups"])
    assert groups_res.exit_code == 0
    assert "auth" in groups_res.output
    assert "ui" in groups_res.output

    # Update group
    update_res = runner.invoke(cli.cli, ["update", "4", "-g", "auth"])
    assert update_res.exit_code == 0
    list_res2 = runner.invoke(cli.cli, ["list", "--json", "-g", "auth"])
    payload2 = json.loads(list_res2.output)
    assert len(payload2) == 3


def test_cli_link_unlink(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Design API"])
    runner.invoke(cli.cli, ["add", "Implement API"])

    # Link task 2 blocked-by task 1
    link_res = runner.invoke(cli.cli, ["link", "2", "1", "--type", "blocked-by"])
    assert link_res.exit_code == 0
    assert "Linked" in link_res.output

    # Show task 1 should display "blocks"
    show_res = runner.invoke(cli.cli, ["show", "1"])
    assert "blocks" in show_res.output
    assert "#2" in show_res.output

    # Show task 2 should display "blocked-by"
    show_res2 = runner.invoke(cli.cli, ["show", "2"])
    assert "blocked-by" in show_res2.output
    assert "#1" in show_res2.output

    # Focus should skip blocked task 2, show task 1
    focus_res = runner.invoke(cli.cli, ["focus"])
    assert "Design API" in focus_res.output

    # Unlink
    unlink_res = runner.invoke(cli.cli, ["unlink", "2", "1", "--type", "blocked-by"])
    assert unlink_res.exit_code == 0
    assert "Removed" in unlink_res.output

    # Show task 2 should have no relations now
    show_res3 = runner.invoke(cli.cli, ["show", "2"])
    assert "blocked-by" not in show_res3.output


def test_cli_list_blocked_indicator(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "First task"])
    runner.invoke(cli.cli, ["add", "Second task"])
    runner.invoke(cli.cli, ["link", "2", "1", "--type", "blocked-by"])

    list_res = runner.invoke(cli.cli, ["list"])
    assert list_res.exit_code == 0
    assert "[B]" in list_res.output


def test_cli_acceptance_criteria_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    init_res = runner.invoke(cli.cli, ["init", str(tmp_path)])
    assert init_res.exit_code == 0

    add_res = runner.invoke(
        cli.cli,
        [
            "add",
            "Implement parser",
            "--acceptance-criteria",
            "handles valid input",
            "--acceptance-criteria",
            "rejects invalid input",
        ],
    )
    assert add_res.exit_code == 0

    list_res = runner.invoke(cli.cli, ["list", "--json"])
    assert list_res.exit_code == 0
    payload = json.loads(list_res.output)
    assert payload[0]["acceptance_criteria"] == [
        "handles valid input",
        "rejects invalid input",
    ]
