"""
Tool handlers and JSON schemas for the tasksquatch MCP server.

Each handler is a top-level function named ``tool_<name>``; the
companion :data:`TOOL_HANDLERS` table maps the user-facing tool name to
the callable so :mod:`tasksquatch.mcp.server` can dispatch a tool call
without importing each function individually. :data:`JSON_SCHEMAS`
holds the corresponding JSON Schema for each tool's arguments and is
sent to the MCP client at ``tools/list`` time so the LLM sees the same
shape the handler expects.

Handlers accept a :class:`CoreContext`, open a per-call session via
:func:`open_session`, resolve any name-based references against the
database, call the relevant ``core/services`` function, and return a
JSON-serializable dict. The dict-not-model contract keeps the MCP
boundary independent of Pydantic's internal version churn — the schemas
in :mod:`tasksquatch.core.schemas` are used purely as serialization
helpers via ``model_dump(mode="json")``.

The MCP permission policy (see :mod:`tasksquatch.mcp._guard` and
``docs/spec.md`` §11) deliberately omits ``delete_task``,
``delete_project``, and ``delete_label`` — destructive deletion of those
entities is reserved for the CLI and TUI surfaces.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from tasksquatch.core import (
    UNSET,
    ActivityEventType,
    Label,
    NotFoundError,
    Priority,
    Project,
    RecurrenceAnchor,
    Task,
)
from tasksquatch.core.schemas import (
    ActivityRead,
    CommentRead,
    LabelRead,
    ProjectRead,
    TaskRead,
)
from tasksquatch.core.services import comments as comment_service
from tasksquatch.core.services import labels as label_service
from tasksquatch.core.services import projects as project_service
from tasksquatch.core.services import queries as query_service
from tasksquatch.core.services import tasks as task_service
from tasksquatch.mcp._session import CoreContext, open_session

ToolHandler = Callable[..., dict[str, Any]]


# --- Argument resolvers ------------------------------------------------


def _resolve_project(
    session: Session,
    *,
    project_id: str | None,
    project_name: str | None,
) -> Project | None:
    """
    Resolve a project reference passed as either id or name.

    ``project_id`` takes precedence when both are given. If neither is
    set the function returns ``None`` so the caller can fall back to
    the Inbox.

    :param session: An open SQLAlchemy session.
    :param project_id: UUIDv7 of the project, or ``None``.
    :param project_name: Human-readable project name, or ``None``.
    :returns: The :class:`Project` row, or ``None`` if neither key was
        supplied.
    :raises NotFoundError: If a key is supplied but no row matches.
    """
    if project_id is not None:
        project = session.get(Project, project_id)
        if project is None:
            raise NotFoundError(
                f"Project {project_id!r} not found.",
                detail={"project_id": project_id},
            )
        return project
    if project_name is not None:
        stmt = select(Project).where(Project.name == project_name)
        project = session.execute(stmt).scalar_one_or_none()
        if project is None:
            raise NotFoundError(
                f"Project named {project_name!r} not found.",
                detail={"project_name": project_name},
            )
        return project
    return None


def _resolve_label(
    session: Session,
    *,
    label_id: str | None,
    label_name: str | None,
) -> Label:
    """
    Resolve a label reference passed as either id or name.

    Exactly one of ``label_id`` or ``label_name`` must be set.

    :param session: An open SQLAlchemy session.
    :param label_id: UUIDv7 of the label, or ``None``.
    :param label_name: Human-readable label name, or ``None``.
    :returns: The :class:`Label` row.
    :raises NotFoundError: If no matching row exists.
    :raises ValueError: If neither key is supplied.
    """
    if label_id is not None:
        label = session.get(Label, label_id)
        if label is None:
            raise NotFoundError(
                f"Label {label_id!r} not found.",
                detail={"label_id": label_id},
            )
        return label
    if label_name is not None:
        stmt = select(Label).where(Label.name == label_name)
        label = session.execute(stmt).scalar_one_or_none()
        if label is None:
            raise NotFoundError(
                f"Label named {label_name!r} not found.",
                detail={"label_name": label_name},
            )
        return label
    raise ValueError("Either label_id or label_name must be supplied.")


def _resolve_task(
    session: Session,
    *,
    task_id: str | None,
    number: int | None,
) -> Task:
    """
    Resolve a task reference passed as either id or user-facing number.

    Exactly one of ``task_id`` or ``number`` must be set.

    :param session: An open SQLAlchemy session.
    :param task_id: UUIDv7 of the task, or ``None``.
    :param number: User-facing task number, or ``None``.
    :returns: The :class:`Task` row.
    :raises NotFoundError: If no matching task exists.
    :raises ValueError: If neither key is supplied.
    """
    if task_id is not None:
        return query_service.get_task_by_id(session, task_id)
    if number is not None:
        return query_service.get_task_by_number(session, number)
    raise ValueError("Either task_id or number must be supplied.")


# --- Coercion helpers --------------------------------------------------


def _parse_date(value: str | None) -> date | None:
    """
    Convert an ISO-8601 date string to a :class:`date`, or pass
    ``None`` through unchanged.

    :param value: ISO-8601 date string (``YYYY-MM-DD``), or ``None``.
    :returns: The parsed :class:`date` or ``None``.
    """
    if value is None:
        return None
    return date.fromisoformat(value)


def _parse_time(value: str | None) -> time | None:
    """
    Convert an ISO-8601 time string to a :class:`time`, or pass
    ``None`` through unchanged.

    :param value: ISO-8601 time string (``HH:MM`` or ``HH:MM:SS``), or
        ``None``.
    :returns: The parsed :class:`time` or ``None``.
    """
    if value is None:
        return None
    return time.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    """
    Convert an ISO-8601 datetime string to a :class:`datetime`, or
    pass ``None`` through unchanged.

    :param value: ISO-8601 datetime string, or ``None``.
    :returns: The parsed :class:`datetime` or ``None``.
    """
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _coerce_priority(value: str | None) -> Priority | None:
    """
    Coerce a string priority code to a :class:`Priority` member.

    :param value: One of ``"P1"``..``"P4"``, or ``None``.
    :returns: The matching :class:`Priority`, or ``None``.
    """
    if value is None:
        return None
    return Priority(value)


def _coerce_recurrence_anchor(value: str | None) -> RecurrenceAnchor | None:
    """
    Coerce a string anchor key to a :class:`RecurrenceAnchor` member.

    :param value: ``"fixed"`` or ``"relative"``, or ``None``.
    :returns: The matching :class:`RecurrenceAnchor`, or ``None``.
    """
    if value is None:
        return None
    return RecurrenceAnchor(value)


def _resolve_label_ids(
    session: Session,
    refs: list[str] | None,
) -> list[str]:
    """
    Resolve a list of label references (ids or names) to label ids.

    Each entry is tried as an id first (since UUIDv7 strings are
    fixed-shape) and falls back to a name lookup if no row matches.
    Both resolutions raise :class:`NotFoundError` on miss so the MCP
    client sees a uniform error.

    :param session: An open SQLAlchemy session.
    :param refs: List of label ids or names, or ``None``.
    :returns: A list of label ids in input order, with duplicates
        preserved.
    """
    if not refs:
        return []
    resolved: list[str] = []
    for ref in refs:
        existing = session.get(Label, ref)
        if existing is not None:
            resolved.append(existing.id)
            continue
        stmt = select(Label).where(Label.name == ref)
        by_name = session.execute(stmt).scalar_one_or_none()
        if by_name is None:
            raise NotFoundError(
                f"Label {ref!r} not found by id or name.",
                detail={"label_ref": ref},
            )
        resolved.append(by_name.id)
    return resolved


def _task_to_dict(task: Task) -> dict[str, Any]:
    """
    Serialize a :class:`Task` to a JSON-safe dict via
    :meth:`TaskRead.from_task`.

    :param task: The ORM row to serialize.
    :returns: A dict containing every public task field.
    """
    return TaskRead.from_task(task).model_dump(mode="json")


def _comment_to_dict(comment: Any) -> dict[str, Any]:
    """
    Serialize a :class:`Comment` ORM row to a JSON-safe dict.

    :param comment: The ORM row to serialize.
    :returns: A dict containing the public comment fields.
    """
    return CommentRead.model_validate(comment).model_dump(mode="json")


def _project_to_dict(project: Project) -> dict[str, Any]:
    """
    Serialize a :class:`Project` ORM row to a JSON-safe dict.

    :param project: The ORM row to serialize.
    :returns: A dict containing the public project fields.
    """
    return ProjectRead.model_validate(project).model_dump(mode="json")


def _label_to_dict(label: Label) -> dict[str, Any]:
    """
    Serialize a :class:`Label` ORM row to a JSON-safe dict.

    :param label: The ORM row to serialize.
    :returns: A dict containing the public label fields.
    """
    return LabelRead.model_validate(label).model_dump(mode="json")


def _activity_to_dict(activity: Any) -> dict[str, Any]:
    """
    Serialize an :class:`ActivityLog` ORM row to a JSON-safe dict.

    :param activity: The ORM row to serialize.
    :returns: A dict containing the public activity log fields.
    """
    return ActivityRead.model_validate(activity).model_dump(mode="json")


# --- Tool handlers -----------------------------------------------------


def tool_add_task(
    core: CoreContext,
    *,
    title: str,
    project_id: str | None = None,
    project_name: str | None = None,
    parent_id: str | None = None,
    parent_number: int | None = None,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    due_time: str | None = None,
    labels: list[str] | None = None,
    recurrence: str | None = None,
    recurrence_anchor: str | None = None,
) -> dict[str, Any]:
    """
    Create a new task and return the serialized :class:`TaskRead`.

    :param core: The MCP context.
    :param title: Required human-readable title.
    :param project_id: Optional project UUIDv7; takes precedence over
        ``project_name``.
    :param project_name: Optional project name to resolve when
        ``project_id`` is not given.
    :param parent_id: Optional parent task UUIDv7; takes precedence
        over ``parent_number``.
    :param parent_number: Optional parent task user-facing number.
    :param description: Optional free-form description.
    :param priority: Optional priority code ``"P1"``..``"P4"``.
    :param due_date: Optional ISO-8601 date.
    :param due_time: Optional ISO-8601 time.
    :param labels: Optional list of label ids or names to attach at
        creation time.
    :param recurrence: Optional RFC 5545 RRULE string.
    :param recurrence_anchor: Optional ``"fixed"`` or ``"relative"``
        anchor.
    :returns: The :class:`TaskRead` payload for the new task.
    """
    with open_session(core) as session:
        project = _resolve_project(
            session, project_id=project_id, project_name=project_name
        )
        resolved_parent_id: str | None
        if parent_id is not None:
            resolved_parent_id = parent_id
        elif parent_number is not None:
            resolved_parent_id = query_service.get_task_by_number(
                session, parent_number
            ).id
        else:
            resolved_parent_id = None

        label_ids = _resolve_label_ids(session, labels)
        priority_enum = _coerce_priority(priority) or Priority.P4
        anchor_enum = _coerce_recurrence_anchor(recurrence_anchor) or (
            RecurrenceAnchor.FIXED
        )

        task = task_service.create_task(
            session,
            title=title,
            project_id=project.id if project is not None else None,
            parent_id=resolved_parent_id,
            description=description,
            priority=priority_enum,
            due_date=_parse_date(due_date),
            due_time=_parse_time(due_time),
            recurrence=recurrence,
            recurrence_anchor=anchor_enum,
            label_ids=label_ids,
        )
        return _task_to_dict(task)


def tool_update_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    due_time: str | None = None,
    recurrence: str | None = None,
    recurrence_anchor: str | None = None,
) -> dict[str, Any]:
    """
    Apply a partial update to an existing task.

    Only fields present in the call are applied. Absent fields are
    treated as :data:`UNSET` and left untouched. Identify the target
    task via ``task_id`` or its user-facing ``number``.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :param title: New title, if changing.
    :param description: New description, if changing.
    :param priority: New priority code, if changing.
    :param due_date: New due date (ISO-8601), if changing.
    :param due_time: New due time (ISO-8601), if changing.
    :param recurrence: New RRULE string, if changing.
    :param recurrence_anchor: New anchor key, if changing.
    :returns: The updated :class:`TaskRead` payload.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)

        kwargs: dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if priority is not None:
            kwargs["priority"] = Priority(priority)
        if due_date is not None:
            kwargs["due_date"] = _parse_date(due_date)
        if due_time is not None:
            kwargs["due_time"] = _parse_time(due_time)
        if recurrence is not None:
            kwargs["recurrence"] = recurrence
        if recurrence_anchor is not None:
            kwargs["recurrence_anchor"] = RecurrenceAnchor(recurrence_anchor)

        updated = task_service.update_task(session, task.id, **kwargs)
        return _task_to_dict(updated)


def tool_complete_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
    when: str | None = None,
) -> dict[str, Any]:
    """
    Mark a task complete, advancing recurrence in place when set.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :param when: Optional ISO-8601 completion timestamp; defaults to
        now (UTC).
    :returns: The mutated :class:`TaskRead` payload.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        completed = task_service.complete_task(
            session, task.id, when=_parse_datetime(when)
        )
        return _task_to_dict(completed)


def tool_uncomplete_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
) -> dict[str, Any]:
    """
    Reverse a task's completion state.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :returns: The mutated :class:`TaskRead` payload.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        uncompleted = task_service.uncomplete_task(session, task.id)
        return _task_to_dict(uncompleted)


def tool_list_tasks(
    core: CoreContext,
    *,
    project_id: str | None = None,
    project_name: str | None = None,
    label_id: str | None = None,
    label_name: str | None = None,
    priority: str | None = None,
    completed: bool | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    parent_id: str | None = None,
    include_descendants: bool = False,
    order_by: str = "position",
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Return tasks matching the supplied filters.

    ``parent_id`` is three-valued at the MCP boundary: pass ``"none"``
    to restrict to top-level tasks, ``"any"`` (or omit) to leave the
    filter unconstrained, or a UUIDv7 to restrict to children of that
    task.

    :param core: The MCP context.
    :param project_id: Restrict to tasks in this project.
    :param project_name: Resolve a project by name when no id is given.
    :param label_id: Restrict to tasks carrying this label.
    :param label_name: Resolve a label by name when no id is given.
    :param priority: Restrict to a priority code.
    :param completed: Restrict to completed or incomplete tasks.
    :param due_before: ISO-8601 date cutoff (inclusive).
    :param due_after: ISO-8601 date cutoff (inclusive).
    :param parent_id: ``"none"``, ``"any"``, or a task UUIDv7.
    :param include_descendants: When restricting to a parent, also
        include every transitive descendant.
    :param order_by: One of ``"position"``, ``"due_date"``,
        ``"priority"``, ``"created_at"``.
    :param limit: Optional maximum result count.
    :returns: ``{"items": [TaskRead, ...]}``.
    """
    with open_session(core) as session:
        project = _resolve_project(
            session, project_id=project_id, project_name=project_name
        )
        label: Label | None
        if label_id is not None or label_name is not None:
            label = _resolve_label(session, label_id=label_id, label_name=label_name)
        else:
            label = None

        parent_filter: str | None | Any
        if parent_id is None or parent_id == "any":
            parent_filter = UNSET
        elif parent_id == "none":
            parent_filter = None
        else:
            parent_filter = parent_id

        tasks = query_service.list_tasks(
            session,
            project_id=project.id if project is not None else None,
            label_id=label.id if label is not None else None,
            parent_id=parent_filter,
            priority=_coerce_priority(priority),
            completed=completed,
            due_before=_parse_date(due_before),
            due_after=_parse_date(due_after),
            include_descendants=include_descendants,
            order_by=order_by,
            limit=limit,
        )
        return {"items": [_task_to_dict(task) for task in tasks]}


def tool_get_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
) -> dict[str, Any]:
    """
    Look up a single task and return its details plus subtasks and
    comments.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :returns: ``{"task": TaskRead, "subtasks": [...], "comments": [...]}``.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        subtasks = query_service.list_subtasks(session, task.id, recursive=False)
        comments = query_service.list_comments(session, task.id)
        return {
            "task": _task_to_dict(task),
            "subtasks": [_task_to_dict(sub) for sub in subtasks],
            "comments": [_comment_to_dict(c) for c in comments],
        }


def tool_search_tasks(
    core: CoreContext,
    *,
    query: str,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Substring-search task titles, case-insensitively.

    :param core: The MCP context.
    :param query: Substring to look for in task titles.
    :param limit: Maximum result count; defaults to 50.
    :returns: ``{"items": [TaskRead, ...]}``.
    """
    with open_session(core) as session:
        results = query_service.search_tasks(session, query, limit=limit)
        return {"items": [_task_to_dict(task) for task in results]}


def tool_add_comment(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
    body: str,
) -> dict[str, Any]:
    """
    Attach a free-form comment to a task.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :param body: The comment text. Whitespace is stripped; empty bodies
        are rejected.
    :returns: The :class:`CommentRead` payload for the new comment.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        comment = comment_service.add_comment(session, task_id=task.id, body=body)
        return _comment_to_dict(comment)


def tool_edit_comment(
    core: CoreContext,
    *,
    comment_id: str,
    body: str,
) -> dict[str, Any]:
    """
    Replace an existing comment's body.

    :param core: The MCP context.
    :param comment_id: UUIDv7 of the comment to edit.
    :param body: The replacement text. Whitespace is stripped; empty
        bodies are rejected.
    :returns: The updated :class:`CommentRead` payload.
    """
    with open_session(core) as session:
        comment = comment_service.edit_comment(session, comment_id, body=body)
        return _comment_to_dict(comment)


def tool_delete_comment(
    core: CoreContext,
    *,
    comment_id: str,
) -> dict[str, Any]:
    """
    Hard-delete a comment.

    Comment deletion is the one destructive operation the MCP surface
    is permitted; task/project/label deletion remains CLI/TUI-only.

    :param core: The MCP context.
    :param comment_id: UUIDv7 of the comment to remove.
    :returns: ``{"deleted": True, "comment_id": comment_id}``.
    """
    with open_session(core) as session:
        comment_service.delete_comment(session, comment_id)
        return {"deleted": True, "comment_id": comment_id}


def tool_add_label_to_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
    label_id: str | None = None,
    label_name: str | None = None,
) -> dict[str, Any]:
    """
    Attach a label to a task.

    The label must already exist; resolving by ``label_name`` does not
    auto-create it. Idempotent: re-attaching an existing label is a
    silent no-op.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :param label_id: Optional label UUIDv7.
    :param label_name: Optional label name to resolve.
    :returns: The mutated :class:`TaskRead` payload.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        label = _resolve_label(session, label_id=label_id, label_name=label_name)
        updated = task_service.add_label(session, task.id, label.id)
        return _task_to_dict(updated)


def tool_remove_label_from_task(
    core: CoreContext,
    *,
    task_id: str | None = None,
    number: int | None = None,
    label_id: str | None = None,
    label_name: str | None = None,
) -> dict[str, Any]:
    """
    Detach a label from a task.

    Idempotent: removing a label that is not attached is a silent
    no-op.

    :param core: The MCP context.
    :param task_id: Optional UUIDv7 of the task.
    :param number: Optional user-facing task number.
    :param label_id: Optional label UUIDv7.
    :param label_name: Optional label name to resolve.
    :returns: The mutated :class:`TaskRead` payload.
    """
    with open_session(core) as session:
        task = _resolve_task(session, task_id=task_id, number=number)
        label = _resolve_label(session, label_id=label_id, label_name=label_name)
        updated = task_service.remove_label(session, task.id, label.id)
        return _task_to_dict(updated)


def tool_create_project(
    core: CoreContext,
    *,
    name: str,
    position: int | None = None,
) -> dict[str, Any]:
    """
    Create a new project.

    :param core: The MCP context.
    :param name: Human-readable project name.
    :param position: Optional explicit sort position; auto-allocated
        when omitted.
    :returns: The :class:`ProjectRead` payload for the new project.
    """
    with open_session(core) as session:
        project = project_service.create_project(session, name=name, position=position)
        return _project_to_dict(project)


def tool_create_label(
    core: CoreContext,
    *,
    name: str,
) -> dict[str, Any]:
    """
    Create a new label.

    :param core: The MCP context.
    :param name: Human-readable label name. Must be unique.
    :returns: The :class:`LabelRead` payload for the new label.
    """
    with open_session(core) as session:
        label = label_service.create_label(session, name=name)
        return _label_to_dict(label)


def tool_list_projects(core: CoreContext) -> dict[str, Any]:
    """
    Return every project, including the Inbox.

    :param core: The MCP context.
    :returns: ``{"items": [ProjectRead, ...]}``.
    """
    with open_session(core) as session:
        projects = project_service.list_projects(session)
        return {"items": [_project_to_dict(p) for p in projects]}


def tool_list_labels(core: CoreContext) -> dict[str, Any]:
    """
    Return every label.

    :param core: The MCP context.
    :returns: ``{"items": [LabelRead, ...]}``.
    """
    with open_session(core) as session:
        labels = label_service.list_labels(session)
        return {"items": [_label_to_dict(label) for label in labels]}


def tool_read_activity_log(
    core: CoreContext,
    *,
    task_id: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """
    Return activity log rows newest-first.

    :param core: The MCP context.
    :param task_id: Optional task UUIDv7 to filter on.
    :param event_type: Optional event-type string (see
        :class:`ActivityEventType`).
    :param since: Optional ISO-8601 timestamp; only rows at or after
        this moment are returned.
    :param limit: Maximum result count; defaults to 200.
    :returns: ``{"items": [ActivityRead, ...]}``.
    """
    with open_session(core) as session:
        rows = query_service.list_activity(
            session,
            task_id=task_id,
            event_type=ActivityEventType(event_type) if event_type else None,
            since=_parse_datetime(since),
            limit=limit,
        )
        return {"items": [_activity_to_dict(row) for row in rows]}


# --- Dispatch tables ---------------------------------------------------


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "add_task": tool_add_task,
    "update_task": tool_update_task,
    "complete_task": tool_complete_task,
    "uncomplete_task": tool_uncomplete_task,
    "list_tasks": tool_list_tasks,
    "get_task": tool_get_task,
    "search_tasks": tool_search_tasks,
    "add_comment": tool_add_comment,
    "edit_comment": tool_edit_comment,
    "delete_comment": tool_delete_comment,
    "add_label_to_task": tool_add_label_to_task,
    "remove_label_from_task": tool_remove_label_from_task,
    "create_project": tool_create_project,
    "create_label": tool_create_label,
    "list_projects": tool_list_projects,
    "list_labels": tool_list_labels,
    "read_activity_log": tool_read_activity_log,
}


_PRIORITY_VALUES = [p.value for p in Priority]
_ANCHOR_VALUES = [a.value for a in RecurrenceAnchor]
_EVENT_VALUES = [e.value for e in ActivityEventType]
_ORDER_BY_VALUES = ["position", "due_date", "priority", "created_at"]


JSON_SCHEMAS: dict[str, dict[str, Any]] = {
    "add_task": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "project_id": {"type": "string"},
            "project_name": {"type": "string"},
            "parent_id": {"type": "string"},
            "parent_number": {"type": "integer"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": _PRIORITY_VALUES},
            "due_date": {"type": "string", "format": "date"},
            "due_time": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "recurrence": {"type": "string"},
            "recurrence_anchor": {"type": "string", "enum": _ANCHOR_VALUES},
        },
        "required": ["title"],
        "additionalProperties": False,
    },
    "update_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
            "title": {"type": "string", "minLength": 1},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": _PRIORITY_VALUES},
            "due_date": {"type": "string", "format": "date"},
            "due_time": {"type": "string"},
            "recurrence": {"type": "string"},
            "recurrence_anchor": {"type": "string", "enum": _ANCHOR_VALUES},
        },
        "additionalProperties": False,
    },
    "complete_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
            "when": {"type": "string", "format": "date-time"},
        },
        "additionalProperties": False,
    },
    "uncomplete_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "list_tasks": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "project_name": {"type": "string"},
            "label_id": {"type": "string"},
            "label_name": {"type": "string"},
            "priority": {"type": "string", "enum": _PRIORITY_VALUES},
            "completed": {"type": "boolean"},
            "due_before": {"type": "string", "format": "date"},
            "due_after": {"type": "string", "format": "date"},
            "parent_id": {"type": "string"},
            "include_descendants": {"type": "boolean"},
            "order_by": {"type": "string", "enum": _ORDER_BY_VALUES},
            "limit": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
    "get_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "search_tasks": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "add_comment": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
            "body": {"type": "string", "minLength": 1},
        },
        "required": ["body"],
        "additionalProperties": False,
    },
    "edit_comment": {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string"},
            "body": {"type": "string", "minLength": 1},
        },
        "required": ["comment_id", "body"],
        "additionalProperties": False,
    },
    "delete_comment": {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string"},
        },
        "required": ["comment_id"],
        "additionalProperties": False,
    },
    "add_label_to_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
            "label_id": {"type": "string"},
            "label_name": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "remove_label_from_task": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "number": {"type": "integer"},
            "label_id": {"type": "string"},
            "label_name": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "create_project": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "position": {"type": "integer"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "create_label": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "list_projects": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "list_labels": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "read_activity_log": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "event_type": {"type": "string", "enum": _EVENT_VALUES},
            "since": {"type": "string", "format": "date-time"},
            "limit": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    },
}
