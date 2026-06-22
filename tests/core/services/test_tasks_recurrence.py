"""
Recurring-task advance tests for :func:`complete_task`.

The recurrence helpers themselves are covered in
``tests/core/test_recurrence.py``; this file verifies the task
service's behavior on top of them — that completion advances the row
in place, emits both ``COMPLETED`` and ``RECURRENCE_ADVANCED``,
clears :attr:`Task.last_notified_at`, and that an exhausted rule
flips the task to permanently completed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    RecurrenceAnchor,
)
from tasksquatch.core.services.tasks import complete_task, create_task


def test_complete_recurring_fixed_advances_one_day(session: Session) -> None:
    task = create_task(
        session,
        title="daily",
        due_date=date(2026, 1, 5),
        recurrence="FREQ=DAILY;INTERVAL=1",
        recurrence_anchor=RecurrenceAnchor.FIXED,
    )
    task.last_notified_at = datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
    session.flush()

    when = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    complete_task(session, task.id, when=when)

    assert task.due_date == date(2026, 1, 6)
    assert task.completed is False
    assert task.completed_at is None
    assert task.last_notified_at is None

    rows = (
        session.execute(select(ActivityLog).order_by(ActivityLog.created_at.asc()))
        .scalars()
        .all()
    )
    event_types = [row.event_type for row in rows]
    # CREATED, COMPLETED, RECURRENCE_ADVANCED — in that order.
    assert event_types[-2:] == [
        ActivityEventType.COMPLETED,
        ActivityEventType.RECURRENCE_ADVANCED,
    ]

    completed = rows[-2]
    assert completed.detail == {
        "task_id": task.id,
        "at": when.isoformat(),
        "advanced_to": {"date": "2026-01-06", "time": None},
    }

    advanced = rows[-1]
    assert advanced.detail == {
        "task_id": task.id,
        "from": {"date": "2026-01-05", "time": None},
        "to": {"date": "2026-01-06", "time": None},
    }


def test_complete_recurring_fixed_until_exhausts(session: Session) -> None:
    # UNTIL on 2026-01-07T00:00:00 means the rule emits 2026-01-08 and later
    # are not generated. Starting from 2026-01-08 with FIXED anchor means
    # rule.after(2026-01-08T00:00) returns None.
    task = create_task(
        session,
        title="daily-until",
        due_date=date(2026, 1, 8),
        recurrence="FREQ=DAILY;INTERVAL=1;UNTIL=20260107T000000",
        recurrence_anchor=RecurrenceAnchor.FIXED,
    )
    when = datetime(2026, 1, 8, 9, 0, tzinfo=UTC)
    complete_task(session, task.id, when=when)

    assert task.completed is True
    assert task.completed_at == when
    # Schedule is left where it was — no further occurrence to advance to.
    assert task.due_date == date(2026, 1, 8)

    completed = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.COMPLETED
            )
        )
        .scalars()
        .all()
    )
    assert len(completed) == 1
    assert completed[0].detail == {
        "task_id": task.id,
        "at": when.isoformat(),
        "recurrence_exhausted": True,
    }

    advanced = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.RECURRENCE_ADVANCED
            )
        )
        .scalars()
        .all()
    )
    assert advanced == []


def test_complete_recurring_relative_advances_after_completion(
    session: Session,
) -> None:
    task = create_task(
        session,
        title="every-3-days",
        due_date=date(2026, 1, 5),
        recurrence="FREQ=DAILY;INTERVAL=3",
        recurrence_anchor=RecurrenceAnchor.RELATIVE,
    )
    when = datetime(2026, 1, 10, 10, 0)
    complete_task(session, task.id, when=when)

    assert task.due_date == date(2026, 1, 11)
    assert task.completed is False
