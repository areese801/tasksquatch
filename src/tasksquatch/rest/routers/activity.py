"""
Activity log router.

The activity log is read-only at the surface boundary; no endpoint
here mutates state. Filtering follows the
:func:`tasksquatch.core.services.queries.list_activity` API one-to-one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tasksquatch.core.errors import ValidationError
from tasksquatch.core.models import ActivityEventType
from tasksquatch.core.schemas import ActivityRead
from tasksquatch.core.services import queries as queries_service
from tasksquatch.rest.dependencies import get_session

router = APIRouter(prefix="/activity", tags=["activity"])


class _ActivityList(BaseModel):
    """
    Response envelope for the activity endpoint.
    """

    items: list[ActivityRead]


def _parse_event_type(value: str | None) -> ActivityEventType | None:
    """
    Translate a string event type into an :class:`ActivityEventType`.

    :param value: A case-sensitive event-type key (e.g. ``"created"``)
        or ``None``.
    :returns: The matching :class:`ActivityEventType`, or ``None`` when
        ``value`` is ``None``.
    :raises ValidationError: If ``value`` is not a recognized type.
    """
    if value is None:
        return None
    try:
        return ActivityEventType(value)
    except ValueError as exc:
        raise ValidationError(
            f"unknown event_type {value!r}; expected one of "
            f"{[e.value for e in ActivityEventType]}",
            detail={"event_type": value},
        ) from exc


@router.get(
    "",
    response_model=_ActivityList,
    summary="List activity log rows",
    description=(
        "Return activity log rows matching the filters, newest first. "
        "Filters chain as AND."
    ),
)
def list_activity_endpoint(
    session: Annotated[Session, Depends(get_session)],
    task_id: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1)] = 200,
) -> _ActivityList:
    """
    Return matching activity log rows as a list envelope.
    """
    rows = queries_service.list_activity(
        session,
        task_id=task_id,
        event_type=_parse_event_type(event_type),
        since=since,
        limit=limit,
    )
    return _ActivityList(items=[ActivityRead.model_validate(row) for row in rows])
