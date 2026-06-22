"""
Process-wide singleton sentinels for tasksquatch core.

The module file name is underscore-private but the :data:`UNSET`
sentinel itself is part of the public ``tasksquatch.core`` surface and
is re-exported from that package. Hiding the implementation module
keeps the sentinel class out of the import-completion noise while
letting service signatures import the bare ``UNSET`` symbol.

The sentinel exists so that partial-update service functions can
distinguish "argument was not provided" from "argument was provided as
``None``". The conventional Pythonic alternative — using ``None`` as
"not provided" — does not survive a domain in which ``None`` is itself
a legal new value (``description = None``, ``due_date = None`` to clear
a scheduled date, etc.).
"""

from __future__ import annotations

from typing import Final


class _UnsetType:
    """
    Singleton marker for "argument not provided" in partial-update APIs.

    The class is private; consumers import the :data:`UNSET` instance
    rather than constructing their own. ``__new__`` enforces the
    singleton invariant so identity checks (``value is UNSET``) are
    reliable across modules and across reloads.
    """

    _instance: _UnsetType | None = None

    def __new__(cls) -> _UnsetType:
        """
        Return the singleton instance, constructing it on first call.

        :returns: The single :class:`_UnsetType` instance shared by the
            entire process.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        """
        Treat the sentinel as falsy so ``if value:`` works intuitively.

        :returns: Always ``False``.
        """
        return False

    def __repr__(self) -> str:
        """
        Return a stable, debuggable repr.

        :returns: The literal string ``"UNSET"``.
        """
        return "UNSET"


UNSET: Final = _UnsetType()
