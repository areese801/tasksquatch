"""
Tests covering the static file mount.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_htmx_served(client: TestClient) -> None:
    """
    ``GET /static/htmx.min.js`` returns 200 with JS content.
    """
    response = client.get("/static/htmx.min.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"].lower()


def test_stylesheet_served(client: TestClient) -> None:
    """
    ``GET /static/style.css`` returns 200 with CSS content.
    """
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "css" in response.headers["content-type"].lower()
