"""
Task-service CRUD tests.

Covers :func:`create_task` defaults and validation, the partial
:func:`update_task` semantics (UNSET no-op, single-field diff,
priority/reschedule fan-out), and the hard-delete cascade behavior of
:func:`delete_task`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tasksquatch.core.errors import (
    NotFoundError,
    RecurrenceError,
    ValidationError,
)
from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    Comment,
    Priority,
    Task,
)
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.labels import create_label
from tasksquatch.core.services.tasks import (
    create_task,
    delete_task,
    update_task,
)

from ._helpers import make_project, make_raw_task


def _count(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def test_create_task_defaults_to_inbox(session: Session) -> None:
    inbox = ensure_inbox(session)
    task = create_task(session, title="Write spec")
    assert task.project_id == inbox.id
    assert task.title == "Write spec"
    assert task.priority is Priority.P4
    assert task.completed is False
    assert _count(session, ActivityEventType.CREATED) == 1


def test_create_task_with_explicit_project(session: Session) -> None:
    project = make_project(session)
    task = create_task(session, title="Deploy", project_id=project.id)
    assert task.project_id == project.id


def test_create_task_strips_and_validates_title(session: Session) -> None:
    task = create_task(session, title="  bake bread  ")
    assert task.title == "bake bread"

    with pytest.raises(ValidationError):
        create_task(session, title="   ")


def test_create_task_subtask_shares_parent_project(session: Session) -> None:
    project = make_project(session)
    parent = create_task(session, title="parent", project_id=project.id)
    child = create_task(
        session,
        title="child",
        project_id=project.id,
        parent_id=parent.id,
    )
    assert child.parent_id == parent.id
    assert child.project_id == project.id


def test_create_task_subtask_cross_project_raises(session: Session) -> None:
    project_a = make_project(session, name="A")
    project_b = make_project(session, name="B")
    parent = create_task(session, title="parent", project_id=project_a.id)
    with pytest.raises(ValidationError):
        create_task(
            session,
            title="child",
            project_id=project_b.id,
            parent_id=parent.id,
        )


def test_create_task_invalid_recurrence_raises(session: Session) -> None:
    with pytest.raises(RecurrenceError):
        create_task(session, title="recurring", recurrence="FREQ=BANANA")


def test_create_task_allocates_sequential_numbers(session: Session) -> None:
    a = create_task(session, title="a")
    b = create_task(session, title="b")
    c = create_task(session, title="c")
    assert (a.number, b.number, c.number) == (1, 2, 3)


def test_create_task_auto_positions_after_siblings(session: Session) -> None:
    project = make_project(session)
    first = create_task(session, title="t1", project_id=project.id)
    second = create_task(session, title="t2", project_id=project.id)
    third = create_task(session, title="t3", project_id=project.id)
    assert (first.position, second.position, third.position) == (1000, 2000, 3000)


def test_create_task_attaches_labels(session: Session) -> None:
    label_a = create_label(session, name="urgent")
    label_b = create_label(session, name="home")
    task = create_task(session, title="t", label_ids=[label_a.id, label_b.id])
    assert {lbl.name for lbl in task.labels} == {"urgent", "home"}


def test_create_task_missing_label_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        create_task(
            session,
            title="t",
            label_ids=["00000000-0000-7000-8000-000000000000"],
        )


def test_update_task_all_unset_is_noop(session: Session) -> None:
    task = create_task(session, title="t")
    created_count = _count(session, ActivityEventType.CREATED)
    updated_count = _count(session, ActivityEventType.UPDATED)

    result = update_task(session, task.id)

    assert result is task
    assert _count(session, ActivityEventType.CREATED) == created_count
    assert _count(session, ActivityEventType.UPDATED) == updated_count


def test_update_task_partial_title_emits_single_diff(session: Session) -> None:
    task = create_task(session, title="old")
    update_task(session, task.id, title="new")

    rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.UPDATED
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {
        "task_id": task.id,
        "changes": {"title": ["old", "new"]},
    }


def test_update_task_priority_emits_priority_changed(session: Session) -> None:
    task = create_task(session, title="t", priority=Priority.P4)
    update_task(session, task.id, priority=Priority.P1)

    assert _count(session, ActivityEventType.UPDATED) == 1
    assert _count(session, ActivityEventType.PRIORITY_CHANGED) == 1

    pc_row = session.execute(
        select(ActivityLog).where(
            ActivityLog.event_type == ActivityEventType.PRIORITY_CHANGED
        )
    ).scalar_one()
    assert pc_row.detail == {
        "task_id": task.id,
        "from": "P4",
        "to": "P1",
    }


def test_update_task_due_date_emits_rescheduled_and_resets_notified(
    session: Session,
) -> None:
    task = create_task(session, title="t")
    # Pre-set last_notified_at to a value to prove it is cleared.
    task.last_notified_at = datetime(2026, 1, 1, tzinfo=UTC)
    session.flush()

    update_task(session, task.id, due_date=date(2026, 1, 5))

    assert task.due_date == date(2026, 1, 5)
    assert task.last_notified_at is None
    assert _count(session, ActivityEventType.UPDATED) == 1
    assert _count(session, ActivityEventType.RESCHEDULED) == 1

    resched = session.execute(
        select(ActivityLog).where(
            ActivityLog.event_type == ActivityEventType.RESCHEDULED
        )
    ).scalar_one()
    assert resched.detail == {
        "task_id": task.id,
        "from": {"date": None, "time": None},
        "to": {"date": "2026-01-05", "time": None},
    }


def test_update_task_clear_description_via_none(session: Session) -> None:
    task = create_task(session, title="t", description="something")
    update_task(session, task.id, description=None)
    assert task.description is None
    assert _count(session, ActivityEventType.UPDATED) == 1


def test_update_task_invalid_recurrence_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(RecurrenceError):
        update_task(session, task.id, recurrence="FREQ=BANANA")


def test_update_task_empty_title_raises(session: Session) -> None:
    task = create_task(session, title="t")
    with pytest.raises(ValidationError):
        update_task(session, task.id, title="   ")


def test_update_task_missing_task_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        update_task(
            session,
            "00000000-0000-7000-8000-000000000000",
            title="anything",
        )


def test_delete_task_removes_row_and_cascades(session: Session) -> None:
    inbox = ensure_inbox(session)
    label = create_label(session, name="x")
    parent = create_task(session, title="parent", project_id=inbox.id)
    child = create_task(
        session,
        title="child",
        project_id=inbox.id,
        parent_id=parent.id,
        label_ids=[label.id],
    )
    # Attach a comment directly through the ORM.
    comment = Comment(task_id=child.id, body="hi")
    session.add(comment)
    session.flush()

    parent_id = parent.id
    child_id = child.id
    comment_id = comment.id

    delete_task(session, parent_id)
    # Drop the identity-map cache so session.get re-loads from the DB,
    # which is where the FK cascade actually happened (subtasks and
    # comments use passive_deletes=True).
    session.expire_all()

    assert session.get(Task, parent_id) is None
    assert session.get(Task, child_id) is None
    assert session.get(Comment, comment_id) is None

    join_count = session.execute(text("SELECT COUNT(*) FROM task_labels")).scalar_one()
    assert join_count == 0

    deleted_rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.TASK_DELETED
            )
        )
        .scalars()
        .all()
    )
    assert len(deleted_rows) == 1
    row = deleted_rows[0]
    assert row.task_id is None  # FK SET NULL after the delete cascade.
    assert row.detail["task_id"] == parent_id
    assert row.detail["title"] == "parent"
    assert row.detail["project_id"] == inbox.id


def test_delete_task_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        delete_task(session, "00000000-0000-7000-8000-000000000000")


def test_create_task_with_missing_parent_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        create_task(
            session,
            title="t",
            parent_id="00000000-0000-7000-8000-000000000000",
        )


def test_create_task_position_isolates_subtask_siblings(session: Session) -> None:
    project = make_project(session)
    parent = create_task(session, title="p", project_id=project.id)
    # Force parent.position high to confirm subtasks compute their own
    # max within the subtask sibling set.
    parent.position = 99_000
    session.flush()

    a = create_task(session, title="a", project_id=project.id, parent_id=parent.id)
    b = create_task(session, title="b", project_id=project.id, parent_id=parent.id)
    assert a.position == 1000
    assert b.position == 2000


def test_make_raw_task_helper_smoke(session: Session) -> None:
    # Sanity-check the test helper so subsequent test files can rely on it.
    project = make_project(session)
    task = make_raw_task(session, project_id=project.id, title="bare")
    assert task.title == "bare"
    assert task.project_id == project.id
