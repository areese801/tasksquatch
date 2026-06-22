from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from tasksquatch.core.db import create_engine_for_path, init_schema


def test_init_schema_creates_every_expected_table(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "schema.db")
    init_schema(engine)

    table_names = set(inspect(engine).get_table_names())
    expected = {
        "projects",
        "tasks",
        "labels",
        "task_labels",
        "comments",
        "activity_log",
        "task_number_seq",
    }

    assert expected.issubset(table_names), table_names
