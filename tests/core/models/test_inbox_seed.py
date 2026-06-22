from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.models import Project
from tasksquatch.core.seed import INBOX_NAME, ensure_inbox


def test_ensure_inbox_creates_a_single_row(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "inbox.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        inbox = ensure_inbox(session)

        assert inbox.name == INBOX_NAME
        assert inbox.is_inbox is True
        assert inbox.position == 0
        assert inbox.id is not None

    with SessionLocal() as session:
        count = session.execute(select(func.count()).select_from(Project)).scalar_one()
        assert count == 1


def test_ensure_inbox_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "inbox.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        first = ensure_inbox(session)
        first_id = first.id

    with session_scope(SessionLocal) as session:
        second = ensure_inbox(session)
        assert second.id == first_id

    with SessionLocal() as session:
        count = session.execute(select(func.count()).select_from(Project)).scalar_one()
        assert count == 1


def test_partial_unique_index_blocks_a_second_inbox(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "inbox.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        ensure_inbox(session)

    with pytest.raises(IntegrityError), session_scope(SessionLocal) as session:
        session.add(Project(name="Second Inbox", is_inbox=True, position=10))
