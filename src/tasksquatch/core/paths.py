"""
Filesystem path resolution for tasksquatch.

Pure helpers for figuring out where the SQLite database file lives. All
resolution is deterministic and based on three inputs: an optional explicit
override, the ``TASKSQUATCH_DB`` environment variable, and XDG-style defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_VAR = "TASKSQUATCH_DB"
_XDG_DATA_HOME = "XDG_DATA_HOME"
_APP_DIR = "tasksquatch"
_DB_FILENAME = "tasksquatch.db"


def get_db_path(override: str | Path | None = None) -> Path:
    """
    Resolve the path to the tasksquatch SQLite database file.

    Resolution precedence:

    1. The ``override`` argument, if provided.
    2. The ``TASKSQUATCH_DB`` environment variable.
    3. ``$XDG_DATA_HOME/tasksquatch/tasksquatch.db``.
    4. ``~/.local/share/tasksquatch/tasksquatch.db`` as the final fallback.

    Tilde (``~``) is expanded in both the override and the environment
    variable. The parent directory of the returned path is created if it
    does not already exist.

    :param override: Optional explicit path to use, bypassing env/XDG lookup.
    :returns: An absolute :class:`Path` whose parent directory exists.
    """
    if override is not None:
        path = Path(override).expanduser()
    else:
        env_value = os.environ.get(_ENV_VAR)
        if env_value:
            path = Path(env_value).expanduser()
        else:
            xdg_value = os.environ.get(_XDG_DATA_HOME)
            if xdg_value:
                path = Path(xdg_value).expanduser() / _APP_DIR / _DB_FILENAME
            else:
                path = Path.home() / ".local" / "share" / _APP_DIR / _DB_FILENAME

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_default_db_path() -> Path:
    """
    Return the default database path with no override.

    Convenience wrapper around :func:`get_db_path` for callers that never
    need to inject a custom path.

    :returns: An absolute :class:`Path` whose parent directory exists.
    """
    return get_db_path()
