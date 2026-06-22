"""
Smoke tests for the REST application factory.

Covers the bare minimum: the app builds, ``/healthz`` returns the
expected body, unknown routes still return FastAPI's default 404, and
the lifespan actually seeds the Inbox in the on-disk database.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tasksquatch.core.models import Project
from tasksquatch.rest.app import create_app


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_404_with_no_route(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 404


def test_lifespan_seeds_inbox(app_factory: Callable[[], FastAPI]) -> None:
    app = app_factory()
    with TestClient(app):
        session_factory: sessionmaker[Session] = app.state.session_factory
        with session_factory() as session:
            inboxes = (
                session.execute(select(Project).where(Project.is_inbox.is_(True)))
                .scalars()
                .all()
            )
            assert len(inboxes) == 1
            assert inboxes[0].name == "Inbox"


def test_create_app_returns_distinct_instances(tmp_path: Path) -> None:
    app_a = create_app(db_path=tmp_path / "a.db")
    app_b = create_app(db_path=tmp_path / "b.db")
    assert app_a is not app_b
    assert isinstance(app_a, FastAPI)
    assert isinstance(app_b, FastAPI)
