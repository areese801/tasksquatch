"""
Notification configuration loader.

Notifications are driven by two knobs: ``lead_seconds`` (how many seconds
early a notification may fire) and ``day_of_time`` (the wall-clock time
used as the notify moment for date-only tasks). Both are documented in
``docs/spec.md`` §6.

The loader resolves the active :class:`NotifyConfig` from three sources,
in descending precedence:

1. Environment variables — ``TASKSQUATCH_NOTIFY_LEAD_SECONDS`` (int) and
   ``TASKSQUATCH_NOTIFY_DAY_OF_TIME`` (``HH:MM``).
2. A ``[notify]`` section in
   ``$XDG_CONFIG_HOME/tasksquatch/config.toml`` (or
   ``~/.config/tasksquatch/config.toml`` when ``XDG_CONFIG_HOME`` is
   not set).
3. The dataclass defaults: ``lead_seconds=0``, ``day_of_time=09:00``.

A missing config file is not an error — the defaults simply win. A
malformed ``HH:MM`` string or a non-integer ``lead_seconds`` raises
:class:`~tasksquatch.core.errors.ValidationError`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any

from tasksquatch.core.errors import ValidationError

_ENV_LEAD_SECONDS = "TASKSQUATCH_NOTIFY_LEAD_SECONDS"
_ENV_DAY_OF_TIME = "TASKSQUATCH_NOTIFY_DAY_OF_TIME"
_XDG_CONFIG_HOME = "XDG_CONFIG_HOME"
_APP_DIR = "tasksquatch"
_CONFIG_FILENAME = "config.toml"


@dataclass(frozen=True)
class NotifyConfig:
    """
    Resolved configuration for the notification pass.

    :ivar lead_seconds: Seconds the notifier may fire before a task's
        notify moment. ``0`` fires at or after the moment only.
    :ivar day_of_time: Wall-clock time used as the notify moment for
        date-only tasks. Defaults to 09:00.
    """

    lead_seconds: int = 0
    day_of_time: time = time(9, 0)


def default_config_path() -> Path:
    """
    Return the default path to the user's tasksquatch config file.

    Honors ``$XDG_CONFIG_HOME`` when set; otherwise falls back to
    ``~/.config/tasksquatch/config.toml``. The path is returned even if
    the file does not exist — the caller decides what to do when it is
    missing.

    :returns: Absolute :class:`Path` to the config file.
    """
    xdg = os.environ.get(_XDG_CONFIG_HOME)
    if xdg:
        return Path(xdg).expanduser() / _APP_DIR / _CONFIG_FILENAME
    return Path.home() / ".config" / _APP_DIR / _CONFIG_FILENAME


def _parse_lead_seconds(raw: str) -> int:
    """
    Parse a lead-seconds string into a non-negative integer.

    :param raw: The raw string from an env var or a TOML value coerced
        via ``str``.
    :returns: The integer lead-seconds value.
    :raises ValidationError: If ``raw`` is not a valid integer.
    """
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid lead_seconds value {raw!r}; expected an integer.",
            detail={"value": raw},
        ) from exc


def _parse_day_of_time(raw: str) -> time:
    """
    Parse an ``HH:MM`` string into a :class:`datetime.time`.

    :param raw: The raw string from an env var or a TOML value.
    :returns: The parsed :class:`time`.
    :raises ValidationError: If ``raw`` is not a valid ``HH:MM`` string.
    """
    try:
        return time.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Invalid day_of_time value {raw!r}; expected HH:MM.",
            detail={"value": raw},
        ) from exc


def _coerce_lead(value: Any) -> int:
    """
    Coerce a TOML value into a non-negative ``lead_seconds`` integer.

    :param value: The raw value pulled from a TOML mapping.
    :returns: The integer lead-seconds value.
    :raises ValidationError: If the value is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(
            f"Invalid lead_seconds value {value!r}; expected an integer.",
            detail={"value": value},
        )
    return value


def _coerce_day_of_time(value: Any) -> time:
    """
    Coerce a TOML value into a :class:`datetime.time`.

    Accepts either a native TOML ``local time`` (returned by
    :mod:`tomllib` as :class:`datetime.time`) or an ``HH:MM`` string.

    :param value: The raw value pulled from a TOML mapping.
    :returns: The parsed :class:`time`.
    :raises ValidationError: If the value is neither a time nor a
        parseable ``HH:MM`` string.
    """
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return _parse_day_of_time(value)
    raise ValidationError(
        f"Invalid day_of_time value {value!r}; expected HH:MM string.",
        detail={"value": value},
    )


def _load_toml_overrides(path: Path) -> dict[str, Any]:
    """
    Load the ``[notify]`` section from a TOML config file.

    Returns an empty dict when ``path`` does not exist (a missing config
    file is not an error). Raises :class:`ValidationError` if the file
    exists but cannot be parsed.

    :param path: Absolute path to the candidate config file.
    :returns: The ``[notify]`` section, or ``{}`` if missing.
    :raises ValidationError: If the file is unreadable or malformed.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError(
            f"Failed to read tasksquatch config at {path}: {exc}",
            detail={"path": str(path)},
        ) from exc
    section = data.get("notify")
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValidationError(
            "tasksquatch config [notify] section must be a table.",
            detail={"path": str(path)},
        )
    return section


def load_notify_config(
    *,
    config_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> NotifyConfig:
    """
    Resolve the active :class:`NotifyConfig`.

    Precedence (highest first): environment variables, the ``[notify]``
    section of the config TOML, then the dataclass defaults. Both
    arguments are intended for testing — production callers pass nothing
    and inherit the process environment plus
    :func:`default_config_path`.

    :param config_path: Override the TOML path; defaults to
        :func:`default_config_path`.
    :param env: Override the environment mapping; defaults to
        :data:`os.environ`.
    :returns: The resolved :class:`NotifyConfig`.
    :raises ValidationError: If any source provides a malformed value.
    """
    env_map = env if env is not None else os.environ
    path = config_path if config_path is not None else default_config_path()

    lead_seconds: int = 0
    day_of_time: time = time(9, 0)

    toml_section = _load_toml_overrides(path)
    if "lead_seconds" in toml_section:
        lead_seconds = _coerce_lead(toml_section["lead_seconds"])
    if "day_of_time" in toml_section:
        day_of_time = _coerce_day_of_time(toml_section["day_of_time"])

    env_lead = env_map.get(_ENV_LEAD_SECONDS)
    if env_lead is not None:
        lead_seconds = _parse_lead_seconds(env_lead)

    env_day = env_map.get(_ENV_DAY_OF_TIME)
    if env_day is not None:
        day_of_time = _parse_day_of_time(env_day)

    return NotifyConfig(lead_seconds=lead_seconds, day_of_time=day_of_time)
