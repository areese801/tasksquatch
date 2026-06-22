"""
Domain exception hierarchy for tasksquatch core.

Every error raised by ``core/services`` is a subclass of
:class:`TasksquatchError`. Each class declares a ``status_code`` class
attribute that surfaces (REST in particular) can translate directly
into an HTTP response code, but the exceptions themselves are
transport-agnostic — the CLI and TUI consume them too.
"""

from __future__ import annotations

from typing import Any


class TasksquatchError(Exception):
    """
    Base class for every domain error raised by ``tasksquatch.core``.

    Carries an optional ``detail`` mapping for structured context that
    surfaces can render to the user (e.g. the number of remaining tasks
    that prevented a project deletion). Subclasses override
    ``status_code`` to map to the HTTP status the REST surface should
    return; the value is also useful as a stable, machine-readable
    classification of the failure for non-HTTP callers.
    """

    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the error with a human message and optional detail.

        :param message: A short, user-facing explanation of what went
            wrong. Used as the exception's ``args[0]`` so ``str(exc)``
            returns it.
        :param detail: Optional structured context to accompany the
            message. Stored verbatim (no copy) on ``self.detail``.
        """
        super().__init__(message)
        self.message = message
        self.detail: dict[str, Any] = detail if detail is not None else {}


class NotFoundError(TasksquatchError):
    """
    Raised when a lookup by id (or other unique key) returns no row.

    Surfaces should treat this as the canonical "404 Not Found"
    condition. Includes the missing identifier in ``detail`` when the
    caller passes it.
    """

    status_code = 404


class ValidationError(TasksquatchError):
    """
    Raised when input fails a business-rule check before any write.

    Examples: empty name after whitespace strip, duplicate label name,
    a malformed RRULE string (via :class:`RecurrenceError`). Maps to
    HTTP 422 Unprocessable Entity at the REST surface.
    """

    status_code = 422


class ProjectNotEmptyError(TasksquatchError):
    """
    Raised when a project deletion is attempted while tasks still
    belong to it.

    The DB-level foreign key uses ``ON DELETE RESTRICT``; the service
    layer surfaces that as this friendlier error rather than letting a
    raw :class:`sqlalchemy.exc.IntegrityError` escape. The ``detail``
    payload includes ``task_count`` so the caller can render a useful
    message.
    """

    status_code = 409


class InboxProtectedError(TasksquatchError):
    """
    Raised when the caller tries to rename or delete the Inbox project.

    The Inbox is a singleton and is part of the application contract —
    it cannot be removed, renamed, or otherwise made to disappear.
    """

    status_code = 409


class RecurrenceError(ValidationError):
    """
    Raised when an RRULE string is malformed or cannot be evaluated.

    Inherits from :class:`ValidationError` (and therefore reports
    ``status_code = 422``) because the underlying problem is bad
    input. Also raised by :func:`tasksquatch.core.recurrence.next_occurrence`
    when a ``RELATIVE`` anchor is used without a completion timestamp.
    """


class AlreadyCompletedError(TasksquatchError):
    """
    Raised when a task that is already completed is completed again.

    The task service treats double-completion as a no-op error so the
    caller can tell whether they performed a state transition; the
    REST layer maps this to HTTP 409 Conflict.
    """

    status_code = 409


class ConcurrencyError(TasksquatchError):
    """
    Reserved for optimistic-concurrency conflicts.

    v1 of tasksquatch does not use ETags, ``If-Match`` headers, or
    version columns (see ``docs/spec.md`` — single-user app), so this
    exception is **not raised by any service today**. It exists as a
    placeholder so that surfaces can register handlers ahead of time
    and so a future version of the app can introduce concurrency
    control without churning the exception hierarchy.
    """

    status_code = 409
