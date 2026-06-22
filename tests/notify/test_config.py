"""
Tests for :mod:`tasksquatch.notify.config`.

Cover the precedence ladder (env > TOML > defaults), the parse of
``HH:MM`` and integer fields, and the validation errors raised on
malformed input.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import pytest

from tasksquatch.core.errors import ValidationError
from tasksquatch.notify.config import (
    NotifyConfig,
    default_config_path,
    load_notify_config,
)


def _write_config(path: Path, body: str) -> None:
    """
    Write ``body`` to ``path``, creating parents as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_defaults_when_no_env_no_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    cfg = load_notify_config(config_path=missing, env={})

    assert cfg == NotifyConfig(lead_seconds=0, day_of_time=time(9, 0))


def test_env_overrides_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    cfg = load_notify_config(
        config_path=missing,
        env={
            "TASKSQUATCH_NOTIFY_LEAD_SECONDS": "900",
            "TASKSQUATCH_NOTIFY_DAY_OF_TIME": "08:30",
        },
    )

    assert cfg == NotifyConfig(lead_seconds=900, day_of_time=time(8, 30))


def test_toml_overrides_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    _write_config(
        config_file,
        '[notify]\nlead_seconds = 600\nday_of_time = "07:15"\n',
    )

    cfg = load_notify_config(config_path=config_file, env={})

    assert cfg == NotifyConfig(lead_seconds=600, day_of_time=time(7, 15))


def test_env_beats_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    _write_config(
        config_file,
        '[notify]\nlead_seconds = 600\nday_of_time = "07:15"\n',
    )

    cfg = load_notify_config(
        config_path=config_file,
        env={
            "TASKSQUATCH_NOTIFY_LEAD_SECONDS": "120",
            "TASKSQUATCH_NOTIFY_DAY_OF_TIME": "10:00",
        },
    )

    assert cfg == NotifyConfig(lead_seconds=120, day_of_time=time(10, 0))


def test_toml_native_time_value(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    # TOML local time literal — not quoted.
    _write_config(config_file, "[notify]\nday_of_time = 06:45:00\n")

    cfg = load_notify_config(config_path=config_file, env={})

    assert cfg.day_of_time == time(6, 45)


def test_invalid_env_day_of_time_raises(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_notify_config(
            config_path=tmp_path / "missing.toml",
            env={"TASKSQUATCH_NOTIFY_DAY_OF_TIME": "not-a-time"},
        )


def test_invalid_env_lead_raises(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_notify_config(
            config_path=tmp_path / "missing.toml",
            env={"TASKSQUATCH_NOTIFY_LEAD_SECONDS": "abc"},
        )


def test_invalid_toml_lead_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    _write_config(config_file, '[notify]\nlead_seconds = "nope"\n')

    with pytest.raises(ValidationError):
        load_notify_config(config_path=config_file, env={})


def test_default_config_path_uses_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert default_config_path() == Path("/tmp/xdg/tasksquatch/config.toml")


def test_default_config_path_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config" / "tasksquatch" / "config.toml"
