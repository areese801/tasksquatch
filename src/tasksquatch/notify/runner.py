"""
Orchestration for ``tasksquatch notify``.

The runner glues four pieces together:

* :func:`tasksquatch.core.services.queries.get_due_tasks` — which tasks
  should fire right now.
* :class:`tasksquatch.notify.config.NotifyConfig` — knobs the user has
  configured (lead time, day-of fire time).
* :class:`tasksquatch.notify.notifier.Notifier` — the desktop backend.
* The task row itself — stamping ``last_notified_at`` to the per-
  occurrence ``notify_moment`` so the next pass deduplicates correctly.

It is exposed as an ``async def run_notify`` (the natural shape for the
desktop_notifier coroutine API) and a synchronous
:func:`run_notify_sync` wrapper the CLI command can call without
caring about event loops.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from tasksquatch.core.services.queries import get_due_tasks
from tasksquatch.notify.config import NotifyConfig, load_notify_config
from tasksquatch.notify.notifier import Notifier

if TYPE_CHECKING:
    from tasksquatch.core.models import Task


def _notify_moment(task: Task, config: NotifyConfig) -> datetime:
    """
    Compute the wall-clock notify moment for a single task.

    Mirrors the logic in
    :func:`tasksquatch.core.services.queries.get_due_tasks`: a task's
    notify moment is ``datetime.combine(due_date, due_time)`` if
    ``due_time`` is set, otherwise ``datetime.combine(due_date,
    config.day_of_time)`` for date-only tasks. The caller is expected
    to only pass tasks where ``due_date is not None`` — every row
    returned by :func:`get_due_tasks` satisfies that.

    :param task: A task selected for notification.
    :param config: The active notify config (supplies the date-only
        ``day_of_time``).
    :returns: The notify moment as a naive local datetime.
    :raises ValueError: If ``task.due_date`` is ``None``.
    """
    if task.due_date is None:
        raise ValueError(
            f"Task {task.id!r} has no due_date; cannot compute notify_moment."
        )
    scheduled_time = task.due_time if task.due_time is not None else config.day_of_time
    return datetime.combine(task.due_date, scheduled_time)


def _format_body(task: Task) -> str:
    """
    Build the notification body text for a task.

    The body is plain text so it renders identically across macOS, Linux
    (DBus), and Windows backends. Currently includes the schedule (date
    plus optional time) and the project name; the title is rendered in
    the notification heading by the runner.

    :param task: The task being notified about.
    :returns: A single-line plain-text body string.
    """
    parts: list[str] = []
    if task.due_date is not None:
        if task.due_time is not None:
            parts.append(
                f"Due {task.due_date.isoformat()} {task.due_time.strftime('%H:%M')}"
            )
        else:
            parts.append(f"Due {task.due_date.isoformat()}")
    project = task.project
    if project is not None:
        parts.append(f"Project: {project.name}")
    return " — ".join(parts) if parts else ""


async def run_notify(
    session: Session,
    *,
    now: datetime | None = None,
    config: NotifyConfig | None = None,
    notifier: Notifier | None = None,
) -> int:
    """
    Fire desktop notifications for every task that is due.

    Pulls eligible tasks via :func:`get_due_tasks`, fires one
    notification per task, and stamps each task's
    :attr:`Task.last_notified_at` to the per-occurrence notify moment.
    Stamping to the moment (not to ``now``) is what keeps the dedup
    invariant honest even when the notifier runs late.

    All mutations happen inside a single transaction: a commit at the
    end of the loop. If any step raises, the session rolls back and no
    ``last_notified_at`` updates leak through — re-running the notifier
    will retry the same set.

    :param session: An open SQLAlchemy session.
    :param now: Override the current time; defaults to a freshly
        stamped :func:`datetime.now` (naive local) so the semantics
        match :func:`get_due_tasks`.
    :param config: The notify config to use; defaults to
        :func:`load_notify_config`.
    :param notifier: The notifier to fire on; defaults to a real
        :class:`Notifier` (which degrades to a no-op on platforms with
        no supported backend).
    :returns: The number of notifications fired.
    """
    effective_now = now if now is not None else datetime.now()
    effective_config = config if config is not None else load_notify_config()
    effective_notifier = notifier if notifier is not None else Notifier()

    due_tasks = get_due_tasks(
        session,
        now=effective_now,
        lead_seconds=effective_config.lead_seconds,
        day_of_time=effective_config.day_of_time,
    )

    fired = 0
    for task in due_tasks:
        moment = _notify_moment(task, effective_config)
        title = f"#{task.number} {task.title}"
        body = _format_body(task)
        await effective_notifier.send(title=title, body=body)
        task.last_notified_at = moment
        session.flush()
        fired += 1

    session.commit()
    return fired


def run_notify_sync(
    session: Session,
    *,
    now: datetime | None = None,
    config: NotifyConfig | None = None,
    notifier: Notifier | None = None,
) -> int:
    """
    Synchronous wrapper around :func:`run_notify`.

    Intended for the CLI command, which lives outside an event loop.
    Internally drives :func:`asyncio.run` so the desktop_notifier
    coroutines have somewhere to execute.

    :param session: An open SQLAlchemy session.
    :param now: See :func:`run_notify`.
    :param config: See :func:`run_notify`.
    :param notifier: See :func:`run_notify`.
    :returns: The number of notifications fired.
    """
    return asyncio.run(
        run_notify(
            session,
            now=now,
            config=config,
            notifier=notifier,
        )
    )
