"""
Tests for the task detail screen.

Covers the snapshot baseline (a task with comments and subtasks), the
comment modal round-trip, the complete keybinding, and the delete
keybinding's confirmation dialog.
"""

from __future__ import annotations

from typing import Any

from freezegun import freeze_time
from textual.widgets import DataTable

from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.tui.app import TasksquatchTuiApp
from tasksquatch.tui.screens.task_detail import TaskDetailScreen


def _seed_detail_fixture(app: TasksquatchTuiApp) -> str:
    """
    Seed a parent task with one comment and one subtask in "Work".

    :param app: The seeded TUI app.
    :returns: The parent task's UUIDv7 id.
    """
    with app.core_factory() as session:
        work = next(
            p for p in projects_service.list_projects(session) if p.name == "Work"
        )
        parent = tasks_service.create_task(
            session,
            title="Plan launch",
            project_id=work.id,
            description="Pre-flight checklist",
        )
        tasks_service.create_task(
            session,
            title="Draft press release",
            project_id=work.id,
            parent_id=parent.id,
        )
        comments_service.add_comment(
            session,
            task_id=parent.id,
            body="kicked off planning meeting",
        )
        return str(parent.id)


def test_task_detail_snapshot(
    snap_compare: Any,
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    The detail screen renders a task with comments and subtasks
    deterministically.
    """
    with freeze_time("2026-06-22T12:00:00"):
        parent_id = _seed_detail_fixture(seeded_app)

    async def run_before(pilot: Any) -> None:
        """
        Push the TaskDetailScreen for the seeded parent task.
        """
        await pilot.app.push_screen(TaskDetailScreen(task_id=parent_id))
        await pilot.pause()

    assert snap_compare(seeded_app, run_before=run_before)


async def test_detail_comment_round_trip(seeded_app: TasksquatchTuiApp) -> None:
    """
    Pressing ``c`` opens the comment modal; submitting persists a new
    comment that the refresh picks up.
    """
    parent_id = _seed_detail_fixture(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(TaskDetailScreen(task_id=parent_id))
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        for ch in "follow up tomorrow":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()

        screen = pilot.app.screen
        assert isinstance(screen, TaskDetailScreen)
        comments_table = screen.query_one("#detail-comments", DataTable)
        assert comments_table.row_count == 2

    with seeded_app.core_factory() as session:
        comments = queries_service.list_comments(session, parent_id)
    bodies = [c.body for c in comments]
    assert "follow up tomorrow" in bodies


async def test_detail_complete_marks_task_done(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Pressing ``d`` from the detail screen marks the task complete.
    """
    parent_id = _seed_detail_fixture(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(TaskDetailScreen(task_id=parent_id))
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        task = queries_service.get_task_by_id(session, parent_id)
    assert task.completed is True


async def test_detail_delete_with_confirmation(
    seeded_app: TasksquatchTuiApp,
) -> None:
    """
    Pressing ``x`` and confirming with ``y`` deletes the task and pops
    the detail screen.
    """
    parent_id = _seed_detail_fixture(seeded_app)

    async with seeded_app.run_test() as pilot:
        await pilot.app.push_screen(TaskDetailScreen(task_id=parent_id))
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

    with seeded_app.core_factory() as session:
        tasks = queries_service.list_tasks(session)
    assert parent_id not in {t.id for t in tasks}
