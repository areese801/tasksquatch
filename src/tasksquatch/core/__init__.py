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
from tasksquatch.core.ids import allocate_task_number, new_id
from tasksquatch.core.paths import get_db_path, get_default_db_path

__all__ = [
    "Base",
    "TaskNumberSeq",
    "allocate_task_number",
    "create_engine_for_path",
    "create_session_factory",
    "get_db_path",
    "get_default_db_path",
    "get_default_engine",
    "get_default_session_factory",
    "init_schema",
    "new_id",
    "session_scope",
]
