"""
Shared fixtures for the MCP surface tests.

Each test gets its own SQLite file under ``tmp_path``, so tests never
share state and never touch the user's real database. The fixture
builds a fully-initialized :class:`CoreContext` — schema created,
Inbox seeded — so individual tests can call tool handlers immediately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tasksquatch.mcp._session import CoreContext, build_core


@pytest.fixture
def core(tmp_path: Path) -> CoreContext:
    """
    Build a per-test :class:`CoreContext` against a fresh SQLite file.

    :param tmp_path: pytest's per-test temporary directory.
    :returns: A populated :class:`CoreContext` ready for tool calls.
    """
    return build_core(tmp_path / "mcp.db")
