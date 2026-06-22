"""
Tests for the read-only query helpers in
:mod:`tasksquatch.core.services.queries`.

Activity, comments, and tasks are all exercised here; the
``get_due_tasks`` selector has its own focused module
(``test_get_due_tasks.py``) because it depends on freezegun for
deterministic time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from tasksquatch.core._sentinels import UNSET
from tasksquatch.core.errors import NotFoundError, ValidationError
from tasksquatch.core.models import ActivityEventType, Priority
from tasksquatch.core.services.comments import add_comment
from tasksquatch.core.services.labels import create_label
from tasksquatch.core.services.projects import create_project
from tasksquatch.core.services.queries import (
    get_task_by_id,
    get_task_by_number,
    list_activity,
    list_comments,
    list_subtasks,
    list_tasks,
    search_tasks,
)
from tasksquatch.core.services.tasks import (
    add_label,
    complete_task,
    create_task,
    update_task,
)


def test_get_task_by_id_returns_row(session: Session) -> None:
    task = create_task(session, title="t")
    assert get_task_by_id(session, task.id).id == task.id


def test_get_task_by_id_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_task_by_id(session, "00000000-0000-7000-8000-000000000000")


def test_get_task_by_number_returns_row(session: Session) -> None:
    task = create_task(session, title="t")
    fetched = get_task_by_number(session, task.number)
    assert fetched.id == task.id


def test_get_task_by_number_missing_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        get_task_by_number(session, 999_999)


def test_list_tasks_default_returns_all(session: Session) -> None:
    a = create_task(session, title="a")
    b = create_task(session, title="b")
    rows = list_tasks(session)
    ids = {r.id for r in rows}
    assert {a.id, b.id} <= ids


def test_list_tasks_filter_by_project(session: Session) -> None:
    work = create_project(session, name="Work")
    home = create_project(session, name="Home")
    w_task = create_task(session, title="w", project_id=work.id)
    h_task = create_task(session, title="h", project_id=home.id)

    rows = list_tasks(session, project_id=work.id)
    assert [r.id for r in rows] == [w_task.id]

    rows = list_tasks(session, project_id=home.id)
    assert [r.id for r in rows] == [h_task.id]


def test_list_tasks_filter_by_label(session: Session) -> None:
    label = create_label(session, name="urgent")
    task = create_task(session, title="needs label")
    other = create_task(session, title="bare")
    add_label(session, task.id, label.id)

    rows = list_tasks(session, label_id=label.id)
    assert [r.id for r in rows] == [task.id]
    assert other.id not in {r.id for r in rows}


def test_list_tasks_filter_by_priority(session: Session) -> None:
    p1 = create_task(session, title="p1", priority=Priority.P1)
    create_task(session, title="p4")
    rows = list_tasks(session, priority=Priority.P1)
    assert [r.id for r in rows] == [p1.id]


def test_list_tasks_filter_by_completed(session: Session) -> None:
    a = create_task(session, title="a")
    b = create_task(session, title="b")
    complete_task(session, a.id)

    open_rows = list_tasks(session, completed=False)
    assert {r.id for r in open_rows} == {b.id}

    closed_rows = list_tasks(session, completed=True)
    assert {r.id for r in closed_rows} == {a.id}


def test_list_tasks_filter_by_due_before_and_after(session: Session) -> None:
    early = create_task(session, title="early", due_date=date(2026, 1, 1))
    mid = create_task(session, title="mid", due_date=date(2026, 6, 15))
    late = create_task(session, title="late", due_date=date(2026, 12, 31))

    before = list_tasks(session, due_before=date(2026, 6, 30))
    assert {r.id for r in before} == {early.id, mid.id}

    after = list_tasks(session, due_after=date(2026, 6, 1))
    assert {r.id for r in after} == {mid.id, late.id}

    window = list_tasks(
        session,
        due_after=date(2026, 5, 1),
        due_before=date(2026, 7, 1),
    )
    assert {r.id for r in window} == {mid.id}


def test_list_tasks_parent_id_unset_returns_both_levels(session: Session) -> None:
    parent = create_task(session, title="parent")
    child = create_task(session, title="child", parent_id=parent.id)

    rows = list_tasks(session)
    ids = {r.id for r in rows}
    assert parent.id in ids
    assert child.id in ids


def test_list_tasks_parent_id_none_returns_top_level_only(session: Session) -> None:
    parent = create_task(session, title="parent")
    child = create_task(session, title="child", parent_id=parent.id)

    rows = list_tasks(session, parent_id=None)
    ids = {r.id for r in rows}
    assert parent.id in ids
    assert child.id not in ids


def test_list_tasks_parent_id_string_returns_direct_children(session: Session) -> None:
    parent = create_task(session, title="parent")
    a = create_task(session, title="a", parent_id=parent.id)
    b = create_task(session, title="b", parent_id=parent.id)
    grandchild = create_task(session, title="gc", parent_id=a.id)

    rows = list_tasks(session, parent_id=parent.id)
    ids = {r.id for r in rows}
    assert ids == {a.id, b.id}
    assert grandchild.id not in ids


def test_list_tasks_include_descendants_walks_tree(session: Session) -> None:
    root = create_task(session, title="root")
    a = create_task(session, title="a", parent_id=root.id)
    b = create_task(session, title="b", parent_id=root.id)
    gc1 = create_task(session, title="gc1", parent_id=a.id)
    ggc1 = create_task(session, title="ggc1", parent_id=gc1.id)

    rows = list_tasks(session, parent_id=root.id, include_descendants=True)
    ids = {r.id for r in rows}
    assert ids == {a.id, b.id, gc1.id, ggc1.id}


def test_list_tasks_order_by_invalid_raises(session: Session) -> None:
    with pytest.raises(ValidationError):
        list_tasks(session, order_by="not_a_column")


@pytest.mark.parametrize("key", ["position", "due_date", "priority", "created_at"])
def test_list_tasks_order_by_valid_keys(session: Session, key: str) -> None:
    create_task(session, title="a", due_date=date(2026, 6, 22))
    create_task(session, title="b", due_date=date(2026, 6, 23))
    rows = list_tasks(session, order_by=key)
    assert len(rows) >= 2


def test_list_tasks_limit(session: Session) -> None:
    for i in range(5):
        create_task(session, title=f"t{i}")
    rows = list_tasks(session, limit=2)
    assert len(rows) == 2


def test_search_tasks_empty_query_returns_empty(session: Session) -> None:
    create_task(session, title="anything")
    assert search_tasks(session, "") == []
    assert search_tasks(session, "   ") == []


def test_search_tasks_substring_case_insensitive(session: Session) -> None:
    a = create_task(session, title="Buy Groceries")
    b = create_task(session, title="Read GROceRY list")
    create_task(session, title="unrelated")

    hits = search_tasks(session, "grocer")
    ids = {r.id for r in hits}
    assert ids == {a.id, b.id}


def test_list_subtasks_direct_only(session: Session) -> None:
    parent = create_task(session, title="p")
    a = create_task(session, title="a", parent_id=parent.id)
    create_task(session, title="gc", parent_id=a.id)

    rows = list_subtasks(session, parent.id, recursive=False)
    assert [r.id for r in rows] == [a.id]


def test_list_subtasks_recursive(session: Session) -> None:
    parent = create_task(session, title="p")
    a = create_task(session, title="a", parent_id=parent.id)
    b = create_task(session, title="b", parent_id=parent.id)
    gc = create_task(session, title="gc", parent_id=a.id)

    rows = list_subtasks(session, parent.id, recursive=True)
    ids = {r.id for r in rows}
    assert ids == {a.id, b.id, gc.id}


def test_list_subtasks_missing_task_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        list_subtasks(session, "00000000-0000-7000-8000-000000000000")


def test_list_comments_orders_ascending(session: Session) -> None:
    task = create_task(session, title="t")
    c1 = add_comment(session, task_id=task.id, body="first")
    c2 = add_comment(session, task_id=task.id, body="second")
    c3 = add_comment(session, task_id=task.id, body="third")

    rows = list_comments(session, task.id)
    assert [r.id for r in rows] == [c1.id, c2.id, c3.id]


def test_list_comments_missing_task_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        list_comments(session, "00000000-0000-7000-8000-000000000000")


def test_list_activity_filter_by_task_id(session: Session) -> None:
    a = create_task(session, title="a")
    b = create_task(session, title="b")
    update_task(session, a.id, title="a-renamed")
    update_task(session, b.id, title="b-renamed")

    rows = list_activity(session, task_id=a.id)
    assert rows
    assert all(r.task_id == a.id for r in rows)


def test_list_activity_filter_by_event_type(session: Session) -> None:
    task = create_task(session, title="t")
    complete_task(session, task.id)

    completed_rows = list_activity(session, event_type=ActivityEventType.COMPLETED)
    assert len(completed_rows) == 1
    assert completed_rows[0].task_id == task.id


def test_list_activity_filter_since(session: Session) -> None:
    create_task(session, title="old")
    cutoff = datetime.now(UTC).replace(tzinfo=None)
    later = cutoff + timedelta(hours=1)
    rows_after = list_activity(session, since=later)
    assert rows_after == []

    rows_before = list_activity(session, since=cutoff - timedelta(hours=1))
    assert rows_before


def test_list_activity_default_order_is_newest_first(session: Session) -> None:
    task = create_task(session, title="t")
    update_task(session, task.id, title="renamed")

    rows = list_activity(session, task_id=task.id)
    assert len(rows) >= 2
    assert rows[0].created_at >= rows[-1].created_at


def test_list_tasks_parent_id_unset_explicit_is_no_filter(session: Session) -> None:
    parent = create_task(session, title="p")
    child = create_task(session, title="c", parent_id=parent.id)

    rows = list_tasks(session, parent_id=UNSET)
    ids = {r.id for r in rows}
    assert {parent.id, child.id} <= ids
