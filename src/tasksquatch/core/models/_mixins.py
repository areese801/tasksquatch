"""
Shared SQLAlchemy mixins for tasksquatch ORM models.

Currently only :class:`TimestampMixin` lives here. Per the design in
``docs/spec.md``, tasksquatch deletes rows hard and does not version
entities, so there is intentionally no ``SoftDeleteMixin`` and no
``VersionMixin``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    """
    Return the current time as a timezone-aware UTC :class:`datetime`.

    Wrapped in a module-level helper rather than inlined as a lambda so
    that the column ``default`` and ``onupdate`` callables are
    introspectable and trivially mockable in tests.

    :returns: A timezone-aware UTC :class:`datetime` for "now".
    """
    return datetime.now(UTC)


class TimestampMixin:
    """
    Mixin that adds ``created_at`` and ``updated_at`` columns.

    Both columns are timezone-aware UTC :class:`datetime` values.
    ``created_at`` is populated on insert; ``updated_at`` is populated
    on insert and refreshed on every UPDATE via ``onupdate``.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
