"""
Enumerations used by the tasksquatch ORM models.

All enum values are stored as plain TEXT in SQLite for portability —
DataGrip, the ``sqlite3`` CLI, and any future migration tooling can
read them without coordinating on a database-native enum type. A small
helper :func:`_enum_col` keeps the column declarations tidy.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class Priority(StrEnum):
    """
    Task priority, mirroring Todoist's P1 (most urgent) through P4.

    Stored as TEXT. P4 is the default for newly created tasks.
    """

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class RecurrenceAnchor(StrEnum):
    """
    How a recurring task computes its next occurrence on completion.

    ``FIXED`` advances from the previous scheduled ``due_date`` (the
    classic "every Tuesday" semantics). ``RELATIVE`` advances from the
    actual completion timestamp (the "every 3 days after I finish"
    semantics).
    """

    FIXED = "fixed"
    RELATIVE = "relative"


class ActivityEventType(StrEnum):
    """
    The set of event kinds that may appear in the activity log.

    The log is append-only and intentionally exhaustive — every
    mutating service in ``core`` writes one of these event types so
    the log is a complete record of state change regardless of which
    surface caused it.
    """

    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"
    UNCOMPLETED = "uncompleted"
    RESCHEDULED = "rescheduled"
    RECURRENCE_ADVANCED = "recurrence_advanced"
    COMMENTED = "commented"
    COMMENT_EDITED = "comment_edited"
    COMMENT_DELETED = "comment_deleted"
    MOVED = "moved"
    PRIORITY_CHANGED = "priority_changed"
    PROJECT_CREATED = "project_created"
    PROJECT_RENAMED = "project_renamed"
    PROJECT_DELETED = "project_deleted"
    LABEL_CREATED = "label_created"
    LABEL_RENAMED = "label_renamed"
    LABEL_DELETED = "label_deleted"
    LABEL_ADDED_TO_TASK = "label_added_to_task"
    LABEL_REMOVED_FROM_TASK = "label_removed_from_task"


def _enum_col(enum: type[StrEnum]) -> SAEnum:
    """
    Build a SQLAlchemy :class:`Enum` column type for a :class:`StrEnum`.

    Uses non-native storage (TEXT with a CHECK constraint), a fixed
    length large enough for every value we currently mint, and a
    ``values_callable`` that pulls the string values rather than the
    Python member names. Centralizing the construction keeps every
    enum column in the schema consistent.

    :param enum: The :class:`StrEnum` subclass to wrap.
    :returns: A SQLAlchemy column type suitable for ``mapped_column``.
    """
    return SAEnum(
        enum,
        native_enum=False,
        create_constraint=True,
        length=64,
        values_callable=lambda e: [v.value for v in e],
    )
