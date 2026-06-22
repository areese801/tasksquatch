"""
Tests for the global fuzzy search screen.

Covers the snapshot baseline against the seeded dataset, the
keystroke-driven narrowing of the results table, and the ``enter``
binding that drills into the task detail screen.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import DataTable

from tasksquatch.tui.app import TasksquatchTuiApp
from tasksquatch.tui.screens.search import SearchScreen
from tasksquatch.tui.screens.task_detail import TaskDetailScreen


def test_search_snapshot(
    snap_compare: Any,
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    The search screen renders the full seeded task set deterministically.
    """

    async def run_before(pilot: Any) -> None:
        """
        Push the SearchScreen onto the seeded app.
        """
        await pilot.app.push_screen(SearchScreen())
        await pilot.pause()

    assert snap_compare(seeded_app, run_before=run_before)


async def test_search_filter_narrows_results(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Typing a fuzzy query into the search filter narrows the result
    table down to the matching task only.
    """
    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(SearchScreen())
        await pilot.pause()
        for ch in "milk":
            await pilot.press(ch)
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, SearchScreen)
        table = screen.query_one("#search-table", DataTable)
        assert table.row_count == 1


async def test_search_enter_opens_task_detail(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Pressing ``enter`` on a result row pushes the detail screen for
    that task.
    """
    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(SearchScreen())
        await pilot.pause()
        for ch in "milk":
            await pilot.press(ch)
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, SearchScreen)
        # Focus the table so enter activates the open binding rather than
        # the filter input's submit handler.
        table = screen.query_one("#search-table", DataTable)
        table.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, TaskDetailScreen)
