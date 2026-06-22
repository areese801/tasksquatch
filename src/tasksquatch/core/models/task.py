"""
Task ORM model.

A task belongs to exactly one project, may have a parent task (subtask
relationship of arbitrary depth), zero or more labels, and zero or more
comments. The user-facing ``number`` is allocated by the service layer
via :func:`tasksquatch.core.ids.allocate_task_number`; the model does
not auto-allocate so that the caller owns the transactional contract.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tasksquatch.core.db import Base
from tasksquatch.core.ids import new_id
from tasksquatch.core.models._enums import Priority, RecurrenceAnchor, _enum_col
from tasksquatch.core.models._mixins import TimestampMixin
from tasksquatch.core.models.label import Label
from tasksquatch.core.models.project import Project

if TYPE_CHECKING:
    from tasksquatch.core.models.comment import Comment


class Task(TimestampMixin, Base):
    """
    A unit of work.

    Recurring tasks advance in place on completion: the same row is
    re-armed with the next ``due_date`` rather than being archived and
    replaced. ``recurrence`` is an RFC 5545 RRULE string, and
    ``recurrence_anchor`` decides whether the next occurrence is
    computed from the previous schedule (``FIXED``) or from the actual
    completion time (``RELATIVE``).
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
    )
    priority: Mapped[Priority] = mapped_column(
        _enum_col(Priority),
        nullable=False,
        default=Priority.P4,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    recurrence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recurrence_anchor: Mapped[RecurrenceAnchor] = mapped_column(
        _enum_col(RecurrenceAnchor),
        nullable=False,
        default=RecurrenceAnchor.FIXED,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="tasks")
    parent: Mapped[Task | None] = relationship(
        remote_side="Task.id",
        back_populates="subtasks",
    )
    subtasks: Mapped[list[Task]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    labels: Mapped[list[Label]] = relationship(
        secondary="task_labels",
        back_populates="tasks",
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_parent_id", "parent_id"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_completed", "completed"),
    )
