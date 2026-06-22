"""
Tests for ``tasksquatch project ...`` — the project sub-app.

Each test runs against a fresh SQLite file in ``tmp_path``. The CLI is
invoked through :class:`typer.testing.CliRunner`; assertions check exit
code, command output, and (where state matters) the resulting database
via an out-of-band session.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from tasksquatch.cli.app import app
from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
)
from tasksquatch.core.models import Project
from tasksquatch.core.seed import ensure_inbox


def _open_session(db_path: Path) -> Session:
    """
    Open a fresh session against ``db_path`` with the schema and Inbox
    materialized.
    """
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    factory: sessionmaker[Session] = create_session_factory(engine)
    sess = factory()
    ensure_inbox(sess)
    sess.commit()
    return sess


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


def test_project_add_then_ls_shows_project_with_zero_tasks(
    runner: CliRunner, db_path: Path
) -> None:
    add = runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    assert add.exit_code == 0, add.output
    assert "Errands" in add.output

    ls = runner.invoke(app, ["--db", str(db_path), "project", "ls"])
    assert ls.exit_code == 0, ls.output
    assert "Errands" in ls.output
    assert "0" in ls.output


def test_project_ls_reflects_attached_task_count(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk", "-p", "Errands"])

    ls = runner.invoke(app, ["--db", str(db_path), "project", "ls"])
    assert ls.exit_code == 0, ls.output
    lines = [line for line in ls.output.splitlines() if "Errands" in line]
    assert lines, ls.output
    assert "1" in lines[0]


def test_project_rename_changes_name(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    rename = runner.invoke(
        app, ["--db", str(db_path), "project", "rename", "Errands", "Personal"]
    )
    assert rename.exit_code == 0, rename.output
    assert "Personal" in rename.output

    sess = _open_session(db_path)
    try:
        names = {p.name for p in sess.execute(select(Project)).scalars().all()}
        assert "Personal" in names
        assert "Errands" not in names
    finally:
        sess.close()


def test_project_rm_blocked_when_tasks_remain(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk", "-p", "Errands"])

    result = runner.invoke(
        app, ["--db", str(db_path), "project", "rm", "Errands", "--yes"]
    )
    assert result.exit_code == 1, result.output
    assert "Errands" in result.output
    assert "task" in result.output.lower()


def test_project_rm_yes_after_detach_succeeds(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk", "-p", "Errands"])
    runner.invoke(app, ["--db", str(db_path), "rm", "1", "--yes"])

    result = runner.invoke(
        app, ["--db", str(db_path), "project", "rm", "Errands", "--yes"]
    )
    assert result.exit_code == 0, result.output
    assert "Errands" in result.output

    sess = _open_session(db_path)
    try:
        names = {p.name for p in sess.execute(select(Project)).scalars().all()}
        assert "Errands" not in names
    finally:
        sess.close()


def test_project_rm_inbox_is_protected(runner: CliRunner, db_path: Path) -> None:
    result = runner.invoke(
        app, ["--db", str(db_path), "project", "rm", "Inbox", "--yes"]
    )
    assert result.exit_code == 1, result.output
    assert "Inbox" in result.output


def test_project_rm_aborts_on_negative_confirmation(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "project", "add", "Errands"])
    result = runner.invoke(
        app, ["--db", str(db_path), "project", "rm", "Errands"], input="n\n"
    )
    assert result.exit_code != 0

    sess = _open_session(db_path)
    try:
        names = {p.name for p in sess.execute(select(Project)).scalars().all()}
        assert "Errands" in names
    finally:
        sess.close()
