"""
``tasksquatch web`` — launch the local REST API + Web UI server.

Runs uvicorn against :func:`tasksquatch.rest.app.get_app_factory`. The
server binds to loopback by default; there is no authentication. See
``docs/spec.md`` §10 for the surface contract.
"""

from __future__ import annotations

import typer
import uvicorn

from tasksquatch.cli.commands._meta import cli_command


@cli_command
def web(
    ctx: typer.Context,
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind host. Defaults to loopback only (no auth).",
    ),
    port: int = typer.Option(8000, "--port", help="TCP port to listen on."),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Auto-reload on code changes (dev only).",
    ),
) -> None:
    """
    Launch the local REST API + Web UI server.

    Blocks the foreground until the user interrupts with Ctrl-C. The
    REST surface is local-only by design: nothing in tasksquatch
    expects it to be reachable from another machine, and no auth
    layer protects it. Pass ``--host 0.0.0.0`` only on a trusted
    network you control.

    :param ctx: Typer click context (unused; present so the command
        plays nicely with the global ``--db`` flag).
    :param host: Bind host; defaults to ``127.0.0.1``.
    :param port: TCP port; defaults to ``8000``.
    :param reload: Enable uvicorn's reload watcher for development.
    """
    uvicorn.run(
        "tasksquatch.rest.app:get_app_factory",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
