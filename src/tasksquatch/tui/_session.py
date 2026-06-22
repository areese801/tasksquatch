"""
SQLAlchemy session plumbing for the tasksquatch TUI.

The TUI is a short-lived surface that opens its own SQLite session
against the on-disk database each time it needs to read or write. This
module owns the engine construction, schema initialization, and Inbox
seeding, and exposes a :class:`CoreFactory` protocol so the rest of
the TUI (and its tests) can ask for a session without knowing how it
was built.

The default factory builds one engine per call to
:func:`default_core_factory` and reuses it across the sessions it
produces, so the connection pool — and the WAL journal — survive
across user actions. Tests inject their own factory backed by a
shared in-memory or temp-file engine.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tasksquatch.core import db, paths, seed


class CoreFactory(Protocol):
    """
    Callable that yields a transactional session bound to ``core``.

    The protocol matches a context manager returning function: calling
    a :class:`CoreFactory` opens a fresh session (with the schema and
    Inbox already in place) and returns a context manager that commits
    on normal exit and rolls back on exception.
    """

    def __call__(self) -> contextlib.AbstractContextManager[Session]:
        """
        Open a transactional session against the TUI's database.

        :returns: A context manager that yields an open :class:`Session`.
        """
        ...


@contextlib.contextmanager
def open_tui_session(db_path: Path | None = None) -> Iterator[Session]:
    """
    Open a one-shot transactional session for a single TUI action.

    Resolves the database path (defaulting to env / XDG when ``None``),
    builds a fresh engine, ensures the schema exists, seeds the Inbox,
    and yields the session inside an active transaction. Commits on
    normal exit, rolls back on exception, and always closes the
    session.

    This is the simplest entry point for tests or scripts that want a
    one-off session; the long-lived TUI app prefers
    :func:`default_core_factory` so a single engine survives across
    every action.

    :param db_path: Optional explicit DB path; ``None`` falls back to
        :func:`tasksquatch.core.paths.get_db_path`.
    :yields: An open :class:`Session` in an active transaction.
    """
    path = paths.get_db_path(db_path)
    engine = db.create_engine_for_path(path)
    db.init_schema(engine)
    session_factory = db.create_session_factory(engine)

    session = session_factory()
    try:
        seed.ensure_inbox(session)
        session.commit()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def default_core_factory(db_path: Path | None = None) -> CoreFactory:
    """
    Build the default :class:`CoreFactory` for the TUI app.

    Constructs the engine and session factory once (and seeds the
    Inbox once on the first call), then returns a callable that opens
    a fresh transactional session per invocation. Reusing the engine
    across actions keeps the SQLite connection pool warm and preserves
    the WAL journal between user gestures.

    :param db_path: Optional explicit DB path; ``None`` falls back to
        :func:`tasksquatch.core.paths.get_db_path`.
    :returns: A :class:`CoreFactory` bound to the resolved database.
    """
    path = paths.get_db_path(db_path)
    engine: Engine = db.create_engine_for_path(path)
    db.init_schema(engine)
    session_factory: sessionmaker[Session] = db.create_session_factory(engine)

    bootstrap_session = session_factory()
    try:
        seed.ensure_inbox(bootstrap_session)
        bootstrap_session.commit()
    except Exception:
        bootstrap_session.rollback()
        raise
    finally:
        bootstrap_session.close()

    @contextlib.contextmanager
    def _scope() -> Iterator[Session]:
        """
        Yield a transactional session backed by the shared engine.

        :yields: An open :class:`Session` in an active transaction.
        """
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _factory() -> contextlib.AbstractContextManager[Session]:
        """
        Return a fresh session context manager.

        :returns: A context manager yielding an open :class:`Session`.
        """
        return _scope()

    return _factory
