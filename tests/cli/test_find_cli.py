"""
Tests for ``tasksquatch find`` — the fzf-driven fuzzy picker.

The real ``fzf`` binary is never executed by these tests: both
:func:`shutil.which` (the existence probe) and :func:`subprocess.run`
(the actual invocation) are monkey-patched at the
:mod:`tasksquatch.cli.commands.find` import level. The tests exercise
the four reachable code paths — fzf missing, fzf user-aborted, fzf
selection round-tripped into an action, and "no incomplete tasks" —
plus an action-mapping check that verifies ``--action done`` flips the
selected task to completed.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from typer.testing import CliRunner

from tasksquatch.cli.app import app
from tasksquatch.cli.commands import find as find_cmd
from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
)
from tasksquatch.core.models import Task
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


def _fzf_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Make ``shutil.which("fzf")`` look like fzf is installed.
    """
    monkeypatch.setattr(find_cmd.shutil, "which", lambda _: "/usr/bin/fzf")


def _fzf_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Make ``shutil.which("fzf")`` look like fzf is absent.
    """
    monkeypatch.setattr(find_cmd.shutil, "which", lambda _: None)


def test_find_exits_two_when_fzf_missing(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_missing(monkeypatch)
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])

    result = runner.invoke(app, ["--db", str(db_path), "find"])
    assert result.exit_code == 2, result.output
    assert "fzf binary not found" in result.output


def test_find_user_abort_returns_exit_one(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_present(monkeypatch)
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])

    def fake_run(*_args: Any, **_kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(args=[], returncode=1, stdout="", stderr="")

    monkeypatch.setattr(find_cmd.subprocess, "run", fake_run)
    result = runner.invoke(app, ["--db", str(db_path), "find"])
    assert result.exit_code == 1, result.output


def test_find_dispatches_show_on_selection(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_present(monkeypatch)
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])

    def fake_run(*_args: Any, **_kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(
            args=[],
            returncode=0,
            stdout="#1  Buy milk  [Inbox]  [-]\n",
            stderr="",
        )

    monkeypatch.setattr(find_cmd.subprocess, "run", fake_run)
    result = runner.invoke(app, ["--db", str(db_path), "find", "--action", "show"])
    assert result.exit_code == 0, result.output
    assert "Buy milk" in result.output


def test_find_action_done_completes_selected_task(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_present(monkeypatch)
    runner.invoke(app, ["--db", str(db_path), "add", "Send email"])

    def fake_run(*_args: Any, **_kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(
            args=[],
            returncode=0,
            stdout="#1  Send email  [Inbox]  [-]\n",
            stderr="",
        )

    monkeypatch.setattr(find_cmd.subprocess, "run", fake_run)
    result = runner.invoke(app, ["--db", str(db_path), "find", "--action", "done"])
    assert result.exit_code == 0, result.output

    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        assert task.completed is True
    finally:
        sess.close()


def test_find_empty_db_exits_zero_with_message(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_present(monkeypatch)

    def fake_run(*_args: Any, **_kwargs: Any) -> CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called when DB is empty")

    monkeypatch.setattr(find_cmd.subprocess, "run", fake_run)
    result = runner.invoke(app, ["--db", str(db_path), "find"])
    assert result.exit_code == 0, result.output
    assert "No incomplete tasks to pick from." in result.output


def test_find_unknown_action_surfaces_validation_error(
    runner: CliRunner, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fzf_present(monkeypatch)
    runner.invoke(app, ["--db", str(db_path), "add", "Buy milk"])

    def fake_run(*_args: Any, **_kwargs: Any) -> CompletedProcess[str]:
        return CompletedProcess(
            args=[],
            returncode=0,
            stdout="#1  Buy milk  [Inbox]  [-]\n",
            stderr="",
        )

    monkeypatch.setattr(find_cmd.subprocess, "run", fake_run)
    result = runner.invoke(app, ["--db", str(db_path), "find", "--action", "nope"])
    assert result.exit_code == 1, result.output
    assert "nope" in result.output


def test_format_fzf_line_uses_dash_for_missing_metadata(
    runner: CliRunner, db_path: Path
) -> None:
    runner.invoke(app, ["--db", str(db_path), "add", "Solo"])
    sess = _open_session(db_path)
    try:
        task = sess.execute(select(Task)).scalars().one()
        line = find_cmd._format_fzf_line(task)
    finally:
        sess.close()
    assert line.startswith("#1  Solo  [Inbox]  [-]")


def test_parse_number_from_line_rejects_malformed_input() -> None:
    from tasksquatch.core.errors import ValidationError

    with pytest.raises(ValidationError):
        find_cmd._parse_number_from_line("no number here")
