from __future__ import annotations

from datetime import date, datetime, time

import pytest
from dateutil.rrule import rrule, rrulebase

from tasksquatch.core.errors import RecurrenceError
from tasksquatch.core.models import RecurrenceAnchor
from tasksquatch.core.recurrence import next_occurrence, parse_rrule


def test_parse_rrule_none_returns_none() -> None:
    assert parse_rrule(None) is None


def test_parse_rrule_empty_string_returns_none() -> None:
    assert parse_rrule("") is None


def test_parse_rrule_whitespace_returns_none() -> None:
    assert parse_rrule("   \n\t ") is None


def test_parse_rrule_valid_returns_rrule() -> None:
    result = parse_rrule("FREQ=DAILY;INTERVAL=2")
    assert result is not None
    assert isinstance(result, rrulebase)


def test_parse_rrule_invalid_raises_recurrence_error() -> None:
    with pytest.raises(RecurrenceError) as excinfo:
        parse_rrule("FREQ=BANANA")
    assert "rrule" in excinfo.value.detail


def test_next_occurrence_fixed_daily_advances_one_day() -> None:
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 1, 5),
        scheduled_time=None,
        completion_dt=None,
    )
    assert result == (date(2026, 1, 6), None)


def test_next_occurrence_fixed_weekly_monday_from_monday() -> None:
    # 2026-01-05 is a Monday
    result = next_occurrence(
        "FREQ=WEEKLY;BYDAY=MO",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 1, 5),
        scheduled_time=None,
        completion_dt=None,
    )
    assert result == (date(2026, 1, 12), None)


def test_next_occurrence_fixed_until_exhausted_returns_none() -> None:
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1;UNTIL=20260105T000000",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 1, 5),
        scheduled_time=None,
        completion_dt=None,
    )
    assert result is None


def test_next_occurrence_fixed_count_exhausted_returns_none() -> None:
    # COUNT=1 emits exactly one occurrence (the dtstart itself); after()
    # with inc=False finds nothing strictly later.
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1;COUNT=1",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 1, 5),
        scheduled_time=None,
        completion_dt=None,
    )
    assert result is None


def test_next_occurrence_relative_advances_after_completion() -> None:
    # dtstart=2026-01-05 anchors the every-3-days pattern at Jan 5, 8, 11, ...
    # Completion at 2026-01-10T10:00 is after Jan 8 but before Jan 11, so
    # dateutil returns Jan 11 as the next firing strictly after the cursor.
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=3",
        anchor=RecurrenceAnchor.RELATIVE,
        scheduled_date=date(2026, 1, 5),
        scheduled_time=None,
        completion_dt=datetime(2026, 1, 10, 10, 0),
    )
    assert result == (date(2026, 1, 11), None)


def test_next_occurrence_relative_requires_completion_dt() -> None:
    with pytest.raises(RecurrenceError):
        next_occurrence(
            "FREQ=DAILY;INTERVAL=1",
            anchor=RecurrenceAnchor.RELATIVE,
            scheduled_date=date(2026, 1, 5),
            scheduled_time=None,
            completion_dt=None,
        )


def test_next_occurrence_date_only_returns_none_time() -> None:
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 6, 1),
        scheduled_time=None,
        completion_dt=None,
    )
    assert result is not None
    assert result[1] is None


def test_next_occurrence_date_and_time_preserves_time() -> None:
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 6, 1),
        scheduled_time=time(8, 0),
        completion_dt=None,
    )
    assert result == (date(2026, 6, 2), time(8, 0))


def test_next_occurrence_invalid_rrule_raises() -> None:
    with pytest.raises(RecurrenceError):
        next_occurrence(
            "FREQ=BANANA",
            anchor=RecurrenceAnchor.FIXED,
            scheduled_date=date(2026, 1, 5),
            scheduled_time=None,
            completion_dt=None,
        )


def test_next_occurrence_across_dst_forward_still_yields_naive_date() -> None:
    # US DST spring-forward in 2026 is March 8. We use naive datetimes so
    # dateutil computes against the wall clock — a daily-at-08:00 rule
    # remains at 08:00 across the boundary regardless of DST drift.
    result = next_occurrence(
        "FREQ=DAILY;INTERVAL=1",
        anchor=RecurrenceAnchor.FIXED,
        scheduled_date=date(2026, 3, 7),
        scheduled_time=time(8, 0),
        completion_dt=None,
    )
    assert result == (date(2026, 3, 8), time(8, 0))


def test_parse_rrule_returns_object_with_after_method() -> None:
    parsed = parse_rrule("FREQ=DAILY;INTERVAL=1")
    assert parsed is not None
    # The unbound rrule binds to "now" as dtstart per dateutil's default;
    # just confirm the API surface we rely on is present.
    assert hasattr(parsed, "after")
    assert isinstance(parsed, rrule | rrulebase)
