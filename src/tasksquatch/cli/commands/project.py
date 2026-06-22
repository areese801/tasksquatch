"""
Project-centric Typer sub-app for the tasksquatch CLI.

``tasksquatch project ...`` exposes the minimum management surface a
single-user app needs: create, list, rename, delete. Each command opens
its own session through
:func:`tasksquatch.cli._context.open_session`, resolves human-friendly
project references via :mod:`tasksquatch.cli._resolvers`, and delegates
to :mod:`tasksquatch.core.services.projects` for the actual mutation.
The :func:`~tasksquatch.cli.commands._meta.cli_command` decorator
translates :class:`~tasksquatch.core.errors.TasksquatchError` into a
friendly red message and a non-zero exit.
"""

from __future__ import annotations

import typer

from tasksquatch.cli._context import get_cli_context, open_session
from tasksquatch.cli._resolvers import resolve_project
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.cli.rendering import print_json, print_table
from tasksquatch.core import UNSET
from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service

project_app = typer.Typer(help="Manage projects.")


@cli_command
def add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Project name."),
) -> None:
    """
    Create a new project.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        project = projects_service.create_project(session, name=name)
        session.commit()

        if cli_ctx.json:
            print_json(
                {
                    "id": project.id,
                    "name": project.name,
                    "is_inbox": project.is_inbox,
                },
                console=cli_ctx.console,
            )
        else:
            cli_ctx.console.print(f"created project {project.name}")


@cli_command
def ls(ctx: typer.Context) -> None:
    """
    List every project with its top-level task count.

    Note: this issues one count query per project. Acceptable for the
    single-user, tens-of-projects scale tasksquatch targets; if project
    counts grow into the hundreds, replace with a single GROUP BY query.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        projects = projects_service.list_projects(session)
        rows = []
        for project in projects:
            task_count = len(
                queries_service.list_tasks(
                    session,
                    project_id=project.id,
                    parent_id=UNSET,
                )
            )
            rows.append(
                {
                    "name": project.name,
                    "task_count": task_count,
                    "is_inbox": project.is_inbox,
                    "id": project.id,
                }
            )

        if cli_ctx.json:
            print_json(rows, console=cli_ctx.console)
        else:
            print_table(
                rows,
                columns=["name", "task_count", "is_inbox", "id"],
                console=cli_ctx.console,
                title="projects",
            )


@cli_command
def rename(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Project name or UUID."),
    new_name: str = typer.Argument(..., help="New project name."),
) -> None:
    """
    Rename a project.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        project = resolve_project(session, ref)
        old_name = project.name
        projects_service.rename_project(session, project.id, new_name)
        session.commit()
        cli_ctx.console.print(f"renamed project {old_name!r} to {project.name!r}")


@cli_command
def rm(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Project name or UUID."),
    yes: bool = typer.Option(
        False,
        "-y",
        "--yes",
        help="Skip confirmation.",
    ),
) -> None:
    """
    Delete a project. The project must have no remaining tasks.
    """
    cli_ctx = get_cli_context(ctx)
    with open_session(cli_ctx) as session:
        project = resolve_project(session, ref)
        name = project.name

        if not yes:
            cli_ctx.console.print(f"about to delete project {name!r}")
            typer.confirm(
                f"delete project {name!r}?",
                default=False,
                abort=True,
            )

        projects_service.delete_project(session, project.id)
        session.commit()
        cli_ctx.console.print(f"deleted project {name!r}")


project_app.command(name="add")(add)
project_app.command(name="ls")(ls)
project_app.command(name="rename")(rename)
project_app.command(name="rm")(rm)
