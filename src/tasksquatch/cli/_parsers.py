"""
Typer option-callback parsers for the tasksquatch CLI.

Each parser accepts the raw string Typer hands it (or ``None`` when the
option was not supplied) and returns a domain value — a
:class:`~tasksquatch.core.models.Priority`, :class:`datetime.date`, or
:class:`datetime.time`. Parsers raise :class:`typer.BadParameter` on
malformed input so Typer exits with status 2 and the standard
"Invalid value for ..." banner.

The parsers themselves are pure functions taking ``str | None``; the
``*_cb`` wrappers adapt them to Typer's callback signature so they can
be wired up via ``typer.Option(..., callback=...)``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import typer

from tasksquatch.core.models import Priority

_PRIORITY_ALIASES: dict[str, Priority] = {
    "p1": Priority.P1,
    "p2": Priority.P2,
    "p3": Priority.P3,
    "p4": Priority.P4,
    "1": Priority.P1,
    "2": Priority.P2,
    "3": Priority.P3,
    "4": Priority.P4,
    "high": Priority.P1,
    "medium": Priority.P2,
    "normal": Priority.P3,
    "low": Priority.P4,
}


def parse_priority(value: str | None) -> Priority | None:
    """
    Parse a CLI priority string into a :class:`Priority`.

    Accepted aliases (case-insensitive):

    * ``"p1"`` / ``"1"`` / ``"high"`` → :data:`Priority.P1`
    * ``"p2"`` / ``"2"`` / ``"medium"`` → :data:`Priority.P2`
    * ``"p3"`` / ``"3"`` / ``"normal"`` → :data:`Priority.P3`
    * ``"p4"`` / ``"4"`` / ``"low"`` → :data:`Priority.P4`

    :param value: The raw option value, or ``None`` if not supplied.
    :returns: The matching :class:`Priority`, or ``None`` when ``value``
        is ``None``.
    :raises typer.BadParameter: If ``value`` is not a recognized alias.
    """
    if value is None:
        return None
    key = value.strip().lower()
    try:
        return _PRIORITY_ALIASES[key]
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown priority {value!r}; expected one of "
            "p1/p2/p3/p4, 1-4, or high/medium/normal/low"
        ) from exc


def parse_date(value: str | None) -> date | None:
    """
    Parse a CLI date string into a :class:`~datetime.date`.

    Accepts ``"YYYY-MM-DD"`` and the literal keywords ``"today"`` and
    ``"tomorrow"``.

    :param value: The raw option value, or ``None`` if not supplied.
    :returns: The parsed :class:`~datetime.date`, or ``None`` when
        ``value`` is ``None``.
    :raises typer.BadParameter: If ``value`` is neither a recognized
        keyword nor a ``YYYY-MM-DD`` string.
    """
    if value is None:
        return None
    stripped = value.strip()
    keyword = stripped.lower()
    if keyword == "today":
        return date.today()
    if keyword == "tomorrow":
        return date.today() + timedelta(days=1)
    try:
        return datetime.strptime(stripped, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter(
            f"invalid date {value!r}; expected YYYY-MM-DD, 'today', or 'tomorrow'"
        ) from exc


def parse_time(value: str | None) -> time | None:
    """
    Parse a CLI time string into a :class:`~datetime.time`.

    Strict ``"HH:MM"`` 24-hour format.

    :param value: The raw option value, or ``None`` if not supplied.
    :returns: The parsed :class:`~datetime.time`, or ``None`` when
        ``value`` is ``None``.
    :raises typer.BadParameter: If ``value`` cannot be parsed as
        ``HH:MM``.
    """
    if value is None:
        return None
    stripped = value.strip()
    try:
        return datetime.strptime(stripped, "%H:%M").time()
    except ValueError as exc:
        raise typer.BadParameter(
            f"invalid time {value!r}; expected HH:MM (24-hour)"
        ) from exc


def parse_priority_cb(value: str | None) -> Priority | None:
    """
    Typer callback wrapper around :func:`parse_priority`.
    """
    return parse_priority(value)


def parse_date_cb(value: str | None) -> date | None:
    """
    Typer callback wrapper around :func:`parse_date`.
    """
    return parse_date(value)


def parse_time_cb(value: str | None) -> time | None:
    """
    Typer callback wrapper around :func:`parse_time`.
    """
    return parse_time(value)
