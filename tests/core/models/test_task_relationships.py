from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import Comment, Label, Task
from tasksquatch.core.seed import ensure_inbox


def test_task_relationships_round_trip(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "rel.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)

        parent_number = allocate_task_number(session)
        parent = Task(
            number=parent_number,
            title="Plan dinner",
            project_id=project.id,
        )
        session.add(parent)
        session.flush()

        child_number = allocate_task_number(session)
        child = Task(
            number=child_number,
            title="Buy ingredients",
            project_id=project.id,
            parent_id=parent.id,
        )
        session.add(child)

        comment = Comment(task_id=parent.id, body="Don't forget the wine.")
        session.add(comment)

        label = Label(name="errand")
        parent.labels.append(label)

        session.flush()
        parent_id = parent.id
        child_id = child.id
        label_id = label.id
        comment_id = comment.id

    with SessionLocal() as session:
        parent = session.execute(select(Task).where(Task.id == parent_id)).scalar_one()

        assert parent.project_id == project.id
        assert parent.parent is None
        assert [t.id for t in parent.subtasks] == [child_id]
        assert [label.id for label in parent.labels] == [label_id]
        assert [c.id for c in parent.comments] == [comment_id]

        child = session.execute(select(Task).where(Task.id == child_id)).scalar_one()
        assert child.parent is not None
        assert child.parent.id == parent_id


def test_label_back_populates_tasks(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "label.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        task = Task(
            number=allocate_task_number(session),
            title="Pay rent",
            project_id=project.id,
        )
        session.add(task)
        label = Label(name="bills")
        task.labels.append(label)
        session.flush()
        label_id = label.id
        task_id = task.id

    with SessionLocal() as session:
        label = session.execute(select(Label).where(Label.id == label_id)).scalar_one()
        assert [t.id for t in label.tasks] == [task_id]
