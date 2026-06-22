"""
``tasksquatch notify`` — placeholder for the due-check pass (Epic 7).
"""

from __future__ import annotations

import typer


def notify() -> None:
    """
    Run the due-check and desktop-notification pass (Epic 7).

    Currently a stub: writes a "not yet implemented" line to stderr
    and exits with status 1 so cron/launchd schedulers surface the
    miss instead of silently succeeding.
    """
    typer.echo(
        "tasksquatch notify is not yet implemented (Epic 7).",
        err=True,
    )
    raise typer.Exit(code=1)
