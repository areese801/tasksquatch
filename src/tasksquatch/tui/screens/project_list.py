"""
Top-level screen listing every project and its task count.

The ProjectListScreen is the entry point of the tasksquatch TUI. It
renders a sortable :class:`DataTable` (one row per project, plus a
task count column derived from a live ``COUNT(*)`` query) and binds
the small set of keys that let the user create, rename, delete, and
drill into projects.

Every keybinding opens a fresh session through
``self.app.core_factory`` so each gesture is a self-contained
transaction. Errors raised by the service layer
(:class:`InboxProtectedError`, :class:`ProjectNotEmptyError`, ...)
are caught and surfaced through ``self.notify`` rather than allowed
to escape and crash the app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select
from textual.app import ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from tasksquatch.core.errors import TasksquatchError
from tasksquatch.core.models import Task
from tasksquatch.core.services import projects as projects_service
from tasksquatch.tui.screens._prompts import ConfirmScreen, TextPromptScreen

if TYPE_CHECKING:
    from tasksquatch.tui.app import TasksquatchTuiApp


class ProjectListScreen(Screen[None]):
    """
    Project listing screen.

    Composes a header, a single :class:`DataTable` (columns: ``Name``
    and ``Tasks``), and a footer that shows the bound actions. The
    Inbox is always present and always sorts first; it cannot be
    renamed or deleted, and attempts to do so surface a notification.
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "open_project", "Open"),
        Binding("n", "new_project", "New"),
        Binding("r", "rename_project", "Rename"),
        Binding("d", "delete_project", "Delete"),
        Binding("s", "search", "Search"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """
        Lay out header, project table, and footer.
        """
        yield Header()
        table: DataTable[str] = DataTable(id="project-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield Footer()

    def on_mount(self) -> None:
        """
        Configure the table columns and load the initial rows.
        """
        table = self.query_one("#project-table", DataTable)
        table.add_columns("Name", "Tasks")
        self.refresh_projects()
        table.focus()

    def refresh_projects(self) -> None:
        """
        Rebuild the project table from the database.

        Opens a one-shot session via the app's :class:`CoreFactory`,
        re-queries the project list plus per-project task counts, and
        repopulates the :class:`DataTable` in place. The cursor lands
        on the first row so ``enter`` always opens something.
        """
        app = self._app
        table = self.query_one("#project-table", DataTable)
        table.clear()

        with app.core_factory() as session:
            projects = projects_service.list_projects(session)
            counts_stmt = select(Task.project_id, func.count()).group_by(
                Task.project_id
            )
            counts = {pid: count for pid, count in session.execute(counts_stmt).all()}
            for project in projects:
                table.add_row(
                    project.name,
                    str(counts.get(project.id, 0)),
                    key=project.id,
                )

        if table.row_count > 0:
            table.move_cursor(row=0)

    def _selected_project(self) -> tuple[str, str] | None:
        """
        Return ``(project_id, project_name)`` for the highlighted row.

        :returns: A tuple of the row's project id and display name, or
            ``None`` when the table is empty.
        """
        table = self.query_one("#project-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is None:
            return None
        project_id = str(row_key.value)
        name_cell = table.get_cell_at(Coordinate(table.cursor_coordinate.row, 0))
        return project_id, str(name_cell)

    def action_cursor_down(self) -> None:
        """
        Move the table cursor down one row.
        """
        self.query_one("#project-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        """
        Move the table cursor up one row.
        """
        self.query_one("#project-table", DataTable).action_cursor_up()

    def action_open_project(self) -> None:
        """
        Push the :class:`TaskListScreen` for the highlighted project.
        """
        from tasksquatch.tui.screens.task_list import TaskListScreen

        selected = self._selected_project()
        if selected is None:
            return
        project_id, project_name = selected
        self.app.push_screen(
            TaskListScreen(project_id=project_id, project_name=project_name)
        )

    def action_new_project(self) -> None:
        """
        Prompt for a new project name and create it.
        """

        def _on_submit(value: str | None) -> None:
            """
            Service-call callback for the prompt's dismissal.
            """
            if value is None:
                return
            stripped = value.strip()
            if not stripped:
                return
            try:
                with self._app.core_factory() as session:
                    projects_service.create_project(session, name=stripped)
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_projects()

        self.app.push_screen(
            TextPromptScreen(title="New project", placeholder="Name"),
            _on_submit,
        )

    def action_rename_project(self) -> None:
        """
        Prompt for a new name and rename the highlighted project.
        """
        selected = self._selected_project()
        if selected is None:
            return
        project_id, current_name = selected

        def _on_submit(value: str | None) -> None:
            """
            Service-call callback for the rename prompt.
            """
            if value is None:
                return
            stripped = value.strip()
            if not stripped:
                return
            try:
                with self._app.core_factory() as session:
                    projects_service.rename_project(session, project_id, stripped)
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_projects()

        self.app.push_screen(
            TextPromptScreen(title="Rename project", initial=current_name),
            _on_submit,
        )

    def action_delete_project(self) -> None:
        """
        Ask for confirmation and delete the highlighted project.
        """
        selected = self._selected_project()
        if selected is None:
            return
        project_id, current_name = selected

        def _on_confirm(confirmed: bool | None) -> None:
            """
            Service-call callback for the delete confirmation.
            """
            if not confirmed:
                return
            try:
                with self._app.core_factory() as session:
                    projects_service.delete_project(session, project_id)
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_projects()

        self.app.push_screen(
            ConfirmScreen(prompt=f"Delete project {current_name!r}?"),
            _on_confirm,
        )

    def action_search(self) -> None:
        """
        Push the global :class:`SearchScreen`.
        """
        from tasksquatch.tui.screens.search import SearchScreen

        def _on_dismiss(_result: None) -> None:
            """
            Refresh on return so any mutations performed via the search
            drill-down are reflected in the project task counts.
            """
            self.refresh_projects()

        self.app.push_screen(SearchScreen(), _on_dismiss)

    def action_quit(self) -> None:
        """
        Exit the app.
        """
        self.app.exit()

    @property
    def _app(self) -> TasksquatchTuiApp:
        """
        Return the running app, typed for editor + mypy clarity.
        """
        from tasksquatch.tui.app import TasksquatchTuiApp

        app = self.app
        assert isinstance(app, TasksquatchTuiApp)
        return app
