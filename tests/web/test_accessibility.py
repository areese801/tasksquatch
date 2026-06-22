"""
Lightweight accessibility checks for the rendered dashboard.

These do not replace a full a11y audit — they enforce just the two
guarantees the project promises today: a skip-to-main link sits at
the top of the body, and every form input has either a wrapping
``<label>`` or an explicit ``aria-label``.
"""

from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient


class _InputLabelCollector(HTMLParser):
    """
    Collect every input's accessible-name signal from a rendered page.

    Walks the DOM with a depth tracker for ``<label>`` elements so an
    ``<input>`` nested inside a label is recognized as labelled even
    when the label uses the implicit (child-wrapping) association.
    Inputs that carry ``aria-label`` are also accepted; everything
    else gets dropped into :pyattr:`missing` for the test to assert
    against.
    """

    def __init__(self) -> None:
        """
        Initialize the collector with an empty missing-input set.
        """
        super().__init__()
        self.label_depth = 0
        self.missing: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """
        Track label nesting and record any unlabelled inputs.
        """
        if tag == "label":
            self.label_depth += 1
            return
        if tag != "input":
            return
        attr_dict = dict(attrs)
        if self.label_depth > 0:
            return
        if attr_dict.get("aria-label"):
            return
        if attr_dict.get("type") == "hidden":
            return
        self.missing.append(attr_dict)

    def handle_endtag(self, tag: str) -> None:
        """
        Pop the label-depth counter when a ``</label>`` is reached.
        """
        if tag == "label" and self.label_depth > 0:
            self.label_depth -= 1


def test_all_inputs_have_label_or_aria(client: TestClient) -> None:
    """
    Every visible ``<input>`` in the dashboard root carries a label.
    """
    response = client.get("/ui/")
    parser = _InputLabelCollector()
    parser.feed(response.text)
    assert parser.missing == []


def test_skip_link_present(client: TestClient) -> None:
    """
    The dashboard ships a Skip to main accessibility link.
    """
    response = client.get("/ui/")
    assert '<a href="#main" class="skip-link">Skip to main</a>' in response.text
