"""
Tests covering ``POST /ui/tasks/{id}/delete``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_delete_removes_task(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``POST /ui/tasks/{id}/delete`` returns an empty HTML body and the
    task no longer appears in the task list.
    """
    task_id = seeded_db["task_a_id"]
    response = client.post(f"/ui/tasks/{task_id}/delete")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "First task" not in response.text
    assert response.text.strip() == "" or "First task" not in response.text

    listing = client.get(f"/ui/projects/{seeded_db['inbox_id']}")
    assert "First task" not in listing.text
    assert "Second task" in listing.text
