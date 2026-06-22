"""
Tests for ``tasksquatch label ...`` — the label sub-app.

Same test conventions as ``test_project_cli.py``: fresh SQLite file per
test, :class:`typer.testing.CliRunner` for invocation, out-of-band
sessions for state assertions.
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
from tasksquatch.core.models import Label
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


def test_label_add_then_ls_shows_label_with_zero_tasks(
    runner: CliRunner, db_path: Path
) -> None:
    add = runner.invoke(app, ["--db", str(db_path), "label", "add", "Home"])
    assert add.exit_code == 0, add.output
    assert "Home" in add.output

    ls = runner.invoke(app, ["--db", str(db_path), "label", "ls"])
    assert ls.exit_code == 0, ls.output
    assert "Home" in ls.output
    assert "0" in ls.output


def test_label_ls_reflects_attached_task_count(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "label", "add", "Home"])
    runner.invoke(app, ["--db", str(db_path), "add", "Water plants", "-l", "Home"])

    ls = runner.invoke(app, ["--db", str(db_path), "label", "ls"])
    assert ls.exit_code == 0, ls.output
    lines = [line for line in ls.output.splitlines() if "Home" in line]
    assert lines, ls.output
    assert "1" in lines[0]


def test_label_rename_changes_name(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "label", "add", "Home"])
    rename = runner.invoke(
        app, ["--db", str(db_path), "label", "rename", "Home", "House"]
    )
    assert rename.exit_code == 0, rename.output
    assert "House" in rename.output

    sess = _open_session(db_path)
    try:
        names = {label.name for label in sess.execute(select(Label)).scalars().all()}
        assert names == {"House"}
    finally:
        sess.close()


def test_label_rm_yes_deletes_label(runner: CliRunner, db_path: Path) -> None:
    runner.invoke(app, ["--db", str(db_path), "label", "add", "House"])
    result = runner.invoke(app, ["--db", str(db_path), "label", "rm", "House", "--yes"])
    assert result.exit_code == 0, result.output

    sess = _open_session(db_path)
    try:
        names = {label.name for label in sess.execute(select(Label)).scalars().all()}
        assert names == set()
    finally:
        sess.close()


def test_label_rm_aborts_on_negative_confirmation(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "label", "add", "Home"])
    result = runner.invoke(
        app, ["--db", str(db_path), "label", "rm", "Home"], input="n\n"
    )
    assert result.exit_code != 0

    sess = _open_session(db_path)
    try:
        names = {label.name for label in sess.execute(select(Label)).scalars().all()}
        assert "Home" in names
    finally:
        sess.close()
