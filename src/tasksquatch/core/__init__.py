"""
tasksquatch core: data model and in-process business logic.

Every surface (CLI, TUI, REST, MCP, notify) imports from this package
and from this package only. ``core`` itself imports nothing from any
surface.
"""

from __future__ import annotations

from tasksquatch.core.db import (
    Base,
    TaskNumberSeq,
    create_engine_for_path,
    create_session_factory,
    get_default_engine,
    get_default_session_factory,
    init_schema,
    session_scope,
)
from tasksquatch.core.errors import (
    AlreadyCompletedError,
    ConcurrencyError,
    InboxProtectedError,
    NotFoundError,
    ProjectNotEmptyError,
    RecurrenceError,
    TasksquatchError,
    ValidationError,
)
from tasksquatch.core.ids import allocate_task_number, new_id
from tasksquatch.core.models import (
    ActivityEventType,
    ActivityLog,
    Comment,
    Label,
    Priority,
    Project,
    RecurrenceAnchor,
    Task,
    task_label,
)
from tasksquatch.core.paths import get_db_path, get_default_db_path
from tasksquatch.core.recurrence import next_occurrence, parse_rrule
from tasksquatch.core.seed import INBOX_NAME, ensure_inbox
from tasksquatch.core.services.activity import emit
from tasksquatch.core.services.labels import (
    create_label,
    delete_label,
    list_labels,
    rename_label,
)
from tasksquatch.core.services.projects import (
    create_project,
    delete_project,
    list_projects,
    move_project,
    rename_project,
)

__all__ = [
    "INBOX_NAME",
    "ActivityEventType",
    "ActivityLog",
    "AlreadyCompletedError",
    "Base",
    "Comment",
    "ConcurrencyError",
    "InboxProtectedError",
    "Label",
    "NotFoundError",
    "Priority",
    "Project",
    "ProjectNotEmptyError",
    "RecurrenceAnchor",
    "RecurrenceError",
    "Task",
    "TaskNumberSeq",
    "TasksquatchError",
    "ValidationError",
    "allocate_task_number",
    "create_engine_for_path",
    "create_label",
    "create_project",
    "create_session_factory",
    "delete_label",
    "delete_project",
    "emit",
    "ensure_inbox",
    "get_db_path",
    "get_default_db_path",
    "get_default_engine",
    "get_default_session_factory",
    "init_schema",
    "list_labels",
    "list_projects",
    "move_project",
    "new_id",
    "next_occurrence",
    "parse_rrule",
    "rename_label",
    "rename_project",
    "session_scope",
    "task_label",
]
