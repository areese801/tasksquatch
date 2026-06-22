"""
Permission-guard tests for the tasksquatch MCP surface.

These tests pin the spec §11 invariant: the MCP cannot delete tasks,
projects, or labels. They exercise :func:`ensure_allowed` directly so
the guard is verified independently of the tool registration table.
"""

from __future__ import annotations

import pytest

from tasksquatch.mcp._guard import ensure_allowed


@pytest.mark.parametrize(
    "denied",
    ["delete_task", "delete_project", "delete_label"],
)
def test_entity_deletion_is_denied(denied: str) -> None:
    """
    The three entity-delete tool names must always raise.
    """
    with pytest.raises(PermissionError, match="entity deletion is reserved"):
        ensure_allowed(denied)


@pytest.mark.parametrize(
    "allowed",
    [
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
    ],
)
def test_known_tools_pass(allowed: str) -> None:
    """
    Every tool listed in the spec §11 envelope must clear the guard.
    """
    ensure_allowed(allowed)


def test_unknown_tool_is_rejected() -> None:
    """
    A name that is neither denied nor allowed is rejected as unknown.
    """
    with pytest.raises(PermissionError, match="Unknown MCP tool"):
        ensure_allowed("something_made_up")


def test_comment_delete_is_allowed() -> None:
    """
    The one destructive operation permitted on the MCP surface is
    comment deletion; it must pass cleanly.
    """
    ensure_allowed("delete_comment")
