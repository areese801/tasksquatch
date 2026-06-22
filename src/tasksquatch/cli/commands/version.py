"""
``tasksquatch version`` — print the installed package version.
"""

from __future__ import annotations

import typer

from tasksquatch import __version__


def version() -> None:
    """
    Print the installed tasksquatch version.
    """
    typer.echo(__version__)
