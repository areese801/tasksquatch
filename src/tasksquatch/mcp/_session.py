"""
Session plumbing for the tasksquatch MCP server.

The MCP server is launched on demand, opens one engine against the
configured SQLite database, and hands out short-lived sessions to each
tool invocation. The helpers in this module exist so server.py and
tools.py do not need to repeat the engine/session boilerplate.

A :class:`CoreContext` is constructed once at server startup via
:func:`build_core`; every tool call then opens a per-call session via
the :func:`open_session` context manager, which commits on normal exit
and rolls back on exception so the in-process activity log stays
consistent regardless of how a tool fails.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tasksquatch.core import paths
from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.seed import ensure_inbox


@dataclass(frozen=True)
class CoreContext:
    """
    Container for the shared engine and session factory used by the
    MCP server.

    A single :class:`CoreContext` is built at server startup. Tool
    handlers never receive the engine directly — they call
    :func:`open_session` with the context to obtain a session whose
    transaction is bounded by the surrounding ``with`` block.
    """

    engine: Engine
    session_factory: sessionmaker[Session]
    db_path: Path


def build_core(db_path: str | Path | None = None) -> CoreContext:
    """
    Build the process-wide :class:`CoreContext` for the MCP server.

    Resolves the SQLite path via
    :func:`tasksquatch.core.paths.get_db_path` (which honors the
    ``TASKSQUATCH_DB`` environment variable when ``db_path`` is
    ``None``), constructs the engine with the standard WAL pragmas,
    creates any missing tables via :func:`init_schema`, and seeds the
    Inbox via :func:`ensure_inbox` so the very first tool call against
    a fresh database does not have to.

    :param db_path: Optional explicit override for the database path.
        When ``None``, resolution falls back to the env var and then
        the XDG default.
    :returns: A fully-initialized :class:`CoreContext`.
    """
    resolved = paths.get_db_path(db_path)
    engine = create_engine_for_path(resolved)
    init_schema(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as session:
        ensure_inbox(session)

    return CoreContext(engine=engine, session_factory=factory, db_path=resolved)


@contextlib.contextmanager
def open_session(core: CoreContext) -> Iterator[Session]:
    """
    Yield a per-tool-call session bound to the MCP context.

    Commits on normal exit, rolls back and re-raises on any exception,
    and always closes the session on exit. Tool handlers must never
    commit or rollback the yielded session themselves — the surrounding
    ``with`` block owns the transaction boundary.

    :param core: The MCP context built by :func:`build_core`.
    :yields: An open :class:`Session`.
    """
    with session_scope(core.session_factory) as session:
        yield session
