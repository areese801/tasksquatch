from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tasksquatch import __version__
from tasksquatch.cli.app import app


def test_version_command_prints_package_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_notify_command_runs_on_empty_db(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--db", str(tmp_path / "smoke.db"), "notify"])
    assert result.exit_code == 0
    assert "fired 0 notification(s)." in result.output


def test_db_global_flag_is_accepted_before_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--db", str(tmp_path / "x.db"), "version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_no_args_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    # Typer's no_args_is_help raises Click's UsageError (exit code 2)
    # but the user-visible behavior — printing the usage banner — is
    # what we care about here.
    assert "Usage:" in result.output


def test_dash_h_shows_usage() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
