"""
FastAPI application factory for the tasksquatch REST surface.

The REST surface is launched on demand by ``tasksquatch web``; it is
not a daemon, has no authentication, and binds to loopback by
default. See ``docs/spec.md`` §10 for the surface contract.

This module owns:

- :func:`create_app` — the canonical factory that builds a
  :class:`FastAPI` app pointing at a specific (or default) database.
- :func:`get_app_factory` — a no-argument callable that uvicorn's
  ``--factory`` mode can invoke to build the default app.
- :func:`lifespan` — the async-context manager FastAPI runs at
  startup/shutdown to initialize the engine, ensure the Inbox is
  seeded, and dispose of the engine on shutdown.

Domain routers are mounted under ``/api/v1`` by :func:`create_app`;
the unversioned ``/healthz`` liveness probe sits at the root.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tasksquatch import __version__
from tasksquatch.core import (
    create_engine_for_path,
    create_session_factory,
    ensure_inbox,
    get_db_path,
    init_schema,
    session_scope,
)
from tasksquatch.rest.errors import register_exception_handlers
from tasksquatch.rest.routers import activity as activity_router
from tasksquatch.rest.routers import comments as comments_router
from tasksquatch.rest.routers import labels as labels_router
from tasksquatch.rest.routers import projects as projects_router
from tasksquatch.rest.routers import tasks as tasks_router
from tasksquatch.web import router as web_router

_STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan that wires the engine and session factory.

    On startup: resolve the database path (honoring
    ``app.state.db_path_override`` if the caller set it),
    build the engine, create the schema, ensure the Inbox row
    exists, and stash the engine and session factory on
    ``app.state``.

    On shutdown: dispose of the engine so its connection pool
    releases SQLite file handles.

    :param app: The FastAPI application being managed.
    """
    db_path = get_db_path(getattr(app.state, "db_path_override", None))
    engine = create_engine_for_path(db_path)
    init_schema(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        ensure_inbox(session)
    app.state.engine = engine
    app.state.session_factory = session_factory
    try:
        yield
    finally:
        engine.dispose()


def create_app(db_path: Path | None = None) -> FastAPI:
    """
    Build a FastAPI application bound to a tasksquatch database.

    :param db_path: Optional path to the SQLite database file. When
        omitted, the lifespan resolves the path via
        :func:`tasksquatch.core.paths.get_db_path` (env var, then XDG
        default).
    :returns: A configured :class:`FastAPI` app. The engine and
        session factory are initialized lazily during the lifespan
        startup, so callers should drive the app via
        :class:`fastapi.testclient.TestClient` (as a context manager)
        or ``uvicorn`` rather than calling endpoints directly.
    """
    app = FastAPI(
        title="tasksquatch",
        version=__version__,
        description="Offline-first, local-only todo tracker.",
        lifespan=lifespan,
    )
    app.state.db_path_override = db_path
    register_exception_handlers(app)

    app.include_router(tasks_router.router, prefix="/api/v1")
    app.include_router(projects_router.router, prefix="/api/v1")
    app.include_router(labels_router.router, prefix="/api/v1")
    app.include_router(comments_router.router, prefix="/api/v1")
    app.include_router(activity_router.router, prefix="/api/v1")

    app.include_router(web_router.router)
    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        """
        Liveness probe.

        :returns: A small JSON object with ``status: "ok"``.
        """
        return {"status": "ok"}

    return app


def get_app_factory() -> FastAPI:
    """
    No-arg factory referenced by ``uvicorn --factory``.

    uvicorn imports this symbol and calls it once (because the CLI
    passes ``factory=True``), and uses the returned :class:`FastAPI`
    as the ASGI application. Wrapping :func:`create_app` (which takes
    an optional ``db_path``) in this nullary thunk lets us keep
    :func:`create_app` typed and explicit while still satisfying
    uvicorn's contract.

    :returns: A freshly-built default :class:`FastAPI` application.
    """
    return create_app()
