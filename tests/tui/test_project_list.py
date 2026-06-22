"""
Tests for the project list screen.

Covers the snapshot of the initial render and the live interactions
that create a new project and refuse to delete the Inbox.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tasksquatch.core.services import projects as projects_service
from tasksquatch.tui._session import default_core_factory
from tasksquatch.tui.app import TasksquatchTuiApp


def test_project_list_snapshot(
    snap_compare: Any,
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    The initial project list renders deterministically.
    """
    assert snap_compare(seeded_app)


async def test_project_list_creates_project_via_prompt(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Pressing ``n``, typing a name, and submitting adds a project.
    """
    async with seeded_app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        for ch in "Side":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

    factory = seeded_app.core_factory
    with factory() as session:
        names = [p.name for p in projects_service.list_projects(session)]
    assert "Side" in names


async def test_inbox_protected_against_delete(db_path: Path) -> None:
    """
    Attempting to delete the Inbox surfaces a warning rather than
    removing the row.
    """
    factory = default_core_factory(db_path)
    app = TasksquatchTuiApp(core_factory=factory)
    async with app.run_test() as pilot:
        # Inbox is the only row and the cursor lands on it.
        await pilot.press("d")
        await pilot.pause()
        # Confirm prompt: press y.
        await pilot.press("y")
        await pilot.pause()

    with factory() as session:
        names = [p.name for p in projects_service.list_projects(session)]
    assert "Inbox" in names
