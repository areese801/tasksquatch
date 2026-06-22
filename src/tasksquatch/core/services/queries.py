"""
Read-only query helpers for tasksquatch core.

This module is the catalogue of every read the surface layers
(CLI, TUI, REST, MCP, notify) reach for. Nothing in here writes to the
database and nothing here emits to the activity log — those concerns
belong to the mutating services in sibling modules.

The query surface is intentionally narrow: a handful of lookup-by-id
helpers, a flexible :func:`list_tasks` filter, a small substring
search, a recursive subtask walker, comment / activity log listings,
and :func:`get_due_tasks` for the notifier. Surfaces that need richer
behavior are expected to compose these helpers in Python rather than
to grow the query surface in lockstep with every feature request.
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core._sentinels import UNSET, _UnsetType
from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    Comment,
    Priority,
    Task,
)

_ORDER_BY_COLUMNS: dict[str, tuple[Any, ...]] = {
    "position": (Task.position.asc(), Task.number.asc()),
    "due_date": (Task.due_date.asc(), Task.number.asc()),
    "priority": (Task.priority.asc(), Task.number.asc()),
    "created_at": (Task.created_at.asc(), Task.number.asc()),
}


def _get_task_or_raise(session: Session, task_id: str) -> Task:
    """
    Fetch a task by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :returns: The :class:`Task` row.
    :raises NotFoundError: If no task exists with that id.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError(
            f"Task {task_id!r} not found.",
            detail={"task_id": task_id},
        )
    return task


def get_task_by_id(session: Session, task_id: str) -> Task:
    """
    Look a task up by its UUIDv7 primary key.

    Relationships (``project``, ``labels``, ``comments``, ``subtasks``)
    are left lazy by default; callers that need them eagerly should
    request explicit ``selectinload`` / ``joinedload`` options on top
    of this helper.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :returns: The :class:`Task` row.
    :raises NotFoundError: If no task exists with that id.
    """
    return _get_task_or_raise(session, task_id)


def get_task_by_number(session: Session, number: int) -> Task:
    """
    Look a task up by its user-facing :attr:`Task.number`.

    Numbers are globally sequential and never reused — see
    ``docs/spec.md`` §5 — so a missing number is permanent.

    :param session: An open SQLAlchemy session.
    :param number: The task's user-facing integer number.
    :returns: The :class:`Task` row.
    :raises NotFoundError: If no task exists with that number.
    """
    stmt = select(Task).where(Task.number == number)
    task = session.execute(stmt).scalar_one_or_none()
    if task is None:
        raise NotFoundError(
            f"Task #{number} not found.",
            detail={"number": number},
        )
    return task


def list_tasks(
    session: Session,
    *,
    project_id: str | None = None,
    label_id: str | None = None,
    parent_id: str | None | _UnsetType = UNSET,
    priority: Priority | None = None,
    completed: bool | None = None,
    due_before: date | None = None,
    due_after: date | None = None,
    include_descendants: bool = False,
    order_by: str = "position",
    limit: int | None = None,
) -> list[Task]:
    """
    Return tasks filtered by the supplied criteria.

    Every supplied filter narrows the result set (AND semantics). The
    ``parent_id`` filter is three-valued: :data:`UNSET` (the default)
    leaves it unconstrained so both top-level tasks and subtasks are
    returned; ``None`` restricts to top-level tasks only; a string id
    restricts to direct children of that parent.

    ``include_descendants`` extends the ``project_id`` or
    ``parent_id="<id>"`` filter by walking subtask trees in Python.
    Recursive CTEs would express the same query in SQL, but the v1
    codebase prefers a small Python BFS for simplicity — this is not a
    hot path and avoids dialect-specific quirks.

    :param session: An open SQLAlchemy session.
    :param project_id: Restrict to tasks in this project.
    :param label_id: Restrict to tasks carrying this label.
    :param parent_id: :data:`UNSET` to leave unconstrained, ``None`` to
        return only top-level tasks, or a string id to return only the
        direct children of that task.
    :param priority: Restrict to tasks at this priority.
    :param completed: Restrict to completed (``True``) or incomplete
        (``False``) tasks.
    :param due_before: Restrict to tasks with ``due_date <= due_before``.
    :param due_after: Restrict to tasks with ``due_date >= due_after``.
    :param include_descendants: When combined with ``project_id`` or
        ``parent_id="<id>"``, also include every transitive descendant.
    :param order_by: Ordering key; one of ``"position"``,
        ``"due_date"``, ``"priority"``, ``"created_at"``.
    :param limit: Optional maximum row count.
    :returns: A list of :class:`Task` rows.
    :raises ValidationError: If ``order_by`` is not a recognized key.
    """
    if order_by not in _ORDER_BY_COLUMNS:
        raise ValidationError(
            f"Unknown order_by key {order_by!r}.",
            detail={
                "order_by": order_by,
                "allowed": sorted(_ORDER_BY_COLUMNS.keys()),
            },
        )

    stmt = select(Task)

    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)
    if label_id is not None:
        stmt = stmt.where(Task.labels.any(id=label_id))
    if not isinstance(parent_id, _UnsetType):
        if parent_id is None:
            stmt = stmt.where(Task.parent_id.is_(None))
        else:
            stmt = stmt.where(Task.parent_id == parent_id)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if completed is not None:
        stmt = stmt.where(Task.completed == completed)
    if due_before is not None:
        stmt = stmt.where(Task.due_date <= due_before)
    if due_after is not None:
        stmt = stmt.where(Task.due_date >= due_after)

    stmt = stmt.order_by(*_ORDER_BY_COLUMNS[order_by])

    rows = list(session.execute(stmt).scalars().all())

    if include_descendants and isinstance(parent_id, str):
        descendants = list_subtasks(session, parent_id, recursive=True)
        seen: set[str] = {row.id for row in rows}
        for descendant in descendants:
            if descendant.id not in seen:
                rows.append(descendant)
                seen.add(descendant.id)

    if limit is not None:
        rows = rows[:limit]

    return rows


def search_tasks(session: Session, query: str, *, limit: int = 50) -> list[Task]:
    """
    Return tasks whose title contains ``query``, case-insensitively.

    An empty or whitespace-only ``query`` returns an empty list rather
    than every task — matching no input to "everything" would be a
    surprising default. Matching uses ``LOWER(title) LIKE :pattern``
    with ``%`` wildcards around the lowercased query; SQLite's ASCII
    ``LIKE`` is already case-insensitive but the explicit ``LOWER()``
    form keeps the intent obvious to readers.

    :param session: An open SQLAlchemy session.
    :param query: The substring to look for in task titles.
    :param limit: Maximum result count; defaults to 50.
    :returns: A list of matching :class:`Task` rows ordered by
        ``number`` for stability.
    """
    stripped = query.strip()
    if not stripped:
        return []

    pattern = f"%{stripped.lower()}%"
    stmt = (
        select(Task)
        .where(func.lower(Task.title).like(pattern))
        .order_by(Task.number.asc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


def list_subtasks(
    session: Session,
    task_id: str,
    *,
    recursive: bool = True,
) -> list[Task]:
    """
    Return the subtasks of ``task_id``.

    ``recursive=False`` returns the direct children only, ordered by
    ``position``. ``recursive=True`` walks the descendants in
    breadth-first order — each level is sorted by ``position`` before
    the walk descends. The parent task itself is never included.

    :param session: An open SQLAlchemy session.
    :param task_id: The parent task's UUIDv7 string id.
    :param recursive: When ``True``, include every transitive
        descendant; when ``False``, return only the direct children.
    :returns: A list of :class:`Task` rows.
    :raises NotFoundError: If no task exists with that id.
    """
    _get_task_or_raise(session, task_id)

    def _children(parent_id: str) -> list[Task]:
        stmt = (
            select(Task)
            .where(Task.parent_id == parent_id)
            .order_by(Task.position.asc(), Task.number.asc())
        )
        return list(session.execute(stmt).scalars().all())

    if not recursive:
        return _children(task_id)

    out: list[Task] = []
    queue: deque[str] = deque([task_id])
    while queue:
        current_id = queue.popleft()
        for child in _children(current_id):
            out.append(child)
            queue.append(child.id)
    return out


def list_comments(session: Session, task_id: str) -> list[Comment]:
    """
    Return every comment attached to ``task_id`` in chronological
    order.

    The task must exist; passing an unknown id raises
    :class:`NotFoundError` rather than returning an empty list, so
    callers can distinguish "no comments yet" from "wrong id."

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :returns: A list of :class:`Comment` rows ordered by
        ``created_at`` ascending.
    :raises NotFoundError: If no task exists with that id.
    """
    _get_task_or_raise(session, task_id)
    stmt = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


def list_activity(
    session: Session,
    *,
    task_id: str | None = None,
    event_type: ActivityEventType | None = None,
    since: datetime | None = None,
    limit: int = 200,
) -> list[ActivityLog]:
    """
    Return activity log rows matching the supplied filters.

    Filters chain as AND. Results are ordered by ``created_at``
    descending so the most recent events come back first — the natural
    shape for "what just happened?" UIs.

    :param session: An open SQLAlchemy session.
    :param task_id: Restrict to rows whose ``task_id`` matches.
    :param event_type: Restrict to rows of this event type.
    :param since: Restrict to rows created at or after this timestamp.
    :param limit: Maximum row count; defaults to 200.
    :returns: A list of :class:`ActivityLog` rows, newest first.
    """
    stmt = select(ActivityLog)
    if task_id is not None:
        stmt = stmt.where(ActivityLog.task_id == task_id)
    if event_type is not None:
        stmt = stmt.where(ActivityLog.event_type == event_type)
    if since is not None:
        stmt = stmt.where(ActivityLog.created_at >= since)
    stmt = stmt.order_by(ActivityLog.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def get_due_tasks(
    session: Session,
    *,
    now: datetime,
    lead_seconds: int = 0,
    day_of_time: time = time(9, 0),
) -> list[Task]:
    """
    Return the tasks the notifier should fire on right now.

    Selection mirrors ``docs/spec.md`` §6:

    * Only incomplete tasks (``completed = False``) with a non-null
      ``due_date`` are candidates.
    * A task's **notify moment** is its scheduled wall-clock time:
      ``datetime.combine(due_date, due_time)`` when ``due_time`` is set,
      otherwise ``datetime.combine(due_date, day_of_time)`` for
      date-only tasks (so a date-only task does not silently fire at
      midnight).
    * A task is **eligible** when
      ``notify_moment <= now + timedelta(seconds=lead_seconds)``.
      ``lead_seconds`` lets the notifier fire slightly early — e.g.
      "remind me 15 minutes before a meeting".
    * A task is **due** (fires now) when it is eligible **and**
      ``last_notified_at is None`` or
      ``last_notified_at < notify_moment``. The strict ``<`` is what
      makes the dedup work: a previous notification stamped at or
      after the current notify moment means we already fired for this
      occurrence and must stay quiet.

    The dedup invariant relies on every mutation that *should* re-arm
    the notifier also resetting ``last_notified_at`` to ``None``
    (``RESCHEDULED`` clears it in :func:`update_task`;
    ``RECURRENCE_ADVANCED`` clears it in :func:`complete_task`).
    :func:`get_due_tasks` trusts that invariant and does not try to
    reason about why a particular timestamp is what it is.

    Timezones: every datetime in v1 is treated as naive local —
    ``due_date`` / ``due_time`` are stored that way, ``last_notified_at``
    is written that way, and the ``now`` argument is expected to be a
    naive local :class:`datetime` (a freshly stamped
    ``datetime.now()`` without ``tzinfo``). Callers that work in UTC
    must convert to local time before calling.

    Performance: the implementation issues a single ``SELECT`` for
    every incomplete task that has a ``due_date``, then filters in
    Python. v1 expects the notifier to be invoked every few minutes
    by cron / launchd / systemd — this is not a hot path. If the task
    table grows past tens of thousands of incomplete dated rows, push
    the filter down into SQL.

    The caller is responsible for stamping
    :attr:`Task.last_notified_at` after firing each notification —
    typically to ``notify_moment`` (not to ``now``) so the dedup
    invariant survives even when the notifier runs late.

    :param session: An open SQLAlchemy session.
    :param now: The current wall-clock time as a naive local
        :class:`datetime`.
    :param lead_seconds: How many seconds early a notification may
        fire. Defaults to zero (fire at or after notify_moment only).
    :param day_of_time: The wall-clock time used as the notify moment
        for date-only tasks. Defaults to 09:00.
    :returns: A list of :class:`Task` rows that should fire now,
        ordered by ``notify_moment`` ascending and then by
        ``Task.number`` ascending for stability.
    """
    stmt = (
        select(Task).where(Task.completed.is_(False)).where(Task.due_date.is_not(None))
    )
    candidates = list(session.execute(stmt).scalars().all())

    horizon = now + timedelta(seconds=lead_seconds)
    due: list[tuple[datetime, int, Task]] = []
    for task in candidates:
        if task.due_date is None:
            continue
        scheduled_time = task.due_time if task.due_time is not None else day_of_time
        notify_moment = datetime.combine(task.due_date, scheduled_time)
        if notify_moment > horizon:
            continue
        last = task.last_notified_at
        if last is not None and last >= notify_moment:
            continue
        due.append((notify_moment, task.number, task))

    due.sort(key=lambda item: (item[0], item[1]))
    return [task for _moment, _number, task in due]
