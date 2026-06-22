"""
Comment CRUD service.

Comments are free-form notes attached to a single task. Every comment
mutation emits a row to the activity log so the historical record of a
task includes the prose that has been written about it.

Comment bodies are stripped of surrounding whitespace before storage
and the empty result is rejected. The ``preview`` payload on each
activity row is truncated to 120 characters so the log can be scanned
without rendering huge blobs.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.ids import new_id
from tasksquatch.core.models import ActivityEventType, Comment, Task
from tasksquatch.core.services.activity import emit

_PREVIEW_CHARS = 120


def _validate_body(body: str) -> str:
    """
    Strip whitespace from ``body`` and reject the empty result.

    :param body: The user-supplied comment body.
    :returns: The stripped body.
    :raises ValidationError: When the stripped body is empty.
    """
    stripped = body.strip()
    if not stripped:
        raise ValidationError("Comment body must not be empty.")
    return stripped


def _get_task_or_raise(session: Session, task_id: str) -> Task:
    """
    Fetch a task by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :returns: The :class:`Task` row.
    :raises NotFoundError: If no task exists with that id.
    """
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError(
            f"Task {task_id!r} not found.",
            detail={"task_id": task_id},
        )
    return task


def _get_comment_or_raise(session: Session, comment_id: str) -> Comment:
    """
    Fetch a comment by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param comment_id: The comment's UUIDv7 string id.
    :returns: The :class:`Comment` row.
    :raises NotFoundError: If no comment exists with that id.
    """
    comment = session.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError(
            f"Comment {comment_id!r} not found.",
            detail={"comment_id": comment_id},
        )
    return comment


def add_comment(session: Session, *, task_id: str, body: str) -> Comment:
    """
    Attach a comment to a task and emit a ``COMMENTED`` activity row.

    The body is stripped before storage and rejected when empty. The
    target task must exist; missing tasks raise :class:`NotFoundError`
    rather than orphaning the comment row.

    :param session: An open SQLAlchemy session.
    :param task_id: The task's UUIDv7 string id.
    :param body: The free-form comment text. Whitespace is stripped.
    :returns: The freshly-flushed :class:`Comment`.
    :raises ValidationError: If ``body`` is empty after stripping.
    :raises NotFoundError: If no task exists with that id.
    """
    clean_body = _validate_body(body)
    task = _get_task_or_raise(session, task_id)

    comment = Comment(id=new_id(), task_id=task.id, body=clean_body)
    session.add(comment)
    session.flush()

    emit(
        session,
        task_id=task.id,
        event_type=ActivityEventType.COMMENTED,
        detail={
            "task_id": task.id,
            "comment_id": comment.id,
            "preview": clean_body[:_PREVIEW_CHARS],
        },
    )
    return comment


def edit_comment(session: Session, comment_id: str, *, body: str) -> Comment:
    """
    Replace a comment's body and emit a ``COMMENT_EDITED`` activity row.

    The activity row captures truncated previews of both the old and
    new body so the log preserves a scannable history of what changed
    without storing the full text twice.

    :param session: An open SQLAlchemy session.
    :param comment_id: The comment's UUIDv7 string id.
    :param body: The replacement body. Whitespace is stripped.
    :returns: The mutated :class:`Comment`.
    :raises ValidationError: If ``body`` is empty after stripping.
    :raises NotFoundError: If no comment exists with that id.
    """
    clean_body = _validate_body(body)
    comment = _get_comment_or_raise(session, comment_id)

    old_body = comment.body
    comment.body = clean_body
    session.flush()

    emit(
        session,
        task_id=comment.task_id,
        event_type=ActivityEventType.COMMENT_EDITED,
        detail={
            "task_id": comment.task_id,
            "comment_id": comment.id,
            "old_preview": old_body[:_PREVIEW_CHARS],
            "new_preview": clean_body[:_PREVIEW_CHARS],
        },
    )
    return comment


def delete_comment(session: Session, comment_id: str) -> None:
    """
    Hard-delete a comment and emit a ``COMMENT_DELETED`` activity row.

    The ``task_id`` is captured before the row is removed so the log
    entry remains usable for filtering after the comment is gone.

    :param session: An open SQLAlchemy session.
    :param comment_id: The comment's UUIDv7 string id.
    :raises NotFoundError: If no comment exists with that id.
    """
    comment = _get_comment_or_raise(session, comment_id)
    task_id = comment.task_id
    session.delete(comment)
    session.flush()

    emit(
        session,
        task_id=task_id,
        event_type=ActivityEventType.COMMENT_DELETED,
        detail={"task_id": task_id, "comment_id": comment_id},
    )
