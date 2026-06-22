"""
Contract tests for the ``/api/v1/labels`` router.

Covers the CRUD round-trip and the 422 path for duplicate names.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_labels_initially_empty(client: TestClient) -> None:
    response = client.get("/api/v1/labels")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_create_label_returns_201_with_location(client: TestClient) -> None:
    response = client.post("/api/v1/labels", json={"name": "urgent"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "urgent"
    assert response.headers["location"] == f"/api/v1/labels/{body['id']}"


def test_create_label_empty_name_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/labels", json={"name": ""})
    assert response.status_code == 422


def test_create_label_missing_name_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/labels", json={})
    assert response.status_code == 422


def test_create_duplicate_label_returns_422(client: TestClient) -> None:
    client.post("/api/v1/labels", json={"name": "dup"})
    response = client.post("/api/v1/labels", json={"name": "dup"})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_get_label_by_id(client: TestClient) -> None:
    created = client.post("/api/v1/labels", json={"name": "tag"}).json()
    response = client.get(f"/api/v1/labels/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "tag"


def test_get_label_404(client: TestClient) -> None:
    response = client.get("/api/v1/labels/missing")
    assert response.status_code == 404


def test_patch_label_renames(client: TestClient) -> None:
    created = client.post("/api/v1/labels", json={"name": "old"}).json()
    response = client.patch(
        f"/api/v1/labels/{created['id']}",
        json={"name": "new"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "new"


def test_patch_label_noop(client: TestClient) -> None:
    created = client.post("/api/v1/labels", json={"name": "keep"}).json()
    response = client.patch(f"/api/v1/labels/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json()["name"] == "keep"


def test_patch_label_duplicate_returns_422(client: TestClient) -> None:
    client.post("/api/v1/labels", json={"name": "a"})
    b = client.post("/api/v1/labels", json={"name": "b"}).json()
    response = client.patch(
        f"/api/v1/labels/{b['id']}",
        json={"name": "a"},
    )
    assert response.status_code == 422


def test_patch_label_404_for_missing(client: TestClient) -> None:
    response = client.patch("/api/v1/labels/missing", json={"name": "x"})
    assert response.status_code == 404


def test_delete_label(client: TestClient) -> None:
    created = client.post("/api/v1/labels", json={"name": "going"}).json()
    response = client.delete(f"/api/v1/labels/{created['id']}")
    assert response.status_code == 204
    follow = client.get(f"/api/v1/labels/{created['id']}")
    assert follow.status_code == 404


def test_delete_label_404_for_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/labels/missing")
    assert response.status_code == 404
