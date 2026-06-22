"""
Task lifecycle service.

The task service is the workhorse of ``core``: every creation, edit,
reschedule, label attach, completion, and hard delete passes through
here so that the activity log records exactly one row per state
change. Surfaces (CLI, REST, MCP, ...) call into these functions
rather than mutating :class:`Task` rows directly.

A small in-house sentinel (:data:`tasksquatch.core.UNSET`) is used by
the partial-update :func:`update_task` so callers can distinguish
"do not touch this field" from "set this field to ``None``" — both
are meaningful operations and ``None`` alone cannot express the
distinction.

Recurrence is handled in place: completing a recurring task does not
archive the row, it advances :attr:`Task.due_date` /
:attr:`Task.due_time` to the next occurrence and re-arms
``completed = False`` (see :func:`complete_task`).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core._sentinels import UNSET, _UnsetType
from tasksquatch.core.errors import (
    AlreadyCompletedError,
    NotFoundError,
    ValidationError,
)
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import (
    ActivityEventType,
    Label,
    Priority,
    Project,
    RecurrenceAnchor,
    Task,
)
from tasksquatch.core.recurrence import next_occurrence, parse_rrule
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.activity import emit


def _jsonable(value: Any) -> Any:
    """
    Convert a Python value to a JSON-serializable form for the
    activity log ``detail`` column.

    ``date``, ``time``, and ``datetime`` values are rendered as ISO
    8601 strings. :class:`StrEnum` values pass through because their
    JSON encoding (via ``str``) is already correct. Everything else
    is returned unchanged so the helper is safe to call on heterogeneous
    payloads.

    :param value: The value to coerce.
    :returns: A JSON-encodable representation of ``value``.
    """
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def _schedule_payload(d: date | None, t: time | None) -> dict[str, str | None]:
    """
    Render a (date, time) pair as a JSON-friendly dict.

    Used by the ``RESCHEDULED`` and ``RECURRENCE_ADVANCED`` activity
    events so the schedule snapshot can be inspected without parsing
    nested ISO strings out of a tuple.

    :param d: The scheduled date, or ``None`` for a task with no
        scheduled date.
    :param t: The scheduled time, or ``None`` for a date-only task.
    :returns: ``{"date": iso-or-none, "time": iso-or-none}``.
    """
    return {
        "date": d.isoformat() if d is not None else None,
        "time": t.isoformat() if t is not None else None,
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


def _get_project_or_raise(session: Session, project_id: str) -> Project:
    """
    Fetch a project by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 string id.
    :returns: The :class:`Project` row.
    :raises NotFoundError: If no project exists with that id.
    """
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(
            f"Project {project_id!r} not found.",
            detail={"project_id": project_id},
        )
    return project


def _get_label_or_raise(session: Session, label_id: str) -> Label:
    """
    Fetch a label by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param label_id: The label's UUIDv7 string id.
    :returns: The :class:`Label` row.
    :raises NotFoundError: If no label exists with that id.
    """
    label = session.get(Label, label_id)
    if label is None:
        raise NotFoundError(
            f"Label {label_id!r} not found.",
            detail={"label_id": label_id},
        )
    return label


def _validate_title(title: str) -> str:
    """
    Strip whitespace from ``title`` and reject the empty result.

    :param title: The user-supplied task title.
    :returns: The stripped title.
    :raises ValidationError: When the stripped title is empty.
    """
    stripped = title.strip()
    if not stripped:
        raise ValidationError("Task title must not be empty.")
    return stripped


def _next_sibling_position(
    session: Session,
    *,
    project_id: str,
    parent_id: str | None,
) -> int:
    """
    Compute the next ``position`` value for a new sibling task.

    Siblings share the same ``project_id`` and the same ``parent_id``
    (``NULL`` parents form their own sibling group at the project's
    top level). The new task sorts after every existing sibling by
    taking ``max(existing.position) + 1000``; if no siblings exist
    the result is ``1000``.

    :param session: An open SQLAlchemy session.
    :param project_id: The destination project id.
    :param parent_id: The destination parent id, or ``None`` for a
        top-level task.
    :returns: The position to assign to the new task.
    """
    stmt = select(func.max(Task.position)).where(Task.project_id == project_id)
    if parent_id is None:
        stmt = stmt.where(Task.parent_id.is_(None))
    else:
        stmt = stmt.where(Task.parent_id == parent_id)
    max_position = session.execute(stmt).scalar()
    return (max_position or 0) + 1000


def create_task(
    session: Session,
    *,
    title: str,
    project_id: str | None = None,
    parent_id: str | None = None,
    description: str | None = None,
    priority: Priority = Priority.P4,
    due_date: date | None = None,
    due_time: time | None = None,
    recurrence: str | None = None,
    recurrence_anchor: RecurrenceAnchor = RecurrenceAnchor.FIXED,
    label_ids: Iterable[str] = (),
) -> Task:
    """
    Insert a new task and emit a ``CREATED`` activity row.

    Resolves the destination project (defaulting to the Inbox), validates
    the parent (if any) shares that project, validates the RRULE string
    if recurrence is requested, allocates a fresh user-facing ``number``,
    auto-positions after existing siblings, attaches the requested
    labels, and flushes the row to the session before returning it.

    :param session: An open SQLAlchemy session.
    :param title: Human-readable task title. Stripped before validation.
    :param project_id: Destination project id; defaults to the Inbox.
    :param parent_id: Optional parent task id for a subtask.
    :param description: Optional free-form description.
    :param priority: Priority level; defaults to ``P4``.
    :param due_date: Optional scheduled date.
    :param due_time: Optional scheduled time (date-only tasks pass
        ``None``).
    :param recurrence: Optional RFC 5545 RRULE string. Validated but
        not normalized.
    :param recurrence_anchor: How the recurrence advances on completion.
    :param label_ids: Iterable of label ids to attach to the new task.
    :returns: The freshly-flushed :class:`Task`.
    :raises ValidationError: If the title is empty after stripping or
        if the parent's project differs from the destination project.
    :raises NotFoundError: If ``project_id``, ``parent_id``, or any
        label id does not exist.
    :raises RecurrenceError: If ``recurrence`` is non-empty but the
        RRULE string cannot be parsed.
    """
    clean_title = _validate_title(title)

    if project_id is None:
        resolved_project_id = ensure_inbox(session).id
    else:
        resolved_project_id = _get_project_or_raise(session, project_id).id

    if parent_id is not None:
        parent = _get_task_or_raise(session, parent_id)
        if parent.project_id != resolved_project_id:
            raise ValidationError(
                "Subtask must belong to the same project as its parent.",
                detail={
                    "parent_id": parent_id,
                    "parent_project_id": parent.project_id,
                    "task_project_id": resolved_project_id,
                },
            )

    if recurrence is not None and recurrence.strip():
        parse_rrule(recurrence)

    labels: list[Label] = [_get_label_or_raise(session, lid) for lid in label_ids]

    number = allocate_task_number(session)
    position = _next_sibling_position(
        session,
        project_id=resolved_project_id,
        parent_id=parent_id,
    )

    task = Task(
        number=number,
        title=clean_title,
        description=description,
        project_id=resolved_project_id,
        parent_id=parent_id,
        priority=priority,
        due_date=due_date,
        due_time=due_time,
        recurrence=recurrence,
        recurrence_anchor=recurrence_anchor,
        position=position,
    )
    for label in labels:
        task.labels.append(label)
    session.add(task)
    session.flush()

    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.CREATED,
        detail={
            "task_id": task.id,
            "number": task.number,
            "project_id": task.project_id,
            "title": task.title,
        },
    )
    return task


def update_task(
    session: Session,
    task_id: str,
    *,
    title: str | _UnsetType = UNSET,
    description: str | None | _UnsetType = UNSET,
    priority: Priority | _UnsetType = UNSET,
    due_date: date | None | _UnsetType = UNSET,
    due_time: time | None | _UnsetType = UNSET,
    recurrence: str | None | _UnsetType = UNSET,
    recurrence_anchor: RecurrenceAnchor | _UnsetType = UNSET,
) -> Task:
    """
    Apply a partial update to a task and emit the relevant activity
    rows.

    Each argument defaults to :data:`UNSET`; arguments left at
    :data:`UNSET` are not touched. Arguments passed explicitly as
    ``None`` (where the field is nullable) clear the underlying
    column. The function computes a diff of every field whose new
    value differs from the current value and emits a single
    ``UPDATED`` row whose ``detail.changes`` carries that diff; in
    addition, ``PRIORITY_CHANGED`` and ``RESCHEDULED`` rows fire for
    those specific fields. A reschedule clears
    :attr:`Task.last_notified_at` so the notify service re-fires on
    the next pass.

    When the diff is empty the function is a complete no-op: no
    activity row is written and the task is returned unchanged.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param title: New title, or :data:`UNSET`.
    :param description: New description (may be ``None``), or
        :data:`UNSET`.
    :param priority: New priority, or :data:`UNSET`.
    :param due_date: New due date (may be ``None``), or :data:`UNSET`.
    :param due_time: New due time (may be ``None``), or :data:`UNSET`.
    :param recurrence: New RRULE string (may be ``None`` to clear),
        or :data:`UNSET`. Validated when set.
    :param recurrence_anchor: New recurrence anchor, or :data:`UNSET`.
    :returns: The (possibly-mutated) :class:`Task`.
    :raises NotFoundError: If no task exists with that id.
    :raises ValidationError: If a supplied title is empty after
        stripping.
    :raises RecurrenceError: If a supplied recurrence string is
        non-empty but cannot be parsed.
    """
    task = _get_task_or_raise(session, task_id)

    if not isinstance(title, _UnsetType):
        title = _validate_title(title)

    if (
        not isinstance(recurrence, _UnsetType)
        and recurrence is not None
        and recurrence.strip()
    ):
        parse_rrule(recurrence)

    incoming: dict[str, Any] = {
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date,
        "due_time": due_time,
        "recurrence": recurrence,
        "recurrence_anchor": recurrence_anchor,
    }

    diff: dict[str, list[Any]] = {}
    for field, new_value in incoming.items():
        if isinstance(new_value, _UnsetType):
            continue
        old_value = getattr(task, field)
        if old_value == new_value:
            continue
        diff[field] = [_jsonable(old_value), _jsonable(new_value)]
        setattr(task, field, new_value)

    if not diff:
        return task

    schedule_changed = "due_date" in diff or "due_time" in diff
    if schedule_changed:
        task.last_notified_at = None

    session.flush()

    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.UPDATED,
        detail={"task_id": task.id, "changes": diff},
    )

    if "priority" in diff:
        old_priority, new_priority = diff["priority"]
        emit(
            session,
            task_id=task.id,
            event_type=ActivityEventType.PRIORITY_CHANGED,
            detail={"task_id": task.id, "from": old_priority, "to": new_priority},
        )

    if schedule_changed:
        current_date_iso = _jsonable(task.due_date)
        current_time_iso = _jsonable(task.due_time)
        date_diff = diff.get("due_date")
        time_diff = diff.get("due_time")
        old_date = date_diff[0] if date_diff is not None else current_date_iso
        new_date = date_diff[1] if date_diff is not None else current_date_iso
        old_time = time_diff[0] if time_diff is not None else current_time_iso
        new_time = time_diff[1] if time_diff is not None else current_time_iso
        emit(
            session,
            task_id=task.id,
            event_type=ActivityEventType.RESCHEDULED,
            detail={
                "task_id": task.id,
                "from": {"date": old_date, "time": old_time},
                "to": {"date": new_date, "time": new_time},
            },
        )

    return task


def _walk_descendants(task: Task) -> list[Task]:
    """
    Return every descendant of ``task`` in breadth-first order.

    The ``task`` itself is not included. Used by :func:`move_task` to
    propagate a new ``project_id`` to every subtask under the moved
    root.

    :param task: The task whose descendants to collect.
    :returns: A flat list of every transitive subtask of ``task``.
    """
    descendants: list[Task] = []
    queue: deque[Task] = deque(task.subtasks)
    while queue:
        current = queue.popleft()
        descendants.append(current)
        queue.extend(current.subtasks)
    return descendants


def move_task(
    session: Session,
    task_id: str,
    *,
    new_project_id: str,
) -> Task:
    """
    Move a top-level task to a different project, taking every
    descendant along with it.

    The subtask-shares-project invariant is enforced recursively: every
    transitive descendant has its ``project_id`` rewritten to match the
    new destination. Moving a subtask directly is disallowed — the
    caller must detach it from its parent first (via :func:`set_parent`
    with ``new_parent_id=None``) so the move is unambiguous.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param new_project_id: The destination project's id.
    :returns: The mutated :class:`Task`.
    :raises NotFoundError: If the task or destination project is
        missing.
    :raises ValidationError: If the task has a parent (must be
        detached first).
    """
    task = _get_task_or_raise(session, task_id)
    if task.parent_id is not None:
        raise ValidationError(
            "Cannot move a subtask directly; detach it from its parent first.",
            detail={"task_id": task.id, "parent_id": task.parent_id},
        )

    new_project = _get_project_or_raise(session, new_project_id)
    old_project_id = task.project_id

    if old_project_id == new_project.id:
        return task

    descendants = _walk_descendants(task)
    task.project_id = new_project.id
    for child in descendants:
        child.project_id = new_project.id
    session.flush()

    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.MOVED,
        detail={
            "task_id": task.id,
            "from_project_id": old_project_id,
            "to_project_id": new_project.id,
            "descendant_count": len(descendants),
        },
    )
    return task


def set_parent(
    session: Session,
    task_id: str,
    *,
    new_parent_id: str | None,
) -> Task:
    """
    Reparent a task, or detach it to the project top level.

    When ``new_parent_id`` is ``None`` the task is detached: its
    ``parent_id`` is cleared and a single ``UPDATED`` activity row
    records the change. When ``new_parent_id`` is supplied, the
    candidate parent must exist, share the same project, and not
    produce a cycle (the candidate's ancestor chain must not contain
    ``task_id``).

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param new_parent_id: The new parent id, or ``None`` to detach.
    :returns: The mutated :class:`Task`.
    :raises NotFoundError: If the task or the new parent is missing.
    :raises ValidationError: If the parent belongs to a different
        project, or if attaching would form a cycle.
    """
    task = _get_task_or_raise(session, task_id)
    old_parent_id = task.parent_id

    if new_parent_id is None:
        if old_parent_id is None:
            return task
        task.parent_id = None
        session.flush()
        emit(
            session,
            task_id=task.id,
            event_type=ActivityEventType.UPDATED,
            detail={
                "task_id": task.id,
                "changes": {"parent_id": [old_parent_id, None]},
            },
        )
        return task

    if new_parent_id == old_parent_id:
        return task

    new_parent = _get_task_or_raise(session, new_parent_id)
    if new_parent.project_id != task.project_id:
        raise ValidationError(
            "Cross-project parent forbidden.",
            detail={
                "task_id": task.id,
                "task_project_id": task.project_id,
                "parent_id": new_parent.id,
                "parent_project_id": new_parent.project_id,
            },
        )

    cursor: Task | None = new_parent
    while cursor is not None:
        if cursor.id == task.id:
            raise ValidationError(
                "Setting this parent would create a cycle.",
                detail={"task_id": task.id, "new_parent_id": new_parent_id},
            )
        cursor = cursor.parent

    task.parent_id = new_parent.id
    session.flush()
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.UPDATED,
        detail={
            "task_id": task.id,
            "changes": {"parent_id": [old_parent_id, new_parent.id]},
        },
    )
    return task


def reorder_task(
    session: Session,
    task_id: str,
    *,
    new_position: int,
) -> Task:
    """
    Move a task to a new sort ``position`` within its sibling list.

    Emits a single ``UPDATED`` activity row carrying the old/new
    position pair. A no-op reorder (``new_position`` equal to the
    current position) returns the task without writing to the log.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param new_position: The new ``position`` value.
    :returns: The mutated :class:`Task`.
    :raises NotFoundError: If no task exists with that id.
    """
    task = _get_task_or_raise(session, task_id)
    old_position = task.position
    if old_position == new_position:
        return task
    task.position = new_position
    session.flush()
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.UPDATED,
        detail={
            "task_id": task.id,
            "changes": {"position": [old_position, new_position]},
        },
    )
    return task


def add_label(session: Session, task_id: str, label_id: str) -> Task:
    """
    Attach a label to a task.

    Idempotent: re-attaching an already-attached label is a silent
    no-op and does not write to the activity log.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param label_id: The label's UUIDv7 string id.
    :returns: The :class:`Task`, with the label attached.
    :raises NotFoundError: If the task or label is missing.
    """
    task = _get_task_or_raise(session, task_id)
    label = _get_label_or_raise(session, label_id)
    if label in task.labels:
        return task
    task.labels.append(label)
    session.flush()
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.LABEL_ADDED_TO_TASK,
        detail={
            "task_id": task.id,
            "label_id": label.id,
            "label_name": label.name,
        },
    )
    return task


def remove_label(session: Session, task_id: str, label_id: str) -> Task:
    """
    Detach a label from a task.

    Idempotent: removing a label that is not attached is a silent
    no-op and does not write to the activity log.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param label_id: The label's UUIDv7 string id.
    :returns: The :class:`Task`, with the label detached.
    :raises NotFoundError: If the task or label is missing.
    """
    task = _get_task_or_raise(session, task_id)
    label = _get_label_or_raise(session, label_id)
    if label not in task.labels:
        return task
    task.labels.remove(label)
    session.flush()
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.LABEL_REMOVED_FROM_TASK,
        detail={
            "task_id": task.id,
            "label_id": label.id,
            "label_name": label.name,
        },
    )
    return task


def complete_task(
    session: Session,
    task_id: str,
    *,
    when: datetime | None = None,
) -> Task:
    """
    Mark a task complete, advancing recurrence in place when set.

    Non-recurring tasks flip ``completed`` to ``True`` and stamp
    ``completed_at``. A second call against an already-completed
    non-recurring task raises :class:`AlreadyCompletedError`.

    Recurring tasks compute the next occurrence with
    :func:`tasksquatch.core.recurrence.next_occurrence` against the
    task's anchor:

    * If the rule is exhausted (``next_occurrence`` returns ``None``)
      the task is treated as finally complete: ``completed = True``,
      ``completed_at = when``, and a ``COMPLETED`` row marks the
      event with ``recurrence_exhausted: True``.
    * Otherwise the row is advanced in place — ``due_date`` /
      ``due_time`` are rewritten to the next occurrence,
      ``completed`` stays ``False``, and
      :attr:`Task.last_notified_at` is cleared so the notify pass
      fires for the new occurrence. Both ``COMPLETED`` and
      ``RECURRENCE_ADVANCED`` activity rows are emitted.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param when: The timestamp to record as the completion. Defaults
        to :func:`datetime.now` in UTC.
    :returns: The mutated :class:`Task`.
    :raises NotFoundError: If no task exists with that id.
    :raises AlreadyCompletedError: If the task is already completed
        and has no recurrence.
    :raises RecurrenceError: If the task carries an invalid recurrence
        string or a ``RELATIVE`` anchor with no usable cursor (which
        :func:`next_occurrence` enforces internally).
    """
    task = _get_task_or_raise(session, task_id)
    if task.completed and not task.recurrence:
        raise AlreadyCompletedError(
            f"Task {task.id!r} is already completed.",
            detail={"task_id": task.id},
        )

    completion_dt = when if when is not None else datetime.now(UTC)

    if not task.recurrence:
        task.completed = True
        task.completed_at = completion_dt
        session.flush()
        emit(
            session,
            task_id=task.id,
            event_type=ActivityEventType.COMPLETED,
            detail={"task_id": task.id, "at": completion_dt.isoformat()},
        )
        return task

    if task.due_date is None:
        raise ValidationError(
            "Recurring task is missing a due_date; cannot advance.",
            detail={"task_id": task.id},
        )

    old_date = task.due_date
    old_time = task.due_time
    next_schedule = next_occurrence(
        task.recurrence,
        anchor=task.recurrence_anchor,
        scheduled_date=old_date,
        scheduled_time=old_time,
        completion_dt=completion_dt,
    )

    if next_schedule is None:
        task.completed = True
        task.completed_at = completion_dt
        session.flush()
        emit(
            session,
            task_id=task.id,
            event_type=ActivityEventType.COMPLETED,
            detail={
                "task_id": task.id,
                "at": completion_dt.isoformat(),
                "recurrence_exhausted": True,
            },
        )
        return task

    new_date, new_time = next_schedule
    task.due_date = new_date
    task.due_time = new_time
    task.completed = False
    task.completed_at = None
    task.last_notified_at = None
    session.flush()

    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.COMPLETED,
        detail={
            "task_id": task.id,
            "at": completion_dt.isoformat(),
            "advanced_to": _schedule_payload(new_date, new_time),
        },
    )
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.RECURRENCE_ADVANCED,
        detail={
            "task_id": task.id,
            "from": _schedule_payload(old_date, old_time),
            "to": _schedule_payload(new_date, new_time),
        },
    )
    return task


def uncomplete_task(session: Session, task_id: str) -> Task:
    """
    Reverse a task's completion state.

    Idempotent for tasks that are not currently completed — the function
    returns the task unchanged without writing to the activity log.
    Otherwise ``completed`` is cleared, ``completed_at`` is set to
    ``None``, and an ``UNCOMPLETED`` row is emitted.

    For recurring tasks this clears the completed flag only; it does
    not roll back a previous due-date advance. Reversing a recurrence
    advance is intentionally not modeled in v1 — the previous schedule
    is gone the moment :func:`complete_task` rewrites
    ``due_date`` / ``due_time``.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :returns: The (possibly-mutated) :class:`Task`.
    :raises NotFoundError: If no task exists with that id.
    """
    task = _get_task_or_raise(session, task_id)
    if not task.completed:
        return task
    task.completed = False
    task.completed_at = None
    session.flush()
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.UNCOMPLETED,
        detail={"task_id": task.id},
    )
    return task


def delete_task(session: Session, task_id: str) -> None:
    """
    Hard-delete a task and emit a ``TASK_DELETED`` activity row.

    The activity row is written before the ``DELETE`` so the identifying
    snapshot (``task_id``, ``number``, ``title``, ``project_id``) is
    captured. The row's ``task_id`` foreign key is then set to ``NULL``
    by the database (``ON DELETE SET NULL`` on
    ``activity_log.task_id``) when the task disappears, so the log
    outlives the entity.

    Subtasks, comments, and ``task_labels`` association rows cascade at
    the database level.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :raises NotFoundError: If no task exists with that id.
    """
    task = _get_task_or_raise(session, task_id)
    snapshot = {
        "task_id": task.id,
        "number": task.number,
        "title": task.title,
        "project_id": task.project_id,
    }
    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.TASK_DELETED,
        detail=snapshot,
    )
    session.delete(task)
    session.flush()
