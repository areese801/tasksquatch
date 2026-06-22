from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.models import ActivityEventType, ActivityLog
from tasksquatch.core.services.activity import emit


def test_emit_creates_row_with_event_type_and_detail(session: Session) -> None:
    payload = {"project_id": "abc", "name": "Errands"}
    row = emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_CREATED,
        detail=payload,
    )

    assert row.id is not None
    assert row.event_type == ActivityEventType.PROJECT_CREATED
    assert row.detail == payload
    assert row.task_id is None
    assert row.created_at is not None


def test_emit_with_task_id_persists_value(session: Session) -> None:
    row = emit(
        session,
        task_id=None,
        event_type=ActivityEventType.CREATED,
        detail={"hello": "world"},
    )
    fetched = session.execute(
        select(ActivityLog).where(ActivityLog.id == row.id)
    ).scalar_one()
    assert fetched.task_id is None
    assert fetched.detail == {"hello": "world"}


def test_emit_default_detail_is_empty_dict(session: Session) -> None:
    row = emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_CREATED,
    )
    assert row.detail == {}


def test_emit_multiple_rows_are_ordered_by_created_at(session: Session) -> None:
    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_CREATED,
        detail={"i": 1},
    )
    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_RENAMED,
        detail={"i": 2},
    )
    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_DELETED,
        detail={"i": 3},
    )

    rows = (
        session.execute(select(ActivityLog).order_by(ActivityLog.created_at))
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert [r.detail["i"] for r in rows] == [1, 2, 3]


def test_emit_coerces_mapping_to_dict(session: Session) -> None:
    from types import MappingProxyType

    frozen = MappingProxyType({"key": "value", "n": 42})
    row = emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_CREATED,
        detail=frozen,
    )

    assert row.detail == {"key": "value", "n": 42}
    assert isinstance(row.detail, dict)


def test_emit_json_detail_round_trip(session: Session) -> None:
    payload = {
        "nested": {"a": 1, "b": [1, 2, 3]},
        "string": "hello",
        "bool": True,
        "null": None,
    }
    row = emit(
        session,
        task_id=None,
        event_type=ActivityEventType.UPDATED,
        detail=payload,
    )
    row_id = row.id

    session.expire_all()
    fetched = session.execute(
        select(ActivityLog).where(ActivityLog.id == row_id)
    ).scalar_one()
    assert fetched.detail == payload
