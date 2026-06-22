"""
Alembic environment for tasksquatch.

The runtime database URL is resolved here rather than in ``alembic.ini``:
the ``TASKSQUATCH_DB`` environment variable wins if set, otherwise we
fall back to :func:`tasksquatch.core.paths.get_default_db_path`. In
both cases the resolved :class:`~pathlib.Path` is converted to a
``sqlite:///`` URL before being handed to Alembic.

Importing :mod:`tasksquatch.core.models` (and :class:`TaskNumberSeq`
from :mod:`tasksquatch.core.db`) here ensures every mapped class has
registered with :attr:`Base.metadata` by the time autogenerate inspects
it.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context
from tasksquatch.core import models  # noqa: F401  (register mappers)
from tasksquatch.core.db import Base, TaskNumberSeq  # noqa: F401  (register mapper)
from tasksquatch.core.paths import get_default_db_path

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_db_url() -> str:
    """
    Return the SQLite URL Alembic should run against.

    Resolution order:

    1. ``TASKSQUATCH_DB`` from the environment, if set.
    2. :func:`tasksquatch.core.paths.get_default_db_path`.

    :returns: A SQLAlchemy ``sqlite:///`` URL string.
    """
    raw = os.environ.get("TASKSQUATCH_DB")
    path = Path(raw).expanduser() if raw else get_default_db_path()
    return f"sqlite:///{path}"


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures the context with a URL only, emitting SQL to stdout
    rather than executing against a live connection.
    """
    context.configure(
        url=_resolve_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode against a live SQLite connection.

    The engine is built from the alembic.ini ``sqlalchemy.*`` section
    but with its URL overridden by :func:`_resolve_db_url` so the
    placeholder URL in alembic.ini is never used.
    """
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _resolve_db_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
