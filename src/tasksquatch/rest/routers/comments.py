"""
Comment resource router.

Comments are attached to a single task. The router uses two prefixes —
``/tasks/{task_id}/comments`` for create and list, and
``/comments/{comment_id}`` for edit and delete — so it intentionally
does not declare a top-level prefix on :class:`APIRouter`. The mount
point in :func:`tasksquatch.rest.app.create_app` supplies the
``/api/v1`` prefix for both groups.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tasksquatch.core.schemas import CommentCreate, CommentRead, CommentUpdate
from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.rest.dependencies import get_session

router = APIRouter(tags=["comments"])


class _CommentList(BaseModel):
    """
    Response envelope for the list-by-task endpoint.
    """

    items: list[CommentRead]


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a task",
    description=(
        "Attach a free-form comment to a task. The body must be "
        "non-empty after whitespace stripping."
    ),
)
def create_comment_endpoint(
    task_id: str,
    payload: CommentCreate,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> CommentRead:
    """
    Insert a comment and return its read view.
    """
    comment = comments_service.add_comment(
        session,
        task_id=task_id,
        body=payload.body,
    )
    response.headers["Location"] = f"/api/v1/comments/{comment.id}"
    return CommentRead.model_validate(comment)


@router.get(
    "/tasks/{task_id}/comments",
    response_model=_CommentList,
    summary="List comments on a task",
    description=(
        "Return every comment on this task in chronological order. The "
        "task must exist — unknown ids return 404."
    ),
)
def list_comments_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> _CommentList:
    """
    Return the task's comments as a list envelope.
    """
    rows = queries_service.list_comments(session, task_id)
    return _CommentList(items=[CommentRead.model_validate(row) for row in rows])


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentRead,
    summary="Edit a comment's body",
    description=(
        "Replace the comment's body. The new body must be non-empty "
        "after whitespace stripping."
    ),
)
def patch_comment_endpoint(
    comment_id: str,
    payload: CommentUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> CommentRead:
    """
    Edit a comment and return the updated read view.
    """
    comment = comments_service.edit_comment(
        session,
        comment_id,
        body=payload.body,
    )
    return CommentRead.model_validate(comment)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    description="Hard-delete a comment from a task.",
)
def delete_comment_endpoint(
    comment_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """
    Hard-delete a comment.
    """
    comments_service.delete_comment(session, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
