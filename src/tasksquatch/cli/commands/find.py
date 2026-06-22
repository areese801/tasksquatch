"""
``tasksquatch find`` — fuzzy interactive task picker via ``fzf``.

The command queries every incomplete task, formats each as a single
fixed-shape line, and pipes the lines through ``fzf`` as a subprocess.
The user's selection is parsed back into a task ``number`` and the
requested ``--action`` is dispatched to the corresponding task command
(``show``, ``done``, ``undo``, ``rm``, ``edit``, ``move``, ``comment``).

``fzf`` is an external binary, not a Python dependency: we shell out to
``/usr/bin/fzf`` (whichever the PATH resolves) using
:func:`subprocess.run`. If ``fzf`` is not installed, the command exits
with code 2 and a hint message rather than crashing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable

import typer

from tasksquatch.cli._context import get_cli_context, open_session
from tasksquatch.cli.commands import tasks as tasks_cmd
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.core.errors import ValidationError
from tasksquatch.core.models import Task
from tasksquatch.core.services import queries as queries_service

FZF_MISSING_HINT = (
    "fzf binary not found. Install it (e.g. `brew install fzf` "
    "on macOS, `apt install fzf` on Debian/Ubuntu) and re-run."
)

_NUMBER_RE = re.compile(r"^#(\d+)")


def _format_fzf_line(task: Task) -> str:
    """
    Format a single task as an fzf-friendly line.

    The shape is ``"#<number>  <title>  [<project>]  [<labels-csv>]"``,
    with ``"-"`` substituted for a missing project or empty labels so
    every line has the same column count. Double-space separators keep
    the columns visually distinct even at narrow terminal widths.

    :param task: The task to format.
    :returns: The single-line representation.
    """
    project_name = task.project.name if task.project is not None else "-"
    label_names = sorted(label.name for label in task.labels)
    labels_csv = ",".join(label_names) if label_names else "-"
    return f"#{task.number}  {task.title}  [{project_name}]  [{labels_csv}]"


def _parse_number_from_line(line: str) -> int:
    """
    Pull the leading ``#<digits>`` out of an fzf selection.

    :param line: The line fzf wrote to stdout.
    :returns: The integer task number.
    :raises ValidationError: If the line does not begin with
        ``#<digits>``.
    """
    match = _NUMBER_RE.match(line.strip())
    if match is None:
        raise ValidationError(
            "could not parse task number from selection",
            detail={"line": line},
        )
    return int(match.group(1))


def _dispatch_action(ctx: typer.Context, action: str, number: int) -> None:
    """
    Invoke the matching task command for ``action`` against ``number``.

    Calls the existing task command functions directly (rather than
    re-entering the CLI through :class:`~typer.testing.CliRunner`) so
    we keep one process and avoid re-parsing arguments. ``rm`` is
    invoked with ``yes=False`` so the user still gets a confirmation
    prompt even when chosen via the fuzzy picker.

    :param ctx: The Typer click context for the current invocation.
    :param action: One of ``show``, ``done``, ``undo``, ``rm``,
        ``edit``, ``move``, ``comment``.
    :param number: The task number parsed from the fzf selection.
    :raises ValidationError: If ``action`` is not a recognized verb.
    """
    ref = str(number)
    handlers: dict[str, Callable[[], None]] = {
        "show": lambda: tasks_cmd.show(ctx, ref=ref),
        "done": lambda: tasks_cmd.done(ctx, ref=ref),
        "undo": lambda: tasks_cmd.undo(ctx, ref=ref),
        "rm": lambda: tasks_cmd.rm(ctx, ref=ref, yes=False),
        "edit": lambda: tasks_cmd.edit(ctx, ref=ref),
        "move": lambda: tasks_cmd.move(
            ctx,
            ref=ref,
            project=typer.prompt("destination project"),
        ),
        "comment": lambda: tasks_cmd.comment(
            ctx,
            ref=ref,
            body=typer.prompt("comment body"),
        ),
    }
    handler = handlers.get(action)
    if handler is None:
        raise ValidationError(
            f"unknown action {action!r}",
            detail={
                "action": action,
                "allowed": sorted(handlers.keys()),
            },
        )
    handler()


@cli_command
def find(
    ctx: typer.Context,
    action: str = typer.Option(
        "show",
        "--action",
        help=(
            "What to do with the selection: show | done | undo | rm | edit "
            "| move | comment."
        ),
    ),
) -> None:
    """
    Pipe incomplete tasks into fzf and act on the user's selection.

    Exit codes:

    * ``0`` — selection successfully dispatched (or no tasks to pick
      from).
    * ``1`` — user aborted the fzf picker (``Esc`` / ``Ctrl-C``) or
      the dispatched action surfaced a domain error.
    * ``2`` — fzf is not installed.
    """
    cli_ctx = get_cli_context(ctx)
    if shutil.which("fzf") is None:
        cli_ctx.console.print(f"[red]{FZF_MISSING_HINT}[/red]")
        raise typer.Exit(code=2)

    with open_session(cli_ctx) as session:
        tasks = queries_service.list_tasks(session, completed=False)
        lines = [_format_fzf_line(task) for task in tasks]

    if not lines:
        cli_ctx.console.print("[yellow]No incomplete tasks to pick from.[/yellow]")
        raise typer.Exit(code=0)

    stdin_text = "\n".join(lines)
    result = subprocess.run(
        ["fzf", "--prompt=tasksquatch> ", "--height=40%", "--reverse"],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise typer.Exit(code=1)

    chosen = result.stdout.strip().splitlines()[0]
    number = _parse_number_from_line(chosen)
    _dispatch_action(ctx, action, number)
