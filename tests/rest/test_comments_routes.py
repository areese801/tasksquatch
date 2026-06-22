"""
Contract tests for the comments router.

Covers the create / list endpoints under ``/api/v1/tasks/{id}/comments``
and the patch / delete endpoints under ``/api/v1/comments/{id}``.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _make_task(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/tasks", json={"title": "host"})
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_create_comment_returns_201_with_location(client: TestClient) -> None:
    task = _make_task(client)
    response = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "first note"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "first note"
    assert body["task_id"] == task["id"]
    assert response.headers["location"] == f"/api/v1/comments/{body['id']}"


def test_create_comment_on_missing_task_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks/missing/comments",
        json={"body": "hi"},
    )
    assert response.status_code == 404


def test_create_comment_empty_body_returns_422(client: TestClient) -> None:
    task = _make_task(client)
    response = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": ""},
    )
    assert response.status_code == 422


def test_create_comment_missing_body_returns_422(client: TestClient) -> None:
    task = _make_task(client)
    response = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={},
    )
    assert response.status_code == 422


def test_list_comments_returns_items_in_order(client: TestClient) -> None:
    task = _make_task(client)
    a = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "first"},
    ).json()
    b = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "second"},
    ).json()
    response = client.get(f"/api/v1/tasks/{task['id']}/comments")
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()["items"]]
    assert ids == [a["id"], b["id"]]


def test_list_comments_404_for_missing_task(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/missing/comments")
    assert response.status_code == 404


def test_patch_comment_updates_body(client: TestClient) -> None:
    task = _make_task(client)
    comment = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "before"},
    ).json()
    response = client.patch(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "after"},
    )
    assert response.status_code == 200
    assert response.json()["body"] == "after"


def test_patch_comment_empty_body_returns_422(client: TestClient) -> None:
    task = _make_task(client)
    comment = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "before"},
    ).json()
    response = client.patch(
        f"/api/v1/comments/{comment['id']}",
        json={"body": ""},
    )
    assert response.status_code == 422


def test_patch_comment_404_for_missing(client: TestClient) -> None:
    response = client.patch("/api/v1/comments/missing", json={"body": "x"})
    assert response.status_code == 404


def test_delete_comment(client: TestClient) -> None:
    task = _make_task(client)
    comment = client.post(
        f"/api/v1/tasks/{task['id']}/comments",
        json={"body": "going"},
    ).json()
    response = client.delete(f"/api/v1/comments/{comment['id']}")
    assert response.status_code == 204

    rows = client.get(f"/api/v1/tasks/{task['id']}/comments").json()["items"]
    assert rows == []


def test_delete_comment_404_for_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/comments/missing")
    assert response.status_code == 404
