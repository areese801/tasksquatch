"""
Label CRUD service.

Labels are cross-project tags. The DB enforces uniqueness on
``labels.name``; the service catches the resulting
:class:`sqlalchemy.exc.IntegrityError` and re-raises a friendlier
:class:`ValidationError`. The many-to-many association in ``task_labels``
is removed automatically when a label is deleted via the FK's
``ON DELETE CASCADE``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import ActivityEventType, Label
from tasksquatch.core.services.activity import emit


def _strip_and_validate_name(name: str) -> str:
    """
    Strip whitespace from ``name`` and reject the empty result.

    :param name: The user-supplied label name to clean.
    :returns: The stripped name.
    :raises ValidationError: When ``name`` is empty after stripping.
    """
    stripped = name.strip()
    if not stripped:
        raise ValidationError("Label name must not be empty.")
    return stripped


def _get_label_or_raise(session: Session, label_id: str) -> Label:
    """
    Fetch a label by id or raise :class:`NotFoundError`.

    :param session: An open SQLAlchemy session.
    :param label_id: The label's UUIDv7 string id.
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


def create_label(session: Session, *, name: str) -> Label:
    """
    Insert a new label and emit a ``LABEL_CREATED`` activity row.

    :param session: An open SQLAlchemy session.
    :param name: Human-readable label name. Whitespace is stripped.
    :returns: The freshly-flushed :class:`Label`.
    :raises ValidationError: If ``name`` is empty after stripping or
        if a label with the same name already exists.
    """
    clean_name = _strip_and_validate_name(name)

    label = Label(name=clean_name)
    session.add(label)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValidationError(
            f"A label named {clean_name!r} already exists.",
            detail={"name": clean_name},
        ) from exc

    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.LABEL_CREATED,
        detail={"label_id": label.id, "name": label.name},
    )
    return label


def list_labels(session: Session) -> list[Label]:
    """
    Return every label ordered by name.

    :param session: An open SQLAlchemy session.
    :returns: A list of :class:`Label` rows in alphabetical order.
    """
    stmt = select(Label).order_by(Label.name.asc())
    return list(session.execute(stmt).scalars().all())


def rename_label(
    session: Session,
    label_id: str,
    new_name: str,
) -> Label:
    """
    Rename a label and emit a ``LABEL_RENAMED`` activity row.

    :param session: An open SQLAlchemy session.
    :param label_id: The label's UUIDv7 string id.
    :param new_name: The replacement name. Whitespace is stripped.
    :returns: The mutated :class:`Label`.
    :raises NotFoundError: If no label exists with that id.
    :raises ValidationError: If ``new_name`` is empty after stripping
        or if it collides with an existing label.
    """
    label = _get_label_or_raise(session, label_id)
    clean_name = _strip_and_validate_name(new_name)
    old_name = label.name
    label.name = clean_name
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ValidationError(
            f"A label named {clean_name!r} already exists.",
            detail={"label_id": label_id, "name": clean_name},
        ) from exc

    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.LABEL_RENAMED,
        detail={
            "label_id": label.id,
            "old_name": old_name,
            "new_name": clean_name,
        },
    )
    return label


def delete_label(session: Session, label_id: str) -> None:
    """
    Delete a label and emit a ``LABEL_DELETED`` activity row.

    The ``task_labels`` association rows are removed by the database
    via ``ON DELETE CASCADE`` on the foreign key; the service does not
    need to remove them explicitly.

    :param session: An open SQLAlchemy session.
    :param label_id: The label's UUIDv7 string id.
    :raises NotFoundError: If no label exists with that id.
    """
    label = _get_label_or_raise(session, label_id)
    emit(
        session,
        task_id=None,
        event_type=ActivityEventType.LABEL_DELETED,
        detail={"label_id": label.id, "name": label.name},
    )
    session.delete(label)
    session.flush()
