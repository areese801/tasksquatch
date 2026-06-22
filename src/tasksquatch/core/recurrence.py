"""
Pure-function helpers for RFC 5545 recurrence rules (RRULE).

This module is deliberately database-free: it parses RRULE strings and
computes the next occurrence of a recurring task, but every input it
needs is passed in by the caller. The task service consumes these
helpers when advancing a recurring task in place; tests can exercise
them without touching SQLAlchemy.

All datetimes handled here are treated as **naive local** times. The
underlying :mod:`dateutil.rrule` library handles RRULE arithmetic
(including DST-aware transitions when timezones are attached) — we
trust its semantics rather than reimplementing them.
"""

from __future__ import annotations

from datetime import date, datetime, time

from dateutil.rrule import rrulebase, rrulestr

from tasksquatch.core.errors import RecurrenceError
from tasksquatch.core.models import RecurrenceAnchor


def parse_rrule(rrule_str: str | None) -> rrulebase | None:
    """
    Parse an RFC 5545 RRULE string into a :class:`dateutil.rrule.rrulebase`.

    Returns ``None`` when ``rrule_str`` is ``None`` or empty (or
    whitespace-only) so callers can treat "no recurrence" as a single
    falsy value. The returned object may be either an ``rrule`` or an
    ``rruleset`` depending on the input; both expose the ``.after()``
    method the task service relies on.

    The rrule is returned **unbound to any ``DTSTART``** — if the
    caller needs occurrence math, use :func:`next_occurrence`, which
    binds a dtstart derived from the task's schedule.

    :param rrule_str: An RFC 5545 RRULE string, or ``None``.
    :returns: A parsed rrule, or ``None`` for empty input.
    :raises RecurrenceError: If ``rrule_str`` is non-empty but cannot
        be parsed.
    """
    if rrule_str is None:
        return None
    stripped = rrule_str.strip()
    if not stripped:
        return None
    try:
        return rrulestr(stripped)
    except ValueError as exc:
        raise RecurrenceError(
            f"Invalid RRULE: {stripped!r}",
            detail={"rrule": stripped, "reason": str(exc)},
        ) from exc


def next_occurrence(
    rrule_str: str,
    *,
    anchor: RecurrenceAnchor,
    scheduled_date: date,
    scheduled_time: time | None,
    completion_dt: datetime | None,
) -> tuple[date, time | None] | None:
    """
    Compute the next occurrence of a recurring task.

    The behavior depends on the recurrence ``anchor``:

    * ``FIXED`` advances strictly after the previous schedule. The
      dtstart used for the rrule is ``scheduled_date`` combined with
      ``scheduled_time`` (or midnight if the task is date-only); the
      next occurrence is the first rule-generated datetime strictly
      after that dtstart.
    * ``RELATIVE`` advances strictly after the actual completion
      timestamp. The dtstart still anchors the rule's *pattern* to
      the original schedule, but ``rrule.after(completion_dt)`` is
      what selects the next firing. This matches the dateutil
      semantics of "next pattern hit after the cursor."

    The returned tuple preserves the task's date-only vs date+time
    shape: a task without a ``scheduled_time`` gets back ``(date,
    None)`` regardless of what the rrule produced internally.

    Timezones: every datetime here is naive local. If the RRULE
    contains ``UNTIL`` or ``COUNT`` and the recurrence is exhausted,
    the function returns ``None``. DST transitions are delegated to
    :mod:`dateutil.rrule`, which computes occurrences against the
    naive wall clock (so a daily-at-08:00 rule stays 08:00 across the
    spring-forward boundary even though "real" elapsed time differs).

    :param rrule_str: An RFC 5545 RRULE string. Required (callers that
        might not have an rrule should check before calling).
    :param anchor: The :class:`RecurrenceAnchor` selecting fixed vs
        relative advance.
    :param scheduled_date: The task's previous due date.
    :param scheduled_time: The task's previous due time, or ``None``
        for a date-only task.
    :param completion_dt: The naive local datetime the task was just
        completed at. Required when ``anchor`` is ``RELATIVE``;
        ignored when ``anchor`` is ``FIXED``.
    :returns: A tuple of (next_date, next_time_or_None), or ``None``
        if the recurrence is exhausted.
    :raises RecurrenceError: If ``rrule_str`` is invalid, or if
        ``anchor`` is ``RELATIVE`` and ``completion_dt`` is ``None``.
    """
    dtstart = datetime.combine(scheduled_date, scheduled_time or time(0, 0))
    try:
        rule = rrulestr(rrule_str, dtstart=dtstart)
    except ValueError as exc:
        raise RecurrenceError(
            f"Invalid RRULE: {rrule_str!r}",
            detail={"rrule": rrule_str, "reason": str(exc)},
        ) from exc

    if anchor is RecurrenceAnchor.FIXED:
        cursor = dtstart
    elif anchor is RecurrenceAnchor.RELATIVE:
        if completion_dt is None:
            raise RecurrenceError(
                "RELATIVE anchor requires completion_dt",
                detail={"anchor": anchor.value},
            )
        cursor = completion_dt
    else:  # pragma: no cover - StrEnum is exhaustive
        raise RecurrenceError(
            f"Unknown recurrence anchor: {anchor!r}",
            detail={"anchor": str(anchor)},
        )

    nxt = rule.after(cursor, inc=False)
    if nxt is None:
        return None

    next_time: time | None = nxt.time() if scheduled_time is not None else None
    return (nxt.date(), next_time)
