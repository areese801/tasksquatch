"""
Initial tasksquatch schema.

Creates every table defined by the TSQ-15 ORM models:

- ``projects`` — flat container of tasks. Carries a partial unique
  index on ``is_inbox`` so at most one Inbox row may exist.
- ``tasks`` — units of work. ``project_id`` is ``ON DELETE RESTRICT``;
  ``parent_id`` is ``ON DELETE CASCADE`` for self-referential subtasks.
- ``labels`` and ``task_labels`` — many-to-many label tagging with
  ``ON DELETE CASCADE`` on both sides of the association.
- ``comments`` — free-form notes per task, cascading on task delete.
- ``activity_log`` — append-only event log; ``task_id`` is ``SET NULL``
  on parent delete so the log outlives the entity it described.
- ``task_number_seq`` — single-row counter backing the user-facing
  task ``number``. Guarded by a CHECK constraint pinning ``id = 1``.

The Inbox project is seeded as the final step of ``upgrade()`` so that
fresh databases always have a default destination for new tasks. The
seed uses an inline :func:`sa.table` reference rather than importing
the ORM ``Project`` model — Alembic best-practice is that data
migrations should not import application models, which can drift away
from the migration's view of the schema.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
import uuid_utils

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """
    Create every domain table and seed the Inbox row.
    """
    op.create_table(
        "labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_inbox", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_projects_name"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index("ix_projects_position", ["position"], unique=False)
        batch_op.create_index(
            "uq_projects_single_inbox",
            ["is_inbox"],
            unique=True,
            sqlite_where=sa.text("is_inbox = 1"),
        )

    op.create_table(
        "task_number_seq",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_task_number_seq_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column(
            "priority",
            sa.Enum(
                "P1",
                "P2",
                "P3",
                "P4",
                name="priority",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_time", sa.Time(), nullable=True),
        sa.Column("recurrence", sa.String(length=500), nullable=True),
        sa.Column(
            "recurrence_anchor",
            sa.Enum(
                "fixed",
                "relative",
                name="recurrenceanchor",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index("ix_tasks_completed", ["completed"], unique=False)
        batch_op.create_index("ix_tasks_due_date", ["due_date"], unique=False)
        batch_op.create_index("ix_tasks_parent_id", ["parent_id"], unique=False)
        batch_op.create_index("ix_tasks_project_id", ["project_id"], unique=False)

    op.create_table(
        "activity_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
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
                "project_created",
                "project_renamed",
                "project_deleted",
                "label_created",
                "label_renamed",
                "label_deleted",
                "label_added_to_task",
                "label_removed_from_task",
                name="activityeventtype",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.create_index("ix_activity_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_activity_event_type", ["event_type"], unique=False)
        batch_op.create_index("ix_activity_task_id", ["task_id"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_labels",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("label_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["label_id"], ["labels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "label_id"),
    )

    # Seed the singleton Inbox row. Defined inline rather than importing
    # tasksquatch.core.models.Project so the migration is insulated from
    # future drift in the ORM model.
    projects_table = sa.table(
        "projects",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("position", sa.Integer),
        sa.column("is_inbox", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    # SQLAlchemy's SQLite DateTime adapter requires a real datetime
    # instance; it serializes to an ISO-8601 TEXT value internally. We
    # truncate sub-second precision so the seeded row reads cleanly in
    # the sqlite3 CLI without exposing microseconds we don't need.
    now = datetime.now(UTC).replace(microsecond=0)
    op.bulk_insert(
        projects_table,
        [
            {
                "id": str(uuid_utils.uuid7()),
                "name": "Inbox",
                "position": 0,
                "is_inbox": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    """
    Drop every domain table in reverse foreign-key order.
    """
    op.drop_table("task_labels")
    op.drop_table("comments")
    with op.batch_alter_table("activity_log", schema=None) as batch_op:
        batch_op.drop_index("ix_activity_task_id")
        batch_op.drop_index("ix_activity_event_type")
        batch_op.drop_index("ix_activity_created_at")
    op.drop_table("activity_log")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_tasks_project_id")
        batch_op.drop_index("ix_tasks_parent_id")
        batch_op.drop_index("ix_tasks_due_date")
        batch_op.drop_index("ix_tasks_completed")
    op.drop_table("tasks")
    op.drop_table("task_number_seq")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_projects_single_inbox", sqlite_where=sa.text("is_inbox = 1")
        )
        batch_op.drop_index("ix_projects_position")
    op.drop_table("projects")
    op.drop_table("labels")
