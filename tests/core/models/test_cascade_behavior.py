from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    Comment,
    Label,
    Project,
    Task,
)
from tasksquatch.core.seed import ensure_inbox


def test_deleting_task_cascades_to_subtasks(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "cascade.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        parent = Task(
            number=allocate_task_number(session),
            title="Parent",
            project_id=project.id,
        )
        session.add(parent)
        session.flush()
        child = Task(
            number=allocate_task_number(session),
            title="Child",
            project_id=project.id,
            parent_id=parent.id,
        )
        session.add(child)
        session.flush()
        parent_id = parent.id
        child_id = child.id

    with session_scope(SessionLocal) as session:
        parent = session.execute(select(Task).where(Task.id == parent_id)).scalar_one()
        session.delete(parent)

    with SessionLocal() as session:
        remaining_ids = (
            session.execute(select(Task.id).where(Task.id.in_([parent_id, child_id])))
            .scalars()
            .all()
        )
        assert remaining_ids == []


def test_deleting_task_cascades_to_comments(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "cascade.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        task = Task(
            number=allocate_task_number(session),
            title="Has comments",
            project_id=project.id,
        )
        session.add(task)
        session.flush()
        for body in ("note one", "note two"):
            session.add(Comment(task_id=task.id, body=body))
        session.flush()
        task_id = task.id

    with session_scope(SessionLocal) as session:
        task = session.execute(select(Task).where(Task.id == task_id)).scalar_one()
        session.delete(task)

    with SessionLocal() as session:
        comment_count = session.execute(
            select(func.count()).select_from(Comment).where(Comment.task_id == task_id)
        ).scalar_one()
        assert comment_count == 0


def test_deleting_task_removes_task_label_links_but_keeps_label(
    tmp_path: Path,
) -> None:
    engine = create_engine_for_path(tmp_path / "cascade.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        task = Task(
            number=allocate_task_number(session),
            title="Has labels",
            project_id=project.id,
        )
        label = Label(name="orphanable")
        task.labels.append(label)
        session.add(task)
        session.flush()
        task_id = task.id
        label_id = label.id

    with session_scope(SessionLocal) as session:
        task = session.execute(select(Task).where(Task.id == task_id)).scalar_one()
        session.delete(task)

    with SessionLocal() as session:
        link_count = session.execute(
            text(
                "SELECT COUNT(*) FROM task_labels "
                "WHERE task_id = :tid OR label_id = :lid"
            ),
            {"tid": task_id, "lid": label_id},
        ).scalar_one()
        assert link_count == 0

        label = session.execute(select(Label).where(Label.id == label_id)).scalar_one()
        assert label.name == "orphanable"


def test_deleting_project_with_tasks_raises_integrity_error(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "cascade.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        ensure_inbox(session)
        project = Project(name="Work", position=10)
        session.add(project)
        session.flush()
        task = Task(
            number=allocate_task_number(session),
            title="Ship it",
            project_id=project.id,
        )
        session.add(task)
        session.flush()
        project_id = project.id

    with pytest.raises(IntegrityError), session_scope(SessionLocal) as session:
        project = session.execute(
            select(Project).where(Project.id == project_id)
        ).scalar_one()
        session.delete(project)


def test_deleting_task_sets_activity_log_task_id_to_null(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "cascade.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        task = Task(
            number=allocate_task_number(session),
            title="Will outlive me in the log",
            project_id=project.id,
        )
        session.add(task)
        session.flush()
        log = ActivityLog(
            task_id=task.id,
            event_type=ActivityEventType.CREATED,
            detail={"title": task.title},
        )
        session.add(log)
        session.flush()
        task_id = task.id
        log_id = log.id

    with session_scope(SessionLocal) as session:
        task = session.execute(select(Task).where(Task.id == task_id)).scalar_one()
        session.delete(task)

    with SessionLocal() as session:
        log = session.execute(
            select(ActivityLog).where(ActivityLog.id == log_id)
        ).scalar_one()
        assert log.task_id is None
        assert log.event_type == ActivityEventType.CREATED
