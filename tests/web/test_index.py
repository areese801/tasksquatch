"""
Smoke tests for the ``GET /ui`` dashboard root.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_ui_root_returns_html(client: TestClient) -> None:
    """
    ``GET /ui/`` returns 200 with an HTML content type.
    """
    response = client.get("/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_ui_root_contains_inbox(
    client: TestClient,
    seeded_db: dict[str, str],
) -> None:
    """
    ``GET /ui/`` renders Inbox in the sidebar and at least one task.
    """
    response = client.get("/ui/")
    body = response.text
    assert "Inbox" in body
    assert "First task" in body


def test_ui_root_includes_skip_link(client: TestClient) -> None:
    """
    The base layout exposes a skip-to-main accessibility link.
    """
    response = client.get("/ui/")
    assert 'href="#main"' in response.text
    assert "Skip to main" in response.text
