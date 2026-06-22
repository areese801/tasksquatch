"""
Tests covering ``POST /ui/tasks/{id}/toggle``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_toggle_marks_completed(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    Toggling an incomplete task returns the row with ``completed``.
    """
    response = client.post(f"/ui/tasks/{seeded_db['task_a_id']}/toggle")
    assert response.status_code == 200
    body = response.text
    assert 'class="task-row completed"' in body


def test_toggle_round_trip(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    Toggling twice leaves the task back at its starting state.
    """
    task_id = seeded_db["task_b_id"]
    first = client.post(f"/ui/tasks/{task_id}/toggle")
    second = client.post(f"/ui/tasks/{task_id}/toggle")
    assert first.status_code == 200
    assert second.status_code == 200
    assert "completed" in first.text.split(">", 1)[0] or "completed" in first.text
    assert 'class="task-row"' in second.text
