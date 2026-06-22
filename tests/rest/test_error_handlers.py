"""
Tests for the REST exception handlers.

Each error type registers its own handler; we exercise each one by
attaching a throwaway route to a fresh FastAPI app and asserting on
the response status code and body shape.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tasksquatch.core.errors import (
    AlreadyCompletedError,
    ConcurrencyError,
    InboxProtectedError,
    NotFoundError,
    ProjectNotEmptyError,
    RecurrenceError,
    TasksquatchError,
    ValidationError,
)
from tasksquatch.rest.errors import register_exception_handlers


def _build_raising_app(exc: Exception) -> FastAPI:
    """
    Build a tiny FastAPI app whose ``/boom`` route raises ``exc``.

    No lifespan is configured because none of the exception handlers
    touch ``app.state``; the test only cares about response shaping.
    """
    app = FastAPI()
    register_exception_handlers(app)

    def _boom() -> None:
        raise exc

    app.add_api_route("/boom", _boom, methods=["GET"])
    return app


class _NoStatusSubclass(TasksquatchError):
    """
    Subclass that has no dedicated handler so it falls through to the
    catch-all :func:`_tasksquatch_handler`.
    """


_HANDLER_CASES: list[tuple[TasksquatchError, int, str]] = [
    (NotFoundError("missing", detail={"id": "abc"}), 404, "not_found"),
    (
        ValidationError("bad input", detail={"field": "name"}),
        422,
        "validation_error",
    ),
    (
        RecurrenceError("bad rrule", detail={"rrule": "x"}),
        422,
        "recurrence_error",
    ),
    (
        ProjectNotEmptyError("has tasks", detail={"task_count": 3}),
        409,
        "project_not_empty",
    ),
    (InboxProtectedError("nope"), 409, "inbox_protected"),
    (AlreadyCompletedError("done already"), 409, "already_completed"),
    (ConcurrencyError("stale"), 409, "concurrency_error"),
    (_NoStatusSubclass("kaboom"), 500, "internal_error"),
]


@pytest.mark.parametrize(("exc", "expected_status", "expected_code"), _HANDLER_CASES)
def test_handlers_translate_exceptions(
    exc: TasksquatchError, expected_status: int, expected_code: str
) -> None:
    app = _build_raising_app(exc)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == expected_status
    body = response.json()
    assert set(body.keys()) == {"code", "message", "details"}
    assert body["code"] == expected_code
    assert body["message"] == exc.message
    assert body["details"] == (exc.detail or {})


def test_details_empty_when_no_detail_provided() -> None:
    exc = NotFoundError("missing")
    app = _build_raising_app(exc)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    body: dict[str, Any] = response.json()
    assert body["details"] == {}


def test_register_idempotent_for_each_class() -> None:
    """
    Registering the handlers twice on the same app must not error.

    FastAPI just overwrites prior entries for the same class.
    """
    app = FastAPI()
    register_exception_handlers(app)
    register_exception_handlers(app)
    register: Callable[[Any], None] = register_exception_handlers
    assert register is register_exception_handlers
