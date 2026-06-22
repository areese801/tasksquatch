import typer

import tasksquatch
from tasksquatch.cli.app import app


def test_package_version_is_non_empty_string() -> None:
    assert isinstance(tasksquatch.__version__, str)
    assert tasksquatch.__version__ != ""


def test_cli_app_is_importable_typer_instance() -> None:
    assert isinstance(app, typer.Typer)
