"""
Alembic wiring and migration-consistency tests.

These tests guard the migration layer at three points:

1. ``alembic upgrade head`` succeeds against an empty SQLite file and
   produces every expected domain table plus the seeded Inbox row.
2. The migration head matches the live ORM ``Base.metadata`` — no
   schema drift between code and migrations.
3. ``alembic downgrade base`` undoes the upgrade cleanly, leaving only
   Alembic's own bookkeeping table behind.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from alembic import command
from tasksquatch.core.db import Base, create_engine_for_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

EXPECTED_TABLES = {
    "projects",
    "tasks",
    "labels",
    "task_labels",
    "comments",
    "activity_log",
    "task_number_seq",
}


def _make_config(db_path: Path) -> Config:
    """
    Build an Alembic :class:`Config` rooted at the project's alembic.ini.

    Sets the script_location to the project's ``alembic/`` directory
    using an absolute path so the test does not depend on the current
    working directory.

    :param db_path: SQLite file the migration should run against. Used
        only for human-readable logging; the actual URL is resolved
        inside ``alembic/env.py`` from ``TASKSQUATCH_DB``.
    :returns: A configured Alembic :class:`Config`.
    """
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # Recorded for debugging; env.py reads TASKSQUATCH_DB directly.
    cfg.attributes["db_path"] = str(db_path)
    return cfg


def test_upgrade_head_creates_schema_and_seeds_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "alembic.db"
    monkeypatch.setenv("TASKSQUATCH_DB", str(db_path))

    cfg = _make_config(db_path)
    command.upgrade(cfg, "head")

    engine = create_engine_for_path(db_path)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(table_names)

    with engine.connect() as conn:
        inbox_rows = [
            tuple(row)
            for row in conn.exec_driver_sql(
                "SELECT name, is_inbox, position FROM projects"
            ).fetchall()
        ]
        assert inbox_rows == [("Inbox", 1, 0)]

        seq_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM task_number_seq"
        ).scalar_one()
        assert seq_count == 0

    engine.dispose()


def test_migration_matches_orm_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "alembic.db"
    monkeypatch.setenv("TASKSQUATCH_DB", str(db_path))

    cfg = _make_config(db_path)
    command.upgrade(cfg, "head")

    engine = create_engine_for_path(db_path)
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={"compare_type": True, "render_as_batch": True},
        )
        diff = compare_metadata(context, Base.metadata)

    engine.dispose()
    assert diff == [], f"Schema drift between ORM and migrations: {diff!r}"


def test_downgrade_base_removes_all_domain_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "alembic.db"
    monkeypatch.setenv("TASKSQUATCH_DB", str(db_path))

    cfg = _make_config(db_path)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = create_engine_for_path(db_path)
    inspector = inspect(engine)
    remaining = set(inspector.get_table_names())
    engine.dispose()

    assert remaining.isdisjoint(EXPECTED_TABLES), (
        f"Tables left after downgrade: {remaining & EXPECTED_TABLES!r}"
    )
