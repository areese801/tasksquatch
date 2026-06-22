"""
SQLite engine, session, and ORM base for tasksquatch core.

This module owns the project-wide :class:`DeclarativeBase`, the SQLite
engine factory (with the WAL/foreign-key PRAGMAs every connection
requires), the session factory, and a transactional ``session_scope``
context manager. It also defines the single piece of infrastructure
state required by the ID allocator — :class:`TaskNumberSeq` — which is
not a domain entity and therefore lives here rather than under a
``models`` package.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint, Integer, create_engine, event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

from tasksquatch.core import paths


class Base(DeclarativeBase):
    """
    Declarative base for every ORM model in tasksquatch.

    All mapped classes — both infrastructure (this module) and domain
    entities (added in later stories) — share this single declarative
    base so that :meth:`Base.metadata.create_all` builds the entire
    schema in one pass.
    """


class TaskNumberSeq(Base):
    """
    Single-row counter table backing the user-facing task ``number``.

    Exactly one row, fixed at ``id = 1``, is ever present in this table.
    The ``last_number`` column holds the highest ``number`` ever issued
    and is never decremented — deleting a task does not free its
    number, which is the design promise that ``#42`` remains a stable
    reference forever.
    """

    __tablename__ = "task_number_seq"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (CheckConstraint("id = 1", name="ck_task_number_seq_singleton"),)


def create_engine_for_path(path: Path, *, echo: bool = False) -> Engine:
    """
    Build a SQLAlchemy engine bound to a SQLite file at ``path``.

    Every new DBAPI connection produced by the engine has the
    tasksquatch standard PRAGMAs applied: ``foreign_keys=ON``,
    ``journal_mode=WAL``, ``synchronous=NORMAL``, and
    ``busy_timeout=5000``. The engine also overrides pysqlite's
    legacy auto-BEGIN behavior so that every SQLAlchemy transaction
    starts with an explicit ``BEGIN IMMEDIATE``, which serializes
    concurrent writers cleanly without risking SQLITE_BUSY from
    upgrading a read lock to a write lock mid-transaction.

    :param path: Filesystem path to the SQLite database file.
    :param echo: When True, log every SQL statement to stderr.
    :returns: A configured SQLAlchemy :class:`Engine`.
    """
    engine = create_engine(
        f"sqlite:///{path}",
        echo=echo,
        future=True,
        # check_same_thread=False lets pooled connections cross threads;
        # SQLAlchemy's pool already serializes per-connection use, and
        # SQLite (in its default thread-safe compile) is fine with this.
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
        # dbapi_connection is the raw sqlite3.Connection; typing it as Any
        # avoids depending on SQLAlchemy's internal DBAPIConnection Protocol.
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA busy_timeout = 5000")
        finally:
            cursor.close()
        # Disable pysqlite's implicit transaction management so the
        # explicit BEGIN IMMEDIATE in the "begin" hook below is the only
        # transaction start. Without this, pysqlite issues its own BEGIN
        # before our hook can fire.
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn: Connection) -> None:
        # BEGIN IMMEDIATE acquires the write lock at transaction start,
        # so concurrent writers queue at BEGIN (where busy_timeout will
        # wait them out) rather than racing into a deadlock when they
        # try to upgrade read locks to write locks at UPDATE time.
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """
    Build a ``sessionmaker`` bound to the given engine.

    Sessions produced by the factory do not auto-flush, do not
    auto-commit, and do not expire attributes on commit — callers
    control the transaction boundary explicitly via
    :func:`session_scope`.

    :param engine: The engine the sessions will use.
    :returns: A configured :class:`sessionmaker`.
    """
    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@contextlib.contextmanager
def session_scope(
    SessionLocal: sessionmaker[Session],
) -> Iterator[Session]:
    """
    Provide a transactional session scope.

    Yields a session, commits on normal exit, rolls back and re-raises
    on any exception, and always closes the session on exit. Callers
    must never commit or rollback the yielded session themselves.

    :param SessionLocal: The session factory to draw the session from.
    :yields: An open :class:`Session`.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@functools.lru_cache(maxsize=1)
def get_default_engine() -> Engine:
    """
    Return the process-wide default engine, building it on first use.

    Cached so every surface in the same process shares one engine and
    therefore one SQLite connection pool. Uses
    :func:`paths.get_default_db_path` to locate the database file.

    :returns: The shared :class:`Engine`.
    """
    return create_engine_for_path(paths.get_default_db_path())


@functools.lru_cache(maxsize=1)
def get_default_session_factory() -> sessionmaker[Session]:
    """
    Return the process-wide default session factory.

    Cached and bound to the engine returned by
    :func:`get_default_engine`.

    :returns: The shared :class:`sessionmaker`.
    """
    return create_session_factory(get_default_engine())


def init_schema(engine: Engine) -> None:
    """
    Create every table declared on :class:`Base` if it does not exist.

    Intended for use by tests and by the ``tasksquatch init`` command
    (added in a later story). Production startup will rely on Alembic
    once migrations land in TSQ-16.

    :param engine: The engine whose database receives the schema.
    """
    Base.metadata.create_all(engine)
