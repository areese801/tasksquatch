"""
Typer application root for ``tasksquatch``.

This module owns the :data:`app` symbol referenced by the
``tasksquatch`` console-script entry point and the global ``--db`` /
``--json`` flags exposed to every subcommand. Each subcommand lives in
its own module under :mod:`tasksquatch.cli.commands` and is registered
on the app here.
"""

from __future__ import annotations

from pathlib import Path

import typer

from tasksquatch.cli._context import CliContext
from tasksquatch.cli.commands import find as find_cmd
from tasksquatch.cli.commands import label as label_cmd
from tasksquatch.cli.commands import notify as notify_cmd
from tasksquatch.cli.commands import project as project_cmd
from tasksquatch.cli.commands import tasks as tasks_cmd
from tasksquatch.cli.commands import version as version_cmd
from tasksquatch.cli.rendering import default_console

app = typer.Typer(
    help="tasksquatch — offline-first todo tracker.",
    no_args_is_help=True,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

_DB_OPTION = typer.Option(
    None,
    "--db",
    help=(
        "Override the SQLite DB path. Falls back to $TASKSQUATCH_DB, then XDG default."
    ),
)
_JSON_OPTION = typer.Option(
    False,
    "--json",
    "-J",
    help="Emit JSON instead of human tables where supported.",
)


@app.callback()
def _root(
    ctx: typer.Context,
    db: Path | None = _DB_OPTION,
    json_output: bool = _JSON_OPTION,
) -> None:
    """
    tasksquatch CLI root.

    Stashes a :class:`CliContext` on the Typer click context so every
    command can read the global flags via
    :func:`tasksquatch.cli._context.get_cli_context`.
    """
    ctx.obj = CliContext(
        db_path=db,
        json=json_output,
        console=default_console(),
    )


app.command(name="version")(version_cmd.version)
app.command(name="notify")(notify_cmd.notify)
app.command(name="add")(tasks_cmd.add)
app.command(name="list")(tasks_cmd.list_tasks)
app.command(name="show")(tasks_cmd.show)
app.command(name="done")(tasks_cmd.done)
app.command(name="undo")(tasks_cmd.undo)
app.command(name="edit")(tasks_cmd.edit)
app.command(name="rm")(tasks_cmd.rm)
app.command(name="move")(tasks_cmd.move)
app.command(name="comment")(tasks_cmd.comment)
app.command(name="find")(find_cmd.find)
app.add_typer(project_cmd.project_app, name="project")
app.add_typer(label_cmd.label_app, name="label")
