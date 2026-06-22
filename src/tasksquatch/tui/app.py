"""
Textual application root for the tasksquatch TUI.

The :class:`TasksquatchTuiApp` owns the long-lived
:class:`CoreFactory` that screens use to open per-action sessions
against the SQLite database. Surfaces (screens, widgets) never
construct sessions themselves — they reach for ``self.app.core_factory``
and let this module decide whether the session is backed by a real
engine or a test-injected fixture.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from tasksquatch.tui._session import CoreFactory, default_core_factory
from tasksquatch.tui.screens.project_list import ProjectListScreen


class TasksquatchTuiApp(App[None]):
    """
    Top-level Textual app for tasksquatch.

    Pushes :class:`ProjectListScreen` on mount and exposes the
    long-lived :attr:`core_factory` so child screens can open
    transactional sessions. The factory is injectable so tests can
    bind the app to a fixture-managed SQLite file without ever
    touching the user's real database.
    """

    CSS_PATH = None
    TITLE = "tasksquatch"

    def __init__(
        self,
        *,
        core_factory: CoreFactory | None = None,
        db_path: Path | None = None,
    ) -> None:
        """
        :param core_factory: Optional explicit :class:`CoreFactory`;
            tests pass a fixture-backed factory here so the app uses
            their database. When ``None``, a default factory is built
            against ``db_path``.
        :param db_path: Optional explicit DB path used only when
            ``core_factory`` is not supplied.
        """
        super().__init__()
        self.core_factory: CoreFactory = (
            core_factory if core_factory is not None else default_core_factory(db_path)
        )

    def on_mount(self) -> None:
        """
        Push the initial project list screen.
        """
        self.push_screen(ProjectListScreen())
