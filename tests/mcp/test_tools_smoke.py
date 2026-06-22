"""
Smoke tests for every tasksquatch MCP tool handler.

These tests drive handlers directly against an in-memory-style core
context — no MCP stdio server is spawned. The goal is end-to-end
coverage of the happy path for every registered tool so a regression
in any handler is caught loudly.
"""

from __future__ import annotations

import pytest

from tasksquatch.core.errors import NotFoundError
from tasksquatch.mcp._session import CoreContext
from tasksquatch.mcp.tools import (
    tool_add_comment,
    tool_add_label_to_task,
    tool_add_task,
    tool_complete_task,
    tool_create_label,
    tool_create_project,
    tool_delete_comment,
    tool_edit_comment,
    tool_get_task,
    tool_list_labels,
    tool_list_projects,
    tool_list_tasks,
    tool_read_activity_log,
    tool_remove_label_from_task,
    tool_search_tasks,
    tool_uncomplete_task,
    tool_update_task,
)


def test_add_task_returns_taskread_shape(core: CoreContext) -> None:
    result = tool_add_task(core, title="Buy milk")
    assert result["title"] == "Buy milk"
    assert result["number"] == 1
    assert result["completed"] is False
    assert result["priority"] == "P4"


def test_complete_then_get_shows_completed(core: CoreContext) -> None:
    created = tool_add_task(core, title="ship it")
    tool_complete_task(core, number=created["number"])
    fetched = tool_get_task(core, number=created["number"])
    assert fetched["task"]["completed"] is True


def test_uncomplete_clears_completed(core: CoreContext) -> None:
    created = tool_add_task(core, title="rinse and repeat")
    tool_complete_task(core, number=created["number"])
    after = tool_uncomplete_task(core, number=created["number"])
    assert after["completed"] is False


def test_update_task_applies_partial_change(core: CoreContext) -> None:
    created = tool_add_task(core, title="original")
    updated = tool_update_task(
        core, number=created["number"], title="renamed", priority="P1"
    )
    assert updated["title"] == "renamed"
    assert updated["priority"] == "P1"


def test_list_tasks_filters_by_project_name(core: CoreContext) -> None:
    proj = tool_create_project(core, name="Side Quests")
    tool_add_task(core, title="In project", project_id=proj["id"])
    tool_add_task(core, title="In Inbox")

    side_only = tool_list_tasks(core, project_name="Side Quests")
    assert {t["title"] for t in side_only["items"]} == {"In project"}


def test_list_tasks_parent_filter_none_returns_top_level_only(
    core: CoreContext,
) -> None:
    parent = tool_add_task(core, title="parent")
    tool_add_task(core, title="child", parent_number=parent["number"])

    top = tool_list_tasks(core, parent_id="none")
    titles = {t["title"] for t in top["items"]}
    assert "parent" in titles
    assert "child" not in titles


def test_search_finds_substring(core: CoreContext) -> None:
    tool_add_task(core, title="Buy milk")
    tool_add_task(core, title="Walk the dog")
    hits = tool_search_tasks(core, query="milk")
    assert len(hits["items"]) == 1
    assert hits["items"][0]["title"] == "Buy milk"


def test_add_comment_visible_in_get(core: CoreContext) -> None:
    created = tool_add_task(core, title="needs a note")
    comment = tool_add_comment(core, number=created["number"], body="hello")
    fetched = tool_get_task(core, number=created["number"])
    assert [c["id"] for c in fetched["comments"]] == [comment["id"]]
    assert fetched["comments"][0]["body"] == "hello"


def test_edit_comment_changes_body(core: CoreContext) -> None:
    task = tool_add_task(core, title="t")
    comment = tool_add_comment(core, number=task["number"], body="first")
    edited = tool_edit_comment(core, comment_id=comment["id"], body="second")
    assert edited["body"] == "second"


def test_delete_comment_removes_it(core: CoreContext) -> None:
    task = tool_add_task(core, title="t")
    comment = tool_add_comment(core, number=task["number"], body="bye")
    res = tool_delete_comment(core, comment_id=comment["id"])
    assert res == {"deleted": True, "comment_id": comment["id"]}
    fetched = tool_get_task(core, number=task["number"])
    assert fetched["comments"] == []


def test_add_label_by_name_requires_existing_label(core: CoreContext) -> None:
    tool_create_label(core, name="urgent")
    task = tool_add_task(core, title="t")
    updated = tool_add_label_to_task(core, number=task["number"], label_name="urgent")
    assert len(updated["label_ids"]) == 1


def test_add_label_by_unknown_name_raises(core: CoreContext) -> None:
    task = tool_add_task(core, title="t")
    with pytest.raises(NotFoundError):
        tool_add_label_to_task(core, number=task["number"], label_name="does-not-exist")


def test_remove_label_detaches(core: CoreContext) -> None:
    label = tool_create_label(core, name="later")
    task = tool_add_task(core, title="t")
    tool_add_label_to_task(core, number=task["number"], label_id=label["id"])
    after = tool_remove_label_from_task(
        core, number=task["number"], label_id=label["id"]
    )
    assert after["label_ids"] == []


def test_create_project_then_list_projects(core: CoreContext) -> None:
    tool_create_project(core, name="Personal")
    names = {p["name"] for p in tool_list_projects(core)["items"]}
    assert "Personal" in names
    assert "Inbox" in names


def test_create_label_then_list_labels(core: CoreContext) -> None:
    tool_create_label(core, name="home")
    names = {label["name"] for label in tool_list_labels(core)["items"]}
    assert names == {"home"}


def test_read_activity_log_contains_completion_event(core: CoreContext) -> None:
    task = tool_add_task(core, title="logged")
    tool_complete_task(core, number=task["number"])
    rows = tool_read_activity_log(core, task_id=task["id"])
    event_types = {row["event_type"] for row in rows["items"]}
    assert "completed" in event_types


def test_add_task_with_labels_at_creation(core: CoreContext) -> None:
    label = tool_create_label(core, name="boot")
    task = tool_add_task(core, title="t", labels=[label["name"]])
    assert label["id"] in task["label_ids"]


def test_add_task_with_project_name(core: CoreContext) -> None:
    proj = tool_create_project(core, name="Work")
    task = tool_add_task(core, title="t", project_name="Work")
    assert task["project_id"] == proj["id"]


def test_search_with_empty_query_returns_nothing(core: CoreContext) -> None:
    tool_add_task(core, title="anything")
    assert tool_search_tasks(core, query="")["items"] == []
