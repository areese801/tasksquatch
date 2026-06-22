"""
Tests covering the HTMX partial endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_project_partial_is_fragment(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``GET /ui/projects/{id}`` returns a bare partial — no ``<html>``.
    """
    response = client.get(f"/ui/projects/{seeded_db['inbox_id']}")
    assert response.status_code == 200
    body = response.text
    assert "<html" not in body.lower()
    assert "task-form" in body


def test_project_partial_lists_inbox_tasks(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    The Inbox partial includes the seeded Inbox task titles.
    """
    response = client.get(f"/ui/projects/{seeded_db['inbox_id']}")
    body = response.text
    assert "First task" in body
    assert "Second task" in body
    assert "Project task" not in body


def test_task_detail_partial(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``GET /ui/tasks/{id}`` returns the detail partial for a task.
    """
    response = client.get(f"/ui/tasks/{seeded_db['task_a_id']}")
    assert response.status_code == 200
    body = response.text
    assert "<html" not in body.lower()
    assert "First task" in body
    assert "Task #" in body
