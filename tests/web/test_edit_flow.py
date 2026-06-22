"""
Tests covering the edit form GET + the PUT update endpoint.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_edit_form_prefilled(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``GET /ui/tasks/{id}/edit`` renders the form prefilled with the
    current task's title.
    """
    response = client.get(f"/ui/tasks/{seeded_db['task_a_id']}/edit")
    assert response.status_code == 200
    body = response.text
    assert "task-form" in body
    assert 'value="First task"' in body


def test_put_updates_title_and_renders_detail(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``PUT /ui/tasks/{id}`` updates the title and returns the detail.
    """
    task_id = seeded_db["task_a_id"]
    response = client.put(
        f"/ui/tasks/{task_id}",
        data={
            "title": "First task (renamed)",
            "project_id": seeded_db["inbox_id"],
            "priority": "P2",
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "First task (renamed)" in body
    assert "P2" in body
