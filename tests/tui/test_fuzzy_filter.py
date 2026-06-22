"""
Unit tests for :func:`fuzzy_score`.

These hold the fuzzy-filter helper to its contract: an empty query
short-circuits to "every candidate, original order", a non-empty
query ranks by descending WRatio and drops anything under the cutoff,
and the indices returned are positions in the input iterable.
"""

from __future__ import annotations

from tasksquatch.tui.widgets.fuzzy_filter import fuzzy_score


def test_empty_query_returns_all_candidates_in_order() -> None:
    candidates = ["alpha", "beta", "gamma"]
    result = fuzzy_score("", candidates)
    assert [idx for idx, _ in result] == [0, 1, 2]
    assert all(score == 100 for _, score in result)


def test_whitespace_query_is_treated_as_empty() -> None:
    result = fuzzy_score("   ", ["x", "y"])
    assert [idx for idx, _ in result] == [0, 1]


def test_query_filters_and_ranks_candidates() -> None:
    candidates = [
        "buy milk",
        "feed the dog",
        "milkshake recipe",
        "totally unrelated thing",
    ]
    result = fuzzy_score("milk", candidates)
    indices = [idx for idx, _ in result]
    assert 0 in indices
    assert 2 in indices
    assert 1 not in indices
    # Scores must be sorted desc.
    scores = [score for _, score in result]
    assert scores == sorted(scores, reverse=True)


def test_query_below_cutoff_drops_candidate() -> None:
    candidates = ["zzz totally unrelated"]
    assert fuzzy_score("alpha", candidates) == []
