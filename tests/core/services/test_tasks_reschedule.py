"""
Tests for :func:`tasksquatch.core.services.tasks.reschedule_overdue`.

Overdue selection mirrors ``docs/spec.md`` §6: incomplete tasks with a
``due_date`` strictly before today. Recurring tasks are excluded by
default because completing them advances the schedule in place. Each
bumped row emits one ``RESCHEDULED`` activity entry carrying the
``"overdue_auto_bump"`` reason so the auto-bump path is
distinguishable from a user-driven update.
"""

from __future__ import annotations

from datetime import date, time

from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.models import ActivityEventType, ActivityLog, RecurrenceAnchor
from tasksquatch.core.services.tasks import (
    create_task,
    reschedule_overdue,
)

_FIXED_TODAY = date(2026, 6, 25)


@freeze_time("2026-06-25")
def test_overdue_task_is_bumped(session: Session) -> None:
    task = create_task(
        session,
        title="ancient",
        due_date=date(2026, 6, 20),
        due_time=time(9, 30),
    )
    task.last_notified_at = None
    session.flush()

    bumped = reschedule_overdue(session)

    assert [t.id for t in bumped] == [task.id]
    assert task.due_date == _FIXED_TODAY
    assert task.due_time == time(9, 30)
    assert task.last_notified_at is None


@freeze_time("2026-06-25")
def test_due_today_left_alone(session: Session) -> None:
    task = create_task(
        session,
        title="today",
        due_date=_FIXED_TODAY,
    )
    bumped = reschedule_overdue(session)

    assert bumped == []
    assert task.due_date == _FIXED_TODAY


@freeze_time("2026-06-25")
def test_future_task_left_alone(session: Session) -> None:
    task = create_task(
        session,
        title="future",
        due_date=date(2026, 7, 1),
    )
    bumped = reschedule_overdue(session)

    assert bumped == []
    assert task.due_date == date(2026, 7, 1)


@freeze_time("2026-06-25")
def test_completed_task_excluded(session: Session) -> None:
    task = create_task(
        session,
        title="done already",
        due_date=date(2025, 1, 1),
    )
    task.completed = True
    session.flush()

    bumped = reschedule_overdue(session)

    assert bumped == []
    assert task.due_date == date(2025, 1, 1)


@freeze_time("2026-06-25")
def test_recurring_excluded_by_default(session: Session) -> None:
    task = create_task(
        session,
        title="daily",
        due_date=date(2025, 1, 1),
        recurrence="FREQ=DAILY",
        recurrence_anchor=RecurrenceAnchor.FIXED,
    )

    bumped = reschedule_overdue(session)

    assert bumped == []
    assert task.due_date == date(2025, 1, 1)


@freeze_time("2026-06-25")
def test_recurring_included_with_flag(session: Session) -> None:
    task = create_task(
        session,
        title="daily",
        due_date=date(2025, 1, 1),
        recurrence="FREQ=DAILY",
        recurrence_anchor=RecurrenceAnchor.FIXED,
    )

    bumped = reschedule_overdue(session, include_recurring=True)

    assert [t.id for t in bumped] == [task.id]
    assert task.due_date == _FIXED_TODAY


@freeze_time("2026-06-25")
def test_activity_log_event_per_bumped_task(session: Session) -> None:
    tasks = [
        create_task(
            session,
            title=f"old-{i}",
            due_date=date(2025, 1, 1),
            due_time=time(10, 0),
        )
        for i in range(3)
    ]
    task_ids = {t.id for t in tasks}

    reschedule_overdue(session)

    rows = list(
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.RESCHEDULED,
                ActivityLog.task_id.in_(task_ids),
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    for row in rows:
        assert row.detail["reason"] == "overdue_auto_bump"
        assert row.detail["from"] == {"date": "2025-01-01", "time": "10:00:00"}
        assert row.detail["to"] == {"date": "2026-06-25", "time": "10:00:00"}


@freeze_time("2026-06-25")
def test_returns_sorted_by_number(session: Session) -> None:
    t1 = create_task(session, title="a", due_date=date(2025, 1, 1))
    t2 = create_task(session, title="b", due_date=date(2025, 6, 1))
    t3 = create_task(session, title="c", due_date=date(2024, 3, 1))

    bumped = reschedule_overdue(session)

    assert [t.id for t in bumped] == [t1.id, t2.id, t3.id]
    assert [t.number for t in bumped] == sorted(t.number for t in (t1, t2, t3))


@freeze_time("2026-06-25")
def test_idempotent_on_clean_day(session: Session) -> None:
    create_task(session, title="old", due_date=date(2025, 1, 1))

    first = reschedule_overdue(session)
    assert len(first) == 1

    baseline = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.RESCHEDULED,
            )
        )
        .scalars()
        .all()
    )

    second = reschedule_overdue(session)
    assert second == []

    after = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.RESCHEDULED,
            )
        )
        .scalars()
        .all()
    )

    assert len(after) == len(baseline)
