"""
Project resource router.

Projects are a flat container of tasks. The Inbox is a singleton and
cannot be renamed or deleted — the service raises
:class:`tasksquatch.core.errors.InboxProtectedError`, which the
registered exception handlers translate to HTTP 409.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError
from tasksquatch.core.models import Project
from tasksquatch.core.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from tasksquatch.core.services import projects as projects_service
from tasksquatch.rest.dependencies import get_session


def _get_project_or_raise(session: Session, project_id: str) -> Project:
    """
    Fetch a project by id or raise :class:`NotFoundError`.

    Mirrors the same helper inside
    :mod:`tasksquatch.core.services.projects`; duplicated here so the
    router does not import the service's underscore-private helper.

    :param session: An open SQLAlchemy session.
    :param project_id: The project's UUIDv7 primary key.
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


router = APIRouter(prefix="/projects", tags=["projects"])


class _ProjectList(BaseModel):
    """
    Response envelope for the list endpoint.
    """

    items: list[ProjectRead]


@router.get(
    "",
    response_model=_ProjectList,
    summary="List projects",
    description=(
        "Return every project ordered by ``position`` then by name. "
        "Projects are intentionally few; this endpoint does not "
        "paginate."
    ),
)
def list_projects_endpoint(
    session: Annotated[Session, Depends(get_session)],
) -> _ProjectList:
    """
    Return every project as a list envelope.
    """
    rows = projects_service.list_projects(session)
    return _ProjectList(items=[ProjectRead.model_validate(row) for row in rows])


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description=(
        "Insert a new project. ``position`` is auto-allocated past the "
        "current max when omitted."
    ),
)
def create_project_endpoint(
    payload: ProjectCreate,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectRead:
    """
    Insert a new project and return its read view.
    """
    project = projects_service.create_project(
        session,
        name=payload.name,
        position=payload.position,
    )
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    return ProjectRead.model_validate(project)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by id",
    description="Return the project with this UUIDv7 id.",
)
def get_project_endpoint(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectRead:
    """
    Return the project with this UUIDv7 primary key.
    """
    project = _get_project_or_raise(session, project_id)
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Update a project",
    description=(
        "Apply a partial update. ``name`` triggers a rename; "
        "``position`` triggers a reorder. Sending neither field is a "
        "no-op that returns the project unchanged."
    ),
)
def patch_project_endpoint(
    project_id: str,
    payload: ProjectUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectRead:
    """
    Patch a project's mutable fields.
    """
    fields = payload.model_fields_set
    project = _get_project_or_raise(session, project_id)

    if "name" in fields and payload.name is not None:
        project = projects_service.rename_project(
            session,
            project_id,
            payload.name,
        )
    if "position" in fields and payload.position is not None:
        project = projects_service.move_project(
            session,
            project_id,
            payload.position,
        )
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    description=(
        "Delete an empty, non-Inbox project. Projects that still have "
        "tasks return 409 ``project_not_empty``; deleting the Inbox "
        "returns 409 ``inbox_protected``."
    ),
)
def delete_project_endpoint(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """
    Delete a project and return 204.
    """
    projects_service.delete_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
