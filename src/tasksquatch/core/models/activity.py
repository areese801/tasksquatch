"""
Activity log ORM model.

The activity log is append-only by application contract. Every
mutating service in :mod:`tasksquatch.core` writes one row per event;
nothing in the application layer edits or deletes rows from this
table. A task deletion sets ``task_id`` to NULL on the related rows
(via ``ON DELETE SET NULL``) so the log outlives the entity it
described.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from tasksquatch.core.db import Base
from tasksquatch.core.ids import new_id
from tasksquatch.core.models._enums import ActivityEventType, _enum_col


def _utcnow() -> datetime:
    """
    Return the current time as a timezone-aware UTC :class:`datetime`.

    Defined locally so the activity log's ``created_at`` column does
    not depend on :mod:`tasksquatch.core.models._mixins`, which is only
    relevant to entities that also need ``updated_at``.

    :returns: A timezone-aware UTC :class:`datetime` for "now".
    """
    return datetime.now(UTC)


class ActivityLog(Base):
    """
    Append-only event record for state changes anywhere in core.

    Deliberately does not use :class:`TimestampMixin`: an activity row
    has a single ``created_at`` and is never updated, so an
    ``updated_at`` column would be misleading.
    """

    __tablename__ = "activity_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[ActivityEventType] = mapped_column(
        _enum_col(ActivityEventType),
        nullable=False,
    )
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        Index("ix_activity_task_id", "task_id"),
        Index("ix_activity_created_at", "created_at"),
        Index("ix_activity_event_type", "event_type"),
    )
