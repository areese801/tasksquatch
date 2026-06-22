"""
Tests for the comment service.

The comment service writes one activity row per mutation (one of
``COMMENTED`` / ``COMMENT_EDITED`` / ``COMMENT_DELETED``) and trims
the preview to 120 characters. These tests cover the happy paths,
the validation rejections, and the activity log emissions.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import ActivityEventType, ActivityLog, Comment
from tasksquatch.core.services.comments import (
    add_comment,
    delete_comment,
    edit_comment,
)
from tasksquatch.core.services.tasks import create_task


def _activity(session: Session, event: ActivityEventType) -> list[ActivityLog]:
    return list(
        session.execute(
            select(ActivityLog)
            .where(ActivityLog.event_type == event)
            .order_by(ActivityLog.created_at.asc())
        )
        .scalars()
        .all()
    )


def test_add_comment_persists_and_emits(session: Session) -> None:
    task = create_task(session, title="t")
    comment = add_comment(session, task_id=task.id, body="  first thoughts  ")
    assert comment.id is not None
    assert comment.task_id == task.id
    assert comment.body == "first thoughts"

    rows = _activity(session, ActivityEventType.COMMENTED)
    assert len(rows) == 1
    assert rows[0].task_id == task.id
    assert rows[0].detail == {
        "task_id": task.id,
        "comment_id": comment.id,
        "preview": "first thoughts",
    }


def test_add_comment_preview_truncates_at_120_chars(session: Session) -> None:
    task = create_task(session, title="t")
    long_body = "x" * 250
    comment = add_comment(session, task_id=task.id, body=long_body)
    assert comment.body == long_body

    rows = _activity(session, ActivityEventType.COMMENTED)
    assert rows[0].detail["preview"] == "x" * 120


def test_add_comment_empty_body_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(ValidationError):
        add_comment(session, task_id=task.id, body="   \n\t ")
    assert _activity(session, ActivityEventType.COMMENTED) == []


def test_add_comment_missing_task_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        add_comment(
            session,
            task_id="00000000-0000-7000-8000-000000000000",
            body="hello",
        )


def test_edit_comment_updates_body_and_emits(session: Session) -> None:
    task = create_task(session, title="t")
    comment = add_comment(session, task_id=task.id, body="original")
    edited = edit_comment(session, comment.id, body="  revised text  ")
    assert edited.id == comment.id
    assert edited.body == "revised text"

    rows = _activity(session, ActivityEventType.COMMENT_EDITED)
    assert len(rows) == 1
    assert rows[0].task_id == task.id
    assert rows[0].detail == {
        "task_id": task.id,
        "comment_id": comment.id,
        "old_preview": "original",
        "new_preview": "revised text",
    }


def test_edit_comment_preview_reflects_old_and_new(session: Session) -> None:
    task = create_task(session, title="t")
    long_old = "a" * 200
    long_new = "b" * 200
    comment = add_comment(session, task_id=task.id, body=long_old)
    edit_comment(session, comment.id, body=long_new)

    rows = _activity(session, ActivityEventType.COMMENT_EDITED)
    assert rows[0].detail["old_preview"] == "a" * 120
    assert rows[0].detail["new_preview"] == "b" * 120


def test_edit_comment_empty_body_raises(session: Session) -> None:
    task = create_task(session, title="t")
    comment = add_comment(session, task_id=task.id, body="keep")
    with pytest.raises(ValidationError):
        edit_comment(session, comment.id, body=" ")

    fetched = session.get(Comment, comment.id)
    assert fetched is not None
    assert fetched.body == "keep"
    assert _activity(session, ActivityEventType.COMMENT_EDITED) == []


def test_edit_comment_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        edit_comment(
            session,
            "00000000-0000-7000-8000-000000000000",
            body="hi",
        )


def test_delete_comment_removes_row_and_emits(session: Session) -> None:
    task = create_task(session, title="t")
    comment = add_comment(session, task_id=task.id, body="bye")
    comment_id = comment.id

    delete_comment(session, comment_id)
    assert session.get(Comment, comment_id) is None

    rows = _activity(session, ActivityEventType.COMMENT_DELETED)
    assert len(rows) == 1
    assert rows[0].detail == {"task_id": task.id, "comment_id": comment_id}


def test_delete_comment_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        delete_comment(session, "00000000-0000-7000-8000-000000000000")
