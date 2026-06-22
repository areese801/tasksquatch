"""
Reusable fuzzy-filter input widget for the tasksquatch TUI.

The :class:`FilterInput` widget wraps Textual's :class:`Input` with the
keybindings and message conventions the surrounding screens expect:
``escape`` clears the value without giving up focus, ``enter`` emits a
submission signal, and every keystroke broadcasts a
:class:`FilterChanged` message so the host screen can re-render its
list in place.

The :func:`fuzzy_score` helper exists so screens can run the actual
fuzzy match against arbitrary candidate strings without coupling that
logic to the widget. It is a thin convenience wrapper around
:func:`rapidfuzz.process.extract` configured for the cutoff and scorer
the TUI uses everywhere.
"""

from __future__ import annotations

from collections.abc import Iterable

from rapidfuzz import fuzz, process
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input


class FilterChanged(Message):
    """
    Posted by :class:`FilterInput` on every value change.

    The host screen listens for this message and re-runs its fuzzy
    filter against the new query. The message is bubbled, so parent
    screens receive it without explicit forwarding.
    """

    def __init__(self, query: str) -> None:
        """
        :param query: The new filter query string, verbatim.
        """
        super().__init__()
        self.query = query


class FilterSubmitted(Message):
    """
    Posted by :class:`FilterInput` when the user presses ``enter``.

    The widget keeps focus so the user can keep typing; the screen is
    free to ignore this message or to perform a "commit current filter"
    side effect (e.g. opening the first matching task in TSQ-26).
    """

    def __init__(self, query: str) -> None:
        """
        :param query: The current filter query at submit time.
        """
        super().__init__()
        self.query = query


class FilterInput(Input):
    """
    Single-line filter input with TUI-friendly keybindings.

    Compared with the stock :class:`Input`, this widget:

    * shows ``/<filter>`` as its placeholder so the user understands
      what the field is for;
    * remaps ``escape`` to clear the value in place (without
      surrendering focus); and
    * emits :class:`FilterChanged` on every keystroke and
      :class:`FilterSubmitted` on ``enter``, both as bubbling messages
      so the surrounding screen can react.
    """

    BINDINGS = [
        Binding("escape", "clear_filter", "Clear", show=False),
    ]

    def __init__(self, *, id: str | None = None) -> None:
        """
        :param id: Optional Textual widget id for selector targeting.
        """
        super().__init__(placeholder="/<filter>", id=id)

    def action_clear_filter(self) -> None:
        """
        Clear the input value in place and notify listeners.

        Focus is preserved so the user can keep typing to refine the
        next query without an extra keystroke.
        """
        if self.value:
            self.value = ""

    def on_input_changed(self, event: Input.Changed) -> None:
        """
        Forward Textual's :class:`Input.Changed` as :class:`FilterChanged`.

        :param event: The underlying Textual change event.
        """
        if event.input is self:
            event.stop()
            self.post_message(FilterChanged(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """
        Forward Textual's :class:`Input.Submitted` as :class:`FilterSubmitted`.

        :param event: The underlying Textual submit event.
        """
        if event.input is self:
            event.stop()
            self.post_message(FilterSubmitted(event.value))


def fuzzy_score(
    query: str,
    candidates: Iterable[str],
) -> list[tuple[int, int]]:
    """
    Score ``candidates`` against ``query`` with rapidfuzz's WRatio.

    Returns a list of ``(index, score)`` pairs ordered by descending
    score, where ``index`` refers to the position of the candidate in
    the input iterable. Candidates scoring below 50 are dropped (see
    rapidfuzz's ``score_cutoff``). An empty or whitespace-only
    ``query`` returns every candidate with score 100 in the original
    order, so callers can use this helper unconditionally without a
    branch in the screen logic.

    :param query: The user's filter string.
    :param candidates: The strings to score.
    :returns: A list of ``(index, score)`` pairs, highest first.
    """
    materialized = list(candidates)
    if not query.strip():
        return [(index, 100) for index in range(len(materialized))]

    raw = process.extract(
        query,
        materialized,
        scorer=fuzz.WRatio,
        score_cutoff=50,
        limit=len(materialized),
    )
    return [(int(index), int(score)) for _value, score, index in raw]
