from __future__ import annotations

import threading
from pathlib import Path

from sqlalchemy import select

from tasksquatch.core.db import (
    TaskNumberSeq,
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.ids import allocate_task_number, new_id


def test_new_id_returns_uuidv7_shaped_string() -> None:
    value = new_id()

    assert isinstance(value, str)
    assert len(value) == 36
    assert value.count("-") == 4
    # In RFC 4122 string form, char at index 14 is the version nibble.
    assert value[14] == "7"


def test_new_id_returns_distinct_values_on_successive_calls() -> None:
    values = {new_id() for _ in range(50)}
    assert len(values) == 50


def test_allocate_task_number_is_sequential_within_one_session(
    tmp_path: Path,
) -> None:
    engine = create_engine_for_path(tmp_path / "test.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    with session_scope(SessionLocal) as session:
        first = allocate_task_number(session)
        second = allocate_task_number(session)
        third = allocate_task_number(session)

    assert (first, second, third) == (1, 2, 3)


def test_allocate_task_number_is_sequential_across_sessions(
    tmp_path: Path,
) -> None:
    engine = create_engine_for_path(tmp_path / "test.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    allocated: list[int] = []
    for _ in range(3):
        with session_scope(SessionLocal) as session:
            allocated.append(allocate_task_number(session))

    assert allocated == [1, 2, 3]

    with SessionLocal() as session:
        row = session.execute(select(TaskNumberSeq)).scalar_one()
        assert row.last_number == 3


def test_allocate_task_number_is_gap_free_under_concurrency(
    tmp_path: Path,
) -> None:
    engine = create_engine_for_path(tmp_path / "test.db")
    init_schema(engine)
    SessionLocal = create_session_factory(engine)

    thread_count = 50
    barrier = threading.Barrier(thread_count)
    results: list[int] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        with session_scope(SessionLocal) as session:
            number = allocate_task_number(session)
        with results_lock:
            results.append(number)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == list(range(1, thread_count + 1))
    assert len(set(results)) == thread_count
