from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    Label,
    Task,
)
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.labels import (
    create_label,
    delete_label,
    list_labels,
    rename_label,
)


def _count_activity(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def test_create_label_happy_path(session: Session) -> None:
    label = create_label(session, name="  urgent  ")
    assert label.name == "urgent"
    assert _count_activity(session, ActivityEventType.LABEL_CREATED) == 1


def test_create_label_empty_raises_validation(session: Session) -> None:
    with pytest.raises(ValidationError):
        create_label(session, name="   ")


def test_create_label_duplicate_raises_validation(session: Session) -> None:
    create_label(session, name="dup")
    with pytest.raises(ValidationError):
        create_label(session, name="dup")


def test_list_labels_ordered_by_name(session: Session) -> None:
    create_label(session, name="zeta")
    create_label(session, name="alpha")
    create_label(session, name="mu")

    labels = list_labels(session)
    assert [label.name for label in labels] == ["alpha", "mu", "zeta"]


def test_rename_label_updates_and_emits_event(session: Session) -> None:
    label = create_label(session, name="old")
    renamed = rename_label(session, label.id, "  new  ")
    assert renamed.name == "new"

    rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.LABEL_RENAMED
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {
        "label_id": label.id,
        "old_name": "old",
        "new_name": "new",
    }


def test_rename_label_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        rename_label(session, "00000000-0000-7000-8000-000000000000", "anything")


def test_rename_label_collision_raises_validation(session: Session) -> None:
    create_label(session, name="taken")
    other = create_label(session, name="other")
    with pytest.raises(ValidationError):
        rename_label(session, other.id, "taken")


def test_rename_label_empty_raises_validation(session: Session) -> None:
    label = create_label(session, name="x")
    with pytest.raises(ValidationError):
        rename_label(session, label.id, "   ")


def test_delete_label_removes_row_and_emits_event(session: Session) -> None:
    label = create_label(session, name="bye")
    label_id = label.id

    delete_label(session, label_id)

    assert session.get(Label, label_id) is None
    assert _count_activity(session, ActivityEventType.LABEL_DELETED) == 1


def test_delete_label_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        delete_label(session, "00000000-0000-7000-8000-000000000000")


def test_delete_label_cascades_task_labels(session: Session) -> None:
    inbox = ensure_inbox(session)
    label = create_label(session, name="tagged")

    number = allocate_task_number(session)
    task = Task(number=number, title="t", project_id=inbox.id)
    task.labels.append(label)
    session.add(task)
    session.flush()

    join_count_before = session.execute(
        text("SELECT COUNT(*) FROM task_labels")
    ).scalar_one()
    assert join_count_before == 1

    delete_label(session, label.id)

    join_count_after = session.execute(
        text("SELECT COUNT(*) FROM task_labels")
    ).scalar_one()
    assert join_count_after == 0
