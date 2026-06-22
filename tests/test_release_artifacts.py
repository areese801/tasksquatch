"""
Regression tests for release packaging artifacts.

These tests guard the non-Python files that the Web UI surface depends
on at runtime — ``htmx.min.js`` and the Jinja2 templates under
``tasksquatch.web``. If hatchling stops bundling them inside the wheel
(see :mod:`tasksquatch.web` and the ``[tool.hatch.build.targets.wheel]``
section of ``pyproject.toml``), the Web UI breaks for installed users
even though the source checkout keeps working.

The checks here use :mod:`importlib.resources`, which resolves to the
filesystem when running against a source checkout (the cage's normal
state) and to the wheel contents when running against an installed
distribution. The release recipe in ``docs/release.md`` calls out an
additional wheel-install smoke that exercises the same paths from a
fresh venv.
"""

from __future__ import annotations

from importlib.resources import files


def test_htmx_is_packaged_with_tasksquatch_web() -> None:
    htmx = files("tasksquatch.web") / "static" / "htmx.min.js"
    assert htmx.is_file(), f"missing packaged file: {htmx}"
    assert htmx.read_bytes(), "htmx.min.js is empty"


def test_stylesheet_is_packaged_with_tasksquatch_web() -> None:
    stylesheet = files("tasksquatch.web") / "static" / "style.css"
    assert stylesheet.is_file(), f"missing packaged file: {stylesheet}"


def test_layout_template_is_packaged_with_tasksquatch_web() -> None:
    layout = files("tasksquatch.web") / "templates" / "layout.html"
    assert layout.is_file(), f"missing packaged file: {layout}"
    assert layout.read_text(encoding="utf-8"), "layout.html is empty"
