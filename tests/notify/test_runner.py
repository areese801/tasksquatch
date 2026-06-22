"""
Tests for :func:`tasksquatch.notify.runner.run_notify`.

The runner is the thin glue layer between
:func:`tasksquatch.core.services.queries.get_due_tasks`, the
:class:`~tasksquatch.notify.config.NotifyConfig`, and a
:class:`~tasksquatch.notify.notifier.Notifier`. These tests pin time
with :mod:`freezegun` and substitute a recording notifier so we can
assert exact title/body content per fire.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from freezegun import freeze_time
from sqlalchemy.orm import Session

from tasksquatch.core.models import RecurrenceAnchor
from tasksquatch.core.services.tasks import (
    complete_task,
    create_task,
    update_task,
)
from tasksquatch.notify.config import NotifyConfig
from tasksquatch.notify.notifier import Notifier
from tasksquatch.notify.runner import run_notify

_FIXED_NOW = datetime(2026, 6, 22, 14, 30, 0)


class MockNotifier(Notifier):
    """
    Recording :class:`Notifier` that captures every ``send`` call.

    Bypasses the real :class:`Notifier.__init__` so no backend is
    constructed; the captured ``calls`` list is the source of truth for
    test assertions.
    """

    def __init__(self) -> None:
        self._backend = None
        self.calls: list[tuple[str, str]] = []

    async def send(self, title: str, body: str) -> None:
        self.calls.append((title, body))


@freeze_time(_FIXED_NOW)
async def test_run_notify_fires_for_due_task_only(session: Session) -> None:
    past_moment = _FIXED_NOW - timedelta(hours=1)
    future_moment = _FIXED_NOW + timedelta(hours=1)
    already_seen_moment = _FIXED_NOW - timedelta(hours=2)

    due = create_task(
        session,
        title="due now",
        due_date=past_moment.date(),
        due_time=past_moment.time(),
    )
    create_task(
        session,
        title="future",
        due_date=future_moment.date(),
        due_time=future_moment.time(),
    )
    seen = create_task(
        session,
        title="already notified",
        due_date=already_seen_moment.date(),
        due_time=already_seen_moment.time(),
    )
    seen.last_notified_at = already_seen_moment
    session.flush()

    notifier = MockNotifier()
    fired = await run_notify(session, now=_FIXED_NOW, notifier=notifier)

    assert fired == 1
    assert len(notifier.calls) == 1
    title, _body = notifier.calls[0]
    assert title == f"#{due.number} due now"
    session.refresh(due)
    assert due.last_notified_at == past_moment


@freeze_time(_FIXED_NOW)
async def test_run_notify_is_idempotent_for_same_occurrence(
    session: Session,
) -> None:
    past_moment = _FIXED_NOW - timedelta(hours=1)
    create_task(
        session,
        title="single occurrence",
        due_date=past_moment.date(),
        due_time=past_moment.time(),
    )

    notifier = MockNotifier()
    first = await run_notify(session, now=_FIXED_NOW, notifier=notifier)
    second = await run_notify(session, now=_FIXED_NOW, notifier=notifier)

    assert first == 1
    assert second == 0
    assert len(notifier.calls) == 1


@freeze_time(_FIXED_NOW)
async def test_reschedule_re_arms_notification(session: Session) -> None:
    initial_moment = _FIXED_NOW - timedelta(hours=1)
    new_moment = _FIXED_NOW - timedelta(minutes=15)

    task = create_task(
        session,
        title="reschedule me",
        due_date=initial_moment.date(),
        due_time=initial_moment.time(),
    )

    notifier = MockNotifier()
    assert await run_notify(session, now=_FIXED_NOW, notifier=notifier) == 1
    assert await run_notify(session, now=_FIXED_NOW, notifier=notifier) == 0

    update_task(
        session,
        task.id,
        due_date=new_moment.date(),
        due_time=new_moment.time(),
    )
    session.refresh(task)
    assert task.last_notified_at is None

    assert await run_notify(session, now=_FIXED_NOW, notifier=notifier) == 1
    session.refresh(task)
    assert task.last_notified_at == new_moment


def test_recurring_task_fires_again_after_advance(session: Session) -> None:
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
        notifier = MockNotifier()

        async def _drive_first() -> None:
            await run_notify(session, now=occurrence_one, notifier=notifier)

        import asyncio

        asyncio.run(_drive_first())
        assert len(notifier.calls) == 1

    with freeze_time(occurrence_one + timedelta(hours=1)):
        complete_task(session, task.id)

    session.refresh(task)
    assert task.due_date == occurrence_two.date()
    assert task.due_time == occurrence_two.time()
    assert task.last_notified_at is None

    with freeze_time(occurrence_two):
        import asyncio

        async def _drive_second() -> None:
            await run_notify(session, now=occurrence_two, notifier=notifier)

        asyncio.run(_drive_second())

    assert len(notifier.calls) == 2
    session.refresh(task)
    assert task.last_notified_at == occurrence_two


async def test_date_only_task_respects_day_of_time(session: Session) -> None:
    target_date = date(2026, 6, 22)
    create_task(session, title="morning chore", due_date=target_date)

    config = NotifyConfig(lead_seconds=0, day_of_time=time(9, 0))
    notifier = MockNotifier()

    # 08:30 → too early.
    fired_early = await run_notify(
        session,
        now=datetime(2026, 6, 22, 8, 30),
        config=config,
        notifier=notifier,
    )
    assert fired_early == 0
    assert notifier.calls == []

    # 09:01 → eligible.
    fired_on_time = await run_notify(
        session,
        now=datetime(2026, 6, 22, 9, 1),
        config=config,
        notifier=notifier,
    )
    assert fired_on_time == 1
    assert len(notifier.calls) == 1


async def test_lead_seconds_allows_early_fire(session: Session) -> None:
    upcoming_moment = _FIXED_NOW + timedelta(minutes=5)
    create_task(
        session,
        title="meeting soon",
        due_date=upcoming_moment.date(),
        due_time=upcoming_moment.time(),
    )

    notifier = MockNotifier()

    # No lead — not yet.
    no_lead = NotifyConfig(lead_seconds=0, day_of_time=time(9, 0))
    fired_no_lead = await run_notify(
        session, now=_FIXED_NOW, config=no_lead, notifier=notifier
    )
    assert fired_no_lead == 0

    # 15-minute lead — fires.
    long_lead = NotifyConfig(lead_seconds=900, day_of_time=time(9, 0))
    fired_with_lead = await run_notify(
        session, now=_FIXED_NOW, config=long_lead, notifier=notifier
    )
    assert fired_with_lead == 1


@freeze_time(_FIXED_NOW)
async def test_run_notify_with_no_due_tasks_returns_zero(session: Session) -> None:
    notifier = MockNotifier()
    fired = await run_notify(session, now=_FIXED_NOW, notifier=notifier)
    assert fired == 0
    assert notifier.calls == []


@freeze_time(_FIXED_NOW)
async def test_body_contains_due_and_project(session: Session) -> None:
    past_moment = _FIXED_NOW - timedelta(hours=1)
    create_task(
        session,
        title="ping",
        due_date=past_moment.date(),
        due_time=past_moment.time(),
    )

    notifier = MockNotifier()
    await run_notify(session, now=_FIXED_NOW, notifier=notifier)

    assert len(notifier.calls) == 1
    _title, body = notifier.calls[0]
    assert past_moment.date().isoformat() in body
    assert past_moment.time().strftime("%H:%M") in body
    assert "Inbox" in body
