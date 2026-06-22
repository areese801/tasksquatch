"""
Tests for the TUI session plumbing.

These exercise :mod:`tasksquatch.tui._session` in isolation: the
schema is initialized, the Inbox is seeded, and the default factory
hands out fresh sessions backed by a shared engine.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from tasksquatch.core.models import Project
from tasksquatch.tui._session import default_core_factory, open_tui_session


def test_open_tui_session_creates_schema_and_inbox(tmp_path: Path) -> None:
    db = tmp_path / "session.db"
    with open_tui_session(db) as session:
        inbox = session.execute(
            select(Project).where(Project.is_inbox.is_(True))
        ).scalar_one()
    assert inbox.name == "Inbox"
    assert db.exists()


def test_default_core_factory_yields_independent_sessions(tmp_path: Path) -> None:
    factory = default_core_factory(tmp_path / "factory.db")
    with factory() as session_a:
        rows = session_a.execute(select(Project)).scalars().all()
    with factory() as session_b:
        rows2 = session_b.execute(select(Project)).scalars().all()
    assert {p.name for p in rows} == {"Inbox"}
    assert {p.name for p in rows2} == {"Inbox"}
    assert session_a is not session_b
