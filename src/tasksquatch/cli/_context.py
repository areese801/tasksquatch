"""
CLI-level dependency injection for tasksquatch.

The Typer root callback builds a :class:`CliContext` once per invocation
and stashes it on ``ctx.obj``; individual commands pull it back out via
:func:`get_cli_context` and obtain a transactional session via
:func:`open_session`. Keeping this plumbing in one module means commands
stay focused on parse-input/format-output and never touch the engine,
session factory, or seed step directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from sqlalchemy.orm import Session

from tasksquatch.core import db, paths, seed


@dataclass
class CliContext:
    """
    Per-invocation CLI state derived from global flags.

    :ivar db_path: Explicit ``--db`` override, or ``None`` to fall back
        to ``$TASKSQUATCH_DB`` / XDG defaults at session-open time.
    :ivar json: When True, commands that support a JSON output mode
        should emit JSON instead of human-readable tables.
    :ivar console: The Rich :class:`Console` that commands print to.
    """

    db_path: Path | None
    json: bool
    console: Console


@contextmanager
def open_session(ctx: CliContext) -> Iterator[Session]:
    """
    Yield a transactional SQLAlchemy session bound to the CLI's DB.

    Resolves the database path from ``ctx.db_path`` (falling back to
    environment / XDG defaults), builds an engine, ensures the schema
    exists, and seeds the Inbox before yielding. Commits on normal
    exit and rolls back on exception.

    ``init_schema`` is idempotent; we use it here so first-run
    ``tasksquatch add ...`` does not require a separate
    ``tasksquatch init`` step. Alembic users get the same schema.

    :param ctx: The CLI context produced by the Typer root callback.
    :yields: An open :class:`Session` inside an active transaction.
    """
    path = paths.get_db_path(ctx.db_path)
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


def get_cli_context(ctx: typer.Context) -> CliContext:
    """
    Return the :class:`CliContext` attached by the root callback.

    :param ctx: The Typer click context for the current invocation.
    :returns: The :class:`CliContext` previously stored on ``ctx.obj``.
    :raises RuntimeError: If ``ctx.obj`` is missing or not a
        :class:`CliContext`, which means the root callback never ran.
    """
    obj = ctx.obj
    if not isinstance(obj, CliContext):
        raise RuntimeError(
            "CliContext is not attached to the Typer context; "
            "the root callback was not invoked."
        )
    return obj
