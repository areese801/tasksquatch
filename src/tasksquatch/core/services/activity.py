"""
Activity log emission service.

The activity log is append-only by application contract. Every mutating
service in :mod:`tasksquatch.core` records its state change by calling
:func:`emit`. Reads, updates, and deletes on the log itself are out of
scope: the log is the historical record and nothing in the application
layer is allowed to rewrite it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from tasksquatch.core.ids import new_id
from tasksquatch.core.models import ActivityEventType, ActivityLog


def emit(
    session: Session,
    *,
    task_id: str | None,
    event_type: ActivityEventType,
    detail: Mapping[str, Any] | None = None,
) -> ActivityLog:
    """
    Insert a single :class:`ActivityLog` row and return it flushed.

    The caller owns the transaction boundary — this function does not
    commit. ``detail`` is coerced to a plain :class:`dict` before
    insertion so callers may safely pass any read-only mapping (a
    Pydantic ``model_dump()`` result, a frozen dict, ``MappingProxyType``)
    without worrying about JSON-column serialization quirks.

    :param session: An open SQLAlchemy session.
    :param task_id: Optional id of the task the event relates to.
        Project- and label-level events pass ``None``.
    :param event_type: The discriminator that classifies the event.
    :param detail: Optional structured payload. Stored verbatim in the
        ``detail`` JSON column; defaults to an empty dict.
    :returns: The freshly-flushed :class:`ActivityLog` instance with
        its primary key and timestamps populated.
    """
    row = ActivityLog(
        id=new_id(),
        task_id=task_id,
        event_type=event_type,
        detail=dict(detail) if detail is not None else {},
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row
