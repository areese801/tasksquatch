"""
Lookup helpers shared by tasksquatch CLI commands.

The CLI accepts human-friendly references for entities — project and
label names, task numbers — so users do not need to copy UUIDs around.
These helpers translate those references into ORM rows, falling back
to UUID lookup when the input looks like a UUID and raising
:class:`~tasksquatch.core.errors.NotFoundError` /
:class:`~tasksquatch.core.errors.ValidationError` on failure so the
:func:`~tasksquatch.cli.commands._meta.cli_command` decorator can
translate the error into a non-zero exit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import Label, Project, Task


def _looks_like_uuid(value: str) -> bool:
    """
    Return ``True`` when ``value`` parses as a canonical UUID.

    :param value: An arbitrary user-supplied string.
    :returns: ``True`` if :class:`uuid.UUID` accepts the string,
        ``False`` otherwise.
    """
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def resolve_project(session: Session, name_or_id: str) -> Project:
    """
    Resolve a project reference to its ORM row.

    Tries a UUID primary-key lookup first when the input looks like a
    UUID; otherwise (or on miss) falls back to a case-insensitive
    match on :attr:`Project.name`.

    :param session: An open SQLAlchemy session.
    :param name_or_id: The user-supplied project reference.
    :returns: The matching :class:`Project`.
    :raises NotFoundError: If neither lookup finds a project.
    """
    if _looks_like_uuid(name_or_id):
        project = session.get(Project, name_or_id)
        if project is not None:
            return project

    stmt = select(Project).where(func.lower(Project.name) == name_or_id.lower())
    project = session.execute(stmt).scalars().first()
    if project is None:
        raise NotFoundError(
            f"project {name_or_id!r} not found",
            detail={"name_or_id": name_or_id},
        )
    return project


def resolve_label(session: Session, name_or_id: str) -> Label:
    """
    Resolve a label reference to its ORM row.

    Mirrors :func:`resolve_project`: UUID lookup first when the input
    looks like a UUID, then a case-insensitive name match.

    :param session: An open SQLAlchemy session.
    :param name_or_id: The user-supplied label reference.
    :returns: The matching :class:`Label`.
    :raises NotFoundError: If neither lookup finds a label.
    """
    if _looks_like_uuid(name_or_id):
        label = session.get(Label, name_or_id)
        if label is not None:
            return label

    stmt = select(Label).where(func.lower(Label.name) == name_or_id.lower())
    label = session.execute(stmt).scalars().first()
    if label is None:
        raise NotFoundError(
            f"label {name_or_id!r} not found",
            detail={"name_or_id": name_or_id},
        )
    return label


def resolve_task_ref(session: Session, ref: str) -> Task:
    """
    Resolve a task reference (a number or UUID) to its ORM row.

    Integers are looked up via :attr:`Task.number`; UUID-shaped
    references go through the primary-key index. Anything else raises
    :class:`ValidationError` so the user sees a precise diagnosis
    instead of a generic "not found".

    :param session: An open SQLAlchemy session.
    :param ref: The user-supplied task reference.
    :returns: The matching :class:`Task`.
    :raises ValidationError: If ``ref`` is neither an integer nor a UUID.
    :raises NotFoundError: If the lookup yields no task.
    """
    stripped = ref.strip()
    if stripped.isdigit():
        number = int(stripped)
        stmt = select(Task).where(Task.number == number)
        task = session.execute(stmt).scalars().first()
        if task is None:
            raise NotFoundError(
                f"task #{number} not found",
                detail={"number": number},
            )
        return task

    if _looks_like_uuid(stripped):
        task = session.get(Task, stripped)
        if task is None:
            raise NotFoundError(
                f"task {stripped!r} not found",
                detail={"task_id": stripped},
            )
        return task

    raise ValidationError(
        "task reference must be a number or UUID",
        detail={"ref": ref},
    )
