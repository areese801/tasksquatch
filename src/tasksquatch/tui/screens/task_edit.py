"""
Task create / edit modal for the tasksquatch TUI.

The :class:`TaskEditScreen` is a dual-mode form. Constructed with
``task_id=None`` it creates a brand-new task (defaulting the project
and parent to the constructor arguments); constructed with a
``task_id`` it loads that task and lets the user mutate every editable
field. Save dismisses with the task id; Cancel dismisses with
``None``.

Project changes are intentionally not supported in edit mode — the
service layer's :func:`~tasksquatch.core.services.tasks.update_task`
does not accept ``project_id``; moving an existing task across
projects goes through :func:`~tasksquatch.core.services.tasks.move_task`
and is reserved for the CLI in v1. The project ``Select`` is
disabled in edit mode so the user can see the current project but not
accidentally rebind it here.
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any

import typer
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static, TextArea

from tasksquatch.cli._parsers import parse_date, parse_time
from tasksquatch.core.errors import TasksquatchError, ValidationError
from tasksquatch.core.models import Priority, RecurrenceAnchor
from tasksquatch.core.services import labels as labels_service
from tasksquatch.core.services import projects as projects_service
from tasksquatch.core.services import queries as queries_service
from tasksquatch.core.services import tasks as tasks_service

if TYPE_CHECKING:
    from tasksquatch.tui.app import TasksquatchTuiApp


_PRIORITY_VALUES: tuple[Priority, ...] = (
    Priority.P1,
    Priority.P2,
    Priority.P3,
    Priority.P4,
)

_ANCHOR_VALUES: tuple[RecurrenceAnchor, ...] = (
    RecurrenceAnchor.FIXED,
    RecurrenceAnchor.RELATIVE,
)


class TaskEditScreen(ModalScreen[str | None]):
    """
    Modal form for creating or editing a task.

    Dismisses with the new (or updated) task's UUIDv7 id on Save and
    with ``None`` on Cancel. Validation failures (bad date, unknown
    label, empty title) surface as a ``self.notify(..., severity="error")``
    rather than crashing the screen, so the user can correct the input
    and resubmit.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "submit", "Save", show=False),
    ]

    def __init__(
        self,
        *,
        task_id: str | None = None,
        project_id: str | None = None,
        parent_id: str | None = None,
    ) -> None:
        """
        :param task_id: UUIDv7 id of the task to edit; ``None`` to
            create.
        :param project_id: Default destination project id when creating.
            Ignored in edit mode.
        :param parent_id: Optional parent task id when creating a
            subtask. Ignored in edit mode.
        """
        super().__init__()
        self._task_id = task_id
        self._project_id_default = project_id
        self._parent_id = parent_id
        self._initial_label_ids: set[str] = set()
        self._label_id_by_name: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        """
        Lay out the form fields and the Save / Cancel buttons.
        """
        with VerticalScroll(id="edit-body"):
            heading = "Edit task" if self._task_id is not None else "New task"
            yield Static(heading, id="edit-heading")
            yield Static("Title", classes="edit-label")
            yield Input(placeholder="Title (required)", id="edit-title")
            yield Static("Description", classes="edit-label")
            yield TextArea("", id="edit-description")
            yield Static("Project", classes="edit-label")
            yield Select(
                options=[("Inbox", "")],
                value="",
                allow_blank=False,
                id="edit-project",
                disabled=self._task_id is not None,
            )
            yield Static("Priority", classes="edit-label")
            yield Select(
                options=[(p.value, p.value) for p in _PRIORITY_VALUES],
                value=Priority.P4.value,
                allow_blank=False,
                id="edit-priority",
            )
            yield Static("Due date", classes="edit-label")
            yield Input(
                placeholder="YYYY-MM-DD or 'today'/'tomorrow' (empty to clear)",
                id="edit-due-date",
            )
            yield Static("Due time", classes="edit-label")
            yield Input(
                placeholder="HH:MM or empty",
                id="edit-due-time",
            )
            yield Static("Recurrence (RRULE)", classes="edit-label")
            yield Input(
                placeholder="FREQ=DAILY ... or empty",
                id="edit-recurrence",
            )
            yield Static("Recurrence anchor", classes="edit-label")
            yield Select(
                options=[(a.value, a.value) for a in _ANCHOR_VALUES],
                value=RecurrenceAnchor.FIXED.value,
                allow_blank=False,
                id="edit-anchor",
            )
            yield Static("Labels", classes="edit-label")
            yield Input(
                placeholder="comma-separated label names (empty to clear)",
                id="edit-labels",
            )
            yield Button("Save", variant="primary", id="edit-save")
            yield Button("Cancel", id="edit-cancel")

    def on_mount(self) -> None:
        """
        Populate the form fields from the database.

        Loads the project list, the label catalogue (so the labels
        input can resolve names to ids on submit), and — in edit mode —
        the existing task row to prefill every field.
        """
        with self._app.core_factory() as session:
            projects = projects_service.list_projects(session)
            labels = labels_service.list_labels(session)
            self._label_id_by_name = {label.name.lower(): label.id for label in labels}

            project_select = self.query_one("#edit-project", Select)
            options = [(project.name, project.id) for project in projects]
            project_select.set_options(options)

            if self._task_id is None:
                target_project_id = self._project_id_default or (
                    projects[0].id if projects else ""
                )
                if target_project_id:
                    project_select.value = target_project_id
                self.query_one("#edit-title", Input).focus()
                return

            task = queries_service.get_task_by_id(session, self._task_id)
            self.query_one("#edit-title", Input).value = task.title
            description_area = self.query_one("#edit-description", TextArea)
            description_area.load_text(task.description or "")
            project_select.value = task.project_id
            self.query_one("#edit-priority", Select).value = task.priority.value
            if task.due_date is not None:
                due_input = self.query_one("#edit-due-date", Input)
                due_input.value = task.due_date.isoformat()
            if task.due_time is not None:
                time_input = self.query_one("#edit-due-time", Input)
                time_input.value = task.due_time.strftime("%H:%M")
            if task.recurrence:
                self.query_one("#edit-recurrence", Input).value = task.recurrence
            anchor_select = self.query_one("#edit-anchor", Select)
            anchor_select.value = task.recurrence_anchor.value
            label_names = sorted(label.name for label in task.labels)
            self.query_one("#edit-labels", Input).value = ", ".join(label_names)
            self._initial_label_ids = {label.id for label in task.labels}
            self.query_one("#edit-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Dispatch Save / Cancel button presses.
        """
        event.stop()
        if event.button.id == "edit-save":
            self._submit()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """
        Dismiss with ``None`` on ``escape``.
        """
        self.dismiss(None)

    def action_submit(self) -> None:
        """
        Dispatch to :meth:`_submit` when the user fires the save
        hotkey.
        """
        self._submit()

    def _submit(self) -> None:
        """
        Validate inputs and dispatch to create / update services.

        Validation errors are surfaced via :meth:`Screen.notify` so the
        user can correct the offending field without losing the rest of
        the form.
        """
        title = self.query_one("#edit-title", Input).value.strip()
        if not title:
            self.notify("Title is required.", severity="error")
            return

        description_raw = self.query_one("#edit-description", TextArea).text
        description = description_raw if description_raw.strip() else None

        priority_value = self.query_one("#edit-priority", Select).value
        if not isinstance(priority_value, str):
            self.notify("Priority must be set.", severity="error")
            return
        priority = Priority(priority_value)

        due_date_raw = self.query_one("#edit-due-date", Input).value.strip()
        due_time_raw = self.query_one("#edit-due-time", Input).value.strip()
        recurrence_raw = self.query_one("#edit-recurrence", Input).value.strip()

        anchor_value = self.query_one("#edit-anchor", Select).value
        if not isinstance(anchor_value, str):
            self.notify("Recurrence anchor must be set.", severity="error")
            return
        anchor = RecurrenceAnchor(anchor_value)

        try:
            due_date = parse_date(due_date_raw) if due_date_raw else None
            due_time = parse_time(due_time_raw) if due_time_raw else None
        except typer.BadParameter as err:
            self.notify(str(err), severity="error")
            return

        recurrence = recurrence_raw if recurrence_raw else None

        labels_raw = self.query_one("#edit-labels", Input).value
        try:
            requested_label_ids = self._resolve_label_ids(labels_raw)
        except ValidationError as err:
            self.notify(err.message, severity="error")
            return

        project_id_value = self.query_one("#edit-project", Select).value
        if not isinstance(project_id_value, str) or not project_id_value:
            self.notify("Project must be selected.", severity="error")
            return

        if self._task_id is None:
            self._create(
                title=title,
                description=description,
                project_id=project_id_value,
                priority=priority,
                due_date=due_date,
                due_time=due_time,
                recurrence=recurrence,
                anchor=anchor,
                label_ids=requested_label_ids,
            )
            return

        self._update(
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
            due_time=due_time,
            recurrence=recurrence,
            anchor=anchor,
            requested_label_ids=requested_label_ids,
        )

    def _resolve_label_ids(self, labels_raw: str) -> list[str]:
        """
        Convert a comma-separated label name list into a list of ids.

        Whitespace and blank entries are tolerated. Unknown names raise
        :class:`ValidationError` so the caller can surface a precise
        error to the user.

        :param labels_raw: Raw labels-field value.
        :returns: The matching label ids, in input order with duplicates
            removed.
        :raises ValidationError: When a name does not match a known
            label.
        """
        if not labels_raw.strip():
            return []
        resolved: list[str] = []
        seen: set[str] = set()
        for raw_name in labels_raw.split(","):
            name = raw_name.strip()
            if not name:
                continue
            label_id = self._label_id_by_name.get(name.lower())
            if label_id is None:
                raise ValidationError(
                    f"Unknown label {name!r}.",
                    detail={"name": name},
                )
            if label_id in seen:
                continue
            seen.add(label_id)
            resolved.append(label_id)
        return resolved

    def _create(
        self,
        *,
        title: str,
        description: str | None,
        project_id: str,
        priority: Priority,
        due_date: date | None,
        due_time: time | None,
        recurrence: str | None,
        anchor: RecurrenceAnchor,
        label_ids: list[str],
    ) -> None:
        """
        Persist a new task and dismiss with its id.

        Service exceptions are caught and surfaced through
        :meth:`Screen.notify`; the modal stays open so the user can
        correct the input.
        """
        try:
            with self._app.core_factory() as session:
                task = tasks_service.create_task(
                    session,
                    title=title,
                    project_id=project_id,
                    parent_id=self._parent_id,
                    description=description,
                    priority=priority,
                    due_date=due_date,
                    due_time=due_time,
                    recurrence=recurrence,
                    recurrence_anchor=anchor,
                    label_ids=label_ids,
                )
                new_id = task.id
        except TasksquatchError as err:
            self.notify(err.message, severity="error")
            return
        self.dismiss(new_id)

    def _update(
        self,
        *,
        title: str,
        description: str | None,
        priority: Priority,
        due_date: date | None,
        due_time: time | None,
        recurrence: str | None,
        anchor: RecurrenceAnchor,
        requested_label_ids: list[str],
    ) -> None:
        """
        Persist edits to an existing task and dismiss with its id.

        Builds the keyword arguments to
        :func:`~tasksquatch.core.services.tasks.update_task` as a diff
        against the current row so unchanged fields are left at
        :data:`UNSET`. Walks the labels diff and issues ``add_label`` /
        ``remove_label`` calls. Service exceptions stay non-fatal — the
        modal remains open with a notification.
        """
        assert self._task_id is not None
        try:
            with self._app.core_factory() as session:
                task = queries_service.get_task_by_id(session, self._task_id)
                kwargs: dict[str, Any] = {}
                if task.title != title:
                    kwargs["title"] = title
                if task.description != description:
                    kwargs["description"] = description
                if task.priority != priority:
                    kwargs["priority"] = priority
                if task.due_date != due_date:
                    kwargs["due_date"] = due_date
                if task.due_time != due_time:
                    kwargs["due_time"] = due_time
                if task.recurrence != recurrence:
                    kwargs["recurrence"] = recurrence
                if task.recurrence_anchor != anchor:
                    kwargs["recurrence_anchor"] = anchor

                if kwargs:
                    tasks_service.update_task(session, self._task_id, **kwargs)

                requested = set(requested_label_ids)
                to_add = requested - self._initial_label_ids
                to_remove = self._initial_label_ids - requested
                for label_id in to_add:
                    tasks_service.add_label(session, self._task_id, label_id)
                for label_id in to_remove:
                    tasks_service.remove_label(session, self._task_id, label_id)
        except TasksquatchError as err:
            self.notify(err.message, severity="error")
            return
        self.dismiss(self._task_id)

    @property
    def _app(self) -> TasksquatchTuiApp:
        """
        Return the running app, typed for editor + mypy clarity.
        """
        from tasksquatch.tui.app import TasksquatchTuiApp

        app = self.app
        assert isinstance(app, TasksquatchTuiApp)
        return app
