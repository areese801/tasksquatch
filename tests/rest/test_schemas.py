"""
Tests for the Pydantic schemas under :mod:`tasksquatch.core.schemas`.

The tests focus on the surface-boundary behaviors that matter:

- :meth:`TaskRead.from_task` round-trips an ORM row with labels.
- :class:`TaskUpdate` honors PATCH semantics via
  ``model_fields_set`` — omitted fields are absent from the set.
- :class:`TaskCreate` validates required fields and applies defaults.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tasksquatch.core import (
    create_engine_for_path,
    create_session_factory,
    create_task,
    ensure_inbox,
    init_schema,
    session_scope,
)
from tasksquatch.core.models import Label, Priority, RecurrenceAnchor
from tasksquatch.core.schemas import (
    LabelCreate,
    LabelRead,
    LabelUpdate,
    ProjectCreate,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)


def test_task_read_from_task_includes_label_ids(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "schemas.db")
    init_schema(engine)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            ensure_inbox(session)
            label_a = Label(name="alpha")
            label_b = Label(name="beta")
            session.add_all([label_a, label_b])
            session.flush()
            task = create_task(
                session,
                title="hello",
                description="world",
                priority=Priority.P2,
                due_date=date(2026, 6, 22),
                recurrence_anchor=RecurrenceAnchor.FIXED,
                label_ids=[label_a.id, label_b.id],
            )
            session.flush()

            read = TaskRead.from_task(task)
            assert read.id == task.id
            assert read.number == task.number
            assert read.title == "hello"
            assert read.description == "world"
            assert read.priority == "P2"
            assert read.recurrence_anchor == "fixed"
            assert read.due_date == date(2026, 6, 22)
            assert set(read.label_ids) == {label_a.id, label_b.id}
            assert read.completed is False
            assert read.completed_at is None
    finally:
        engine.dispose()


def test_task_update_tracks_set_fields() -> None:
    update = TaskUpdate(title="renamed")
    assert update.model_fields_set == {"title"}
    assert update.title == "renamed"
    assert update.description is None

    empty = TaskUpdate()
    assert empty.model_fields_set == set()

    multi = TaskUpdate(title="x", priority=Priority.P1, label_ids=[])
    assert multi.model_fields_set == {"title", "priority", "label_ids"}
    assert multi.label_ids == []


def test_task_create_rejects_empty_or_missing_title() -> None:
    with pytest.raises(ValueError):
        TaskCreate(title="")
    with pytest.raises(ValueError):
        TaskCreate.model_validate({})


def test_task_create_applies_defaults() -> None:
    payload = TaskCreate(title="do the thing")
    assert payload.priority is Priority.P4
    assert payload.recurrence_anchor is RecurrenceAnchor.FIXED
    assert payload.label_ids == []
    assert payload.project_id is None
    assert payload.due_date is None


def test_task_update_label_ids_distinguishes_none_from_empty() -> None:
    untouched = TaskUpdate()
    assert untouched.label_ids is None
    assert "label_ids" not in untouched.model_fields_set

    cleared = TaskUpdate(label_ids=[])
    assert cleared.label_ids == []
    assert "label_ids" in cleared.model_fields_set


def test_project_update_tracks_set_fields() -> None:
    update = ProjectUpdate(name="newname")
    assert update.model_fields_set == {"name"}
    assert ProjectUpdate().model_fields_set == set()


def test_project_create_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        ProjectCreate(name="")


def test_label_create_and_update_validate() -> None:
    assert LabelCreate(name="tag").name == "tag"
    assert LabelUpdate().model_fields_set == set()
    assert LabelUpdate(name="renamed").model_fields_set == {"name"}
    with pytest.raises(ValueError):
        LabelCreate(name="")


def test_label_read_round_trips_orm_attributes(tmp_path: Path) -> None:
    engine = create_engine_for_path(tmp_path / "labels.db")
    init_schema(engine)
    session_factory = create_session_factory(engine)
    try:
        with session_scope(session_factory) as session:
            label = Label(name="cross-cutting")
            session.add(label)
            session.flush()
            read = LabelRead.model_validate(label)
            assert read.id == label.id
            assert read.name == "cross-cutting"
    finally:
        engine.dispose()
