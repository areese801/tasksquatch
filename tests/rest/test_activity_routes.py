"""
Contract tests for the ``/api/v1/activity`` router.

Verifies that mutations produce activity rows visible through the
read endpoint and that the filters (task id, event type, since,
limit) narrow the response correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient


def _all_activity(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/v1/activity")
    assert response.status_code == 200
    return list(response.json()["items"])


def test_activity_contains_created_event_after_task_post(
    client: TestClient,
) -> None:
    task = client.post("/api/v1/tasks", json={"title": "ping"}).json()
    rows = _all_activity(client)
    matches = [
        row
        for row in rows
        if row["event_type"] == "created" and row["task_id"] == task["id"]
    ]
    assert len(matches) == 1
    assert matches[0]["detail"]["task_id"] == task["id"]


def test_activity_filter_by_task_id(client: TestClient) -> None:
    a = client.post("/api/v1/tasks", json={"title": "a"}).json()
    b = client.post("/api/v1/tasks", json={"title": "b"}).json()

    rows = client.get(
        "/api/v1/activity",
        params={"task_id": a["id"]},
    ).json()["items"]
    assert rows, "expected at least one event for task A"
    assert all(row["task_id"] == a["id"] for row in rows)
    assert not any(row["task_id"] == b["id"] for row in rows)


def test_activity_filter_by_event_type(client: TestClient) -> None:
    task = client.post("/api/v1/tasks", json={"title": "completable"}).json()
    client.post(f"/api/v1/tasks/{task['id']}/complete", json={})

    rows = client.get(
        "/api/v1/activity",
        params={"event_type": "completed"},
    ).json()["items"]
    assert rows, "expected at least one completed event"
    assert all(row["event_type"] == "completed" for row in rows)


def test_activity_filter_by_event_type_unknown_returns_422(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/activity",
        params={"event_type": "totally-made-up"},
    )
    assert response.status_code == 422


def test_activity_filter_by_since(client: TestClient) -> None:
    client.post("/api/v1/tasks", json={"title": "early"})
    far_future = (datetime.now(UTC) + timedelta(days=365)).isoformat()
    rows = client.get(
        "/api/v1/activity",
        params={"since": far_future},
    ).json()["items"]
    assert rows == []


def test_activity_respects_limit(client: TestClient) -> None:
    for i in range(5):
        client.post("/api/v1/tasks", json={"title": f"t-{i}"})
    rows = client.get(
        "/api/v1/activity",
        params={"limit": 2},
    ).json()["items"]
    assert len(rows) == 2


def test_activity_order_is_newest_first(client: TestClient) -> None:
    first = client.post("/api/v1/tasks", json={"title": "first"}).json()
    second = client.post("/api/v1/tasks", json={"title": "second"}).json()
    rows = client.get("/api/v1/activity").json()["items"]
    created_rows = [row for row in rows if row["event_type"] == "created"]
    task_ids_in_order = [row["task_id"] for row in created_rows]
    assert task_ids_in_order.index(second["id"]) < task_ids_in_order.index(first["id"])
