"""
Task-service tests for :func:`move_task` and :func:`set_parent`.

These two functions enforce the subtask-shares-project invariant from
two different angles: ``move_task`` rewrites every descendant's
project to follow the moved root, and ``set_parent`` rejects any
reparenting that would cross a project boundary or form a cycle.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import ActivityEventType, ActivityLog
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.tasks import (
    create_task,
    move_task,
    set_parent,
)

from ._helpers import make_project


def _count(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def test_move_task_rewrites_descendant_project(session: Session) -> None:
    src = make_project(session, name="src")
    dst = make_project(session, name="dst")
    parent = create_task(session, title="parent", project_id=src.id)
    child = create_task(
        session,
        title="child",
        project_id=src.id,
        parent_id=parent.id,
    )
    grandchild = create_task(
        session,
        title="grandchild",
        project_id=src.id,
        parent_id=child.id,
    )

    move_task(session, parent.id, new_project_id=dst.id)

    assert parent.project_id == dst.id
    assert child.project_id == dst.id
    assert grandchild.project_id == dst.id

    moved = session.execute(
        select(ActivityLog).where(ActivityLog.event_type == ActivityEventType.MOVED)
    ).scalar_one()
    assert moved.detail == {
        "task_id": parent.id,
        "from_project_id": src.id,
        "to_project_id": dst.id,
        "descendant_count": 2,
    }


def test_move_task_with_no_descendants(session: Session) -> None:
    src = make_project(session, name="src")
    dst = make_project(session, name="dst")
    task = create_task(session, title="solo", project_id=src.id)
    move_task(session, task.id, new_project_id=dst.id)
    assert task.project_id == dst.id
    assert _count(session, ActivityEventType.MOVED) == 1


def test_move_subtask_raises_validation(session: Session) -> None:
    project = make_project(session)
    other = make_project(session, name="other")
    parent = create_task(session, title="parent", project_id=project.id)
    child = create_task(
        session,
        title="child",
        project_id=project.id,
        parent_id=parent.id,
    )
    with pytest.raises(ValidationError):
        move_task(session, child.id, new_project_id=other.id)


def test_move_task_missing_destination_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(NotFoundError):
        move_task(
            session,
            task.id,
            new_project_id="00000000-0000-7000-8000-000000000000",
        )


def test_move_task_to_same_project_is_noop(session: Session) -> None:
    project = make_project(session)
    task = create_task(session, title="t", project_id=project.id)
    move_task(session, task.id, new_project_id=project.id)
    assert _count(session, ActivityEventType.MOVED) == 0


def test_set_parent_attaches_in_same_project(session: Session) -> None:
    project = make_project(session)
    a = create_task(session, title="a", project_id=project.id)
    b = create_task(session, title="b", project_id=project.id)
    set_parent(session, b.id, new_parent_id=a.id)
    assert b.parent_id == a.id

    row = session.execute(
        select(ActivityLog).where(ActivityLog.event_type == ActivityEventType.UPDATED)
    ).scalar_one()
    assert row.detail == {
        "task_id": b.id,
        "changes": {"parent_id": [None, a.id]},
    }


def test_set_parent_cross_project_raises(session: Session) -> None:
    project_a = make_project(session, name="A")
    project_b = make_project(session, name="B")
    parent = create_task(session, title="parent", project_id=project_a.id)
    child = create_task(session, title="child", project_id=project_b.id)
    with pytest.raises(ValidationError):
        set_parent(session, child.id, new_parent_id=parent.id)


def test_set_parent_cycle_raises(session: Session) -> None:
    project = make_project(session)
    a = create_task(session, title="a", project_id=project.id)
    b = create_task(session, title="b", project_id=project.id, parent_id=a.id)
    c = create_task(session, title="c", project_id=project.id, parent_id=b.id)
    # Trying to make ``a`` a child of ``c`` would form a cycle.
    with pytest.raises(ValidationError):
        set_parent(session, a.id, new_parent_id=c.id)


def test_set_parent_self_cycle_raises(session: Session) -> None:
    project = make_project(session)
    a = create_task(session, title="a", project_id=project.id)
    with pytest.raises(ValidationError):
        set_parent(session, a.id, new_parent_id=a.id)


def test_set_parent_detach_to_top_level(session: Session) -> None:
    inbox = ensure_inbox(session)
    parent = create_task(session, title="parent", project_id=inbox.id)
    child = create_task(
        session,
        title="child",
        project_id=inbox.id,
        parent_id=parent.id,
    )
    set_parent(session, child.id, new_parent_id=None)
    assert child.parent_id is None

    row = session.execute(
        select(ActivityLog).where(ActivityLog.event_type == ActivityEventType.UPDATED)
    ).scalar_one()
    assert row.detail == {
        "task_id": child.id,
        "changes": {"parent_id": [parent.id, None]},
    }


def test_set_parent_detach_when_already_top_level_is_noop(session: Session) -> None:
    task = create_task(session, title="t")
    set_parent(session, task.id, new_parent_id=None)
    assert _count(session, ActivityEventType.UPDATED) == 0


def test_set_parent_missing_task_raises(session: Session) -> None:
    parent = create_task(session, title="parent")
    with pytest.raises(NotFoundError):
        set_parent(
            session,
            "00000000-0000-7000-8000-000000000000",
            new_parent_id=parent.id,
        )


def test_set_parent_missing_new_parent_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(NotFoundError):
        set_parent(
            session,
            task.id,
            new_parent_id="00000000-0000-7000-8000-000000000000",
        )
