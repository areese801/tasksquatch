"""
Task resource router.

This router is the largest of the bunch because a task carries
scheduling, recurrence, position, parent linkage, and a many-to-many
labels relationship. Each endpoint translates the request to a call
into :mod:`tasksquatch.core.services.tasks` (or
:mod:`tasksquatch.core.services.queries` for reads), then serializes
the result through :class:`tasksquatch.core.schemas.TaskRead`.

The PATCH endpoint honors :pyattr:`pydantic.BaseModel.model_fields_set`
semantics: fields the client did not send are not touched. Label
reconciliation is performed after the scalar update by diffing the
incoming list against ``task.labels`` and dispatching to
:func:`tasksquatch.core.services.tasks.add_label` /
:func:`tasksquatch.core.services.tasks.remove_label`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from tasksquatch.core import UNSET
from tasksquatch.core._sentinels import _UnsetType
from tasksquatch.core.errors import ValidationError
from tasksquatch.core.models import Priority
from tasksquatch.core.schemas import TaskCreate, TaskRead, TaskUpdate
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.rest.dependencies import get_session

router = APIRouter(prefix="/tasks", tags=["tasks"])


class _TaskList(BaseModel):
    """
    Response envelope for :func:`list_tasks` and related listings.
    """

    items: list[TaskRead]


class RescheduleOverdueRequest(BaseModel):
    """
    Body for :func:`reschedule_overdue_endpoint`.

    ``include_recurring`` opts recurring tasks into the bump (the
    advance-in-place flow normally covers them). ``dry_run`` rolls the
    transaction back after building the response, so callers can
    preview without committing.
    """

    include_recurring: bool = False
    dry_run: bool = False


class _CompleteBody(BaseModel):
    """
    Optional body for :func:`complete_task` carrying the completion
    timestamp. Clients that want the server default may post an empty
    object or omit the body entirely.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    when: datetime | None = None


class _MoveBody(BaseModel):
    """
    Body for :func:`move_task` carrying the destination project id.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(..., min_length=1)


class _ParentBody(BaseModel):
    """
    Body for :func:`set_parent` — ``None`` detaches the task from its
    current parent and promotes it to the project top level.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    parent_id: str | None = None


def _resolve_parent_filter(parent_id: str | None) -> str | None | _UnsetType:
    """
    Translate the ``parent_id`` query parameter to the
    :func:`list_tasks` argument.

    ``None`` (the user omitted the query param) and the string
    ``"any"`` mean "do not filter on parent" — both resolve to
    :data:`UNSET`. The string ``"none"`` filters to top-level tasks
    only. Any other value is treated as a real parent id.

    :param parent_id: The raw query value or ``None`` if omitted.
    :returns: The value to pass as ``parent_id=`` to
        :func:`tasksquatch.core.services.queries.list_tasks`.
    """
    if parent_id is None:
        return UNSET
    lowered = parent_id.lower()
    if lowered == "any":
        return UNSET
    if lowered == "none":
        return None
    return parent_id


def _to_priority(value: str | None) -> Priority | None:
    """
    Translate a string priority into a :class:`Priority`.

    :param value: A case-insensitive priority key (``"p1"`` … ``"p4"``)
        or ``None``.
    :returns: The matching :class:`Priority`, or ``None`` when ``value``
        is ``None``.
    :raises ValidationError: If ``value`` is not a recognized priority.
    """
    if value is None:
        return None
    key = value.strip().upper()
    try:
        return Priority(key)
    except ValueError as exc:
        raise ValidationError(
            f"unknown priority {value!r}; expected one of "
            f"{[p.value for p in Priority]}",
            detail={"priority": value},
        ) from exc


def _apply_label_reconciliation(
    session: Session,
    task_id: str,
    desired: list[str],
) -> None:
    """
    Reconcile a task's labels to exactly the ids in ``desired``.

    Reads the current set, computes adds and removes, and dispatches
    to :func:`add_label` and :func:`remove_label` for each diff entry.
    Idempotent in the underlying service: re-attaching an attached
    label and detaching a missing label are silent no-ops.

    :param session: The active per-request session.
    :param task_id: The task whose labels are being reconciled.
    :param desired: The exact set of label ids the client wants
        attached after the update.
    """
    task = queries_service.get_task_by_id(session, task_id)
    current_ids = {label.id for label in task.labels}
    target_ids = set(desired)
    for to_add in target_ids - current_ids:
        tasks_service.add_label(session, task_id, to_add)
    for to_remove in current_ids - target_ids:
        tasks_service.remove_label(session, task_id, to_remove)


def _apply_task_patch(
    session: Session,
    task_id: str,
    payload: TaskUpdate,
) -> None:
    """
    Translate a :class:`TaskUpdate` into the appropriate service calls.

    Honors PATCH semantics via ``payload.model_fields_set``: only the
    fields the client actually sent are passed to
    :func:`tasksquatch.core.services.tasks.update_task` (everything
    else stays :data:`UNSET`). ``position``, ``project_id``, and
    ``parent_id`` are handled by their dedicated service functions
    (``reorder_task``, ``move_task``, ``set_parent``) because
    :func:`update_task` does not accept them. ``label_ids`` is
    reconciled last via :func:`_apply_label_reconciliation`.

    :param session: The active per-request session.
    :param task_id: The task being patched.
    :param payload: The validated request body.
    :raises ValidationError: If the client sent ``title: null``
        explicitly. Title is not nullable in the data model.
    """
    fields = payload.model_fields_set

    if "title" in fields and payload.title is None:
        raise ValidationError(
            "Task title must not be null.",
            detail={"field": "title"},
        )

    title_arg: str | _UnsetType = (
        payload.title if "title" in fields and payload.title is not None else UNSET
    )
    description_arg: str | None | _UnsetType = (
        payload.description if "description" in fields else UNSET
    )
    priority_arg: Priority | _UnsetType = (
        payload.priority
        if "priority" in fields and payload.priority is not None
        else UNSET
    )
    due_date_arg: date | None | _UnsetType = (
        payload.due_date if "due_date" in fields else UNSET
    )
    due_time_arg: Any = payload.due_time if "due_time" in fields else UNSET
    recurrence_arg: str | None | _UnsetType = (
        payload.recurrence if "recurrence" in fields else UNSET
    )
    anchor_arg: Any = (
        payload.recurrence_anchor
        if "recurrence_anchor" in fields and payload.recurrence_anchor is not None
        else UNSET
    )

    scalar_touched = any(
        f in fields
        for f in (
            "title",
            "description",
            "priority",
            "due_date",
            "due_time",
            "recurrence",
            "recurrence_anchor",
        )
    )
    if scalar_touched:
        tasks_service.update_task(
            session,
            task_id,
            title=title_arg,
            description=description_arg,
            priority=priority_arg,
            due_date=due_date_arg,
            due_time=due_time_arg,
            recurrence=recurrence_arg,
            recurrence_anchor=anchor_arg,
        )

    if "project_id" in fields:
        if payload.project_id is None:
            raise ValidationError(
                "Task project_id must not be null.",
                detail={"field": "project_id"},
            )
        tasks_service.move_task(
            session,
            task_id,
            new_project_id=payload.project_id,
        )

    if "parent_id" in fields:
        tasks_service.set_parent(
            session,
            task_id,
            new_parent_id=payload.parent_id,
        )

    if "position" in fields:
        if payload.position is None:
            raise ValidationError(
                "Task position must not be null.",
                detail={"field": "position"},
            )
        tasks_service.reorder_task(
            session,
            task_id,
            new_position=payload.position,
        )

    if "label_ids" in fields and payload.label_ids is not None:
        _apply_label_reconciliation(session, task_id, payload.label_ids)


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    description=(
        "Create a new task. ``project_id`` defaults to the Inbox when "
        "omitted. The response carries the persisted row including the "
        "allocated user-facing ``number`` and any attached label ids."
    ),
)
def create_task_endpoint(
    payload: TaskCreate,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Insert a new task and return its read view.

    Sets the ``Location`` response header to the new task's canonical
    URL so REST clients can follow it without parsing the body.
    """
    task = tasks_service.create_task(
        session,
        title=payload.title,
        project_id=payload.project_id,
        parent_id=payload.parent_id,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
        due_time=payload.due_time,
        recurrence=payload.recurrence,
        recurrence_anchor=payload.recurrence_anchor,
        label_ids=payload.label_ids,
    )
    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    return TaskRead.from_task(task)


@router.get(
    "",
    response_model=_TaskList,
    summary="List tasks",
    description=(
        "Return tasks matching the supplied filters. ``parent_id`` is "
        'three-valued: ``"any"`` (default when omitted) leaves the '
        'filter unconstrained, ``"none"`` restricts to top-level '
        "tasks only, and any other value is treated as a parent id. "
        "``include_descendants`` extends a project- or parent-scoped "
        "query with every transitive subtask."
    ),
)
def list_tasks_endpoint(
    session: Annotated[Session, Depends(get_session)],
    project_id: Annotated[str | None, Query()] = None,
    label_id: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    completed: Annotated[bool | None, Query()] = None,
    due_before: Annotated[date | None, Query()] = None,
    due_after: Annotated[date | None, Query()] = None,
    parent_id: Annotated[str | None, Query()] = None,
    include_descendants: Annotated[bool, Query()] = False,
    order_by: Annotated[str, Query()] = "position",
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> _TaskList:
    """
    Return a list of tasks matching the supplied filters.
    """
    rows = queries_service.list_tasks(
        session,
        project_id=project_id,
        label_id=label_id,
        parent_id=_resolve_parent_filter(parent_id),
        priority=_to_priority(priority),
        completed=completed,
        due_before=due_before,
        due_after=due_after,
        include_descendants=include_descendants,
        order_by=order_by,
        limit=limit,
    )
    return _TaskList(items=[TaskRead.from_task(task) for task in rows])


@router.post(
    "/reschedule-overdue",
    response_model=_TaskList,
    summary="Bump every overdue, incomplete task to today.",
    description=(
        "Bump every overdue, incomplete task's ``due_date`` to today. "
        "Recurring tasks are skipped by default; set "
        "``include_recurring`` to bump them too. Set ``dry_run`` to "
        "preview without committing — the response body still lists "
        "the rows that would be bumped."
    ),
)
def reschedule_overdue_endpoint(
    body: RescheduleOverdueRequest,
    session: Annotated[Session, Depends(get_session)],
) -> _TaskList:
    """
    Bump every overdue, incomplete task and return the bumped rows.

    The ``TaskRead`` payload is built before any optional rollback so
    label relationships are serialized while the rows are still bound
    to the session.
    """
    bumped = tasks_service.reschedule_overdue(
        session,
        include_recurring=body.include_recurring,
    )
    rendered = _TaskList(items=[TaskRead.from_task(task) for task in bumped])
    if body.dry_run:
        session.rollback()
    return rendered


@router.get(
    "/by-number/{number}",
    response_model=TaskRead,
    summary="Get a task by its user-facing number",
    description=(
        "Look up a task by its globally sequential ``number``. Numbers "
        "are never reused, so a missing number is permanent."
    ),
)
def get_task_by_number_endpoint(
    number: Annotated[int, Path(ge=1)],
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Return the task whose user-facing ``number`` matches.
    """
    task = queries_service.get_task_by_number(session, number)
    return TaskRead.from_task(task)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task by id",
    description="Return the task with this UUIDv7 id.",
)
def get_task_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Return the task with this UUIDv7 primary key.
    """
    task = queries_service.get_task_by_id(session, task_id)
    return TaskRead.from_task(task)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    description=(
        "Apply a partial update. Only fields the client actually sends "
        "are modified — Pydantic's ``model_fields_set`` is the source "
        "of truth. ``label_ids`` is three-valued: omitted means leave "
        "labels alone, an empty list removes all labels, a populated "
        "list replaces the label set with exactly those ids."
    ),
)
def patch_task_endpoint(
    task_id: str,
    payload: TaskUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Apply a partial update and return the resulting read view.
    """
    queries_service.get_task_by_id(session, task_id)
    _apply_task_patch(session, task_id, payload)
    task = queries_service.get_task_by_id(session, task_id)
    return TaskRead.from_task(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description=(
        "Hard-delete a task along with its subtasks and comments. The "
        "task's ``number`` is retired permanently and is never reused."
    ),
)
def delete_task_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """
    Hard-delete a task; cascade to subtasks and comments.
    """
    tasks_service.delete_task(session, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{task_id}/complete",
    response_model=TaskRead,
    summary="Mark a task complete",
    description=(
        "Complete a task. Non-recurring tasks transition to "
        "``completed = True``; recurring tasks advance in place to the "
        "next occurrence and stay incomplete. The body may include "
        "``when`` to override the server clock; send ``{}`` for "
        "default behavior."
    ),
)
def complete_task_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
    payload: Annotated[_CompleteBody | None, Body()] = None,
) -> TaskRead:
    """
    Complete (or advance) a task and return the resulting read view.
    """
    when = payload.when if payload is not None else None
    task = tasks_service.complete_task(session, task_id, when=when)
    return TaskRead.from_task(task)


@router.post(
    "/{task_id}/uncomplete",
    response_model=TaskRead,
    summary="Reopen a completed task",
    description="Reverse a task's completion state.",
)
def uncomplete_task_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Reverse a task's completion state and return the read view.
    """
    task = tasks_service.uncomplete_task(session, task_id)
    return TaskRead.from_task(task)


@router.post(
    "/{task_id}/move",
    response_model=TaskRead,
    summary="Move a task to a different project",
    description=(
        "Move a top-level task to another project. Subtasks travel "
        "with their parent. Subtasks themselves cannot be moved "
        "directly — detach them first via ``POST /tasks/{id}/parent``."
    ),
)
def move_task_endpoint(
    task_id: str,
    payload: _MoveBody,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Move a task to a different project and return the read view.
    """
    task = tasks_service.move_task(
        session,
        task_id,
        new_project_id=payload.project_id,
    )
    return TaskRead.from_task(task)


@router.post(
    "/{task_id}/parent",
    response_model=TaskRead,
    summary="Reparent a task or detach it to the top level",
    description=(
        "Set or clear a task's parent. Passing ``parent_id: null`` "
        "promotes the task to the project's top level. The new parent "
        "must share the task's project and must not produce a cycle."
    ),
)
def set_parent_endpoint(
    task_id: str,
    payload: _ParentBody,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Reparent a task and return the read view.
    """
    task = tasks_service.set_parent(
        session,
        task_id,
        new_parent_id=payload.parent_id,
    )
    return TaskRead.from_task(task)


@router.get(
    "/{task_id}/subtasks",
    response_model=_TaskList,
    summary="List subtasks of a task",
    description=(
        "Return the direct children of the task by default. Set "
        "``recursive=true`` to walk every transitive descendant."
    ),
)
def list_subtasks_endpoint(
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
    recursive: Annotated[bool, Query()] = True,
) -> _TaskList:
    """
    Return the subtasks of a task.
    """
    queries_service.get_task_by_id(session, task_id)
    rows = queries_service.list_subtasks(session, task_id, recursive=recursive)
    return _TaskList(items=[TaskRead.from_task(task) for task in rows])


@router.post(
    "/{task_id}/labels/{label_id}",
    response_model=TaskRead,
    summary="Attach a label to a task",
    description=(
        "Attach a label to a task. Idempotent — re-attaching an "
        "already-attached label is a silent no-op."
    ),
)
def add_label_endpoint(
    task_id: str,
    label_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> TaskRead:
    """
    Attach a label to a task and return the read view.
    """
    task = tasks_service.add_label(session, task_id, label_id)
    return TaskRead.from_task(task)


@router.delete(
    "/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a label from a task",
    description=(
        "Detach a label from a task. Idempotent — removing a label "
        "that is not attached is a silent no-op and still returns 204."
    ),
)
def remove_label_endpoint(
    task_id: str,
    label_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """
    Detach a label from a task.
    """
    tasks_service.remove_label(session, task_id, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
