"""
Project ORM model.

A project groups tasks. Every task belongs to exactly one project; the
default project is the Inbox. A partial unique index guarantees that
exactly one project may carry ``is_inbox = True`` at a time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tasksquatch.core.db import Base
from tasksquatch.core.ids import new_id
from tasksquatch.core.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from tasksquatch.core.models.task import Task


class Project(TimestampMixin, Base):
    """
    A flat container of tasks.

    Projects have no parent-child relationship in v1; the only structural
    distinction is the singleton Inbox, which is enforced at the
    database level via a partial unique index on ``is_inbox``.

    The foreign key from :class:`Task` to :class:`Project` is
    ``ON DELETE RESTRICT``, so a project that still has tasks cannot be
    deleted at the DB level. The service layer is responsible for
    surfacing that as a friendly error rather than letting the
    :class:`IntegrityError` escape.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    is_inbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tasks: Mapped[list[Task]] = relationship(
        back_populates="project",
        cascade="save-update, merge",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_projects_name"),
        Index("ix_projects_position", "position"),
        # Partial unique index: only rows with is_inbox = 1 participate,
        # so the constraint enforces at most one Inbox row but does not
        # collapse all non-Inbox projects onto a single is_inbox = 0.
        Index(
            "uq_projects_single_inbox",
            "is_inbox",
            unique=True,
            sqlite_where=text("is_inbox = 1"),
        ),
    )
