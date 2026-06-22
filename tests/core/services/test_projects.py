from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tasksquatch.core.errors import (
    InboxProtectedError,
    NotFoundError,
    ProjectNotEmptyError,
    ValidationError,
)
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import ActivityEventType, ActivityLog, Project, Task
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.projects import (
    create_project,
    delete_project,
    list_projects,
    move_project,
    rename_project,
)


def _activity_event_count(session: Session, event: ActivityEventType) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityLog)
        .where(ActivityLog.event_type == event)
    ).scalar_one()


def test_create_project_strips_whitespace(session: Session) -> None:
    project = create_project(session, name="  Errands  ")
    assert project.name == "Errands"


def test_create_project_empty_name_raises_validation(session: Session) -> None:
    with pytest.raises(ValidationError):
        create_project(session, name="   ")


def test_create_project_auto_positions_after_max(session: Session) -> None:
    ensure_inbox(session)  # position 0
    a = create_project(session, name="A")
    b = create_project(session, name="B")

    assert a.position == 1000
    assert b.position == 2000


def test_create_project_emits_activity_row(session: Session) -> None:
    project = create_project(session, name="Errands")
    rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.PROJECT_CREATED
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {"project_id": project.id, "name": "Errands"}


def test_list_projects_orders_by_position_then_name(session: Session) -> None:
    inbox = ensure_inbox(session)
    z = create_project(session, name="Zeta")
    a = create_project(session, name="Alpha")
    m = create_project(session, name="Mid", position=500)

    projects = list_projects(session)
    assert [p.id for p in projects] == [inbox.id, m.id, z.id, a.id]


def test_rename_project_updates_name_and_emits_event(session: Session) -> None:
    project = create_project(session, name="Old")

    renamed = rename_project(session, project.id, "  New  ")
    assert renamed.name == "New"

    rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.PROJECT_RENAMED
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {
        "project_id": project.id,
        "old_name": "Old",
        "new_name": "New",
    }


def test_rename_project_inbox_raises(session: Session) -> None:
    inbox = ensure_inbox(session)
    with pytest.raises(InboxProtectedError):
        rename_project(session, inbox.id, "NotInbox")


def test_rename_project_missing_raises_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        rename_project(session, "00000000-0000-7000-8000-000000000000", "anything")


def test_rename_project_empty_name_raises(session: Session) -> None:
    project = create_project(session, name="X")
    with pytest.raises(ValidationError):
        rename_project(session, project.id, "  ")


def test_move_project_updates_position(session: Session) -> None:
    project = create_project(session, name="X")
    assert project.position == 1000

    moved = move_project(session, project.id, 42)
    assert moved.position == 42


def test_move_project_missing_raises_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        move_project(session, "00000000-0000-7000-8000-000000000000", 5)


def test_move_project_does_not_emit_activity(session: Session) -> None:
    project = create_project(session, name="X")
    before = _activity_event_count(session, ActivityEventType.PROJECT_RENAMED)
    move_project(session, project.id, 99)
    after = _activity_event_count(session, ActivityEventType.PROJECT_RENAMED)
    assert before == after


def test_delete_project_inbox_raises(session: Session) -> None:
    inbox = ensure_inbox(session)
    with pytest.raises(InboxProtectedError):
        delete_project(session, inbox.id)


def test_delete_project_with_tasks_raises(session: Session) -> None:
    project = create_project(session, name="With Tasks")
    number = allocate_task_number(session)
    task = Task(
        number=number,
        title="A task",
        project_id=project.id,
    )
    session.add(task)
    session.flush()

    with pytest.raises(ProjectNotEmptyError) as excinfo:
        delete_project(session, project.id)
    assert excinfo.value.detail["task_count"] == 1


def test_delete_project_empty_succeeds_and_emits_event(session: Session) -> None:
    project = create_project(session, name="Empty")
    project_id = project.id

    delete_project(session, project_id)

    assert session.get(Project, project_id) is None

    rows = (
        session.execute(
            select(ActivityLog).where(
                ActivityLog.event_type == ActivityEventType.PROJECT_DELETED
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].detail == {"project_id": project_id, "name": "Empty"}


def test_delete_project_missing_raises_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        delete_project(session, "00000000-0000-7000-8000-000000000000")
