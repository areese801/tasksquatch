from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, select

from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.models import ActivityEventType, ActivityLog


def test_activity_log_accepts_json_detail(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "activity.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    payload = {"from": "P4", "to": "P1", "by": "cli"}

    with session_scope(SessionLocal) as session:
        log = ActivityLog(
            event_type=ActivityEventType.PRIORITY_CHANGED,
            detail=payload,
        )
        session.add(log)
        session.flush()
        log_id = log.id

    with SessionLocal() as session:
        log = session.execute(
            select(ActivityLog).where(ActivityLog.id == log_id)
        ).scalar_one()
        assert log.detail == payload
        assert log.event_type == ActivityEventType.PRIORITY_CHANGED


def test_activity_log_has_no_updated_at_column() -> None:
    columns = {c.name for c in ActivityLog.__table__.columns}

    assert "created_at" in columns
    assert "updated_at" not in columns


def test_activity_log_indexes_task_id_and_created_at(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "activity.db")
    init_schema(engine)

    indexes = inspect(engine).get_indexes("activity_log")
    index_names = {idx["name"] for idx in indexes}

    assert "ix_activity_task_id" in index_names
    assert "ix_activity_created_at" in index_names
    assert "ix_activity_event_type" in index_names
