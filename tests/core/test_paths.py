from __future__ import annotations

from pathlib import Path

import pytest

from tasksquatch.core.paths import get_db_path, get_default_db_path


def test_explicit_override_wins_over_env_and_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("TASKSQUATCH_DB", str(tmp_path / "env" / "env.db"))
    target = tmp_path / "explicit" / "explicit.db"

    result = get_db_path(target)

    assert result == target
    assert result.parent.is_dir()


def test_env_var_wins_over_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    env_path = tmp_path / "env" / "from-env.db"
    monkeypatch.setenv("TASKSQUATCH_DB", str(env_path))

    result = get_db_path()

    assert result == env_path
    assert result.parent.is_dir()


def test_xdg_path_used_when_env_var_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TASKSQUATCH_DB", raising=False)
    xdg_root = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    result = get_db_path()

    assert result == xdg_root / "tasksquatch" / "tasksquatch.db"
    assert result.parent.is_dir()


def test_home_fallback_when_xdg_and_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TASKSQUATCH_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))

    result = get_db_path()

    assert result == fake_home / ".local" / "share" / "tasksquatch" / "tasksquatch.db"
    assert result.parent.is_dir()


def test_parent_directory_is_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TASKSQUATCH_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    target = tmp_path / "deeply" / "nested" / "path" / "tasksquatch.db"
    assert not target.parent.exists()

    result = get_db_path(target)

    assert result == target
    assert result.parent.is_dir()


def test_tilde_in_env_var_is_expanded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("TASKSQUATCH_DB", "~/foo/bar.db")

    result = get_db_path()

    assert result == fake_home / "foo" / "bar.db"
    assert result.parent.is_dir()


def test_tilde_in_override_is_expanded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    result = get_db_path("~/from-override.db")

    assert result == fake_home / "from-override.db"
    assert result.parent.is_dir()


def test_get_default_db_path_matches_get_db_path_without_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xdg_root = tmp_path / "xdg"
    monkeypatch.delenv("TASKSQUATCH_DB", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_root))

    assert get_default_db_path() == get_db_path()
