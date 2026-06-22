"""
Add the ``task_deleted`` value to the ``activity_log.event_type`` CHECK
constraint.

The :class:`tasksquatch.core.models._enums.ActivityEventType` enum is
stored as plain TEXT in SQLite with a CHECK constraint that enumerates
every permitted value (see :func:`_enum_col`). Adding a new enum member
requires rewriting that constraint; on SQLite the rewrite happens via
``batch_alter_table`` (which transparently copies the table to a new
one with the desired CHECK in place).

This migration is the schema half of TSQ-18's task service work — the
service emits ``TASK_DELETED`` rows on hard delete, which the previous
constraint would have rejected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT_VALUES_WITH_TASK_DELETED: tuple[str, ...] = (
    "created",
    "updated",
    "completed",
    "uncompleted",
    "rescheduled",
    "recurrence_advanced",
    "commented",
    "comment_edited",
    "comment_deleted",
    "moved",
    "priority_changed",
    "task_deleted",
    "project_created",
    "project_renamed",
    "project_deleted",
    "label_created",
    "label_renamed",
    "label_deleted",
    "label_added_to_task",
    "label_removed_from_task",
)

_EVENT_VALUES_WITHOUT_TASK_DELETED: tuple[str, ...] = tuple(
    value for value in _EVENT_VALUES_WITH_TASK_DELETED if value != "task_deleted"
)


def _event_type_enum(values: tuple[str, ...]) -> sa.Enum:
    """
    Build the SQLAlchemy ``Enum`` column type for the activity event
    type, parameterized over the value set so the upgrade and downgrade
    paths share construction logic.

    :param values: The ordered tuple of permitted event values.
    :returns: A non-native :class:`sqlalchemy.Enum` carrying a CHECK
        constraint over ``values``.
    """
    return sa.Enum(
        *values,
        name="activityeventtype",
        native_enum=False,
        create_constraint=True,
        length=64,
    )


def upgrade() -> None:
    """
    Rewrite the ``activity_log.event_type`` CHECK constraint to include
    the ``task_deleted`` value.
    """
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_event_type_enum(_EVENT_VALUES_WITHOUT_TASK_DELETED),
            type_=_event_type_enum(_EVENT_VALUES_WITH_TASK_DELETED),
            existing_nullable=False,
        )


def downgrade() -> None:
    """
    Restore the original CHECK constraint by dropping the
    ``task_deleted`` value from the permitted set.
    """
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_event_type_enum(_EVENT_VALUES_WITH_TASK_DELETED),
            type_=_event_type_enum(_EVENT_VALUES_WITHOUT_TASK_DELETED),
            existing_nullable=False,
        )
