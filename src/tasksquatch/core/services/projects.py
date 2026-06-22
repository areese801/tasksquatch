"""
Project CRUD service.

All project-level mutations go through this module so the activity log
captures them uniformly. The Inbox is a singleton sentinel — it cannot
be renamed or deleted, and the service enforces that with explicit
errors rather than relying on a database constraint.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import (
    InboxProtectedError,
    NotFoundError,
    ProjectNotEmptyError,
    ValidationError,
)
from tasksquatch.core.models import ActivityEventType, Project, Task
from tasksquatch.core.services.activity import emit


def _strip_and_validate_name(name: str, *, field: str = "name") -> str:
    """
    Strip whitespace from ``name`` and reject the empty result.

    :param name: The user-supplied name to clean.
    :param field: The field label used in the error message.
    :returns: The stripped name.
    :raises ValidationError: When ``name`` is empty after stripping.
    """
    stripped = name.strip()
    if not stripped:
        raise ValidationError(f"Project {field} must not be empty.")
    return stripped


def create_project(
    session: Session,
    *,
    name: str,
    position: int | None = None,
) -> Project:
    """
    Insert a new project and emit a ``PROJECT_CREATED`` activity row.

    Whitespace is stripped from ``name`` before validation. When
    ``position`` is not supplied, the new project sorts after every
    existing one by taking ``max(existing.position) + 1000``; if there
    are no existing projects the default of ``1000`` from the model
    applies.

    :param session: An open SQLAlchemy session.
    :param name: Human-readable project name.
    :param position: Optional explicit sort position. Auto-allocated
        when omitted.
    :returns: The freshly-flushed :class:`Project`.
    :raises ValidationError: If ``name`` is empty after stripping.
    """
    clean_name = _strip_and_validate_name(name)

    if position is None:
        max_position = session.execute(select(func.max(Project.position))).scalar()
        resolved_position = (max_position or 0) + 1000
    else:
        resolved_position = position

    project = Project(name=clean_name, position=resolved_position, is_inbox=False)
    session.add(project)
    session.flush()

    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_CREATED,
        detail={"project_id": project.id, "name": project.name},
    )
    return project


def list_projects(session: Session) -> list[Project]:
    """
    Return every project ordered by ``position`` then ``name``.

    :param session: An open SQLAlchemy session.
    :returns: A list of :class:`Project` rows in deterministic order.
    """
    stmt = select(Project).order_by(Project.position.asc(), Project.name.asc())
    return list(session.execute(stmt).scalars().all())


def _get_project_or_raise(session: Session, project_id: str) -> Project:
    """
    Fetch a project by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 string id.
    :returns: The :class:`Project` row.
    :raises NotFoundError: If no project exists with that id.
    """
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(
            f"Project {project_id!r} not found.",
            detail={"project_id": project_id},
        )
    return project


def rename_project(
    session: Session,
    project_id: str,
    new_name: str,
) -> Project:
    """
    Rename a project and emit a ``PROJECT_RENAMED`` activity row.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 string id.
    :param new_name: The replacement name. Whitespace is stripped.
    :returns: The mutated :class:`Project`.
    :raises NotFoundError: If no project exists with that id.
    :raises InboxProtectedError: If the target is the Inbox.
    :raises ValidationError: If ``new_name`` is empty after stripping.
    """
    project = _get_project_or_raise(session, project_id)
    if project.is_inbox:
        raise InboxProtectedError(
            "The Inbox project cannot be renamed.",
            detail={"project_id": project.id},
        )

    clean_name = _strip_and_validate_name(new_name)
    old_name = project.name
    project.name = clean_name
    session.flush()

    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_RENAMED,
        detail={
            "project_id": project.id,
            "old_name": old_name,
            "new_name": clean_name,
        },
    )
    return project


def move_project(
    session: Session,
    project_id: str,
    new_position: int,
) -> Project:
    """
    Update a project's sort ``position``.

    Does not emit a dedicated activity event in v1: reordering is a
    high-frequency UI gesture and the log would drown in noise. The
    event type may be reintroduced later if the activity feed proves
    it needs the visibility.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 string id.
    :param new_position: The new sort position.
    :returns: The mutated :class:`Project`.
    :raises NotFoundError: If no project exists with that id.
    """
    # TODO(spec): consider adding ActivityEventType.PROJECT_REORDERED
    # if reorder events become user-visible (e.g. in the web activity
    # feed). Intentionally silent today.
    project = _get_project_or_raise(session, project_id)
    project.position = new_position
    session.flush()
    return project


def delete_project(session: Session, project_id: str) -> None:
    """
    Delete a project that has no remaining tasks.

    Emits the ``PROJECT_DELETED`` activity row *before* removing the
    project so that the log persists the operation even if a downstream
    error rolls back the delete. The activity log has no foreign key
    to ``projects`` — the project id lives only in the JSON detail —
    so the order does not introduce an FK race.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 string id.
    :raises NotFoundError: If no project exists with that id.
    :raises InboxProtectedError: If the target is the Inbox.
    :raises ProjectNotEmptyError: If the project still has tasks.
    """
    project = _get_project_or_raise(session, project_id)
    if project.is_inbox:
        raise InboxProtectedError(
            "The Inbox project cannot be deleted.",
            detail={"project_id": project.id},
        )

    task_count = session.execute(
        select(func.count()).select_from(Task).where(Task.project_id == project.id)
    ).scalar_one()
    if task_count > 0:
        raise ProjectNotEmptyError(
            f"Project {project.name!r} still has {task_count} task(s).",
            detail={"project_id": project.id, "task_count": task_count},
        )

    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.PROJECT_DELETED,
        detail={"project_id": project.id, "name": project.name},
    )
    session.delete(project)
    session.flush()
