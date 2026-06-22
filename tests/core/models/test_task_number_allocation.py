from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from tasksquatch.core.db import (
    TaskNumberSeq,
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.ids import allocate_task_number
from tasksquatch.core.models import Task
from tasksquatch.core.seed import ensure_inbox


def test_two_allocations_in_one_transaction_are_one_and_two(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "alloc.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        first_number = allocate_task_number(session)
        session.add(Task(number=first_number, title="One", project_id=project.id))
        second_number = allocate_task_number(session)
        session.add(Task(number=second_number, title="Two", project_id=project.id))

    assert (first_number, second_number) == (1, 2)


def test_deleting_a_task_does_not_reset_the_counter(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "alloc.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        first_number = allocate_task_number(session)
        task = Task(number=first_number, title="First", project_id=project.id)
        session.add(task)
        session.flush()
        task_id = task.id

    assert first_number == 1

    with session_scope(SessionLocal) as session:
        task = session.execute(select(Task).where(Task.id == task_id)).scalar_one()
        session.delete(task)

    with session_scope(SessionLocal) as session:
        project = ensure_inbox(session)
        next_number = allocate_task_number(session)
        session.add(Task(number=next_number, title="Second", project_id=project.id))

    assert next_number == 2

    with SessionLocal() as session:
        seq = session.execute(select(TaskNumberSeq)).scalar_one()
        assert seq.last_number == 2
