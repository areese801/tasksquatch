"""
Rich-based output helpers for the tasksquatch CLI.

These helpers are intentionally tiny: a default console factory, a
table printer, a JSON printer that handles dates and datetimes, and a
``Task`` flattener that future commands can hand to either. Centralizing
them keeps the actual command modules free of presentation logic and
gives the test suite one place to assert formatting invariants.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, time
from typing import Any

from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.orm.exc import DetachedInstanceError

from tasksquatch.core.models import Comment, Task


def default_console() -> Console:
    """
    Build a fresh Rich :class:`Console`.

    :returns: A new console writing to the process's stdout.
    """
    return Console()


def print_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    console: Console,
    title: str | None = None,
) -> None:
    """
    Render ``rows`` as a Rich table with the given ``columns``.

    :param rows: A sequence of dict-like rows. Missing keys render
        as ``"-"`` rather than raising.
    :param columns: Column headers, in order. Each header is also the
        key used to look up the value in each row.
    :param console: The console to print to.
    :param title: Optional table title.
    """
    table = Table(title=title)
    for column in columns:
        table.add_column(column)
    for row in rows:
        values = [_stringify(row.get(column, "-")) for column in columns]
        table.add_row(*values)
    console.print(table)


def print_json(payload: Any, *, console: Console) -> None:
    """
    Serialize ``payload`` to JSON and print it via the console.

    Uses ``default=str`` so :class:`~datetime.date`,
    :class:`~datetime.datetime`, :class:`~datetime.time`, and other
    non-JSON-native values round-trip as their ``str()`` form rather
    than raising.

    :param payload: Any JSON-serializable structure (with the
        ``default=str`` fallback for dates/datetimes/etc.).
    :param console: The console to print to.
    """
    console.print_json(json.dumps(payload, default=str))


def render_task(task: Task) -> dict[str, Any]:
    """
    Flatten a :class:`Task` ORM row into a dict suitable for display.

    Relationship attributes (``project``, ``labels``) are accessed
    lazily; if the task is detached from its session, or if SQLAlchemy
    refuses to lazy-load for any other reason, the related field
    falls back to ``"-"`` rather than propagating the exception.

    :param task: A :class:`Task` instance, ideally still bound to a
        live session so relationships can load.
    :returns: A dict with the keys ``number``, ``title``, ``project``,
        ``priority``, ``due``, ``labels``, and ``completed``. The
        ``completed`` value is the underlying boolean for clarity in
        both table rendering and JSON output.
    """
    project_name = _safe_relationship(
        lambda: task.project.name if task.project else "-"
    )
    labels = _safe_relationship(
        lambda: ",".join(sorted(label.name for label in task.labels)) or "-"
    )
    return {
        "number": task.number,
        "title": task.title,
        "project": project_name,
        "priority": task.priority.value,
        "due": _fmt_due(task.due_date, task.due_time),
        "labels": labels,
        "completed": task.completed,
    }


def render_task_detail(
    task: Task,
    *,
    subtasks: Sequence[Task] = (),
    comments: Sequence[Comment] = (),
) -> dict[str, Any]:
    """
    Build a rich detail dict for a single task, suitable for ``show``.

    Extends :func:`render_task` with description, recurrence, anchor,
    parent reference, subtask summaries, and comment timestamps. The
    relationship fields fall back to ``"-"`` when the related row cannot
    be loaded, matching :func:`render_task`'s defensive style.

    :param task: The task to render.
    :param subtasks: The subtasks to embed, in display order. Each is
        flattened to a ``{number, title, completed}`` summary.
    :param comments: The comments to embed, in chronological order.
        Each is flattened to ``{id, created_at, body}``.
    :returns: A dict with the keys of :func:`render_task` plus
        ``description``, ``recurrence``, ``recurrence_anchor``,
        ``parent``, ``subtasks``, ``comments``, ``created_at``,
        ``completed_at``.
    """
    base = render_task(task)
    base.update(
        {
            "id": task.id,
            "description": task.description or "-",
            "recurrence": task.recurrence or "-",
            "recurrence_anchor": task.recurrence_anchor.value,
            "parent": _safe_parent_number(task),
            "subtasks": [
                {
                    "number": sub.number,
                    "title": sub.title,
                    "completed": sub.completed,
                }
                for sub in subtasks
            ],
            "comments": [
                {
                    "id": comment.id,
                    "created_at": comment.created_at.isoformat(),
                    "body": comment.body,
                }
                for comment in comments
            ],
            "created_at": task.created_at.isoformat(),
            "completed_at": (
                task.completed_at.isoformat() if task.completed_at else None
            ),
        }
    )
    return base


def _safe_relationship(getter: Any) -> str:
    """
    Run ``getter`` and return ``"-"`` if a relationship cannot load.

    Catches :class:`DetachedInstanceError` and SQLAlchemy's
    :class:`MissingGreenlet` so detached or async-context tasks still
    render instead of crashing the command.
    """
    try:
        return str(getter())
    except (DetachedInstanceError, MissingGreenlet):
        return "-"


def _safe_parent_number(task: Task) -> int | None:
    """
    Return the parent task's user-facing ``number``, or ``None``.

    Mirrors :func:`_safe_relationship`'s defensiveness against detached
    instances and missing greenlets — both return ``None`` here so
    JSON output keeps a stable shape.
    """
    try:
        parent = task.parent
    except (DetachedInstanceError, MissingGreenlet):
        return None
    if parent is None:
        return None
    return parent.number


def _fmt_due(due_date: date | None, due_time: time | None) -> str:
    """
    Format a ``(date, time)`` pair as ``"YYYY-MM-DD"`` or
    ``"YYYY-MM-DD HH:MM"``.

    Returns ``"-"`` when ``due_date`` is ``None``. ``due_time`` is
    ignored if no date is present, since a bare time with no date is
    meaningless in tasksquatch's data model.
    """
    if due_date is None:
        return "-"
    if due_time is None:
        return due_date.isoformat()
    return f"{due_date.isoformat()} {due_time.strftime('%H:%M')}"


def _stringify(value: Any) -> str:
    """
    Render a cell value as a string for :func:`print_table`.

    Booleans render as ``"true"``/``"false"``; ``None`` becomes
    ``"-"``; everything else falls through to :func:`str`.
    """
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
