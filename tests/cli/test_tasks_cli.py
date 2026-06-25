"""
Tests for the task-centric Typer commands in
:mod:`tasksquatch.cli.commands.tasks`.

Each test runs against a fresh SQLite file in ``tmp_path`` so the
behaviour of one command does not leak into another. The CLI is
invoked through :class:`typer.testing.CliRunner`; assertions check
exit code, command output, and (where state matters) the resulting
database via an out-of-band session.
"""

from __future__ import annotations

import json
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from tasksquatch.cli._parsers import parse_date, parse_priority, parse_time
from tasksquatch.cli.app import app
from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
)
from tasksquatch.core.models import Priority, Task
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.labels import create_label
from tasksquatch.core.services.projects import create_project


def _open_session(db_path: Path) -> Session:
    """
    Open a fresh session against ``db_path`` with the schema and Inbox
    materialized.

    :param db_path: Path to the SQLite file backing the CLI.
    :returns: An open :class:`Session`.
    """
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    factory: sessionmaker[Session] = create_session_factory(engine)
    sess = factory()
    ensure_inbox(sess)
    sess.commit()
    return sess


def _seed_project(db_path: Path, name: str) -> None:
    """
    Create a project named ``name`` on ``db_path``.
    """
    sess = _open_session(db_path)
    try:
        create_project(sess, name=name)
        sess.commit()
    finally:
        sess.close()


def _seed_label(db_path: Path, name: str) -> None:
    """
    Create a label named ``name`` on ``db_path``.
    """
    sess = _open_session(db_path)
    try:
        create_label(sess, name=name)
        sess.commit()
    finally:
        sess.close()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """
    A unique SQLite path per test.
    """
    return tmp_path / "tasks.db"


@pytest.fixture()
def runner() -> CliRunner:
    """
    A fresh :class:`CliRunner` per test.
    """
    return CliRunner()


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_lands_in_inbox(runner: CliRunner, db_path: Path) -> None:
    result = runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])
    assert result.exit_code == 0, result.output
    assert "Buy milk" in result.output

    listing = runner.invoke(app, ["--db", str(db_path), "list"])
    assert listing.exit_code == 0
    assert "Buy milk" in listing.output


def test_add_with_project_attaches_to_project(runner: CliRunner, db_path: Path) -> None:
    _seed_project(db_path, "Errands")
    result = runner.invoke(
        app, ["--db", str(db_path), "add", "Get groceries", "-p", "Errands"]
    )
    assert result.exit_code == 0, result.output

    sess = _open_session(db_path)
    try:
        tasks = list(sess.execute(select(Task)).scalars().all())
        assert len(tasks) == 1
        assert tasks[0].project.name == "Errands"
        assert tasks[0].title == "Get groceries"
    finally:
        sess.close()


def test_add_with_full_options_round_trips(runner: CliRunner, db_path: Path) -> None:
    _seed_label(db_path, "Home")
    result = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "add",
            "Water plants",
            "--due",
            "2026-07-01",
            "--time",
            "09:00",
            "--priority",
            "P1",
            "--label",
            "Home",
            "--rrule",
            "FREQ=DAILY",
        ],
    )
    assert result.exit_code == 0, result.output

    show = runner.invoke(app, ["--db", str(db_path), "show", "1"])
    assert show.exit_code == 0, show.output
    assert "Water plants" in show.output
    assert "2026-07-01" in show.output
    assert "09:00" in show.output
    assert "P1" in show.output
    assert "Home" in show.output
    assert "FREQ=DAILY" in show.output


def test_add_with_bad_date_exits_two(runner: CliRunner, db_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--db", str(db_path), "add", "Bogus", "--due", "not-a-date"],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_unknown_number_exits_one(runner: CliRunner, db_path: Path) -> None:
    result = runner.invoke(app, ["--db", str(db_path), "show", "999"])
    assert result.exit_code == 1
    assert "task #999 not found" in result.output


# ---------------------------------------------------------------------------
# done / undo
# ---------------------------------------------------------------------------


def test_done_then_list_completed_shows_task(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Send email"])
    done = runner.invoke(app, ["--db", str(db_path), "done", "1"])
    assert done.exit_code == 0, done.output
    assert "completed" in done.output

    listing = runner.invoke(app, ["--db", str(db_path), "list", "--completed", "done"])
    assert listing.exit_code == 0, listing.output
    assert "Send email" in listing.output


def test_list_completed_open_excludes_done_tasks(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Pending task"])
    runner.invoke(app, ["--db", str(db_path), "add", "Finished task"])
    runner.invoke(app, ["--db", str(db_path), "done", "2"])

    listing = runner.invoke(app, ["--db", str(db_path), "list", "--completed", "open"])
    assert listing.exit_code == 0, listing.output
    assert "Pending task" in listing.output
    assert "Finished task" not in listing.output


def test_list_completed_all_shows_open_and_done(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Pending task"])
    runner.invoke(app, ["--db", str(db_path), "add", "Finished task"])
    runner.invoke(app, ["--db", str(db_path), "done", "2"])

    explicit = runner.invoke(app, ["--db", str(db_path), "list", "--completed", "all"])
    assert explicit.exit_code == 0, explicit.output
    assert "Pending task" in explicit.output
    assert "Finished task" in explicit.output
    assert "completed" in explicit.output
    assert "true" in explicit.output
    assert "false" in explicit.output

    default = runner.invoke(app, ["--db", str(db_path), "list"])
    assert default.exit_code == 0, default.output
    assert "Pending task" in default.output
    assert "Finished task" in default.output


def test_list_completed_filtered_drops_redundant_column(
    runner: CliRunner, db_path: Path
) -> None:
    """
    A filtered ``list`` view drops the ``completed`` column since every
    visible row would otherwise carry the same value.
    """
    runner.invoke(app, ["--db", str(db_path), "add", "Pending task"])
    runner.invoke(app, ["--db", str(db_path), "add", "Finished task"])
    runner.invoke(app, ["--db", str(db_path), "done", "2"])

    open_listing = runner.invoke(
        app, ["--db", str(db_path), "list", "--completed", "open"]
    )
    assert open_listing.exit_code == 0, open_listing.output
    assert "completed" not in open_listing.output
    assert "Pending task" in open_listing.output

    done_listing = runner.invoke(
        app, ["--db", str(db_path), "list", "--completed", "done"]
    )
    assert done_listing.exit_code == 0, done_listing.output
    assert "completed" not in done_listing.output
    assert "Finished task" in done_listing.output


def test_list_completed_invalid_value_exits_two(
    runner: CliRunner, db_path: Path
) -> None:
    result = runner.invoke(
        app, ["--db", str(db_path), "list", "--completed", "garbage"]
    )
    assert result.exit_code == 2
    assert "garbage" in result.output


def test_undo_reverts_completion(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Pay bill"])
    runner.invoke(app, ["--db", str(db_path), "done", "1"])
    undo = runner.invoke(app, ["--db", str(db_path), "undo", "1"])
    assert undo.exit_code == 0, undo.output
    assert "reopened" in undo.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.completed is False
        assert task.completed_at is None
    finally:
        sess.close()


def test_done_on_recurring_task_advances_due_date(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "add",
            "Stand-up",
            "--due",
            "2026-07-01",
            "--rrule",
            "FREQ=DAILY",
        ],
    )
    done = runner.invoke(app, ["--db", str(db_path), "done", "1"])
    assert done.exit_code == 0, done.output
    assert "advanced to 2026-07-02" in done.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.completed is False
        assert task.due_date == date(2026, 7, 2)
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


def test_edit_updates_priority_and_attaches_label(
    runner: CliRunner, db_path: Path
) -> None:
    _seed_label(db_path, "Work")
    runner.invoke(app, ["--db", str(db_path), "add", "Write report"])

    edit = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "edit",
            "1",
            "--priority",
            "P2",
            "--label-add",
            "Work",
        ],
    )
    assert edit.exit_code == 0, edit.output

    show = runner.invoke(app, ["--db", str(db_path), "show", "1"])
    assert "P2" in show.output
    assert "Work" in show.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.priority is Priority.P2
        assert {label.name for label in task.labels} == {"Work"}
    finally:
        sess.close()


def test_edit_clear_due_date_with_none_token(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Pickup", "--due", "2026-07-01"])
    edit = runner.invoke(app, ["--db", str(db_path), "edit", "1", "--due", "none"])
    assert edit.exit_code == 0, edit.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.due_date is None
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# rm
# ---------------------------------------------------------------------------


def test_rm_yes_flag_deletes_without_prompt(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Throwaway"])
    result = runner.invoke(app, ["--db", str(db_path), "rm", "1", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted task #1" in result.output

    sess = _open_session(db_path)
    try:
        tasks = list(sess.execute(select(Task)).scalars().all())
        assert tasks == []
    finally:
        sess.close()


def test_rm_aborts_on_negative_confirmation(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Keep me"])
    result = runner.invoke(app, ["--db", str(db_path), "rm", "1"], input="n\n")
    assert result.exit_code != 0

    sess = _open_session(db_path)
    try:
        tasks = list(sess.execute(select(Task)).scalars().all())
        assert len(tasks) == 1
    finally:
        sess.close()


def test_rm_proceeds_on_positive_confirmation(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Throwaway"])
    result = runner.invoke(app, ["--db", str(db_path), "rm", "1"], input="y\n")
    assert result.exit_code == 0, result.output

    sess = _open_session(db_path)
    try:
        tasks = list(sess.execute(select(Task)).scalars().all())
        assert tasks == []
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------


def test_move_top_level_task_to_other_project(runner: CliRunner, db_path: Path) -> None:
    _seed_project(db_path, "Errands")
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])

    result = runner.invoke(app, ["--db", str(db_path), "move", "1", "Errands"])
    assert result.exit_code == 0, result.output
    assert "Errands" in result.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.project.name == "Errands"
    finally:
        sess.close()


def test_move_subtask_surfaces_friendly_error(runner: CliRunner, db_path: Path) -> None:
    _seed_project(db_path, "Errands")
    runner.invoke(app, ["--db", str(db_path), "add", "Parent"])
    runner.invoke(app, ["--db", str(db_path), "add", "Child", "--parent", "1"])

    result = runner.invoke(app, ["--db", str(db_path), "move", "2", "Errands"])
    assert result.exit_code == 1
    assert "subtask" in result.output.lower()


# ---------------------------------------------------------------------------
# comment
# ---------------------------------------------------------------------------


def test_comment_added_and_visible_in_show(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Review PR"])
    add_comment = runner.invoke(
        app, ["--db", str(db_path), "comment", "1", "looking good"]
    )
    assert add_comment.exit_code == 0, add_comment.output

    show = runner.invoke(app, ["--db", str(db_path), "show", "1"])
    assert show.exit_code == 0, show.output
    assert "looking good" in show.output


# ---------------------------------------------------------------------------
# list / json
# ---------------------------------------------------------------------------


def test_json_list_emits_parseable_json(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])
    runner.invoke(app, ["--db", str(db_path), "add", "Walk dog"])

    result = runner.invoke(app, ["--db", str(db_path), "--json", "list"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert isinstance(payload, list)
    titles = {row["title"] for row in payload}
    assert {"Buy milk", "Walk dog"}.issubset(titles)


# ---------------------------------------------------------------------------
# reschedule-overdue
# ---------------------------------------------------------------------------


def _seed_overdue_task(db_path: Path, title: str, due: date) -> None:
    """
    Create an overdue task in ``db_path`` with the given ``due`` date.
    """
    sess = _open_session(db_path)
    try:
        from tasksquatch.core.services.tasks import create_task

        create_task(sess, title=title, due_date=due)
        sess.commit()
    finally:
        sess.close()


def test_reschedule_overdue_dry_run_does_not_write(
    runner: CliRunner, db_path: Path
) -> None:
    _seed_overdue_task(db_path, "ancient", date(2020, 1, 1))
    result = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "reschedule-overdue",
            "--dry-run",
            "--yes",
            "--today",
            "2026-06-25",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "would bump" in result.output
    assert "ancient" in result.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.due_date == date(2020, 1, 1)
    finally:
        sess.close()


def test_reschedule_overdue_yes_writes(runner: CliRunner, db_path: Path) -> None:
    _seed_overdue_task(db_path, "ancient", date(2020, 1, 1))
    result = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "reschedule-overdue",
            "--yes",
            "--today",
            "2026-06-25",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "bumped 1" in result.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.due_date == date(2026, 6, 25)
    finally:
        sess.close()


def test_reschedule_overdue_prompts_without_yes(
    runner: CliRunner, db_path: Path
) -> None:
    _seed_overdue_task(db_path, "ancient", date(2020, 1, 1))
    confirmed = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "reschedule-overdue",
            "--today",
            "2026-06-25",
        ],
        input="y\n",
    )
    assert confirmed.exit_code == 0, confirmed.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.due_date == date(2026, 6, 25)
    finally:
        sess.close()

    _seed_overdue_task(db_path, "ancient2", date(2019, 1, 1))
    aborted = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "reschedule-overdue",
            "--today",
            "2026-06-25",
        ],
        input="n\n",
    )
    assert aborted.exit_code != 0

    sess = _open_session(db_path)
    try:
        rows = sess.execute(select(Task).order_by(Task.number)).scalars().all()
        assert rows[-1].due_date == date(2019, 1, 1)
    finally:
        sess.close()


def test_reschedule_overdue_no_tasks_exits_zero(
    runner: CliRunner, db_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "reschedule-overdue",
            "--yes",
            "--today",
            "2026-06-25",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "No overdue tasks" in result.output


def test_reschedule_overdue_json_output(runner: CliRunner, db_path: Path) -> None:
    _seed_overdue_task(db_path, "ancient", date(2020, 1, 1))
    result = runner.invoke(
        app,
        [
            "--db",
            str(db_path),
            "--json",
            "reschedule-overdue",
            "--yes",
            "--today",
            "2026-06-25",
        ],
    )
    assert result.exit_code == 0, result.output

    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(result.output.lstrip())
    assert isinstance(payload, list)
    assert payload[0]["title"] == "ancient"
    assert payload[0]["new_due"] == "2026-06-25"
    assert payload[0]["old_due"] == "2020-01-01"


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------


def test_parse_date_today_and_tomorrow_keywords() -> None:
    assert parse_date("today") == date.today()
    assert parse_date("tomorrow") == date.today() + timedelta(days=1)
    assert parse_date("2026-07-01") == date(2026, 7, 1)


def test_parse_priority_accepts_aliases() -> None:
    assert parse_priority("p1") is Priority.P1
    assert parse_priority("high") is Priority.P1
    assert parse_priority("3") is Priority.P3


def test_parse_time_strict_hhmm() -> None:
    assert parse_time("09:30") == time(9, 30)
