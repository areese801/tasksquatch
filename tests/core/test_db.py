from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from tasksquatch.core.db import (
    TaskNumberSeq,
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)


def test_pragmas_set_on_fresh_connection(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "test.db")
    with engine.connect() as conn:
        foreign_keys = conn.execute(
            text("SELECT foreign_keys FROM pragma_foreign_keys")
        ).scalar_one()
        journal_mode = conn.execute(
            text("SELECT journal_mode FROM pragma_journal_mode")
        ).scalar_one()
        synchronous = conn.execute(
            text("SELECT synchronous FROM pragma_synchronous")
        ).scalar_one()
        busy_timeout = conn.execute(
            text("SELECT timeout FROM pragma_busy_timeout")
        ).scalar_one()

    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"
    assert synchronous == 1
    assert busy_timeout == 5000


def test_init_schema_creates_task_number_seq_table(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "test.db")
    init_schema(engine)

    inspector = inspect(engine)
    assert "task_number_seq" in inspector.get_table_names()


def test_session_scope_commits_on_normal_exit(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        session.add(TaskNumberSeq(id=1, last_number=7))

    engine_reopened = create_engine_for_path(db_path)
    SessionReopened = create_session_factory(engine_reopened)
    with SessionReopened() as session:
        row = session.execute(select(TaskNumberSeq)).scalar_one()
        assert row.id == 1
        assert row.last_number == 7


def test_session_scope_rolls_back_on_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    class BoomError(RuntimeError):
        pass

    with pytest.raises(BoomError), session_scope(SessionLocal) as session:
        session.add(TaskNumberSeq(id=1, last_number=42))
        session.flush()
        raise BoomError("kaboom")

    engine_reopened = create_engine_for_path(db_path)
    SessionReopened = create_session_factory(engine_reopened)
    with SessionReopened() as session:
        rows = session.execute(select(TaskNumberSeq)).scalars().all()
        assert rows == []
