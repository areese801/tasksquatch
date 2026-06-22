"""
tasksquatch MCP stdio server entry point.

This module wires the in-process ``core`` library to the MCP stdio
transport. It is launched as the ``tasksquatch-mcp`` console script by
Claude Code (and any other MCP client) so the LLM can drive the
tracker via the tool surface declared in :mod:`tasksquatch.mcp.tools`.

The server is intentionally minimal: one :class:`CoreContext` is built
at startup (so DB-path or migration errors surface immediately rather
than on the first tool call), the registered handlers dispatch through
:data:`TOOL_HANDLERS`, and every domain failure is rendered to the
client as a single :class:`TextContent` carrying a JSON error envelope.

The server never imports any other surface (CLI, REST, TUI) — it talks
directly to ``tasksquatch.core``.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import mcp.server.stdio
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.types import TextContent, Tool

from tasksquatch import __version__
from tasksquatch.core.errors import TasksquatchError
from tasksquatch.mcp._guard import ensure_allowed
from tasksquatch.mcp._session import CoreContext, build_core
from tasksquatch.mcp.tools import JSON_SCHEMAS, TOOL_HANDLERS

_ENV_DB_VAR = "TASKSQUATCH_DB"


def _tool_description(name: str) -> str:
    """
    Return the short description used to advertise a tool to clients.

    Pulled from the first non-empty line of the handler's docstring so
    the public-facing description never drifts from what is documented
    in the source.

    :param name: The tool name registered in :data:`TOOL_HANDLERS`.
    :returns: A single-line description.
    """
    handler = TOOL_HANDLERS[name]
    doc = (handler.__doc__ or "").strip()
    if not doc:
        return name
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return name


def _build_tools() -> list[Tool]:
    """
    Construct the list of :class:`Tool` definitions exposed by the
    server.

    The list mirrors :data:`JSON_SCHEMAS` in iteration order; each tool
    name must have a matching entry in :data:`TOOL_HANDLERS`.

    :returns: A list of :class:`Tool` objects for ``tools/list``.
    """
    tools: list[Tool] = []
    for name, schema in JSON_SCHEMAS.items():
        tools.append(
            Tool(
                name=name,
                description=_tool_description(name),
                inputSchema=schema,
            )
        )
    return tools


def _error_payload(exc: TasksquatchError) -> dict[str, Any]:
    """
    Render a :class:`TasksquatchError` to a JSON-safe error envelope.

    :param exc: The domain exception to render.
    :returns: A dict with ``error``, ``code``, and ``details`` keys.
    """
    return {
        "error": exc.message,
        "code": exc.__class__.__name__,
        "details": exc.detail or {},
    }


def build_server(core: CoreContext) -> Server[Any, Any]:
    """
    Construct the configured :class:`Server` bound to a core context.

    Registers a ``tools/list`` handler that returns the static tool
    list and a ``tools/call`` handler that dispatches through
    :func:`ensure_allowed` and :data:`TOOL_HANDLERS`. Domain errors are
    caught and serialized as JSON so the MCP client receives a
    structured failure rather than a transport exception.

    :param core: The :class:`CoreContext` shared across tool calls.
    :returns: A ready-to-run :class:`Server`.
    """
    server: Server[Any, Any] = Server("tasksquatch")
    tools = _build_tools()

    # The MCP SDK's decorator factories return untyped callables;
    # silence mypy here so the rest of the module can stay strict.
    @server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
    async def _list_tools() -> list[Tool]:
        return tools

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> list[TextContent]:
        try:
            ensure_allowed(name)
            handler = TOOL_HANDLERS[name]
            result = handler(core, **arguments)
        except TasksquatchError as exc:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(_error_payload(exc)),
                )
            ]
        except PermissionError as exc:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": str(exc),
                            "code": "PermissionError",
                            "details": {},
                        }
                    ),
                )
            ]
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server


async def _serve(server: Server[Any, Any]) -> None:
    """
    Run the MCP server on stdio until the client disconnects.

    :param server: The :class:`Server` returned by :func:`build_server`.
    """
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="tasksquatch",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    """
    Console-script entry point for ``tasksquatch-mcp``.

    Resolves the SQLite path from the ``TASKSQUATCH_DB`` environment
    variable (or the standard XDG fallback), eagerly builds the core
    context so any DB or schema error fails fast, constructs the
    server, and then drives it via :func:`asyncio.run` on the stdio
    transport.
    """
    db_override = os.environ.get(_ENV_DB_VAR)
    core = build_core(db_override)
    server = build_server(core)
    asyncio.run(_serve(server))
