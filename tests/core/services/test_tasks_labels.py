"""
Task-label attachment tests.

These cover the happy path for :func:`add_label` and
:func:`remove_label` plus the spec's idempotency contract: re-adding
an attached label or removing a missing one is a silent no-op and
must not write to the activity log.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError
from tasksquatch.core.models import ActivityEventType, ActivityLog
from tasksquatch.core.services.labels import create_label
from tasksquatch.core.services.tasks import (
    add_label,
    create_task,
    remove_label,
)


def _count(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def _join_count(session: Session) -> int:
    count = session.execute(text("SELECT COUNT(*) FROM task_labels")).scalar_one()
    return int(count)


def test_add_label_happy_path(session: Session) -> None:
    task = create_task(session, title="t")
    label = create_label(session, name="urgent")
    add_label(session, task.id, label.id)

    assert any(lbl.id == label.id for lbl in task.labels)
    assert _count(session, ActivityEventType.LABEL_ADDED_TO_TASK) == 1
    assert _join_count(session) == 1


def test_add_label_idempotent(session: Session) -> None:
    task = create_task(session, title="t")
    label = create_label(session, name="urgent")
    add_label(session, task.id, label.id)
    add_label(session, task.id, label.id)

    assert _join_count(session) == 1
    assert _count(session, ActivityEventType.LABEL_ADDED_TO_TASK) == 1


def test_remove_label_happy_path(session: Session) -> None:
    task = create_task(session, title="t")
    label = create_label(session, name="urgent")
    add_label(session, task.id, label.id)
    remove_label(session, task.id, label.id)

    assert all(lbl.id != label.id for lbl in task.labels)
    assert _join_count(session) == 0
    assert _count(session, ActivityEventType.LABEL_REMOVED_FROM_TASK) == 1


def test_remove_label_missing_association_is_noop(session: Session) -> None:
    task = create_task(session, title="t")
    label = create_label(session, name="urgent")
    remove_label(session, task.id, label.id)

    assert _join_count(session) == 0
    assert _count(session, ActivityEventType.LABEL_REMOVED_FROM_TASK) == 0


def test_add_label_missing_task_raises(session: Session) -> None:
    label = create_label(session, name="urgent")
    with pytest.raises(NotFoundError):
        add_label(session, "00000000-0000-7000-8000-000000000000", label.id)


def test_add_label_missing_label_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(NotFoundError):
        add_label(session, task.id, "00000000-0000-7000-8000-000000000000")


def test_remove_label_missing_task_raises(session: Session) -> None:
    label = create_label(session, name="urgent")
    with pytest.raises(NotFoundError):
        remove_label(session, "00000000-0000-7000-8000-000000000000", label.id)


def test_remove_label_missing_label_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(NotFoundError):
        remove_label(session, task.id, "00000000-0000-7000-8000-000000000000")
