"""
Shared fixtures for ``tasksquatch.notify`` tests.

Mirrors :mod:`tests.core.services.conftest` so the notify tests can lean
on the same SQLite-per-test setup the service-layer tests use.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
)


@pytest.fixture()
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    """
    Build a sessionmaker over a fresh temporary SQLite database.

    :param tmp_path: pytest's per-test temp dir fixture.
    :returns: A sessionmaker bound to an initialized empty schema.
    """
    engine = create_engine_for_path(tmp_path / "notify.db")
    init_schema(engine)
    return create_session_factory(engine)


@pytest.fixture()
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """
    Yield a session that commits on success and rolls back on error.

    :param session_factory: The factory from :func:`session_factory`.
    :yields: An open SQLAlchemy session.
    """
    sess = session_factory()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
