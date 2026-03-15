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


def test_cli_note_add_and_show(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task with notes"])

    # Add a note
    note_res = runner.invoke(cli.cli, ["note", "1", "Blocked on infra", "--author", "jason"])
    assert note_res.exit_code == 0
    assert "Note added" in note_res.output

    # Show without --notes: no notes section
    show_res = runner.invoke(cli.cli, ["show", "1"])
    assert show_res.exit_code == 0
    assert "Notes" not in show_res.output

    # Show with --notes: notes section present
    show_notes_res = runner.invoke(cli.cli, ["show", "1", "--notes"])
    assert show_notes_res.exit_code == 0
    assert "Notes" in show_notes_res.output
    assert "Blocked on infra" in show_notes_res.output


def test_cli_note_requires_author(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Some task"])

    # Missing --author should fail
    result = runner.invoke(cli.cli, ["note", "1", "some content"])
    assert result.exit_code != 0


def test_cli_review_creates_cr1_stub(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "A task"])

    # First review creates CR-1
    review_res = runner.invoke(cli.cli, ["review", "1"])
    assert review_res.exit_code == 0
    assert "Created CR-1" in review_res.output

    # Second review does not create another stub
    review_res2 = runner.invoke(cli.cli, ["review", "1"])
    assert review_res2.exit_code == 0
    assert "Created CR-1" not in review_res2.output


def test_cli_cr_workflow(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "A task"])
    runner.invoke(cli.cli, ["review", "1"])

    # cr list
    list_res = runner.invoke(cli.cli, ["cr", "list", "1"])
    assert list_res.exit_code == 0
    assert "CR" in list_res.output

    # cr update
    update_res = runner.invoke(cli.cli, ["cr", "update", "1", "1", "--reviewer", "jason", "--recommendations", "Split the module"])
    assert update_res.exit_code == 0
    assert "Updated" in update_res.output

    # cr show
    show_res = runner.invoke(cli.cli, ["cr", "show", "1", "1"])
    assert show_res.exit_code == 0
    assert "jason" in show_res.output
    assert "Split the module" in show_res.output

    # cr add creates CR-2
    add_res = runner.invoke(cli.cli, ["cr", "add", "1"])
    assert add_res.exit_code == 0
    assert "CR-2" in add_res.output

    # cr delete with --yes
    delete_res = runner.invoke(cli.cli, ["cr", "delete", "1", "2", "--yes"])
    assert delete_res.exit_code == 0
    assert "Deleted" in delete_res.output

    # verify only CR-1 remains
    list_res2 = runner.invoke(cli.cli, ["cr", "list", "1"])
    assert "CR-2" not in list_res2.output


def test_cli_export_include_notes(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task"])
    runner.invoke(cli.cli, ["note", "1", "Important observation", "--author", "jason"])
    runner.invoke(cli.cli, ["review", "1"])

    # Export without --include-notes: no notes key
    export_res = runner.invoke(cli.cli, ["export"])
    assert export_res.exit_code == 0
    payload = json.loads(export_res.output)
    assert "notes" not in payload[0]
    assert "reviews" not in payload[0]

    # Export with --include-notes: notes and reviews present
    export_notes_res = runner.invoke(cli.cli, ["export", "--include-notes"])
    assert export_notes_res.exit_code == 0
    payload2 = json.loads(export_notes_res.output)
    assert "notes" in payload2[0]
    assert len(payload2[0]["notes"]) == 1
    assert payload2[0]["notes"][0]["author"] == "jason"
    assert "reviews" in payload2[0]
    assert len(payload2[0]["reviews"]) == 1


def test_cli_agent_option_records_history(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task"])

    # start with explicit agent
    start_res = runner.invoke(cli.cli, ["start", "1", "--agent", "claude-sonnet-4-6"])
    assert start_res.exit_code == 0

    # done with explicit agent
    done_res = runner.invoke(cli.cli, ["done", "1", "--agent", "jason"])
    assert done_res.exit_code == 0

    # verify history via show --history
    show_res = runner.invoke(cli.cli, ["show", "1", "--history"])
    assert show_res.exit_code == 0
    assert "History" in show_res.output
    assert "claude-sonnet-4-6" in show_res.output
    assert "jason" in show_res.output
    assert "todo" in show_res.output
    assert "in-progress" in show_res.output
    assert "done" in show_res.output


def test_cli_agent_defaults_to_env_var(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))
    monkeypatch.setenv("TASKER_AGENT", "env-agent")

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task"])
    runner.invoke(cli.cli, ["start", "1"])  # no --agent, should use $TASKER_AGENT

    show_res = runner.invoke(cli.cli, ["show", "1", "--history"])
    assert "env-agent" in show_res.output


def test_cli_show_history_flag(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task"])

    # show without --history: no History section
    show_res = runner.invoke(cli.cli, ["show", "1"])
    assert show_res.exit_code == 0
    assert "History" not in show_res.output

    # show with --history: History section present (empty)
    show_hist_res = runner.invoke(cli.cli, ["show", "1", "--history"])
    assert show_hist_res.exit_code == 0
    assert "History" in show_hist_res.output


def test_cli_export_include_history(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("TASKER_DB_PATH", str(db_path))

    runner = CliRunner()
    runner.invoke(cli.cli, ["init", str(tmp_path)])
    runner.invoke(cli.cli, ["add", "Task"])
    runner.invoke(cli.cli, ["start", "1", "--agent", "bot"])
    runner.invoke(cli.cli, ["done", "1", "--agent", "human"])

    # Export without --include-history: no history key
    export_res = runner.invoke(cli.cli, ["export"])
    assert export_res.exit_code == 0
    payload = json.loads(export_res.output)
    assert "history" not in payload[0]

    # Export with --include-history: history array present
    export_hist_res = runner.invoke(cli.cli, ["export", "--include-history"])
    assert export_hist_res.exit_code == 0
    payload2 = json.loads(export_hist_res.output)
    assert "history" in payload2[0]
    assert len(payload2[0]["history"]) == 2
    assert payload2[0]["history"][0]["agent"] == "bot"
    assert payload2[0]["history"][0]["new_value"] == "in-progress"
    assert payload2[0]["history"][1]["agent"] == "human"
    assert payload2[0]["history"][1]["new_value"] == "done"


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
