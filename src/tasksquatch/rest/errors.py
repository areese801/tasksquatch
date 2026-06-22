"""
Exception handlers for the tasksquatch REST surface.

Each domain exception in :mod:`tasksquatch.core.errors` carries a
``status_code`` and an optional ``detail`` mapping. The handlers in
this module render a uniform JSON body for every error type so the
clients (the local Web UI and user automation) can parse failures
consistently:

.. code-block:: json

    {
        "code": "not_found",
        "message": "Task #42 does not exist",
        "details": {"task_id": "..."}
    }

The catch-all handler for :class:`TasksquatchError` covers any
subclass that does not have its own dedicated handler (e.g.
:class:`ConcurrencyError`, which is reserved for the future but does
not need its own response code today).
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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


def _error_body(exc: TasksquatchError, code: str) -> dict[str, Any]:
    """
    Build the canonical JSON body for a domain exception.

    :param exc: The exception that was raised.
    :param code: A short machine-readable identifier for the failure.
    :returns: A dict ready to be serialized as the response body.
    """
    return {
        "code": code,
        "message": exc.message,
        "details": exc.detail or {},
    }


async def _not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`NotFoundError` into a 404 response.
    """
    err = cast(NotFoundError, exc)
    return JSONResponse(
        status_code=NotFoundError.status_code,
        content=_error_body(err, "not_found"),
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`ValidationError` into a 422 response.
    """
    err = cast(ValidationError, exc)
    return JSONResponse(
        status_code=ValidationError.status_code,
        content=_error_body(err, "validation_error"),
    )


async def _recurrence_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`RecurrenceError` into a 422 response.

    :class:`RecurrenceError` is a :class:`ValidationError` subclass;
    it gets its own handler so the response carries a more specific
    ``code`` field for clients that want to surface recurrence problems
    differently from generic validation failures.
    """
    err = cast(RecurrenceError, exc)
    return JSONResponse(
        status_code=RecurrenceError.status_code,
        content=_error_body(err, "recurrence_error"),
    )


async def _project_not_empty_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`ProjectNotEmptyError` into a 409 response.
    """
    err = cast(ProjectNotEmptyError, exc)
    return JSONResponse(
        status_code=ProjectNotEmptyError.status_code,
        content=_error_body(err, "project_not_empty"),
    )


async def _inbox_protected_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`InboxProtectedError` into a 409 response.
    """
    err = cast(InboxProtectedError, exc)
    return JSONResponse(
        status_code=InboxProtectedError.status_code,
        content=_error_body(err, "inbox_protected"),
    )


async def _already_completed_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`AlreadyCompletedError` into a 409 response.
    """
    err = cast(AlreadyCompletedError, exc)
    return JSONResponse(
        status_code=AlreadyCompletedError.status_code,
        content=_error_body(err, "already_completed"),
    )


async def _concurrency_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate :class:`ConcurrencyError` into a 409 response.

    No service raises this today (v1 has no optimistic concurrency),
    but registering the handler now means the eventual feature does
    not need to touch the REST app to plug in.
    """
    err = cast(ConcurrencyError, exc)
    return JSONResponse(
        status_code=ConcurrencyError.status_code,
        content=_error_body(err, "concurrency_error"),
    )


async def _tasksquatch_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Translate any other :class:`TasksquatchError` subclass into 500.

    This is the catch-all. FastAPI dispatches the most specific
    handler first, so this only runs for subclasses that do not have
    their own dedicated handler above.
    """
    err = cast(TasksquatchError, exc)
    return JSONResponse(
        status_code=TasksquatchError.status_code,
        content=_error_body(err, "internal_error"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Wire every domain exception handler onto a FastAPI app.

    Order matters in the sense that more specific subclasses are
    registered first; FastAPI itself picks the most specific match
    regardless of registration order, but listing them specific-first
    keeps the intent obvious to a reader.

    :param app: The FastAPI application to mutate.
    """
    app.add_exception_handler(NotFoundError, _not_found_handler)
    app.add_exception_handler(RecurrenceError, _recurrence_handler)
    app.add_exception_handler(ValidationError, _validation_handler)
    app.add_exception_handler(ProjectNotEmptyError, _project_not_empty_handler)
    app.add_exception_handler(InboxProtectedError, _inbox_protected_handler)
    app.add_exception_handler(AlreadyCompletedError, _already_completed_handler)
    app.add_exception_handler(ConcurrencyError, _concurrency_handler)
    app.add_exception_handler(TasksquatchError, _tasksquatch_handler)
