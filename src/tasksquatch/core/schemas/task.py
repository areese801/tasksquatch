"""
Pydantic v2 schemas for the :class:`~tasksquatch.core.models.Task`
entity.

The Task schemas are the most involved in the package because a task
carries the full kitchen sink of optional scheduling fields, a
many-to-many relationship to labels, and PATCH semantics on update.

``TaskRead`` flattens ``Task.labels`` into a list of label ids via the
:meth:`TaskRead.from_task` classmethod; callers that already hold a
plain ORM row should prefer that helper over generic
``model_validate`` because Pydantic v2 cannot synthesize the
``label_ids`` list from ``from_attributes`` alone.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from tasksquatch.core.models import Priority, RecurrenceAnchor, Task


class TaskRead(BaseModel):
    """
    Read-side view of a task.

    ``priority`` and ``recurrence_anchor`` are emitted as their string
    values rather than the enum members, so consumers see ``"P4"`` and
    ``"fixed"`` regardless of how the enum is stored.

    ``label_ids`` is the flattened list of associated label primary
    keys, populated by :meth:`from_task`. The schema does not pull the
    relationship lazily, so callers must use the helper rather than
    plain ``model_validate`` when the source is an ORM row.
    """

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: str
    number: int
    title: str
    description: str | None
    project_id: str
    parent_id: str | None
    priority: str
    due_date: date | None
    due_time: time | None
    recurrence: str | None
    recurrence_anchor: str
    position: int
    completed: bool
    completed_at: datetime | None
    last_notified_at: datetime | None
    created_at: datetime
    updated_at: datetime
    label_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_task(cls, task: Task) -> Self:
        """
        Build a :class:`TaskRead` from a :class:`Task` ORM row.

        Flattens ``task.labels`` into a list of label ids. The caller
        is responsible for ensuring ``task.labels`` is loaded before
        the session closes — accessing the relationship lazily after
        the session has been closed will raise a SQLAlchemy
        ``DetachedInstanceError``.

        :param task: A :class:`Task` ORM instance.
        :returns: A populated :class:`TaskRead`.
        """
        return cls(
            id=task.id,
            number=task.number,
            title=task.title,
            description=task.description,
            project_id=task.project_id,
            parent_id=task.parent_id,
            priority=task.priority.value,
            due_date=task.due_date,
            due_time=task.due_time,
            recurrence=task.recurrence,
            recurrence_anchor=task.recurrence_anchor.value,
            position=task.position,
            completed=task.completed,
            completed_at=task.completed_at,
            last_notified_at=task.last_notified_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            label_ids=[label.id for label in task.labels],
        )


class TaskCreate(BaseModel):
    """
    Payload for creating a task.

    Only ``title`` is required. Every other field mirrors the optional
    parameters on
    :func:`tasksquatch.core.services.tasks.create_task`. ``priority``
    defaults to :pyattr:`Priority.P4` and ``recurrence_anchor`` defaults
    to :pyattr:`RecurrenceAnchor.FIXED`, matching the model defaults.
    ``label_ids`` is an empty list by default; pass label primary keys
    to attach labels at creation time.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    description: str | None = None
    project_id: str | None = None
    parent_id: str | None = None
    priority: Priority = Priority.P4
    due_date: date | None = None
    due_time: time | None = None
    recurrence: str | None = None
    recurrence_anchor: RecurrenceAnchor = RecurrenceAnchor.FIXED
    position: int | None = None
    label_ids: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """
    PATCH-style payload for updating a task.

    Every field is optional. A client must distinguish "field omitted"
    from "field set to null" by simply not including the key in the
    JSON body — Pydantic exposes that distinction via
    :pyattr:`pydantic.BaseModel.model_fields_set`. The service layer
    uses :data:`tasksquatch.core.UNSET` to model "untouched" internally
    and translates omitted fields to ``UNSET`` at the surface
    boundary.

    Special cases:

    - ``title`` is ``str | None`` only to allow omission; sending an
      explicit ``null`` is invalid and the REST layer rejects it. A
      task always has a title.
    - ``label_ids`` is ``list[str] | None``. ``None`` (omitted) means
      "do not touch labels"; ``[]`` means "remove all labels"; a
      populated list means "replace labels with exactly these ids".
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    project_id: str | None = None
    parent_id: str | None = None
    priority: Priority | None = None
    due_date: date | None = None
    due_time: time | None = None
    recurrence: str | None = None
    recurrence_anchor: RecurrenceAnchor | None = None
    position: int | None = None
    label_ids: list[str] | None = None
