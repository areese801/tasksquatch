"""
FastAPI dependency callables for the tasksquatch REST surface.

The REST app stores its SQLAlchemy engine and session factory on
``app.state`` during the lifespan startup. These helpers read those
attributes back out for use as :func:`fastapi.Depends` arguments, so
routers (added in TSQ-24) and tests can declare a typed ``session``
parameter without each one reaching into ``app.state`` directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(request: Request) -> Engine:
    """
    Return the engine bound to the current FastAPI application.

    :param request: The active FastAPI request — gives access to the
        application instance and therefore to ``app.state``.
    :returns: The :class:`Engine` initialized during the lifespan
        startup.
    :raises RuntimeError: If the engine has not been initialized.
        This indicates the request was served before the lifespan
        startup ran, which the framework normally prevents.
    """
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise RuntimeError(
            "tasksquatch REST engine is not initialized; "
            "this dependency must be resolved after the lifespan startup."
        )
    return cast(Engine, engine)


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """
    Return the session factory bound to the current application.

    :param request: The active FastAPI request.
    :returns: The :class:`sessionmaker` initialized during the
        lifespan startup.
    :raises RuntimeError: If the session factory has not been
        initialized.
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise RuntimeError(
            "tasksquatch REST session factory is not initialized; "
            "this dependency must be resolved after the lifespan startup."
        )
    return cast(sessionmaker[Session], factory)


def get_session(request: Request) -> Iterator[Session]:
    """
    Yield a per-request SQLAlchemy session.

    Commits on normal exit, rolls back if the endpoint raises, and
    always closes the session in the ``finally`` clause. Endpoints
    declare this as a dependency via
    ``session: Session = Depends(get_session)`` so they never own the
    transaction boundary themselves.

    :param request: The active FastAPI request.
    :yields: An open :class:`Session` bound to the lifespan engine.
    """
    factory = get_session_factory(request)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
