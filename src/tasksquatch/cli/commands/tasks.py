"""
Task-centric Typer commands for the tasksquatch CLI.

Each command opens a session through
:func:`tasksquatch.cli._context.open_session`, resolves any
human-friendly references (project name, label name, task number),
delegates to :mod:`tasksquatch.core.services.tasks` (or its sibling
services) for the actual state change, and renders the result via
the helpers in :mod:`tasksquatch.cli.rendering`. The
:func:`~tasksquatch.cli.commands._meta.cli_command` decorator turns
domain errors into a non-zero exit with a friendly message.

A small convention for ``edit`` lets users clear scalar fields without
the spec's :data:`tasksquatch.core.UNSET` sentinel: passing the literal
string ``"none"`` (case-insensitive) for a date, time, or RRULE option
clears the field; passing the empty string ``""`` for the description
clears it. Omitting an option leaves the underlying field untouched.
"""

from __future__ import annotations

from datetime import date, time
from typing import cast

import typer

from tasksquatch.cli._context import CliContext, get_cli_context, open_session
from tasksquatch.cli._parsers import (
    parse_date,
    parse_date_cb,
    parse_priority_cb,
    parse_time,
    parse_time_cb,
)
from tasksquatch.cli._resolvers import (
    resolve_label,
    resolve_project,
    resolve_task_ref,
)
from tasksquatch.cli.commands._meta import cli_command
from tasksquatch.cli.rendering import (
    print_json,
    print_table,
    render_task,
    render_task_detail,
)
from tasksquatch.core import UNSET
from tasksquatch.core._sentinels import _UnsetType
from tasksquatch.core.errors import ValidationError
from tasksquatch.core.models import Priority, RecurrenceAnchor
from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service

_CLEAR_TOKENS = frozenset({"none", "clear", "null"})


def _parse_anchor(value: str) -> RecurrenceAnchor:
    """
    Parse a CLI ``--anchor`` value into :class:`RecurrenceAnchor`.

    :param value: ``"fixed"`` or ``"relative"`` (case-insensitive).
    :returns: The matching :class:`RecurrenceAnchor`.
    :raises ValidationError: If ``value`` is not a recognized anchor.
    """
    key = value.strip().lower()
    if key == "fixed":
        return RecurrenceAnchor.FIXED
    if key == "relative":
        return RecurrenceAnchor.RELATIVE
    raise ValidationError(
        f"unknown recurrence anchor {value!r}; expected 'fixed' or 'relative'",
        detail={"anchor": value},
    )


def _maybe_clear(value: str | None) -> str | None | _UnsetType:
    """
    Translate the ``"none"`` / ``""`` sentinels for the ``edit`` UX.

    - ``None`` (not provided): :data:`UNSET` (do not touch the field).
    - ``""`` or one of the clear tokens: ``None`` (clear the field).
    - Any other string: itself.
    """
    if value is None:
        return UNSET
    stripped = value.strip()
    if stripped == "" or stripped.lower() in _CLEAR_TOKENS:
        return None
    return value


@cli_command
def add(
    ctx: typer.Context,
    title: str = typer.Argument(..., help="Task title."),
    project: str | None = typer.Option(
        None,
        "-p",
        "--project",
        help="Project name or ID; defaults to Inbox.",
    ),
    due: str | None = typer.Option(
        None,
        "-d",
        "--due",
        help="Due date (YYYY-MM-DD, 'today', or 'tomorrow').",
        callback=parse_date_cb,
    ),
    time_: str | None = typer.Option(
        None,
        "-t",
        "--time",
        help="Due time (HH:MM, 24-hour).",
        callback=parse_time_cb,
    ),
    priority: str | None = typer.Option(
        None,
        "-P",
        "--priority",
        help="Priority: p1/p2/p3/p4, 1-4, or high/medium/normal/low.",
        callback=parse_priority_cb,
    ),
    labels: list[str] = typer.Option(  # noqa: B008
        [],
        "-l",
        "--label",
        help="Label name or ID; repeatable.",
    ),
    rrule: str | None = typer.Option(
        None,
        "-r",
        "--rrule",
        help="RRULE recurrence (RFC 5545).",
    ),
    anchor: str = typer.Option(
        "fixed",
        "-a",
        "--anchor",
        help="Recurrence anchor: fixed | relative.",
    ),
    parent: str | None = typer.Option(
        None,
        "--parent",
        help="Parent task number or UUID.",
    ),
    description: str | None = typer.Option(
        None,
        "--desc",
        help="Markdown description.",
    ),
) -> None:
    """
    Create a new task.
    """
    cli_ctx = get_cli_context(ctx)
    due_date = cast(date | None, due)
    due_time = cast(time | None, time_)
    priority_value = cast(Priority | None, priority)
    parsed_anchor = _parse_anchor(anchor)

    with open_session(cli_ctx) as session:
        project_id = resolve_project(session, project).id if project else None
        label_ids = [resolve_label(session, lbl).id for lbl in labels]
        parent_id = resolve_task_ref(session, parent).id if parent else None

        task = tasks_service.create_task(
            session,
            title=title,
            project_id=project_id,
            parent_id=parent_id,
            description=description,
            priority=priority_value if priority_value is not None else Priority.P4,
            due_date=due_date,
            due_time=due_time,
            recurrence=rrule,
            recurrence_anchor=parsed_anchor,
            label_ids=label_ids,
        )
        session.commit()

        if cli_ctx.json:
            print_json(render_task(task), console=cli_ctx.console)
        else:
            cli_ctx.console.print(f"created task #{task.number}: {task.title}")


@cli_command
def list_tasks(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None,
        "-p",
        "--project",
        help="Restrict to this project (name or ID).",
    ),
    label: str | None = typer.Option(
        None,
        "-l",
        "--label",
        help="Restrict to tasks carrying this label (name or ID).",
    ),
    priority: str | None = typer.Option(
        None,
        "-P",
        "--priority",
        help="Restrict to this priority.",
        callback=parse_priority_cb,
    ),
    completed: bool | None = typer.Option(
        None,
        "--completed/--no-completed",
        help="Restrict to completed or incomplete tasks.",
    ),
    due_before: str | None = typer.Option(
        None,
        "--due-before",
        help="Restrict to tasks due on or before this date.",
        callback=parse_date_cb,
    ),
    due_after: str | None = typer.Option(
        None,
        "--due-after",
        help="Restrict to tasks due on or after this date.",
        callback=parse_date_cb,
    ),
    top_level: bool = typer.Option(
        False,
        "--top-level/--no-top-level",
        help="When set, return only top-level tasks (no subtasks).",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Maximum row count.",
    ),
    order_by: str = typer.Option(
        "position",
        "--order-by",
        help="Ordering: position | due_date | priority | created_at.",
    ),
) -> None:
    """
    List tasks, optionally filtered.
    """
    cli_ctx = get_cli_context(ctx)
    priority_value = cast(Priority | None, priority)
    due_before_date = cast(date | None, due_before)
    due_after_date = cast(date | None, due_after)

    with open_session(cli_ctx) as session:
        project_id = resolve_project(session, project).id if project else None
        label_id = resolve_label(session, label).id if label else None
        parent_filter: str | None | _UnsetType = None if top_level else UNSET

        rows = queries_service.list_tasks(
            session,
            project_id=project_id,
            label_id=label_id,
            parent_id=parent_filter,
            priority=priority_value,
            completed=completed,
            due_before=due_before_date,
            due_after=due_after_date,
            order_by=order_by,
            limit=limit,
        )

        rendered = [render_task(task) for task in rows]
        if cli_ctx.json:
            print_json(rendered, console=cli_ctx.console)
        else:
            print_table(
                rendered,
                columns=[
                    "number",
                    "title",
                    "project",
                    "priority",
                    "due",
                    "labels",
                    "completed",
                ],
                console=cli_ctx.console,
                title="tasks",
            )


@cli_command
def show(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
) -> None:
    """
    Show full detail for a single task.
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        subtasks = queries_service.list_subtasks(session, task.id, recursive=False)
        comments = queries_service.list_comments(session, task.id)

        detail = render_task_detail(task, subtasks=subtasks, comments=comments)

        if cli_ctx.json:
            print_json(detail, console=cli_ctx.console)
        else:
            _print_task_detail(cli_ctx, detail)


def _print_task_detail(
    cli_ctx: CliContext,
    detail: dict[str, object],
) -> None:
    """
    Print the human-readable detail view of a single task.
    """
    console = cli_ctx.console
    console.print(f"#{detail['number']} {detail['title']}")
    console.print(f"  project:     {detail['project']}")
    console.print(f"  priority:    {detail['priority']}")
    console.print(f"  due:         {detail['due']}")
    console.print(f"  labels:      {detail['labels']}")
    console.print(f"  completed:   {detail['completed']}")
    if detail["recurrence"] != "-":
        console.print(
            f"  recurrence:  {detail['recurrence']} ({detail['recurrence_anchor']})"
        )
    if detail["parent"] is not None:
        console.print(f"  parent:      #{detail['parent']}")
    console.print(f"  description: {detail['description']}")
    console.print(f"  created_at:  {detail['created_at']}")
    if detail["completed_at"] is not None:
        console.print(f"  completed_at: {detail['completed_at']}")
    subtasks = cast(list[dict[str, object]], detail["subtasks"])
    if subtasks:
        console.print("  subtasks:")
        for sub in subtasks:
            mark = "x" if sub["completed"] else " "
            console.print(f"    [{mark}] #{sub['number']} {sub['title']}")
    comments = cast(list[dict[str, object]], detail["comments"])
    if comments:
        console.print("  comments:")
        for comment in comments:
            console.print(f"    [{comment['created_at']}] {comment['body']}")


@cli_command
def done(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
) -> None:
    """
    Mark a task complete.
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        was_recurring = bool(task.recurrence)
        previous_completed = task.completed
        previous_number = task.number
        previous_title = task.title

        tasks_service.complete_task(session, task.id)
        session.commit()

        if was_recurring and not task.completed and not previous_completed:
            new_due = task.due_date.isoformat() if task.due_date is not None else "-"
            cli_ctx.console.print(
                f"completed task #{previous_number}: {previous_title} "
                f"(advanced to {new_due})"
            )
        else:
            cli_ctx.console.print(
                f"completed task #{previous_number}: {previous_title}"
            )


@cli_command
def undo(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
) -> None:
    """
    Reverse a task's completed state.
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        tasks_service.uncomplete_task(session, task.id)
        session.commit()
        cli_ctx.console.print(f"reopened task #{task.number}: {task.title}")


@cli_command
def edit(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
    title: str | None = typer.Option(
        None,
        "--title",
        help="New title.",
    ),
    due: str | None = typer.Option(
        None,
        "-d",
        "--due",
        help="New due date (YYYY-MM-DD / today / tomorrow / none).",
    ),
    time_: str | None = typer.Option(
        None,
        "-t",
        "--time",
        help="New due time (HH:MM / none).",
    ),
    priority: str | None = typer.Option(
        None,
        "-P",
        "--priority",
        help="New priority (p1/p2/p3/p4 / 1-4 / high/medium/normal/low).",
        callback=parse_priority_cb,
    ),
    description: str | None = typer.Option(
        None,
        "--desc",
        help="New description; pass '' to clear.",
    ),
    rrule: str | None = typer.Option(
        None,
        "-r",
        "--rrule",
        help="New RRULE; pass 'none' to clear.",
    ),
    anchor: str | None = typer.Option(
        None,
        "-a",
        "--anchor",
        help="New recurrence anchor: fixed | relative.",
    ),
    label_add: list[str] = typer.Option(  # noqa: B008
        [],
        "--label-add",
        help="Label to attach; repeatable.",
    ),
    label_remove: list[str] = typer.Option(  # noqa: B008
        [],
        "--label-remove",
        help="Label to detach; repeatable.",
    ),
) -> None:
    """
    Edit a task's fields and labels in place.

    Omit an option to leave its field untouched. Pass ``"none"`` for a
    date, time, or RRULE to clear that field; pass an empty string for
    ``--desc`` to clear the description.
    """
    cli_ctx = get_cli_context(ctx)
    priority_value = cast(Priority | None, priority)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)

        title_arg: str | _UnsetType = UNSET if title is None else title
        description_arg = _maybe_clear(description)
        due_date_arg: date | None | _UnsetType = _convert_due_arg(due)
        due_time_arg: time | None | _UnsetType = _convert_time_arg(time_)
        recurrence_arg: str | None | _UnsetType = _maybe_clear(rrule)
        anchor_arg: RecurrenceAnchor | _UnsetType = (
            UNSET if anchor is None else _parse_anchor(anchor)
        )
        priority_arg: Priority | _UnsetType = (
            UNSET if priority_value is None else priority_value
        )

        tasks_service.update_task(
            session,
            task.id,
            title=title_arg,
            description=description_arg,
            priority=priority_arg,
            due_date=due_date_arg,
            due_time=due_time_arg,
            recurrence=recurrence_arg,
            recurrence_anchor=anchor_arg,
        )

        for label_ref in label_add:
            label = resolve_label(session, label_ref)
            tasks_service.add_label(session, task.id, label.id)
        for label_ref in label_remove:
            label = resolve_label(session, label_ref)
            tasks_service.remove_label(session, task.id, label.id)

        session.commit()
        cli_ctx.console.print(f"updated task #{task.number}")


def _convert_due_arg(due: str | None) -> date | None | _UnsetType:
    """
    Translate the ``edit --due`` option into a service argument.

    ``None`` (unset) → :data:`UNSET`; ``"none"`` / ``""`` → ``None``;
    anything else → the parsed :class:`~datetime.date` (or
    :class:`typer.BadParameter` on malformed input).
    """
    if due is None:
        return UNSET
    stripped = due.strip()
    if stripped == "" or stripped.lower() in _CLEAR_TOKENS:
        return None
    return parse_date(due)


def _convert_time_arg(value: str | None) -> time | None | _UnsetType:
    """
    Translate the ``edit --time`` option into a service argument.

    ``None`` (unset) → :data:`UNSET`; ``"none"`` / ``""`` → ``None``;
    anything else → the parsed :class:`~datetime.time` (or
    :class:`typer.BadParameter` on malformed input).
    """
    if value is None:
        return UNSET
    stripped = value.strip()
    if stripped == "" or stripped.lower() in _CLEAR_TOKENS:
        return None
    return parse_time(value)


@cli_command
def rm(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
    yes: bool = typer.Option(
        False,
        "-y",
        "--yes",
        help="Skip confirmation.",
    ),
) -> None:
    """
    Hard-delete a task (and its subtasks and comments).
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        number = task.number
        title = task.title

        if not yes:
            cli_ctx.console.print(
                f"about to delete task #{number}: {title} (and all subtasks/comments)"
            )
            typer.confirm(
                f"delete task #{number}?",
                default=False,
                abort=True,
            )

        tasks_service.delete_task(session, task.id)
        session.commit()
        cli_ctx.console.print(f"deleted task #{number}")


@cli_command
def move(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
    project: str = typer.Argument(
        ...,
        help="Destination project name or ID.",
    ),
) -> None:
    """
    Move a top-level task to another project.
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        destination = resolve_project(session, project)
        tasks_service.move_task(session, task.id, new_project_id=destination.id)
        session.commit()
        cli_ctx.console.print(
            f"moved task #{task.number} to project {destination.name!r}"
        )


@cli_command
def comment(
    ctx: typer.Context,
    ref: str = typer.Argument(..., help="Task number or UUID."),
    body: str = typer.Argument(..., help="Comment body."),
) -> None:
    """
    Add a comment to a task.
    """
    cli_ctx = get_cli_context(ctx)

    with open_session(cli_ctx) as session:
        task = resolve_task_ref(session, ref)
        comments_service.add_comment(session, task_id=task.id, body=body)
        session.commit()
        cli_ctx.console.print(f"added comment to #{task.number}")
