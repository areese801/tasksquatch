"""
Contract tests for the ``/api/v1/projects`` router.

Covers the CRUD round-trip, error responses for protected operations
on the Inbox (rename / delete), and the 409 path for deleting a
project that still has tasks.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _inbox(client: TestClient) -> dict[str, Any]:
    rows = client.get("/api/v1/projects").json()["items"]
    return dict(next(row for row in rows if row["is_inbox"]))


def test_list_projects_returns_inbox(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(row["is_inbox"] for row in items)


def test_create_project_returns_201_with_location(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "Side"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Side"
    assert body["is_inbox"] is False
    assert response.headers["location"] == f"/api/v1/projects/{body['id']}"


def test_create_project_empty_name_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": ""})
    assert response.status_code == 422


def test_create_project_missing_name_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={})
    assert response.status_code == 422


def test_get_project_by_id(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Work"}).json()
    response = client.get(f"/api/v1/projects/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Work"


def test_get_project_404(client: TestClient) -> None:
    response = client.get("/api/v1/projects/does-not-exist")
    assert response.status_code == 404


def test_patch_project_renames(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Side"}).json()
    response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"name": "Main"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Main"


def test_patch_project_moves_position(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Movable"}).json()
    response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"position": 42},
    )
    assert response.status_code == 200
    assert response.json()["position"] == 42


def test_patch_project_noop(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Keep"}).json()
    response = client.patch(f"/api/v1/projects/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json()["name"] == "Keep"


def test_patch_project_404_for_missing(client: TestClient) -> None:
    response = client.patch("/api/v1/projects/missing", json={"name": "x"})
    assert response.status_code == 404


def test_rename_inbox_returns_409(client: TestClient) -> None:
    inbox = _inbox(client)
    response = client.patch(
        f"/api/v1/projects/{inbox['id']}",
        json={"name": "NotInbox"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "inbox_protected"


def test_delete_inbox_returns_409(client: TestClient) -> None:
    inbox = _inbox(client)
    response = client.delete(f"/api/v1/projects/{inbox['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "inbox_protected"


def test_delete_empty_project_succeeds(client: TestClient) -> None:
    created = client.post("/api/v1/projects", json={"name": "Empty"}).json()
    response = client.delete(f"/api/v1/projects/{created['id']}")
    assert response.status_code == 204
    follow = client.get(f"/api/v1/projects/{created['id']}")
    assert follow.status_code == 404


def test_delete_non_empty_project_returns_409(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "Has-tasks"}).json()
    client.post(
        "/api/v1/tasks",
        json={"title": "blocker", "project_id": project["id"]},
    )
    response = client.delete(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "project_not_empty"


def test_delete_project_404_for_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/projects/missing")
    assert response.status_code == 404
