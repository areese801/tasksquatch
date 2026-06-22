"""
Task detail screen for the tasksquatch TUI.

The :class:`TaskDetailScreen` shows the full read view of a single task
— header, metadata block, description, subtasks, and comments — and
exposes the per-task mutations (edit, comment, complete, uncomplete,
delete) as one-key bindings. Mutations open the corresponding modal
(comment prompt, edit form, delete confirmation) and re-query the
database on dismissal so the view stays in sync.

The screen is intentionally read-heavy; every actual write goes through
``tasksquatch.core.services`` via the per-action factory the app owns,
which keeps the surface compatible with the rest of the TUI even when
tests bind their own SQLAlchemy session factory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Markdown, Static

from tasksquatch.core.errors import TasksquatchError
from tasksquatch.core.services import comments as comments_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service
from tasksquatch.tui.screens._prompts import ConfirmScreen, TextPromptScreen

if TYPE_CHECKING:
    from tasksquatch.tui.app import TasksquatchTuiApp


@dataclass(frozen=True)
class _TaskSnapshot:
    """
    Display-ready snapshot of a task and its surroundings.

    Holding pre-rendered strings on a dataclass keeps the render path
    decoupled from the SQLAlchemy session that produced the data — by
    the time the widgets read from the snapshot, the session has been
    closed.
    """

    task_id: str
    number: int
    title: str
    project_name: str
    completed: bool
    priority: str
    due: str
    recurrence: str
    recurrence_anchor: str
    parent: str
    labels: str
    description: str
    subtasks: list[tuple[str, int, str, bool]]
    comments: list[tuple[str, str]]


class TaskDetailScreen(Screen[None]):
    """
    Read view for a single task, with per-task mutation bindings.

    Composes a header, a metadata pane, a rendered Markdown description,
    a subtasks :class:`DataTable`, and a comments :class:`DataTable`.
    Bindings cover edit (``e``), comment (``c``), complete (``d``),
    uncomplete (``u``), and delete (``x``); pressing ``enter`` on a
    subtask row pushes another :class:`TaskDetailScreen` for that
    child.
    """

    BINDINGS = [
        Binding("e", "edit_task", "Edit"),
        Binding("c", "comment_task", "Comment"),
        Binding("d", "complete_task", "Done"),
        Binding("u", "uncomplete_task", "Undo"),
        Binding("x", "delete_task", "Delete"),
        Binding("enter", "open_subtask", "Open"),
        Binding("escape", "pop_screen", "Back", show=False),
        Binding("q", "pop_screen", "Back"),
    ]

    def __init__(self, task_id: str) -> None:
        """
        :param task_id: UUIDv7 string id of the task to display.
        """
        super().__init__()
        self._task_id = task_id
        self._snapshot: _TaskSnapshot | None = None

    def compose(self) -> ComposeResult:
        """
        Lay out the header, body container, and footer.
        """
        yield Header()
        with Vertical(id="detail-body"):
            yield Static("", id="detail-title")
            yield Static("", id="detail-meta")
            yield Markdown("", id="detail-description")
            yield Static("Subtasks", id="detail-subtasks-label")
            subtasks: DataTable[str] = DataTable(id="detail-subtasks")
            subtasks.cursor_type = "row"
            subtasks.zebra_stripes = True
            yield subtasks
            yield Static("Comments", id="detail-comments-label")
            comments: DataTable[str] = DataTable(id="detail-comments")
            comments.cursor_type = "row"
            comments.zebra_stripes = True
            yield comments
        yield Footer()

    def on_mount(self) -> None:
        """
        Configure tables and load the initial snapshot.
        """
        subtasks = self.query_one("#detail-subtasks", DataTable)
        subtasks.add_columns("#", "Title", "Done")
        comments = self.query_one("#detail-comments", DataTable)
        comments.add_columns("When", "Body")
        self.refresh_detail()

    def refresh_detail(self) -> None:
        """
        Reload the task, subtasks, and comments from the database.

        Pulls a fresh snapshot through the app's :class:`CoreFactory`
        and rewrites the static widgets and tables in place. Called on
        first mount and after every mutation (edit, comment, complete,
        uncomplete) so the view always reflects the persisted state.
        """
        snapshot = self._load_snapshot()
        self._snapshot = snapshot

        title_widget = self.query_one("#detail-title", Static)
        marker = "[x] " if snapshot.completed else "[ ] "
        title_widget.update(
            f"{marker}#{snapshot.number} {snapshot.title}  ({snapshot.project_name})"
        )

        meta_widget = self.query_one("#detail-meta", Static)
        meta_widget.update(
            "\n".join(
                [
                    f"Priority: {snapshot.priority}",
                    f"Due: {snapshot.due}",
                    f"Recurrence: {snapshot.recurrence} ({snapshot.recurrence_anchor})",
                    f"Parent: {snapshot.parent}",
                    f"Labels: {snapshot.labels}",
                ]
            )
        )

        description_widget = self.query_one("#detail-description", Markdown)
        description_widget.update(snapshot.description)

        subtasks_table = self.query_one("#detail-subtasks", DataTable)
        subtasks_table.clear()
        for sub_id, number, title, completed in snapshot.subtasks:
            marker = "[x]" if completed else "[ ]"
            subtasks_table.add_row(f"#{number}", title, marker, key=sub_id)

        comments_table = self.query_one("#detail-comments", DataTable)
        comments_table.clear()
        for created_at, preview in snapshot.comments:
            comments_table.add_row(created_at, preview)

    def _load_snapshot(self) -> _TaskSnapshot:
        """
        Open a session and build a :class:`_TaskSnapshot` for the task.

        :returns: A fully rendered :class:`_TaskSnapshot`.
        :raises NotFoundError: If the task no longer exists.
        """
        with self._app.core_factory() as session:
            task = queries_service.get_task_by_id(session, self._task_id)
            project_name = task.project.name
            parent_label = "-"
            if task.parent_id is not None:
                parent = queries_service.get_task_by_id(session, task.parent_id)
                parent_label = f"#{parent.number} {parent.title}"
            label_names = sorted(label.name for label in task.labels)
            labels_text = ", ".join(label_names) if label_names else "-"
            if task.due_date is None:
                due_text = "-"
            elif task.due_time is None:
                due_text = task.due_date.isoformat()
            else:
                due_text = f"{task.due_date.isoformat()} {task.due_time.isoformat()}"
            recurrence_text = task.recurrence if task.recurrence else "-"
            anchor_text = task.recurrence_anchor.value
            description_text = (
                task.description if task.description else "_(no description)_"
            )

            subtask_rows: list[tuple[str, int, str, bool]] = []
            for sub in queries_service.list_subtasks(
                session, self._task_id, recursive=False
            ):
                subtask_rows.append((sub.id, sub.number, sub.title, sub.completed))

            comment_rows: list[tuple[str, str]] = []
            for comment in queries_service.list_comments(session, self._task_id):
                created_at = comment.created_at.isoformat(timespec="seconds")
                preview = comment.body.replace("\n", " ")
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                comment_rows.append((created_at, preview))

            return _TaskSnapshot(
                task_id=task.id,
                number=task.number,
                title=task.title,
                project_name=project_name,
                completed=task.completed,
                priority=task.priority.value,
                due=due_text,
                recurrence=recurrence_text,
                recurrence_anchor=anchor_text,
                parent=parent_label,
                labels=labels_text,
                description=description_text,
                subtasks=subtask_rows,
                comments=comment_rows,
            )

    def action_edit_task(self) -> None:
        """
        Open the :class:`TaskEditScreen` for this task and refresh on
        dismissal.
        """
        from tasksquatch.tui.screens.task_edit import TaskEditScreen

        def _on_edit_done(_result: str | None) -> None:
            """
            Refresh the detail view after the edit modal closes.
            """
            self.refresh_detail()

        self.app.push_screen(
            TaskEditScreen(task_id=self._task_id),
            _on_edit_done,
        )

    def action_comment_task(self) -> None:
        """
        Prompt for a comment body and attach it to this task.
        """

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
                        session,
                        task_id=self._task_id,
                        body=stripped,
                    )
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.refresh_detail()

        self.app.push_screen(
            TextPromptScreen(title="New comment", placeholder="Body"),
            _on_submit,
        )

    def action_complete_task(self) -> None:
        """
        Mark this task complete via the service layer.
        """
        try:
            with self._app.core_factory() as session:
                tasks_service.complete_task(session, self._task_id)
        except TasksquatchError as err:
            self.notify(err.message, severity="warning")
            return
        self.refresh_detail()

    def action_uncomplete_task(self) -> None:
        """
        Reopen this task via the service layer.
        """
        try:
            with self._app.core_factory() as session:
                tasks_service.uncomplete_task(session, self._task_id)
        except TasksquatchError as err:
            self.notify(err.message, severity="warning")
            return
        self.refresh_detail()

    def action_delete_task(self) -> None:
        """
        Confirm and hard-delete this task; pop the screen on success.
        """

        def _on_confirm(confirmed: bool | None) -> None:
            """
            Service-call callback for the delete confirmation.
            """
            if not confirmed:
                return
            try:
                with self._app.core_factory() as session:
                    tasks_service.delete_task(session, self._task_id)
            except TasksquatchError as err:
                self.notify(err.message, severity="warning")
                return
            self.app.pop_screen()

        self.app.push_screen(
            ConfirmScreen(prompt="Delete task and all subtasks/comments?"),
            _on_confirm,
        )

    def action_open_subtask(self) -> None:
        """
        Push a fresh :class:`TaskDetailScreen` for the highlighted
        subtask row.

        Does nothing when the focus is not on the subtasks table or
        when the table is empty.
        """
        table = self.query_one("#detail-subtasks", DataTable)
        if not table.has_focus or table.row_count == 0:
            return
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        if row_key.value is None:
            return
        self.app.push_screen(TaskDetailScreen(task_id=str(row_key.value)))

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
