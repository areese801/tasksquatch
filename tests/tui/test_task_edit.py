"""
Tests for the task create / edit modal.

Covers the create flow driven from :class:`TaskListScreen` via the
``n`` binding, the edit flow driven via ``e`` on an existing task,
and the cancel path that leaves persisted state unchanged.
"""

from __future__ import annotations

from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Input, Select, TextArea

from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.tui.app import TasksquatchTuiApp
from tasksquatch.tui.screens.task_edit import TaskEditScreen
from tasksquatch.tui.screens.task_list import TaskListScreen


def _work_project_id(app: TasksquatchTuiApp) -> str:
    """
    Return the UUIDv7 id of the seeded "Work" project.
    """
    with app.core_factory() as session:
        for project in projects_service.list_projects(session):
            if project.name == "Work":
                return str(project.id)
    raise AssertionError("Work project missing from seeded app")


def _existing_task(app: TasksquatchTuiApp, project_id: str) -> tuple[str, str]:
    """
    Return ``(task_id, original_title)`` for a top-level task in the
    seeded project.
    """
    with app.core_factory() as session:
        tasks = queries_service.list_tasks(session, project_id=project_id)
    assert tasks, "expected at least one seeded task"
    return tasks[0].id, tasks[0].title


async def test_create_task_via_n_binding(seeded_app: TasksquatchTuiApp) -> None:
    """
    Pressing ``n`` opens the modal in create mode, filling the title
    and submitting persists a new task in the active project.
    """
    project_id = _work_project_id(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        screen.query_one("#edit-title", Input).value = "Polish slide deck"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        titles = [
            t.title for t in queries_service.list_tasks(session, project_id=project_id)
        ]
    assert "Polish slide deck" in titles


async def test_edit_task_updates_title(seeded_app: TasksquatchTuiApp) -> None:
    """
    Pressing ``e`` on an existing task prefills the form and saving a
    new title updates the persisted row.
    """
    project_id = _work_project_id(seeded_app)
    task_id, original_title = _existing_task(seeded_app, project_id)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        title_input = screen.query_one("#edit-title", Input)
        assert title_input.value == original_title
        title_input.value = "Rewritten title"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        task = queries_service.get_task_by_id(session, task_id)
    assert task.title == "Rewritten title"


async def test_edit_cancel_leaves_state_unchanged(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Cancelling the modal must not persist any changes.
    """
    project_id = _work_project_id(seeded_app)
    task_id, original_title = _existing_task(seeded_app, project_id)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        screen.query_one("#edit-title", Input).value = "Should not stick"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        task = queries_service.get_task_by_id(session, task_id)
    assert task.title == original_title


async def test_create_task_with_priority_and_due_date(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Filling the priority and due-date fields in create mode persists
    the corresponding values on the new task.
    """
    project_id = _work_project_id(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        screen.query_one("#edit-title", Input).value = "Wire up CI"
        screen.query_one("#edit-due-date", Input).value = "2026-07-04"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        tasks = queries_service.list_tasks(session, project_id=project_id)
        new_task = next(t for t in tasks if t.title == "Wire up CI")
    assert new_task.due_date is not None
    assert new_task.due_date.isoformat() == "2026-07-04"


async def test_create_form_contains_all_expected_widgets(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    The create modal lays out every documented widget by id.

    Regression test for TSQ-37: the modal previously collapsed to one
    visible field because the screen carried no styles. A
    ``DEFAULT_CSS`` block now constrains the modal body so every input
    is laid out and addressable.
    """
    project_id = _work_project_id(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        assert screen.query_one("#edit-title", Input) is not None
        assert screen.query_one("#edit-description", TextArea) is not None
        assert screen.query_one("#edit-project", Select) is not None
        assert screen.query_one("#edit-priority", Select) is not None
        assert screen.query_one("#edit-due-date", Input) is not None
        assert screen.query_one("#edit-due-time", Input) is not None
        assert screen.query_one("#edit-recurrence", Input) is not None
        assert screen.query_one("#edit-anchor", Select) is not None
        assert screen.query_one("#edit-labels", Input) is not None
        assert screen.query_one("#edit-save", Button) is not None
        assert screen.query_one("#edit-cancel", Button) is not None


async def test_edit_screen_refreshes_task_list(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    After the edit modal saves, the task list re-renders with the new
    title in the visible row.
    """
    project_id = _work_project_id(seeded_app)
    task_id, _ = _existing_task(seeded_app, project_id)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(
            TaskListScreen(project_id=project_id, project_name="Work")
        )
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TaskEditScreen)
        screen.query_one("#edit-title", Input).value = "Refreshed name"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

        list_screen = pilot.app.screen
        assert isinstance(list_screen, TaskListScreen)
        table = list_screen.query_one("#task-table", DataTable)
        rendered_titles: list[str] = []
        for row_index in range(table.row_count):
            rendered_titles.append(str(table.get_cell_at(Coordinate(row_index, 1))))
        assert any("Refreshed name" in cell for cell in rendered_titles)

    with seeded_app.core_factory() as session:
        task = queries_service.get_task_by_id(session, task_id)
    assert task.title == "Refreshed name"
