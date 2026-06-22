"""
Task listing screen for a single project.

Composes a :class:`FilterInput` over a :class:`DataTable` that shows
the project's top-level tasks. Keystrokes drive complete / uncomplete
/ delete / comment / create / search / open-detail / edit actions;
the ``/`` key focuses the filter input, which fuzzy-filters the
displayed rows by title, project name, and attached label names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from tasksquatch.core import UNSET
from tasksquatch.core.errors import TasksquatchError
from tasksquatch.core.models import Task
from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.tui.screens._prompts import ConfirmScreen, TextPromptScreen
from tasksquatch.tui.screens.search import SearchScreen
from tasksquatch.tui.screens.task_detail import TaskDetailScreen
from tasksquatch.tui.screens.task_edit import TaskEditScreen
from tasksquatch.tui.widgets.fuzzy_filter import (
    FilterChanged,
    FilterInput,
    fuzzy_score,
)

if TYPE_CHECKING:
    from tasksquatch.tui.app import TasksquatchTuiApp


@dataclass(frozen=True)
class _TaskRow:
    """
    Pre-rendered task row used to populate the :class:`DataTable`.

    Holding the rendered strings (and a separate ``haystack`` for the
    fuzzy filter) on a dataclass keeps the filter / refresh paths
    decoupled from the SQLAlchemy session that produced the data.
    """

    task_id: str
    number: int
    title: str
    priority: str
    due: str
    labels: str
    completed: bool
    haystack: str


class TaskListScreen(Screen[None]):
    """
    Task listing screen for a single project.

    The screen owns a small in-memory cache of the project's tasks
    (:class:`_TaskRow` records) so that filtering does not need to
    re-query the database on every keystroke. Mutations refresh the
    cache before re-rendering.
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "open_task", "Open"),
        Binding("n", "new_task", "New"),
        Binding("d", "complete_task", "Done"),
        Binding("u", "uncomplete_task", "Undo"),
        Binding("e", "edit_task", "Edit"),
        Binding("x", "delete_task", "Delete"),
        Binding("c", "comment_task", "Comment"),
        Binding("s", "search", "Search"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("escape", "escape", "Back", show=False),
        Binding("q", "pop_screen", "Back"),
    ]

    def __init__(
        self,
        project_id: str,
        *,
        project_name: str = "",
    ) -> None:
        """
        :param project_id: UUIDv7 string id of the project to display.
        :param project_name: Name used to label the screen and as part
            of the fuzzy-filter haystack for each task row.
        """
        super().__init__()
        self._project_id = project_id
        self._project_name = project_name
        self._rows: list[_TaskRow] = []
        self._filter_query = ""

    def compose(self) -> ComposeResult:
        """
        Lay out the filter input, the task table, and the footer.
        """
        yield Header()
        yield FilterInput(id="task-filter")
        table: DataTable[str] = DataTable(id="task-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield Footer()

    def on_mount(self) -> None:
        """
        Configure the table columns and load the initial rows.

        Focuses the :class:`DataTable` rather than letting the
        :class:`FilterInput` auto-focus (Textual focuses the first
        focusable widget by default); the user explicitly opts into
        filtering via the ``/`` binding.
        """
        table = self.query_one("#task-table", DataTable)
        table.add_columns("#", "Title", "Priority", "Due", "Labels")
        self.refresh_tasks()
        table.focus()

    def refresh_tasks(self) -> None:
        """
        Reload tasks from the database and re-render the table.

        Top-level tasks only (``parent_id=None``); subtasks roll up into
        the parent's detail view in TSQ-26. The current filter query is
        re-applied after the fetch so a refresh after, e.g., completing
        a task keeps the user's narrowed view. The cursor is restored
        to the previously-selected task when the row survives the
        refresh so follow-up actions (``u`` after ``d``) keep working
        on the same task.
        """
        preserve_task_id = self._selected_task()
        app = self._app
        with app.core_factory() as session:
            tasks = queries_service.list_tasks(
                session,
                project_id=self._project_id,
                parent_id=UNSET,
            )
            self._rows = [self._render_row(task) for task in tasks]
        self._apply_filter(preserve_task_id=preserve_task_id)

    def _render_row(self, task: Task) -> _TaskRow:
        """
        Convert a :class:`Task` ORM row into a display-ready
        :class:`_TaskRow`.

        :param task: The task to render.
        :returns: A frozen dataclass containing the cell strings and
            the fuzzy-filter haystack.
        """
        label_names = sorted(label.name for label in task.labels)
        labels_csv = ", ".join(label_names)
        due_text: str
        if task.due_date is None:
            due_text = "-"
        elif task.due_time is None:
            due_text = task.due_date.isoformat()
        else:
            due_text = f"{task.due_date.isoformat()} {task.due_time.isoformat()}"
        title_display = task.title if not task.completed else f"\u2713 {task.title}"
        haystack = " ".join([task.title, self._project_name, labels_csv]).strip()
        return _TaskRow(
            task_id=task.id,
            number=task.number,
            title=title_display,
            priority=task.priority.value,
            due=due_text,
            labels=labels_csv,
            completed=task.completed,
            haystack=haystack,
        )

    def _apply_filter(self, *, preserve_task_id: str | None = None) -> None:
        """
        Re-render the table according to the current filter query.

        Calls :func:`fuzzy_score` against the cached row haystacks and
        rebuilds the :class:`DataTable` rows in place. An empty filter
        is a no-op fast path that preserves the natural row order.

        :param preserve_task_id: When supplied and still visible after
            the rebuild, the cursor is restored to that task's row. Used
            by :meth:`refresh_tasks` so an action like ``d`` followed
            by ``u`` keeps operating on the same row.
        """
        table = self.query_one("#task-table", DataTable)
        table.clear()

        if not self._filter_query.strip():
            visible = list(enumerate(self._rows))
        else:
            scored = fuzzy_score(
                self._filter_query,
                (row.haystack for row in self._rows),
            )
            visible = [(idx, self._rows[idx]) for idx, _ in scored]

        target_row: int = 0
        for visible_index, (_, row) in enumerate(visible):
            table.add_row(
                f"#{row.number}",
                row.title,
                row.priority,
                row.due,
                row.labels,
                key=row.task_id,
            )
            if preserve_task_id is not None and row.task_id == preserve_task_id:
                target_row = visible_index

        if table.row_count > 0:
            table.move_cursor(row=target_row)

    def on_filter_changed(self, message: FilterChanged) -> None:
        """
        Handle a filter-text change from the :class:`FilterInput`.

        :param message: The bubbled change message.
        """
        message.stop()
        self._filter_query = message.query
        self._apply_filter()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """
        Open the highlighted task when the user activates a row.

        The :class:`DataTable` emits :class:`DataTable.RowSelected` on
        ``enter`` (when the table has focus and ``cursor_type`` is
        ``"row"``). The ``enter`` binding alone is shadowed by the
        table's own key handling, so we re-dispatch through
        :meth:`action_open_task` from the event handler that the
        widget always delivers.

        :param event: The bubbled row-activation message.
        """
        event.stop()
        self.action_open_task()

    def _selected_task(self) -> str | None:
        """
        Return the UUIDv7 id of the highlighted row, or ``None``.

        :returns: The selected task id, or ``None`` when the table is
            empty.
        """
        table = self.query_one("#task-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is None:
            return None
        return str(row_key.value)

    def action_cursor_down(self) -> None:
        """
        Move the task table cursor down.
        """
        self.query_one("#task-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        """
        Move the task table cursor up.
        """
        self.query_one("#task-table", DataTable).action_cursor_up()

    def action_open_task(self) -> None:
        """
        Push :class:`TaskDetailScreen` for the highlighted row.
        """
        task_id = self._selected_task()
        if task_id is None:
            return

        def _on_dismiss(_result: None) -> None:
            """
            Refresh after the detail screen returns control.
            """
            self.refresh_tasks()

        self.app.push_screen(TaskDetailScreen(task_id=task_id), _on_dismiss)

    def action_edit_task(self) -> None:
        """
        Push :class:`TaskEditScreen` for the highlighted row.
        """
        task_id = self._selected_task()
        if task_id is None:
            return

        def _on_dismiss(_result: str | None) -> None:
            """
            Refresh on edit completion so the list reflects new values.
            """
            self.refresh_tasks()

        self.app.push_screen(TaskEditScreen(task_id=task_id), _on_dismiss)

    def action_new_task(self) -> None:
        """
        Push :class:`TaskEditScreen` in create mode for this project.
        """

        def _on_dismiss(_result: str | None) -> None:
            """
            Refresh on create completion so the new task appears.
            """
            self.refresh_tasks()

        self.app.push_screen(
            TaskEditScreen(project_id=self._project_id),
            _on_dismiss,
        )

    def action_search(self) -> None:
        """
        Push the global :class:`SearchScreen` and refresh on return.
        """

        def _on_dismiss(_result: None) -> None:
            """
            Refresh after the search screen returns control so any
            mutations performed via the detail drill-down are visible.
            """
            self.refresh_tasks()

        self.app.push_screen(SearchScreen(), _on_dismiss)

    def action_complete_task(self) -> None:
        """
        Mark the highlighted task complete.
        """
        task_id = self._selected_task()
        if task_id is None:
            return
        try:
            with self._app.core_factory() as session:
                tasks_service.complete_task(session, task_id)
        except TasksquatchError as err:
            self.notify(err.message, severity="warning")
            return
        self.refresh_tasks()

    def action_uncomplete_task(self) -> None:
        """
        Reopen the highlighted task.
        """
        task_id = self._selected_task()
        if task_id is None:
            return
        try:
            with self._app.core_factory() as session:
                tasks_service.uncomplete_task(session, task_id)
        except TasksquatchError as err:
            self.notify(err.message, severity="warning")
            return
        self.refresh_tasks()

    def action_delete_task(self) -> None:
        """
        Confirm and hard-delete the highlighted task.
        """
        task_id = self._selected_task()
        if task_id is None:
            return

        def _on_confirm(confirmed: bool | None) -> None:
            """
            Service-call callback for the delete confirmation.
            """
            if not confirmed:
                return
            try:
                with self._app.core_factory() as session:
                    tasks_service.delete_task(session, task_id)
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_tasks()

        self.app.push_screen(
            ConfirmScreen(prompt="Delete this task?"),
            _on_confirm,
        )

    def action_comment_task(self) -> None:
        """
        Prompt for a comment body and attach it to the highlighted task.
        """
        task_id = self._selected_task()
        if task_id is None:
            return

        def _on_submit(value: str | None) -> None:
            """
            Service-call callback for the comment prompt.
            """
            if value is None:
                return
            stripped = value.strip()
            if not stripped:
                return
            try:
                with self._app.core_factory() as session:
                    comments_service.add_comment(
                        session, task_id=task_id, body=stripped
                    )
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_tasks()

        self.app.push_screen(
            TextPromptScreen(title="New comment", placeholder="Body"),
            _on_submit,
        )

    def action_focus_filter(self) -> None:
        """
        Move keyboard focus to the filter input.
        """
        self.query_one("#task-filter", FilterInput).focus()

    def action_escape(self) -> None:
        """
        ``escape`` semantics: clear filter focus or pop the screen.

        If the filter is focused, clear it (so the user can keep typing
        afresh without leaving the screen). Otherwise pop back to the
        project list.
        """
        filter_input = self.query_one("#task-filter", FilterInput)
        if filter_input.has_focus:
            if filter_input.value:
                filter_input.value = ""
            else:
                self.query_one("#task-table", DataTable).focus()
            return
        self.app.pop_screen()

    def action_pop_screen(self) -> None:
        """
        Pop back to the project list.
        """
        self.app.pop_screen()

    @property
    def _app(self) -> TasksquatchTuiApp:
        """
        Return the running app, typed for editor + mypy clarity.
        """
        from tasksquatch.tui.app import TasksquatchTuiApp

        app = self.app
        assert isinstance(app, TasksquatchTuiApp)
        return app
