"""
Tests for the task list screen.

Covers the initial snapshot, the fuzzy filter narrowing the table,
and the ``d`` (complete) action mutating a task through the service
layer.
"""

from __future__ import annotations

from typing import Any

from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.tui.app import TasksquatchTuiApp
from tasksquatch.tui.screens.task_list import TaskListScreen
from tasksquatch.tui.widgets.fuzzy_filter import FilterInput


def _work_project_id(app: TasksquatchTuiApp) -> str:
    """
    Return the UUIDv7 id of the seeded "Work" project.

    :param app: The seeded TUI app fixture.
    :returns: The id of the "Work" project.
    """
    with app.core_factory() as session:
        for project in projects_service.list_projects(session):
            if project.name == "Work":
                return str(project.id)
    raise AssertionError("Work project missing from seeded app")


def test_task_list_snapshot(
    snap_compare: Any,
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Opening the seeded "Work" project renders deterministically.
    """
    project_id = _work_project_id(seeded_app)

    async def run_before(pilot: Any) -> None:
        """
        Push the TaskListScreen for the seeded Work project.
        """
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()

    assert snap_compare(seeded_app, run_before=run_before)


async def test_task_filter_narrows_visible_rows(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Typing ``milk`` into the filter leaves only the matching task.
    """
    # Find the Errands project so we can open the screen that holds "buy milk".
    with seeded_app.core_factory() as session:
        errands = next(
            p for p in projects_service.list_projects(session) if p.name == "Errands"
        )

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=errands.id, project_name="Errands")
        )
        await pilot.pause()
        await pilot.press("slash")
        await pilot.pause()
        for ch in "milk":
            await pilot.press(ch)
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, TaskListScreen)
        from textual.widgets import DataTable

        table = screen.query_one("#task-table", DataTable)
        assert table.row_count == 1
        # Filter widget retains focus.
        filter_input = screen.query_one("#task-filter", FilterInput)
        assert filter_input.has_focus
        assert filter_input.value == "milk"


async def test_complete_task_via_d_key(seeded_app: TasksquatchTuiApp) -> None:
    """
    Pressing ``d`` on a task marks it complete via the service.
    """
    project_id = _work_project_id(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        tasks = queries_service.list_tasks(session, project_id=project_id)
        completed = [t for t in tasks if t.completed]
    assert len(completed) >= 1
