"""
Label ORM model and the ``task_labels`` association table.

Labels are cross-cutting tags that span projects. The many-to-many
relationship to :class:`Task` is materialized by the ``task_labels``
table, which lives here next to :class:`Label`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tasksquatch.core.db import Base
from tasksquatch.core.ids import new_id

if TYPE_CHECKING:
    from tasksquatch.core.models.task import Task


task_label = Table(
    "task_labels",
    Base.metadata,
    Column(
        "task_id",
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        String(36),
        ForeignKey("labels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Label(Base):
    """
    A user-defined tag that may be attached to any task.

    Labels do not carry timestamps — they are lightweight, mostly-static
    entities whose history is captured in the activity log when needed.
    """

    __tablename__ = "labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    tasks: Mapped[list[Task]] = relationship(
        secondary="task_labels",
        back_populates="labels",
    )
