"""
Global fuzzy search screen for the tasksquatch TUI.

The :class:`SearchScreen` lets the user fuzzy-search every task in the
database, across projects and parent boundaries, by title (plus the
project name and any attached labels as part of the haystack). Hitting
``enter`` on a result row drills into the :class:`TaskDetailScreen`
for that task.

Search is in-process: every task is loaded once on mount, cached as a
list of ``(task_id, haystack)`` pairs, and re-ranked on every
keystroke via :func:`fuzzy_score`. The cache size is bounded by the
total task count, which is fine for v1's single-user, local-only
workload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from tasksquatch.core import UNSET
from tasksquatch.core.services import queries as queries_service
from tasksquatch.tui.screens.task_detail import TaskDetailScreen
from tasksquatch.tui.widgets.fuzzy_filter import (
    FilterChanged,
    FilterInput,
    fuzzy_score,
)

if TYPE_CHECKING:
    from tasksquatch.tui.app import TasksquatchTuiApp


_RESULT_LIMIT = 50


@dataclass(frozen=True)
class _SearchRow:
    """
    Pre-rendered search row.

    Pre-rendered cell strings plus a search ``haystack`` keep the
    per-keystroke re-rank loop allocation-light, and stay decoupled
    from the SQLAlchemy session that built them.
    """

    task_id: str
    number: int
    title: str
    project: str
    labels: str
    completed: bool
    haystack: str


class SearchScreen(Screen[None]):
    """
    Global fuzzy search across every task in the database.

    Composes a :class:`FilterInput` over a :class:`DataTable`. On
    mount the screen pulls every task through
    :func:`queries.list_tasks` with ``parent_id=UNSET`` (so both
    top-level tasks and subtasks are included) and caches the rendered
    rows. Filter changes re-rank the cache via :func:`fuzzy_score` and
    paint the top fifty matches.
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "open_task", "Open"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("escape", "escape", "Back", show=False),
        Binding("q", "pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        """
        Initialize the screen.

        The cache is populated in :meth:`on_mount`; the constructor
        sets up the empty state so the test harness can push the
        screen without paying for a database round trip up front.
        """
        super().__init__()
        self._rows: list[_SearchRow] = []
        self._filter_query = ""

    def compose(self) -> ComposeResult:
        """
        Lay out the header, filter input, results table, and footer.
        """
        yield Header()
        yield FilterInput(id="search-filter")
        table: DataTable[str] = DataTable(id="search-table")
        table.cursor_type = "row"
        table.zebra_stripes = True
        yield table
        yield Footer()

    def on_mount(self) -> None:
        """
        Populate the cache and render the initial results.
        """
        table = self.query_one("#search-table", DataTable)
        table.add_columns("#", "Title", "Project", "Labels")
        self._load_rows()
        self._apply_filter()
        self.query_one("#search-filter", FilterInput).focus()

    def _load_rows(self) -> None:
        """
        Reload every task from the database into the row cache.
        """
        rows: list[_SearchRow] = []
        with self._app.core_factory() as session:
            tasks = queries_service.list_tasks(session, parent_id=UNSET)
            for task in tasks:
                label_names = sorted(label.name for label in task.labels)
                labels_csv = ", ".join(label_names)
                title_display = (
                    task.title if not task.completed else f"\u2713 {task.title}"
                )
                haystack = " ".join([task.title, task.project.name, labels_csv]).strip()
                rows.append(
                    _SearchRow(
                        task_id=task.id,
                        number=task.number,
                        title=title_display,
                        project=task.project.name,
                        labels=labels_csv,
                        completed=task.completed,
                        haystack=haystack,
                    )
                )
        self._rows = rows

    def _apply_filter(self) -> None:
        """
        Re-rank the cached rows by fuzzy score and re-render the
        table.

        An empty query paints the first :data:`_RESULT_LIMIT` rows in
        their natural order. Any non-empty query runs the rows through
        :func:`fuzzy_score` and paints the highest-scoring 50.
        """
        table = self.query_one("#search-table", DataTable)
        table.clear()

        if not self._filter_query.strip():
            visible = self._rows[:_RESULT_LIMIT]
        else:
            scored = fuzzy_score(
                self._filter_query,
                (row.haystack for row in self._rows),
            )
            visible = [self._rows[idx] for idx, _ in scored[:_RESULT_LIMIT]]

        for row in visible:
            table.add_row(
                f"#{row.number}",
                row.title,
                row.project,
                row.labels,
                key=row.task_id,
            )

        if table.row_count > 0:
            table.move_cursor(row=0)

    def on_filter_changed(self, message: FilterChanged) -> None:
        """
        Handle a filter-text change from the :class:`FilterInput`.

        :param message: The bubbled change message.
        """
        message.stop()
        self._filter_query = message.query
        self._apply_filter()

    def action_cursor_down(self) -> None:
        """
        Move the results table cursor down.
        """
        self.query_one("#search-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        """
        Move the results table cursor up.
        """
        self.query_one("#search-table", DataTable).action_cursor_up()

    def action_open_task(self) -> None:
        """
        Push :class:`TaskDetailScreen` for the highlighted result row.

        Does nothing when the results table is empty.
        """
        self._open_selected()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """
        Open the detail screen when the user activates a row.

        When focus is on the table the ``enter`` keypress is consumed
        by the :class:`DataTable` before our screen-level binding sees
        it, so we hook the resulting ``RowSelected`` event here to keep
        the keystroke working from either focus position.
        """
        if event.data_table.id != "search-table":
            return
        event.stop()
        self._open_selected()

    def _open_selected(self) -> None:
        """
        Common helper that pushes :class:`TaskDetailScreen` for the
        highlighted row, or does nothing when there is no row.
        """
        table = self.query_one("#search-table", DataTable)
        if table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is None:
            return
        self.app.push_screen(TaskDetailScreen(task_id=str(row_key.value)))

    def action_focus_filter(self) -> None:
        """
        Move keyboard focus to the filter input.
        """
        self.query_one("#search-filter", FilterInput).focus()

    def action_escape(self) -> None:
        """
        ``escape`` semantics: clear the filter or pop the screen.

        If the filter input is focused and has content, clear it.
        Otherwise pop back to the previous screen.
        """
        filter_input = self.query_one("#search-filter", FilterInput)
        if filter_input.has_focus:
            if filter_input.value:
                filter_input.value = ""
            else:
                self.query_one("#search-table", DataTable).focus()
            return
        self.app.pop_screen()

    def action_pop_screen(self) -> None:
        """
        Pop back to the previous screen.
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
