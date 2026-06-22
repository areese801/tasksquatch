"""
Tests covering ``POST /ui/tasks`` form-driven task creation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_task_minimal(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    A minimal form post creates a task and re-renders the list.
    """
    response = client.post(
        "/ui/tasks",
        data={"title": "New from form"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "New from form" in response.text


def test_create_task_with_project_and_priority(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    A create with project_id and priority routes to the right project
    and renders the corresponding task list back.
    """
    response = client.post(
        "/ui/tasks",
        data={
            "title": "High prio",
            "project_id": seeded_db["project_id"],
            "priority": "P1",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "High prio" in body
    assert "Project task" in body
    assert "First task" not in body
