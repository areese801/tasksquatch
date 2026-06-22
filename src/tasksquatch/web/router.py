"""
Server-rendered HTMX dashboard for the tasksquatch Web UI surface.

The router mounts under ``/ui`` and renders Jinja2 templates against
``tasksquatch.core``. Each endpoint is a thin adapter that parses form
or path data, calls one of the service functions, and returns either
the full ``index.html`` page or one of the ``_*.html`` partials so
HTMX can swap a single region of the DOM.

There is no JavaScript framework here. The browser ships ``htmx.min.js``
(vendored under :mod:`tasksquatch.web.static`) and a single hand-written
stylesheet; everything else is server-rendered HTML.

Errors raised by ``core.services`` propagate up to the FastAPI app's
registered exception handlers, which produce JSON bodies. HTMX users
will see a brief flash of the JSON envelope on failure rather than a
styled toast — acceptable for v1 because the Web UI is a local
single-user surface and the failure modes (validation errors, missing
ids) are infrequent.
"""

from __future__ import annotations

import html
import pathlib
import re
from collections.abc import Iterable
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from tasksquatch.core import UNSET
from tasksquatch.core._sentinels import _UnsetType
from tasksquatch.core.errors import ValidationError
from tasksquatch.core.models import Priority, Project, RecurrenceAnchor
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import labels as labels_service
from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.rest.dependencies import get_session

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"


def _render_markdown(value: str | None) -> str:
    """
    Render a free-form Markdown-ish string as HTML.

    Production callers may swap in a real Markdown library, but adding
    ``markdown`` as a runtime dependency is out of scope for v1, so
    this fallback escapes the input and converts blank-line-separated
    blocks into ``<p>`` tags. Single newlines become ``<br>``.

    :param value: The user-supplied text, or ``None``.
    :returns: An HTML fragment safe to mark as ``| safe`` in a
        template. ``None`` and the empty string render as an empty
        string.
    """
    if not value:
        return ""
    escaped = html.escape(value)
    paragraphs = re.split(r"\n\s*\n", escaped.strip())
    rendered = [f"<p>{block.replace(chr(10), '<br>')}</p>" for block in paragraphs]
    return "\n".join(rendered)


templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.filters["markdown"] = _render_markdown


router = APIRouter(prefix="/ui", tags=["web"])


def _resolve_project(session: Session, project_id: str | None) -> Project:
    """
    Return the requested project, defaulting to the Inbox.

    Falling back to the Inbox when ``project_id`` does not match any
    existing row keeps the dashboard usable when a stale id sits in the
    user's browser history.

    :param session: The active per-request session.
    :param project_id: A project id, or ``None`` to fall back to Inbox.
    :returns: The matching :class:`Project`, or the Inbox.
    """
    if project_id is None:
        return ensure_inbox(session)
    for project in projects_service.list_projects(session):
        if project.id == project_id:
            return project
    return ensure_inbox(session)


def _parse_date(value: str | None) -> date | None:
    """
    Coerce a form-supplied date string to a :class:`datetime.date`.

    Empty strings and ``None`` collapse to ``None`` so the form's
    "blank means no date" semantics survive.
    """
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_time(value: str | None) -> time | None:
    """
    Coerce a form-supplied time string (``HH:MM`` or ``HH:MM:SS``).

    Empty strings and ``None`` collapse to ``None``.
    """
    if not value:
        return None
    return time.fromisoformat(value)


def _parse_priority(value: str | None) -> Priority:
    """
    Coerce a form-supplied priority key to a :class:`Priority`.

    Falls back to :pyattr:`Priority.P4` when no value is sent so the
    HTML form's default select option lines up with the service
    default.
    """
    if not value:
        return Priority.P4
    key = value.strip().upper()
    try:
        return Priority(key)
    except ValueError as exc:
        raise ValidationError(
            f"unknown priority {value!r}",
            detail={"priority": value},
        ) from exc


def _parse_anchor(value: str | None) -> RecurrenceAnchor:
    """
    Coerce a form-supplied recurrence anchor string to the enum.

    Falls back to :pyattr:`RecurrenceAnchor.FIXED` when blank.
    """
    if not value:
        return RecurrenceAnchor.FIXED
    key = value.strip().lower()
    try:
        return RecurrenceAnchor(key)
    except ValueError as exc:
        raise ValidationError(
            f"unknown recurrence anchor {value!r}",
            detail={"recurrence_anchor": value},
        ) from exc


def _parse_label_ids(value: str | None) -> list[str]:
    """
    Split a comma-separated label-id string into a list of ids.
    """
    if not value:
        return []
    return [chunk.strip() for chunk in value.split(",") if chunk.strip()]


def _resolve_label_ids(
    session: Session,
    raw: Iterable[str],
) -> list[str]:
    """
    Translate a list of label ids or names to canonical label ids.

    Existing ids pass through unchanged; values that are not ids but
    match an existing label by name resolve to that label's id. Unknown
    values are silently dropped so the form can be forgiving when the
    user clears the field.
    """
    known = {label.id: label for label in labels_service.list_labels(session)}
    by_name = {label.name: label for label in known.values()}
    resolved: list[str] = []
    for value in raw:
        if value in known:
            resolved.append(value)
        elif value in by_name:
            resolved.append(by_name[value].id)
    return resolved


def _render_index(
    request: Request,
    session: Session,
    current_project: Project,
) -> HTMLResponse:
    """
    Render the full ``index.html`` page bound to a current project.
    """
    projects = projects_service.list_projects(session)
    tasks = queries_service.list_tasks(
        session,
        project_id=current_project.id,
        parent_id=None,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "projects": projects,
            "current_project": current_project,
            "tasks": tasks,
        },
    )


def _render_task_list(
    request: Request,
    session: Session,
    current_project: Project,
) -> HTMLResponse:
    """
    Render the ``_task_list.html`` partial for a project.
    """
    projects = projects_service.list_projects(session)
    tasks = queries_service.list_tasks(
        session,
        project_id=current_project.id,
        parent_id=None,
    )
    return templates.TemplateResponse(
        request,
        "_task_list.html",
        {
            "projects": projects,
            "current_project": current_project,
            "tasks": tasks,
        },
    )


def _render_task_row(
    request: Request,
    session: Session,
    task_id: str,
) -> HTMLResponse:
    """
    Render the ``_task_row.html`` partial for a single task.
    """
    task = queries_service.get_task_by_id(session, task_id)
    return templates.TemplateResponse(
        request,
        "_task_row.html",
        {"task": task},
    )


def _render_task_detail(
    request: Request,
    session: Session,
    task_id: str,
) -> HTMLResponse:
    """
    Render the ``_task_detail.html`` partial for a single task.
    """
    task = queries_service.get_task_by_id(session, task_id)
    project = _resolve_project(session, task.project_id)
    subtasks = queries_service.list_subtasks(session, task_id, recursive=False)
    comments = queries_service.list_comments(session, task_id)
    return templates.TemplateResponse(
        request,
        "_task_detail.html",
        {
            "task": task,
            "project": project,
            "subtasks": subtasks,
            "comments": comments,
        },
    )


@router.get("/", response_class=HTMLResponse, summary="Render the dashboard")
def index(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project_id: str | None = None,
) -> HTMLResponse:
    """
    Render the full dashboard page.

    The current project defaults to the Inbox when ``project_id`` is
    omitted. The HTML carries the sidebar, the task list for the
    current project, and an empty detail panel.

    :param request: The active FastAPI request — required by
        :class:`Jinja2Templates`.
    :param session: The per-request SQLAlchemy session.
    :param project_id: Optional id of the project to land on.
    """
    current = _resolve_project(session, project_id)
    return _render_index(request, session, current)


@router.get(
    "/projects/{project_id}",
    response_class=HTMLResponse,
    summary="Render the task-list partial for a project",
)
def project_tasks(
    request: Request,
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """
    Render the ``_task_list.html`` partial scoped to a project.
    """
    current = _resolve_project(session, project_id)
    return _render_task_list(request, session, current)


@router.get(
    "/tasks/{task_id}",
    response_class=HTMLResponse,
    summary="Render the task detail panel",
)
def task_detail(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """
    Render the ``_task_detail.html`` partial for a single task.
    """
    return _render_task_detail(request, session, task_id)


@router.get(
    "/tasks/{task_id}/edit",
    response_class=HTMLResponse,
    summary="Render the prefilled edit form for a task",
)
def task_edit_form(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """
    Render the ``_task_form.html`` partial prefilled for editing.
    """
    task = queries_service.get_task_by_id(session, task_id)
    projects = projects_service.list_projects(session)
    return templates.TemplateResponse(
        request,
        "_task_form.html",
        {
            "task": task,
            "projects": projects,
            "current_project": None,
        },
    )


@router.post(
    "/tasks",
    response_class=HTMLResponse,
    summary="Create a task and re-render the current task list",
)
def create_task_endpoint(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    title: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    priority: Annotated[str | None, Form()] = None,
    due_date: Annotated[str | None, Form()] = None,
    due_time: Annotated[str | None, Form()] = None,
    labels: Annotated[str | None, Form()] = None,
    recurrence: Annotated[str | None, Form()] = None,
    recurrence_anchor: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """
    Insert a task from the create form and re-render the task list.

    The full ``_task_list.html`` partial is returned (rather than just
    the new row) so the empty-state message disappears on first create
    and the form fields reset without the client juggling
    ``hx-swap-oob`` directives.
    """
    resolved_project = _resolve_project(session, project_id)
    label_ids = _resolve_label_ids(session, _parse_label_ids(labels))
    rrule = recurrence.strip() if recurrence else None
    tasks_service.create_task(
        session,
        title=title,
        project_id=resolved_project.id,
        priority=_parse_priority(priority),
        due_date=_parse_date(due_date),
        due_time=_parse_time(due_time),
        recurrence=rrule or None,
        recurrence_anchor=_parse_anchor(recurrence_anchor),
        label_ids=label_ids,
    )
    return _render_task_list(request, session, resolved_project)


@router.post(
    "/tasks/{task_id}/toggle",
    response_class=HTMLResponse,
    summary="Toggle a task's completion state",
)
def toggle_task(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """
    Toggle completion via ``complete_task`` / ``uncomplete_task``.

    Returns the updated ``_task_row.html`` so HTMX can swap the row in
    place via ``hx-target="closest .task-row"``.
    """
    task = queries_service.get_task_by_id(session, task_id)
    if task.completed:
        tasks_service.uncomplete_task(session, task_id)
    else:
        tasks_service.complete_task(session, task_id)
    return _render_task_row(request, session, task_id)


@router.post(
    "/tasks/{task_id}/delete",
    response_class=HTMLResponse,
    summary="Delete a task",
)
def delete_task_endpoint(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """
    Delete a task and return the empty partial so HTMX wipes the row.
    """
    tasks_service.delete_task(session, task_id)
    return templates.TemplateResponse(request, "_empty.html", {})


@router.put(
    "/tasks/{task_id}",
    response_class=HTMLResponse,
    summary="Update a task from the edit form",
)
def update_task_endpoint(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
    title: Annotated[str, Form()],
    project_id: Annotated[str | None, Form()] = None,
    priority: Annotated[str | None, Form()] = None,
    due_date: Annotated[str | None, Form()] = None,
    due_time: Annotated[str | None, Form()] = None,
    labels: Annotated[str | None, Form()] = None,
    recurrence: Annotated[str | None, Form()] = None,
    recurrence_anchor: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """
    Apply edits to a task and re-render the detail panel.

    Scalar fields go through :func:`tasks_service.update_task`; a
    project change routes through :func:`tasks_service.move_task` so
    the activity log captures the move semantics. Labels are reconciled
    by diffing the resolved id list against the task's current labels.
    """
    task = queries_service.get_task_by_id(session, task_id)
    rrule_arg: str | None | _UnsetType
    if recurrence is None:
        rrule_arg = UNSET
    else:
        stripped = recurrence.strip()
        rrule_arg = stripped or None
    tasks_service.update_task(
        session,
        task_id,
        title=title,
        priority=_parse_priority(priority),
        due_date=_parse_date(due_date),
        due_time=_parse_time(due_time),
        recurrence=rrule_arg,
        recurrence_anchor=_parse_anchor(recurrence_anchor),
    )

    if project_id and project_id != task.project_id:
        tasks_service.move_task(session, task_id, new_project_id=project_id)

    desired_label_ids = set(_resolve_label_ids(session, _parse_label_ids(labels)))
    current_label_ids = {label.id for label in task.labels}
    for to_add in desired_label_ids - current_label_ids:
        tasks_service.add_label(session, task_id, to_add)
    for to_remove in current_label_ids - desired_label_ids:
        tasks_service.remove_label(session, task_id, to_remove)

    return _render_task_detail(request, session, task_id)


@router.post(
    "/tasks/{task_id}/comments",
    response_class=HTMLResponse,
    summary="Attach a comment to a task",
)
def add_comment_endpoint(
    request: Request,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
    body: Annotated[str, Form()],
) -> HTMLResponse:
    """
    Attach a comment and re-render the task detail.

    Kept in the v1 router so the detail panel can grow a comment box
    without another round trip. Not currently exercised by the bundled
    templates — present for direct HTMX use.
    """
    comments_service.add_comment(session, task_id=task_id, body=body)
    return _render_task_detail(request, session, task_id)


__all__ = ["router", "templates"]
