"""
Registration tests for the tasksquatch MCP server.

These tests assert that the MCP advertises exactly the spec §11 tool
set — every allowed name is present, and no deletion tool slips
through.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.types import ListToolsRequest

from tasksquatch.mcp._guard import ALLOWED_TOOLS, DENIED_PATTERNS
from tasksquatch.mcp._session import CoreContext
from tasksquatch.mcp.server import build_server
from tasksquatch.mcp.tools import JSON_SCHEMAS, TOOL_HANDLERS


def _list_registered_tools(core: CoreContext) -> Any:
    """
    Drive the server's registered ``tools/list`` handler and return
    its ``ServerResult``.

    The MCP SDK exposes the handler via ``server.request_handlers``;
    invoking it directly avoids spinning up the stdio transport just
    to verify the registration table.

    :param core: The MCP context used to build the server.
    :returns: The ``ServerResult`` wrapping the ``ListToolsResult``.
    """
    server = build_server(core)
    handler = next(
        h for cls, h in server.request_handlers.items() if cls is ListToolsRequest
    )

    async def _invoke() -> Any:
        return await handler(ListToolsRequest(method="tools/list"))

    return asyncio.run(_invoke())


def test_handler_table_matches_schema_table() -> None:
    """
    Every handler must have a JSON schema and vice versa.
    """
    assert set(TOOL_HANDLERS) == set(JSON_SCHEMAS)


def test_handler_table_matches_allowed_tools() -> None:
    """
    The dispatch table must be exactly the spec-blessed allow-list.
    """
    assert set(TOOL_HANDLERS) == set(ALLOWED_TOOLS)


def test_reschedule_overdue_tasks_is_registered() -> None:
    """
    The :func:`reschedule_overdue` MCP tool must be both registered
    and allow-listed. The handler-table-vs-allow-list assertion
    covers consistency in general, but pinning the name explicitly
    catches accidental rename regressions.
    """
    assert "reschedule_overdue_tasks" in TOOL_HANDLERS
    assert "reschedule_overdue_tasks" in JSON_SCHEMAS
    assert "reschedule_overdue_tasks" in ALLOWED_TOOLS


def test_no_delete_tools_registered() -> None:
    """
    The three denied tool names must never appear in the dispatch
    table.
    """
    for pattern in DENIED_PATTERNS:
        assert pattern not in TOOL_HANDLERS
        assert pattern not in JSON_SCHEMAS


def test_build_server_registers_every_tool(core: CoreContext) -> None:
    """
    Constructing the :class:`Server` and listing tools must surface
    every entry in :data:`TOOL_HANDLERS`.
    """
    result = _list_registered_tools(core)
    listed = {tool.name for tool in result.root.tools}
    assert listed == set(TOOL_HANDLERS)


def test_listed_tools_carry_descriptions(core: CoreContext) -> None:
    """
    Every registered tool must surface a non-empty description so the
    LLM has a hint about what each tool does.
    """
    result = _list_registered_tools(core)
    for tool in result.root.tools:
        assert tool.description, f"Tool {tool.name} has no description"
        assert tool.inputSchema is not None
