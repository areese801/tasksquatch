"""
Label-centric Typer sub-app for the tasksquatch CLI.

``tasksquatch label ...`` mirrors the project sub-app: create, list,
rename, delete. Labels are cross-project tags; the core service emits
the activity log entries and the database cascades association cleanup
on delete, so this surface only handles input parsing, reference
resolution, and output formatting.
"""

from __future__ import annotations

import typer

from tasksquatch.cli._context import get_cli_context, open_session
from tasksquatch.cli._resolvers import resolve_label
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.cli.rendering import print_json, print_table
from tasksquatch.core import UNSET
from tasksquatch.core.services import labels as labels_service
from tasksquatch.core.services import queries as queries_service

label_app = typer.Typer(help="Manage labels.")


@cli_command
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Label name."),
) -> None:
    """
    Create a new label.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        label = labels_service.create_label(session, name=name)
        session.commit()

        if cli_ctx.json:
            print_json(
                {"id": label.id, "name": label.name},
                console=cli_ctx.console,
            )
        else:
            cli_ctx.console.print(f"created label {label.name}")


@cli_command
def ls(ctx: typer.Context) -> None:
    """
    List every label with its top-level task count.

    Note: this issues one count query per label. Acceptable at the
    single-user, tens-of-labels scale tasksquatch targets; if label
    counts grow into the hundreds, replace with a single GROUP BY query.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        labels = labels_service.list_labels(session)
        rows = []
        for label in labels:
            task_count = len(
                queries_service.list_tasks(
                    session,
                    label_id=label.id,
                    parent_id=UNSET,
                )
            )
            rows.append(
                {
                    "name": label.name,
                    "task_count": task_count,
                    "id": label.id,
                }
            )

        if cli_ctx.json:
            print_json(rows, console=cli_ctx.console)
        else:
            print_table(
                rows,
                columns=["name", "task_count", "id"],
                console=cli_ctx.console,
                title="labels",
            )


@cli_command
def rename(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Label name or UUID."),
    new_name: str = typer.Argument(..., help="New label name."),
) -> None:
    """
    Rename a label.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        label = resolve_label(session, ref)
        old_name = label.name
        labels_service.rename_label(session, label.id, new_name)
        session.commit()
        cli_ctx.console.print(f"renamed label {old_name!r} to {label.name!r}")


@cli_command
def rm(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Label name or UUID."),
    yes: bool = typer.Option(
        False,
        "-y",
        "--yes",
        help="Skip confirmation.",
    ),
) -> None:
    """
    Delete a label. The association rows are removed via cascade.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        label = resolve_label(session, ref)
        name = label.name

        if not yes:
            cli_ctx.console.print(f"about to delete label {name!r}")
            typer.confirm(
                f"delete label {name!r}?",
                default=False,
                abort=True,
            )

        labels_service.delete_label(session, label.id)
        session.commit()
        cli_ctx.console.print(f"deleted label {name!r}")


label_app.command(name="add")(add)
label_app.command(name="ls")(ls)
label_app.command(name="rename")(rename)
label_app.command(name="rm")(rm)
