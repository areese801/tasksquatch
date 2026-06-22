"""
Tests for :mod:`tasksquatch.notify.notifier`.

The real :class:`~tasksquatch.notify.notifier.Notifier` must construct
without raising even when no desktop backend is available (headless CI,
sandboxed test runner, no DBus). :class:`NullNotifier` is the explicit
escape hatch tests use to assert no real backend is touched.
"""

from __future__ import annotations

from tasksquatch.notify.notifier import Notifier, NullNotifier


def test_notifier_instantiates_without_raising() -> None:
    notifier = Notifier()
    assert isinstance(notifier, Notifier)


async def test_null_notifier_send_is_noop() -> None:
    null = NullNotifier()
    await null.send("title", "body")


async def test_real_notifier_send_does_not_raise() -> None:
    """
    Even when the underlying backend cannot be reached, ``send`` must
    not raise — the runner stamps ``last_notified_at`` whether or not
    the desktop actually received a banner.
    """
    notifier = Notifier()
    await notifier.send("title", "body")
