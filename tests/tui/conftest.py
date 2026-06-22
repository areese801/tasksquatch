"""
Shared fixtures for the TUI test suite.

Every TUI test runs against a fresh on-disk SQLite database (Textual
snapshot tests need WAL, so ``:memory:`` is not enough). The
``seeded_app`` fixture lays down a small, deterministic dataset —
Inbox plus "Work" and "Errands" projects, with five tasks spread
across them — and returns the not-yet-started
:class:`TasksquatchTuiApp` so the test can drive it through
``run_test`` or hand it directly to ``snap_compare``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.tui._session import default_core_factory
from tasksquatch.tui.app import TasksquatchTuiApp


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """
    Return a fresh, isolated SQLite file path for this test.

    :param tmp_path: pytest's per-test temp directory fixture.
    :returns: A path under ``tmp_path`` that does not yet exist on
        disk. The TUI session helpers create the file on first use.
    """
    return tmp_path / "tui.db"


@pytest.fixture()
def seeded_app(db_path: Path) -> TasksquatchTuiApp:
    """
    Build a TUI app pre-seeded with a small deterministic dataset.

    The fixture creates two user projects ("Work" and "Errands") on
    top of the auto-seeded Inbox, and lays down five tasks spread
    across them — including one with a recognizable substring
    ("buy milk") that the fuzzy-filter test asserts on.

    :param db_path: The per-test database path fixture.
    :returns: A :class:`TasksquatchTuiApp` bound to the seeded
        database, ready to hand to ``snap_compare`` or to start with
        ``run_test``.
    """
    factory = default_core_factory(db_path)
    with factory() as session:
        work = projects_service.create_project(session, name="Work")
        errands = projects_service.create_project(session, name="Errands")
        tasks_service.create_task(
            session,
            title="Write spec",
            project_id=work.id,
        )
        tasks_service.create_task(
            session,
            title="Ship deploy",
            project_id=work.id,
        )
        tasks_service.create_task(
            session,
            title="buy milk",
            project_id=errands.id,
        )
        tasks_service.create_task(
            session,
            title="Pick up dry cleaning",
            project_id=errands.id,
        )
        tasks_service.create_task(
            session,
            title="Inbox triage",
        )
    return TasksquatchTuiApp(core_factory=factory)
