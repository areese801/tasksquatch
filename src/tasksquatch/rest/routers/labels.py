"""
Label resource router.

Labels are cross-project tags. The underlying ``labels`` table enforces
a uniqueness constraint on ``name``; the service catches the database
error and re-raises a friendly :class:`ValidationError`, which the
registered exception handler returns as HTTP 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError
from tasksquatch.core.models import Label
from tasksquatch.core.schemas import LabelCreate, LabelRead, LabelUpdate
from tasksquatch.core.services import labels as labels_service
from tasksquatch.rest.dependencies import get_session

router = APIRouter(prefix="/labels", tags=["labels"])


class _LabelList(BaseModel):
    """
    Response envelope for the list endpoint.
    """

    items: list[LabelRead]


def _get_label_or_raise(session: Session, label_id: str) -> Label:
    """
    Fetch a label by id or raise :class:`NotFoundError`.

    Mirrors the same helper inside
    :mod:`tasksquatch.core.services.labels`; duplicated here so the
    router does not import an underscore-private symbol.

    :param session: An open SQLAlchemy session.
    :param label_id: The label's UUIDv7 primary key.
    :returns: The :class:`Label` row.
    :raises NotFoundError: If no label exists with that id.
    """
    label = session.get(Label, label_id)
    if label is None:
        raise NotFoundError(
            f"Label {label_id!r} not found.",
            detail={"label_id": label_id},
        )
    return label


@router.get(
    "",
    response_model=_LabelList,
    summary="List labels",
    description="Return every label ordered alphabetically by name.",
)
def list_labels_endpoint(
    session: Annotated[Session, Depends(get_session)],
) -> _LabelList:
    """
    Return every label as a list envelope.
    """
    rows = labels_service.list_labels(session)
    return _LabelList(items=[LabelRead.model_validate(row) for row in rows])


@router.post(
    "",
    response_model=LabelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a label",
    description=(
        "Insert a new label. Duplicate names return HTTP 422 ``validation_error``."
    ),
)
def create_label_endpoint(
    payload: LabelCreate,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> LabelRead:
    """
    Insert a new label and return its read view.
    """
    label = labels_service.create_label(session, name=payload.name)
    response.headers["Location"] = f"/api/v1/labels/{label.id}"
    return LabelRead.model_validate(label)


@router.get(
    "/{label_id}",
    response_model=LabelRead,
    summary="Get a label by id",
    description="Return the label with this UUIDv7 id.",
)
def get_label_endpoint(
    label_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> LabelRead:
    """
    Return the label with this UUIDv7 primary key.
    """
    label = _get_label_or_raise(session, label_id)
    return LabelRead.model_validate(label)


@router.patch(
    "/{label_id}",
    response_model=LabelRead,
    summary="Rename a label",
    description=(
        "Rename a label. Sending an empty ``name`` returns 422; "
        "colliding with an existing label name returns 422."
    ),
)
def patch_label_endpoint(
    label_id: str,
    payload: LabelUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> LabelRead:
    """
    Rename a label or no-op if no rename was requested.
    """
    label = _get_label_or_raise(session, label_id)
    if "name" in payload.model_fields_set and payload.name is not None:
        label = labels_service.rename_label(session, label_id, payload.name)
    return LabelRead.model_validate(label)


@router.delete(
    "/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a label",
    description=(
        "Hard-delete a label. Any ``task_labels`` association rows are "
        "removed by the database via ON DELETE CASCADE."
    ),
)
def delete_label_endpoint(
    label_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """
    Hard-delete a label.
    """
    labels_service.delete_label(session, label_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
