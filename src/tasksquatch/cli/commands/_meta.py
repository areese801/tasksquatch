"""
Shared command-level helpers for the tasksquatch CLI.

The :func:`cli_command` decorator wraps a Typer command function so
that :class:`~tasksquatch.core.errors.TasksquatchError` instances
raised from the service layer turn into a friendly red error message
and a non-zero exit code instead of a stack trace. Unexpected
exceptions are deliberately allowed to propagate — Typer's default
handling surfaces them to the developer rather than masking bugs.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import typer

from tasksquatch.cli._context import get_cli_context
from tasksquatch.core.errors import TasksquatchError


def cli_command[F: Callable[..., Any]](fn: F) -> F:
    """
    Translate domain errors raised by ``fn`` into a CLI-friendly exit.

    The decorated function must accept the Typer click context as its
    first positional parameter (named ``ctx``) so the wrapper can pull
    the :class:`~tasksquatch.cli._context.CliContext` and print to the
    user's Rich console.

    On :class:`~tasksquatch.core.errors.TasksquatchError`, prints
    ``Error: <message>`` in red and raises ``typer.Exit(code=1)`` so
    the shell sees a non-zero status. All other exceptions propagate
    unchanged.

    :param fn: The Typer command callable to wrap.
    :returns: The wrapped callable, with the same signature.
    """

    @wraps(fn)
    def wrapper(ctx: typer.Context, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(ctx, *args, **kwargs)
        except TasksquatchError as err:
            cli_ctx = get_cli_context(ctx)
            cli_ctx.console.print(f"[red]Error:[/red] {err.message}")
            raise typer.Exit(code=1) from err

    return wrapper  # type: ignore[return-value]
