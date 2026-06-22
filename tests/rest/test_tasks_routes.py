"""
Contract tests for the ``/api/v1/tasks`` router.

Exercises the full CRUD round-trip, the list endpoint's filter
combinations, PATCH semantics (including the three-valued
``label_ids`` rules), completion and uncompletion, recurrence
advance via the REST surface, project move, parent (set/clear),
the subtask listing, label attach/detach, and the relevant error
responses (404, 422).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _inbox_id(client: TestClient) -> str:
    """
    Return the seeded Inbox project id.
    """
    rows = client.get("/api/v1/projects").json()["items"]
    inbox = next(row for row in rows if row["is_inbox"])
    return str(inbox["id"])


def _make_label(client: TestClient, name: str) -> dict[str, Any]:
    response = client.post("/api/v1/labels", json={"name": name})
    assert response.status_code == 201, response.text
    return dict(response.json())


def _make_task(client: TestClient, **payload: Any) -> dict[str, Any]:
    response = client.post("/api/v1/tasks", json={"title": "task", **payload})
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_create_task_returns_201_with_location_header(client: TestClient) -> None:
    response = client.post("/api/v1/tasks", json={"title": "first"})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "first"
    assert body["number"] == 1
    assert body["completed"] is False
    assert response.headers["location"] == f"/api/v1/tasks/{body['id']}"


def test_create_task_defaults_to_inbox(client: TestClient) -> None:
    inbox = _inbox_id(client)
    task = _make_task(client, title="defaults-to-inbox")
    assert task["project_id"] == inbox


def test_create_task_with_explicit_fields(client: TestClient) -> None:
    label = _make_label(client, "urgent")
    inbox = _inbox_id(client)
    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "kitchen-sink",
            "description": "lots of fields",
            "project_id": inbox,
            "priority": "P1",
            "due_date": "2026-12-31",
            "due_time": "09:00:00",
            "label_ids": [label["id"]],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["description"] == "lots of fields"
    assert body["priority"] == "P1"
    assert body["due_date"] == "2026-12-31"
    assert body["due_time"] == "09:00:00"
    assert body["label_ids"] == [label["id"]]


def test_create_task_empty_title_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/tasks", json={"title": ""})
    assert response.status_code == 422


def test_create_task_missing_title_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/tasks", json={})
    assert response.status_code == 422


def test_get_task_by_id(client: TestClient) -> None:
    task = _make_task(client, title="lookup-by-id")
    response = client.get(f"/api/v1/tasks/{task['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == task["id"]


def test_get_task_by_id_404_for_unknown(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"


def test_get_task_by_number(client: TestClient) -> None:
    task = _make_task(client, title="lookup-by-number")
    response = client.get(f"/api/v1/tasks/by-number/{task['number']}")
    assert response.status_code == 200
    assert response.json()["id"] == task["id"]


def test_get_task_by_number_404_for_unknown(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/by-number/99999")
    assert response.status_code == 404


def test_list_tasks_returns_envelope(client: TestClient) -> None:
    _make_task(client, title="a")
    _make_task(client, title="b")
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    titles = {row["title"] for row in body["items"]}
    assert {"a", "b"} <= titles


def test_list_tasks_filters_by_project_label_priority(client: TestClient) -> None:
    label = _make_label(client, "filterlabel")
    inbox = _inbox_id(client)
    _make_task(client, title="loose")
    matched = _make_task(
        client,
        title="matches",
        priority="P1",
        label_ids=[label["id"]],
    )
    response = client.get(
        "/api/v1/tasks",
        params={
            "project_id": inbox,
            "label_id": label["id"],
            "priority": "p1",
        },
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [row["id"] for row in items] == [matched["id"]]


def test_list_tasks_completed_filter(client: TestClient) -> None:
    open_task = _make_task(client, title="open")
    done = _make_task(client, title="done")
    client.post(f"/api/v1/tasks/{done['id']}/complete", json={})

    completed = client.get("/api/v1/tasks", params={"completed": True}).json()
    assert {row["id"] for row in completed["items"]} == {done["id"]}

    incomplete = client.get("/api/v1/tasks", params={"completed": False}).json()
    assert {row["id"] for row in incomplete["items"]} == {open_task["id"]}


def test_list_tasks_due_window(client: TestClient) -> None:
    early = _make_task(client, title="early", due_date="2026-01-15")
    later = _make_task(client, title="later", due_date="2026-06-01")
    nope = _make_task(client, title="undated")  # noqa: F841

    response = client.get(
        "/api/v1/tasks",
        params={"due_before": "2026-03-01"},
    )
    items = response.json()["items"]
    assert {row["id"] for row in items} == {early["id"]}

    response = client.get(
        "/api/v1/tasks",
        params={"due_after": "2026-03-01"},
    )
    items = response.json()["items"]
    assert {row["id"] for row in items} == {later["id"]}


def test_list_tasks_parent_id_none_returns_top_level_only(
    client: TestClient,
) -> None:
    parent = _make_task(client, title="parent")
    child = _make_task(client, title="child", parent_id=parent["id"])  # noqa: F841

    top_level = client.get(
        "/api/v1/tasks",
        params={"parent_id": "none"},
    ).json()["items"]
    assert {row["id"] for row in top_level} == {parent["id"]}


def test_list_tasks_parent_id_any_returns_all(client: TestClient) -> None:
    parent = _make_task(client, title="parent")
    child = _make_task(client, title="child", parent_id=parent["id"])

    all_rows = client.get("/api/v1/tasks", params={"parent_id": "any"}).json()["items"]
    ids = {row["id"] for row in all_rows}
    assert {parent["id"], child["id"]} <= ids


def test_list_tasks_parent_id_specific(client: TestClient) -> None:
    parent = _make_task(client, title="parent")
    child_a = _make_task(client, title="child-a", parent_id=parent["id"])
    child_b = _make_task(client, title="child-b", parent_id=parent["id"])
    _make_task(client, title="unrelated")

    rows = client.get(
        "/api/v1/tasks",
        params={"parent_id": parent["id"]},
    ).json()["items"]
    assert {row["id"] for row in rows} == {child_a["id"], child_b["id"]}


def test_list_tasks_limit(client: TestClient) -> None:
    for i in range(5):
        _make_task(client, title=f"item-{i}")
    rows = client.get("/api/v1/tasks", params={"limit": 2}).json()["items"]
    assert len(rows) == 2


def test_list_tasks_order_by_unknown_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/tasks", params={"order_by": "bogus"})
    assert response.status_code == 422


def test_list_tasks_unknown_priority_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/tasks", params={"priority": "P9"})
    assert response.status_code == 422


def test_patch_task_partial_update(client: TestClient) -> None:
    task = _make_task(client, title="orig", description="orig desc")
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"title": "renamed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "renamed"
    assert body["description"] == "orig desc"


def test_patch_task_clear_description(client: TestClient) -> None:
    task = _make_task(client, title="t", description="not null")
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"description": None},
    )
    assert response.status_code == 200
    assert response.json()["description"] is None


def test_patch_task_explicit_null_title_rejected(client: TestClient) -> None:
    task = _make_task(client, title="keep")
    response = client.patch(f"/api/v1/tasks/{task['id']}", json={"title": None})
    assert response.status_code == 422


def test_patch_task_empty_body_is_noop(client: TestClient) -> None:
    task = _make_task(client, title="unchanged")
    response = client.patch(f"/api/v1/tasks/{task['id']}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == "unchanged"


def test_patch_task_labels_omitted_means_no_change(client: TestClient) -> None:
    label = _make_label(client, "keep")
    task = _make_task(client, title="t", label_ids=[label["id"]])
    response = client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "x"})
    assert response.status_code == 200
    assert response.json()["label_ids"] == [label["id"]]


def test_patch_task_labels_empty_clears(client: TestClient) -> None:
    label = _make_label(client, "drop")
    task = _make_task(client, title="t", label_ids=[label["id"]])
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"label_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["label_ids"] == []


def test_patch_task_labels_replace_set(client: TestClient) -> None:
    keep = _make_label(client, "keep")
    drop = _make_label(client, "drop")
    add = _make_label(client, "add")
    task = _make_task(client, title="t", label_ids=[keep["id"], drop["id"]])
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"label_ids": [keep["id"], add["id"]]},
    )
    assert response.status_code == 200
    assert set(response.json()["label_ids"]) == {keep["id"], add["id"]}


def test_patch_task_404_for_missing(client: TestClient) -> None:
    response = client.patch("/api/v1/tasks/missing", json={"title": "x"})
    assert response.status_code == 404


def test_patch_task_invalid_recurrence_returns_422(client: TestClient) -> None:
    task = _make_task(client, title="t")
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"recurrence": "not-a-rrule"},
    )
    assert response.status_code == 422


def test_delete_task(client: TestClient) -> None:
    task = _make_task(client, title="going")
    response = client.delete(f"/api/v1/tasks/{task['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404


def test_delete_task_404_for_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/tasks/missing")
    assert response.status_code == 404


def test_complete_task_default_when(client: TestClient) -> None:
    task = _make_task(client, title="done")
    response = client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert body["completed_at"] is not None


def test_complete_task_with_explicit_when(client: TestClient) -> None:
    task = _make_task(client, title="done")
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC).isoformat()
    response = client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json={"when": when},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is True
    assert body["completed_at"].startswith("2026-01-01T12:00:00")


def test_complete_task_twice_returns_409(client: TestClient) -> None:
    task = _make_task(client, title="done-once")
    client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    response = client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert response.status_code == 409


def test_complete_recurring_task_advances_due_date(client: TestClient) -> None:
    task = _make_task(
        client,
        title="weekly",
        due_date="2026-06-22",
        recurrence="FREQ=WEEKLY",
    )
    response = client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert response.status_code == 200
    body = response.json()
    expected_next = (date(2026, 6, 22) + timedelta(days=7)).isoformat()
    assert body["due_date"] == expected_next
    assert body["completed"] is False


def test_uncomplete_task(client: TestClient) -> None:
    task = _make_task(client, title="reopen")
    client.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    response = client.post(f"/api/v1/tasks/{task['id']}/uncomplete")
    assert response.status_code == 200
    body = response.json()
    assert body["completed"] is False
    assert body["completed_at"] is None


def test_move_task(client: TestClient) -> None:
    other = client.post("/api/v1/projects", json={"name": "Side"}).json()
    task = _make_task(client, title="movable")
    response = client.post(
        f"/api/v1/tasks/{task['id']}/move",
        json={"project_id": other["id"]},
    )
    assert response.status_code == 200
    assert response.json()["project_id"] == other["id"]


def test_move_task_to_missing_project_returns_404(client: TestClient) -> None:
    task = _make_task(client, title="movable")
    response = client.post(
        f"/api/v1/tasks/{task['id']}/move",
        json={"project_id": "does-not-exist"},
    )
    assert response.status_code == 404


def test_set_parent_attaches_and_detaches(client: TestClient) -> None:
    parent = _make_task(client, title="parent")
    child = _make_task(client, title="child")
    response = client.post(
        f"/api/v1/tasks/{child['id']}/parent",
        json={"parent_id": parent["id"]},
    )
    assert response.status_code == 200
    assert response.json()["parent_id"] == parent["id"]

    detach = client.post(
        f"/api/v1/tasks/{child['id']}/parent",
        json={"parent_id": None},
    )
    assert detach.status_code == 200
    assert detach.json()["parent_id"] is None


def test_subtasks_endpoint(client: TestClient) -> None:
    parent = _make_task(client, title="parent")
    a = _make_task(client, title="child-a", parent_id=parent["id"])
    b = _make_task(client, title="child-b", parent_id=parent["id"])

    response = client.get(f"/api/v1/tasks/{parent['id']}/subtasks")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["items"]}
    assert ids == {a["id"], b["id"]}


def test_subtasks_recursive_walks_descendants(client: TestClient) -> None:
    parent = _make_task(client, title="parent")
    child = _make_task(client, title="child", parent_id=parent["id"])
    grand = _make_task(client, title="grand", parent_id=child["id"])

    response = client.get(
        f"/api/v1/tasks/{parent['id']}/subtasks",
        params={"recursive": True},
    )
    ids = {row["id"] for row in response.json()["items"]}
    assert ids == {child["id"], grand["id"]}


def test_subtasks_404_for_missing(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/missing/subtasks")
    assert response.status_code == 404


def test_add_label_endpoint(client: TestClient) -> None:
    label = _make_label(client, "tag")
    task = _make_task(client, title="t")
    response = client.post(
        f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
    )
    assert response.status_code == 200
    assert response.json()["label_ids"] == [label["id"]]


def test_add_label_unknown_label_returns_404(client: TestClient) -> None:
    task = _make_task(client, title="t")
    response = client.post(f"/api/v1/tasks/{task['id']}/labels/missing")
    assert response.status_code == 404


def test_remove_label_endpoint(client: TestClient) -> None:
    label = _make_label(client, "tag")
    task = _make_task(client, title="t", label_ids=[label["id"]])
    response = client.delete(
        f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
    )
    assert response.status_code == 204
    fetched = client.get(f"/api/v1/tasks/{task['id']}").json()
    assert fetched["label_ids"] == []


def test_remove_label_noop_when_not_attached(client: TestClient) -> None:
    label = _make_label(client, "tag")
    task = _make_task(client, title="t")
    response = client.delete(
        f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
    )
    assert response.status_code == 204


@pytest.mark.parametrize(
    "payload",
    [
        {"due_date": "not-a-date"},
        {"priority": "P9"},
        {"due_time": "25:99"},
    ],
)
def test_patch_task_validation_errors(
    client: TestClient, payload: dict[str, Any]
) -> None:
    task = _make_task(client, title="x")
    response = client.patch(f"/api/v1/tasks/{task['id']}", json=payload)
    assert response.status_code == 422
