"""
Validation-error tests for the tasksquatch MCP tool handlers.

These tests exercise the unhappy paths — empty titles, malformed
RRULEs, missing task ids — and assert that the core's domain errors
propagate out of the tool handlers unchanged so the MCP server can
render them to the client as structured failures.
"""

from __future__ import annotations

import pytest

from tasksquatch.core.errors import (
    NotFoundError,
    RecurrenceError,
    ValidationError,
)
from tasksquatch.mcp._session import CoreContext
from tasksquatch.mcp.tools import (
    tool_add_task,
    tool_get_task,
    tool_update_task,
)


def test_add_task_empty_title_raises_validation_error(core: CoreContext) -> None:
    with pytest.raises(ValidationError):
        tool_add_task(core, title="   ")


def test_add_task_bad_rrule_raises_recurrence_error(core: CoreContext) -> None:
    with pytest.raises(RecurrenceError):
        tool_add_task(core, title="recur", recurrence="not a real rrule")


def test_get_task_missing_id_raises_not_found(core: CoreContext) -> None:
    with pytest.raises(NotFoundError):
        tool_get_task(core, task_id="00000000-0000-0000-0000-000000000000")


def test_get_task_missing_number_raises_not_found(core: CoreContext) -> None:
    with pytest.raises(NotFoundError):
        tool_get_task(core, number=999_999)


def test_update_task_unknown_id_raises_not_found(core: CoreContext) -> None:
    with pytest.raises(NotFoundError):
        tool_update_task(
            core,
            task_id="00000000-0000-0000-0000-000000000000",
            title="anything",
        )


def test_update_task_empty_title_raises_validation_error(
    core: CoreContext,
) -> None:
    created = tool_add_task(core, title="real")
    with pytest.raises(ValidationError):
        tool_update_task(core, number=created["number"], title="   ")
