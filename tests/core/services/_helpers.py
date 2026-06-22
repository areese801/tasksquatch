"""
Shared builders for task-service tests.

The functions here are intentionally minimal — they exist to remove
the per-test boilerplate of allocating a task ``number`` and wiring up
foreign keys when the test does not care about that infrastructure.
Tests that *do* care (e.g. position-allocation tests) drive
:func:`tasksquatch.core.services.tasks.create_task` directly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import Project, Task
from tasksquatch.core.services.projects import create_project


def make_project(session: Session, name: str = "Work") -> Project:
    """
    Insert a non-Inbox project and return it.

    :param session: An open SQLAlchemy session.
    :param name: Human-readable project name.
    :returns: The freshly-created :class:`Project`.
    """
    return create_project(session, name=name)


def make_raw_task(
    session: Session,
    *,
    project_id: str,
    title: str = "task",
    parent_id: str | None = None,
    position: int = 1000,
) -> Task:
    """
    Insert a task directly via the ORM, bypassing
    :func:`tasksquatch.core.services.tasks.create_task`.

    Useful for tests that need a deterministic precondition without
    triggering the activity log emissions that ``create_task`` would
    produce.

    :param session: An open SQLAlchemy session.
    :param project_id: Destination project id.
    :param title: Task title.
    :param parent_id: Optional parent task id.
    :param position: Sort position; defaults to the model default of
        1000.
    :returns: The freshly-flushed :class:`Task`.
    """
    task = Task(
        number=allocate_task_number(session),
        title=title,
        project_id=project_id,
        parent_id=parent_id,
        position=position,
    )
    session.add(task)
    session.flush()
    return task
