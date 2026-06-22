"""
Completion / uncompletion lifecycle tests.

Recurring-task advance is exercised in ``test_tasks_recurrence.py``;
these tests cover the simpler non-recurring paths and the idempotency
contracts the spec calls out for :func:`uncomplete_task`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import AlreadyCompletedError, NotFoundError
from tasksquatch.core.models import ActivityEventType, ActivityLog
from tasksquatch.core.services.tasks import (
    complete_task,
    create_task,
    uncomplete_task,
)


def _count(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def test_complete_task_non_recurring_marks_completed(session: Session) -> None:
    task = create_task(session, title="t")
    when = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    complete_task(session, task.id, when=when)
    assert task.completed is True
    assert task.completed_at == when

    row = session.execute(
        select(ActivityLog).where(ActivityLog.event_type == ActivityEventType.COMPLETED)
    ).scalar_one()
    assert row.detail == {"task_id": task.id, "at": when.isoformat()}


def test_complete_task_already_completed_raises(session: Session) -> None:
    task = create_task(session, title="t")
    complete_task(session, task.id)
    with pytest.raises(AlreadyCompletedError):
        complete_task(session, task.id)


def test_complete_task_uses_default_when(session: Session) -> None:
    task = create_task(session, title="t")
    before = datetime.now(UTC)
    complete_task(session, task.id)
    after = datetime.now(UTC)
    assert task.completed_at is not None
    # completed_at is stored as a naive datetime by SQLAlchemy's
    # DateTime column on SQLite, but we set a tz-aware value before
    # flush, so the in-memory copy retains tzinfo on this same session.
    assert before <= task.completed_at <= after


def test_complete_task_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        complete_task(session, "00000000-0000-7000-8000-000000000000")


def test_uncomplete_task_idempotent_on_incomplete(session: Session) -> None:
    task = create_task(session, title="t")
    uncomplete_task(session, task.id)
    assert task.completed is False
    assert _count(session, ActivityEventType.UNCOMPLETED) == 0


def test_uncomplete_task_reverses_completion(session: Session) -> None:
    task = create_task(session, title="t")
    complete_task(session, task.id)
    assert task.completed is True

    uncomplete_task(session, task.id)
    assert task.completed is False
    assert task.completed_at is None
    assert _count(session, ActivityEventType.UNCOMPLETED) == 1


def test_uncomplete_task_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        uncomplete_task(session, "00000000-0000-7000-8000-000000000000")
