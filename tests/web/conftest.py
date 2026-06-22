"""
Shared fixtures for the Web UI surface tests.

Each test gets a fresh REST app pointing at a temporary SQLite file
plus a small seeded fixture set (one extra project, three tasks) so
that the typical Inbox-default rendering has something to display.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tasksquatch.core import (
    create_engine_for_path,
    create_project,
    create_session_factory,
    create_task,
    ensure_inbox,
    init_schema,
    session_scope,
)
from tasksquatch.rest.app import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """
    Return a per-test SQLite path the tests share with the REST app.
    """
    return tmp_path / "web.db"


@pytest.fixture
def seeded_db(db_path: Path) -> dict[str, str]:
    """
    Seed the per-test database with one extra project and three tasks.

    :returns: A mapping with ``inbox_id``, ``project_id``, ``task_ids``
        keys the tests can use to navigate the seed data.
    """
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        inbox = ensure_inbox(session)
        project = create_project(session, name="Work")
        task_a = create_task(session, title="First task", project_id=inbox.id)
        task_b = create_task(session, title="Second task", project_id=inbox.id)
        task_c = create_task(session, title="Project task", project_id=project.id)
        ids = {
            "inbox_id": inbox.id,
            "project_id": project.id,
            "task_a_id": task_a.id,
            "task_b_id": task_b.id,
            "task_c_id": task_c.id,
        }
    engine.dispose()
    return ids


@pytest.fixture
def app_factory(db_path: Path) -> Callable[[], FastAPI]:
    """
    Return a no-arg factory that builds a REST app for the test db.
    """

    def _factory() -> FastAPI:
        """
        Build a fresh REST application bound to the test db file.
        """
        return create_app(db_path=db_path)

    return _factory


@pytest.fixture
def client(
    app_factory: Callable[[], FastAPI],
    seeded_db: dict[str, str],
) -> Iterator[TestClient]:
    """
    Yield a :class:`TestClient` with seed data already loaded.

    The ``seeded_db`` fixture runs before the app starts so the
    lifespan's :func:`ensure_inbox` call finds the seeded Inbox row.
    """
    app = app_factory()
    with TestClient(app) as test_client:
        yield test_client
