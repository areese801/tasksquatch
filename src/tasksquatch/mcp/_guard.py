"""
Defensive allow-list for tasksquatch MCP tools.

Per ``docs/spec.md`` §11 the MCP surface deliberately has a smaller
permission envelope than the CLI and TUI. It may create, read, update,
complete, uncomplete, comment, and edit/delete its own comments — but
it **may not delete tasks, projects, or labels**. Destructive deletion
of those entities is reserved for the CLI and TUI surfaces so the
human is always in the loop for irreversible operations.

This module enforces that policy independently of the tool dispatch
table in :mod:`tasksquatch.mcp.tools`. Even if a future change
accidentally registers a ``delete_task`` tool, the guard will reject
the call before it reaches a handler.
"""

from __future__ import annotations

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "add_task",
        "update_task",
        "complete_task",
        "uncomplete_task",
        "list_tasks",
        "get_task",
        "search_tasks",
        "add_comment",
        "edit_comment",
        "delete_comment",
        "add_label_to_task",
        "remove_label_from_task",
        "create_project",
        "create_label",
        "list_projects",
        "list_labels",
        "read_activity_log",
    }
)

DENIED_PATTERNS: tuple[str, ...] = (
    "delete_task",
    "delete_project",
    "delete_label",
)


def ensure_allowed(tool_name: str) -> None:
    """
    Validate that ``tool_name`` is permitted on the MCP surface.

    The deny check runs first so a name that somehow shows up in both
    the deny list and the allow list still fails — the policy is the
    source of truth, not the registration table.

    :param tool_name: The MCP tool name about to be dispatched.
    :raises PermissionError: If the tool is explicitly denied
        (entity deletion) or is not in :data:`ALLOWED_TOOLS`.
    """
    if any(pattern == tool_name for pattern in DENIED_PATTERNS):
        raise PermissionError(
            f"MCP cannot {tool_name}: entity deletion is reserved for "
            f"CLI/TUI per spec §11."
        )
    if tool_name not in ALLOWED_TOOLS:
        raise PermissionError(f"Unknown MCP tool: {tool_name}")
