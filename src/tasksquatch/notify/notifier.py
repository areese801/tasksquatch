"""
Async wrapper around :mod:`desktop_notifier` for tasksquatch.

The notifier is intentionally minimal: a single ``async def send(title,
body)`` coroutine that pushes one desktop notification. Construction is
lazy and forgiving — if no supported backend is available on the
platform (a headless CI runner, a server without DBus, an unsupported
OS), the constructor logs at ``DEBUG`` and the instance degrades to a
silent no-op rather than crashing the notify pass. Tests can also pick
:class:`NullNotifier` explicitly when they want to assert no real
backend is touched.
"""

from __future__ import annotations

import logging
from typing import Any

from desktop_notifier import DesktopNotifier

logger = logging.getLogger(__name__)


class Notifier:
    """
    Async desktop-notification wrapper.

    The underlying :class:`desktop_notifier.DesktopNotifier` is
    instantiated once per :class:`Notifier`. If instantiation raises
    (no supported backend, missing DBus session, sandbox without
    notification permissions, ...) the failure is swallowed and the
    notifier becomes a silent no-op — ``send`` still completes
    successfully so the calling notify pass can stamp
    ``last_notified_at`` and move on.
    """

    def __init__(self, *, app_name: str = "tasksquatch") -> None:
        """
        Construct the notifier, tolerating backend-init failure.

        :param app_name: The application name reported to the desktop
            notification system. Defaults to ``"tasksquatch"``.
        """
        self._backend: Any | None
        try:
            self._backend = DesktopNotifier(app_name=app_name)
        except Exception as exc:
            logger.debug("desktop_notifier unavailable on this platform: %s", exc)
            self._backend = None

    async def send(self, title: str, body: str) -> None:
        """
        Push a single desktop notification.

        Silently no-ops when no backend was available at instantiation
        or when the backend raises while sending. A failure to notify
        is **not** propagated to the runner: the user has chosen to be
        reminded, and a transient backend hiccup should not stop other
        reminders in the same pass from going out.

        :param title: The notification title line.
        :param body: The notification body text.
        """
        if self._backend is None:
            return
        try:
            await self._backend.send(title=title, message=body)
        except Exception as exc:
            logger.debug("desktop_notifier.send failed: %s", exc)


class NullNotifier(Notifier):
    """
    Explicit no-op :class:`Notifier` for tests and unsupported hosts.

    Subclassing :class:`Notifier` (rather than implementing a separate
    protocol) keeps the runner's type hint a single concrete class and
    means callers can substitute a :class:`NullNotifier` anywhere a
    :class:`Notifier` is expected.
    """

    def __init__(self) -> None:
        """
        Construct a no-op notifier without touching the desktop layer.
        """
        self._backend = None

    async def send(self, title: str, body: str) -> None:
        """
        Discard the notification.

        :param title: Ignored.
        :param body: Ignored.
        """
        return
