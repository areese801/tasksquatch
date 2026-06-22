"""
Tests for :func:`tasksquatch.core.services.queries.get_due_tasks`.

Notification dedup turns on the precise relationship between the
task's notify moment, its ``last_notified_at``, and the wall clock.
We pin time with :mod:`freezegun` so the cases are deterministic.

All datetimes in this file are naive local — matching the v1
contract documented on :func:`get_due_tasks`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from freezegun import freeze_time
from sqlalchemy.orm import Session

from tasksquatch.core.models import RecurrenceAnchor
from tasksquatch.core.services.queries import get_due_tasks
from tasksquatch.core.services.tasks import complete_task, create_task

_FIXED_NOW = datetime(2026, 6, 22, 14, 30, 0)


@freeze_time(_FIXED_NOW)
def test_due_task_with_no_last_notified_is_returned(session: Session) -> None:
    notify_moment = _FIXED_NOW - timedelta(hours=1)
    task = create_task(
        session,
        title="meeting",
        due_date=notify_moment.date(),
        due_time=notify_moment.time(),
    )
    assert task.last_notified_at is None

    rows = get_due_tasks(session, now=_FIXED_NOW)
    assert [r.id for r in rows] == [task.id]


@freeze_time(_FIXED_NOW)
def test_last_notified_equal_to_moment_blocks(session: Session) -> None:
    notify_moment = _FIXED_NOW - timedelta(hours=1)
    task = create_task(
        session,
        title="meeting",
        due_date=notify_moment.date(),
        due_time=notify_moment.time(),
    )
    task.last_notified_at = notify_moment
    session.flush()

    rows = get_due_tasks(session, now=_FIXED_NOW)
    assert rows == []


@freeze_time(_FIXED_NOW)
def test_last_notified_older_than_moment_is_returned(session: Session) -> None:
    notify_moment = _FIXED_NOW - timedelta(hours=1)
    task = create_task(
        session,
        title="meeting",
        due_date=notify_moment.date(),
        due_time=notify_moment.time(),
    )
    task.last_notified_at = notify_moment - timedelta(hours=1)
    session.flush()

    rows = get_due_tasks(session, now=_FIXED_NOW)
    assert [r.id for r in rows] == [task.id]


@freeze_time(_FIXED_NOW.replace(hour=8, minute=30))
def test_date_only_not_yet_due_with_default_day_of_time(session: Session) -> None:
    task = create_task(
        session,
        title="morning chore",
        due_date=date(2026, 6, 22),
    )
    rows = get_due_tasks(session, now=datetime(2026, 6, 22, 8, 30))
    assert rows == []
    # Task exists so this is not a "no candidates" assertion either.
    assert task.due_date == date(2026, 6, 22)


@freeze_time(_FIXED_NOW.replace(hour=9, minute=1))
def test_date_only_due_at_default_day_of_time(session: Session) -> None:
    task = create_task(
        session,
        title="morning chore",
        due_date=date(2026, 6, 22),
    )
    rows = get_due_tasks(session, now=datetime(2026, 6, 22, 9, 1))
    assert [r.id for r in rows] == [task.id]


@freeze_time(_FIXED_NOW)
def test_lead_seconds_allows_early_fire(session: Session) -> None:
    notify_moment = _FIXED_NOW + timedelta(minutes=10)
    task = create_task(
        session,
        title="meeting in 10 minutes",
        due_date=notify_moment.date(),
        due_time=notify_moment.time(),
    )
    # Without lead — not yet eligible.
    assert get_due_tasks(session, now=_FIXED_NOW) == []

    # 15-minute lead — eligible now.
    rows = get_due_tasks(session, now=_FIXED_NOW, lead_seconds=900)
    assert [r.id for r in rows] == [task.id]


@freeze_time(_FIXED_NOW)
def test_no_due_date_is_skipped(session: Session) -> None:
    create_task(session, title="undated")
    assert get_due_tasks(session, now=_FIXED_NOW) == []


@freeze_time(_FIXED_NOW)
def test_completed_task_never_returned(session: Session) -> None:
    notify_moment = _FIXED_NOW - timedelta(hours=1)
    task = create_task(
        session,
        title="done",
        due_date=notify_moment.date(),
        due_time=notify_moment.time(),
    )
    complete_task(session, task.id)

    assert get_due_tasks(session, now=_FIXED_NOW) == []


def test_recurring_task_re_arms_after_advance(session: Session) -> None:
    occurrence_one = datetime(2026, 1, 5, 9, 0)
    occurrence_two = datetime(2026, 1, 6, 9, 0)

    with freeze_time(occurrence_one):
        task = create_task(
            session,
            title="daily standup",
            due_date=occurrence_one.date(),
            due_time=occurrence_one.time(),
            recurrence="FREQ=DAILY;INTERVAL=1",
            recurrence_anchor=RecurrenceAnchor.FIXED,
        )
        rows = get_due_tasks(session, now=occurrence_one)
        assert [r.id for r in rows] == [task.id]

        # Simulate the notifier firing for this occurrence.
        task.last_notified_at = occurrence_one
        session.flush()
        # No further fires for this occurrence.
        assert get_due_tasks(session, now=occurrence_one) == []

    # Complete-in-place advances the recurrence and clears
    # last_notified_at — see complete_task.
    with freeze_time(occurrence_one + timedelta(hours=1)):
        complete_task(session, task.id)
    assert task.due_date == occurrence_two.date()
    assert task.due_time == occurrence_two.time()
    assert task.last_notified_at is None

    with freeze_time(occurrence_two):
        rows = get_due_tasks(session, now=occurrence_two)
        assert [r.id for r in rows] == [task.id]


@freeze_time(_FIXED_NOW)
def test_ordering_by_notify_moment_then_number(session: Session) -> None:
    earlier = _FIXED_NOW - timedelta(hours=2)
    later = _FIXED_NOW - timedelta(minutes=30)

    # Create the "later" task first so its number is lower.
    task_later = create_task(
        session,
        title="later moment, lower number",
        due_date=later.date(),
        due_time=later.time(),
    )
    task_earlier = create_task(
        session,
        title="earlier moment, higher number",
        due_date=earlier.date(),
        due_time=earlier.time(),
    )
    # Two ties on notify moment — distinguished by number.
    task_tie_low = create_task(
        session,
        title="tie low",
        due_date=earlier.date(),
        due_time=earlier.time(),
    )
    task_tie_high = create_task(
        session,
        title="tie high",
        due_date=earlier.date(),
        due_time=earlier.time(),
    )
    assert (
        task_later.number
        < task_earlier.number
        < task_tie_low.number
        < task_tie_high.number
    )

    rows = get_due_tasks(session, now=_FIXED_NOW)
    assert [r.id for r in rows] == [
        task_earlier.id,
        task_tie_low.id,
        task_tie_high.id,
        task_later.id,
    ]


@freeze_time(_FIXED_NOW)
def test_custom_day_of_time_for_date_only(session: Session) -> None:
    task = create_task(
        session,
        title="afternoon date-only",
        due_date=_FIXED_NOW.date(),
    )
    # At 14:30 with day_of_time=15:00 the date-only task is not yet
    # eligible.
    rows = get_due_tasks(session, now=_FIXED_NOW, day_of_time=time(15, 0))
    assert rows == []
    # At 15:00 with the same day_of_time it is.
    rows = get_due_tasks(
        session,
        now=_FIXED_NOW.replace(hour=15, minute=0),
        day_of_time=time(15, 0),
    )
    assert [r.id for r in rows] == [task.id]
