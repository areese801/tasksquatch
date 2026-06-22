"""
Comment ORM model.

Comments are free-form notes attached to a task. Deleting a task
cascades to its comments at the DB level via ``ON DELETE CASCADE``.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tasksquatch.core.db import Base
from tasksquatch.core.ids import new_id
from tasksquatch.core.models._mixins import TimestampMixin
from tasksquatch.core.models.task import Task


class Comment(TimestampMixin, Base):
    """
    A note attached to a single task.

    Editing or deleting a comment is recorded as a separate event in
    the activity log; the comment row itself is mutated in place on
    edit and removed on delete.
    """

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped[Task] = relationship(back_populates="comments")
