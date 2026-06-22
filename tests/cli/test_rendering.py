from __future__ import annotations

import io
import json
from datetime import date, time
from pathlib import Path

import pytest
from rich.console import Console
from sqlalchemy.orm import Session, sessionmaker

from tasksquatch.cli.rendering import (
    default_console,
    print_json,
    print_table,
    render_task,
)
from tasksquatch.core.db import (
    create_engine_for_path,
    create_session_factory,
    init_schema,
)
from tasksquatch.core.seed import ensure_inbox
from tasksquatch.core.services.labels import create_label
from tasksquatch.core.services.projects import create_project
from tasksquatch.core.services.tasks import add_label, create_task


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine_for_path(tmp_path / "render.db")
    init_schema(engine)
    factory: sessionmaker[Session] = create_session_factory(engine)
    sess = factory()
    ensure_inbox(sess)
    sess.commit()
    return sess


def _capturing_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=200), buf


def test_default_console_returns_console_instance() -> None:
    assert isinstance(default_console(), Console)


def test_print_table_renders_title_and_values() -> None:
    console, buf = _capturing_console()
    print_table(
        [{"name": "alpha", "count": 7}],
        columns=["name", "count"],
        console=console,
        title="Things",
    )
    output = buf.getvalue()
    assert "Things" in output
    assert "alpha" in output
    assert "7" in output


def test_print_table_renders_dash_for_missing_keys() -> None:
    console, buf = _capturing_console()
    print_table(
        [{"name": "alpha"}],
        columns=["name", "count"],
        console=console,
    )
    output = buf.getvalue()
    assert "alpha" in output
    assert "-" in output


def test_print_json_serializes_dates() -> None:
    console, buf = _capturing_console()
    print_json({"when": date(2026, 6, 22), "ok": True}, console=console)
    parsed = json.loads(buf.getvalue())
    assert parsed == {"when": "2026-06-22", "ok": True}


def test_render_task_returns_expected_keys(session: Session) -> None:
    project = create_project(session, name="Work")
    label_a = create_label(session, name="urgent")
    label_b = create_label(session, name="home")
    task = create_task(
        session,
        title="ship it",
        project_id=project.id,
        due_date=date(2026, 7, 1),
        due_time=time(9, 30),
    )
    add_label(session, task_id=task.id, label_id=label_a.id)
    add_label(session, task_id=task.id, label_id=label_b.id)
    session.refresh(task)

    rendered = render_task(task)

    assert set(rendered.keys()) == {
        "number",
        "title",
        "project",
        "priority",
        "due",
        "labels",
        "completed",
    }
    assert rendered["title"] == "ship it"
    assert rendered["project"] == "Work"
    assert rendered["due"] == "2026-07-01 09:30"
    assert rendered["labels"] == "home,urgent"
    assert rendered["completed"] is False
    assert rendered["priority"] == task.priority.value
    assert isinstance(rendered["number"], int)
