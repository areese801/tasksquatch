"""
Regression tests for the ``scripts/smoke-*.sh`` suite.

These do not execute the smoke scripts themselves (that would require
the package to be installed in the test environment and would slow the
unit suite down considerably). Instead they assert on the shell-script
metadata that has burned us before: executable bits, the
``#!/usr/bin/env bash`` shebang, the ``set -euo pipefail`` discipline,
and — when ``shellcheck`` is available on the host — a clean
``shellcheck`` run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _smoke_scripts() -> list[Path]:
    """
    Return every top-level ``scripts/smoke-*.sh`` file.

    The ``lib/`` helpers are intentionally excluded — they are
    sourced rather than executed and the executable-bit check would
    not apply.
    """
    return sorted(_SCRIPTS_DIR.glob("smoke-*.sh"))


def _script_ids() -> Iterator[str]:
    """
    Generate readable parametrize ids from the script paths.
    """
    for path in _smoke_scripts():
        yield path.name


SMOKE_SCRIPTS = _smoke_scripts()


def test_smoke_scripts_are_discovered() -> None:
    """
    Guard against a future refactor accidentally moving or deleting
    every smoke script — if the list is empty the rest of this module
    silently passes.
    """
    assert SMOKE_SCRIPTS, "no scripts/smoke-*.sh files found"


@pytest.mark.parametrize("script", SMOKE_SCRIPTS, ids=list(_script_ids()))
def test_smoke_script_is_executable(script: Path) -> None:
    """
    Every smoke script must have its executable bit set so the
    ``make smoke*`` targets and the README instructions work without
    asking the user to ``chmod +x``.
    """
    assert os.access(script, os.X_OK), f"{script} is not executable"


@pytest.mark.parametrize("script", SMOKE_SCRIPTS, ids=list(_script_ids()))
def test_smoke_script_has_bash_shebang(script: Path) -> None:
    """
    Pinning ``#!/usr/bin/env bash`` keeps the scripts portable across
    macOS (where ``/bin/sh`` is dash-ish) and Linux while still
    relying on bash features like ``[[ ... ]]``.
    """
    first = script.read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/usr/bin/env bash", f"{script} shebang is {first!r}"


@pytest.mark.parametrize("script", SMOKE_SCRIPTS, ids=list(_script_ids()))
def test_smoke_script_sets_safe_bash_options(script: Path) -> None:
    """
    ``set -euo pipefail`` near the top is the project's baseline for
    fail-fast behavior — without it a smoke script can silently
    skip past failures and report a green run.
    """
    head = script.read_text(encoding="utf-8").splitlines()[:20]
    joined = "\n".join(head)
    assert "set -euo pipefail" in joined, (
        f"{script} missing 'set -euo pipefail' in first 20 lines"
    )


@pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="shellcheck not available on this host",
)
@pytest.mark.parametrize("script", SMOKE_SCRIPTS, ids=list(_script_ids()))
def test_smoke_script_passes_shellcheck(script: Path) -> None:
    """
    Run ``shellcheck`` on the script when it is available.

    Skipped silently when ``shellcheck`` isn't installed so the test
    suite still runs in environments that don't have it (CI installs
    it on demand; many dev machines won't).
    """
    result = subprocess.run(
        ["shellcheck", "--severity=warning", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"shellcheck failed for {script.name}:\n{result.stdout}\n{result.stderr}"
    )
