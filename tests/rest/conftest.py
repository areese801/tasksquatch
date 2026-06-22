"""
Shared fixtures for the REST surface tests.

The factory fixture rebuilds a fresh :class:`FastAPI` per test
pointing at a temporary SQLite file, so tests never share state and
never touch the user's real database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tasksquatch.rest.app import create_app


@pytest.fixture
def app_factory(tmp_path: Path) -> Callable[[], FastAPI]:
    """
    Return a no-arg factory that builds a fresh REST app per call.

    Each invocation points at the same per-test SQLite file under
    ``tmp_path``. Reusing the path across calls within a single test
    is intentional — it lets tests construct multiple apps and observe
    schema continuity.

    :param tmp_path: pytest's per-test temporary directory.
    :returns: A nullary callable that returns a configured
        :class:`FastAPI`.
    """
    db_path = tmp_path / "rest.db"

    def _factory() -> FastAPI:
        """
        Build a fresh REST application bound to the test db file.
        """
        return create_app(db_path=db_path)

    return _factory


@pytest.fixture
def client(app_factory: Callable[[], FastAPI]) -> Iterator[TestClient]:
    """
    Yield a :class:`TestClient` with the lifespan running.

    Using ``with TestClient(app) as client`` drives the FastAPI
    lifespan, which is what wires the engine and session factory onto
    ``app.state``. Without that, dependencies that read ``app.state``
    blow up at request time.

    :param app_factory: The per-test factory fixture.
    :yields: An open :class:`TestClient`.
    """
    app = app_factory()
    with TestClient(app) as test_client:
        yield test_client
