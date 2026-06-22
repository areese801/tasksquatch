"""
``tasksquatch notify`` — run the due-check + desktop-notification pass.

The CLI command is a thin shell over
:func:`tasksquatch.notify.runner.run_notify_sync`. It opens a CLI
session against the configured database, invokes the runner once, and
prints a short line summarizing how many notifications were fired.

The command is the entry point cron / launchd / systemd timers call —
see ``docs/notifications.md`` for the supported scheduling recipes.
"""

from __future__ import annotations

import typer

from tasksquatch.cli._context import get_cli_context, open_session
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.notify.runner import run_notify_sync


@cli_command
def notify(ctx: typer.Context) -> None:
    """
    Run the due-check and desktop-notification pass.

    Opens a session against the configured database, fires desktop
    notifications for every task currently due, and stamps each task's
    ``last_notified_at`` for dedup. Prints the count of notifications
    fired on exit.
    """
    app_ctx = get_cli_context(ctx)
    with open_session(app_ctx) as session:
        count = run_notify_sync(session)
    app_ctx.console.print(f"fired [bold]{count}[/bold] notification(s).")
