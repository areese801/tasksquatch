"""
``tasksquatch tui`` — launch the interactive Textual interface.

Builds a :class:`TasksquatchTuiApp` against the database resolved by
the CLI root callback (honoring ``--db`` / ``$TASKSQUATCH_DB`` / the
XDG default) and hands control off to Textual until the user quits.
"""

from __future__ import annotations

import typer

from tasksquatch.cli._context import get_cli_context
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.tui.app import TasksquatchTuiApp


@cli_command
def tui(ctx: typer.Context) -> None:
    """
    Launch the interactive Textual TUI.

    Blocks the foreground until the user quits the app (``q`` on the
    project list, ``Ctrl-C`` anywhere). The TUI opens its own short-
    lived sessions against the resolved database path; concurrency
    with the CLI / notify is handled at the SQLite WAL layer.

    :param ctx: Typer click context, used to resolve the CLI's
        :class:`CliContext` and therefore the database path.
    """
    cli_ctx = get_cli_context(ctx)
    app = TasksquatchTuiApp(db_path=cli_ctx.db_path)
    app.run()
