"""
Small reusable modal screens used by the project and task list.

Two modal patterns are needed across the TUI: a single-line text
prompt (for "enter a project name", "rename to ...", "comment body")
and a yes/no confirmation prompt (for destructive actions like
``delete``). Both live here so the screens that use them stay focused
on their own logic.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class TextPromptScreen(ModalScreen[str | None]):
    """
    Modal that asks the user for a single line of text.

    Dismisses with the submitted string on ``enter`` (or when the user
    activates the OK button) and with ``None`` on ``escape`` (or when
    the Cancel button is pressed). An optional ``initial`` value
    pre-populates the input so a "rename" prompt can show the current
    name without an extra round trip.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        *,
        title: str,
        initial: str = "",
        placeholder: str = "",
    ) -> None:
        """
        :param title: Heading shown above the input.
        :param initial: Pre-filled value; useful for rename prompts.
        :param placeholder: Placeholder text when the input is empty.
        """
        super().__init__()
        self._title = title
        self._initial = initial
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        """
        Lay the modal out: title, input, and OK / Cancel buttons.
        """
        with Vertical(id="prompt-body"):
            yield Static(self._title, id="prompt-title")
            yield Input(
                value=self._initial,
                placeholder=self._placeholder,
                id="prompt-input",
            )
            yield Button("OK", variant="primary", id="prompt-ok")
            yield Button("Cancel", id="prompt-cancel")

    def on_mount(self) -> None:
        """
        Move focus to the input on first appearance.
        """
        self.query_one("#prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """
        Dismiss with the submitted value on ``enter``.
        """
        event.stop()
        self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Dispatch OK / Cancel button presses.
        """
        event.stop()
        if event.button.id == "prompt-ok":
            value = self.query_one("#prompt-input", Input).value
            self.dismiss(value)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        """
        Dismiss with ``None`` when the user presses ``escape``.
        """
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    """
    Modal that asks the user to confirm a destructive action.

    Dismisses with ``True`` when the user presses ``y`` or activates
    the Yes button, and with ``False`` on ``n`` / ``escape`` / Cancel.
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "deny", "No", show=False),
        Binding("escape", "deny", "Cancel", show=False),
    ]

    def __init__(self, *, prompt: str) -> None:
        """
        :param prompt: The question to display to the user.
        """
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        """
        Lay the modal out: prompt text plus Yes / No buttons.
        """
        with Vertical(id="confirm-body"):
            yield Static(self._prompt, id="confirm-prompt")
            yield Button("Yes", variant="error", id="confirm-yes")
            yield Button("No", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Dispatch Yes / No button presses.
        """
        event.stop()
        self.dismiss(event.button.id == "confirm-yes")

    def action_confirm(self) -> None:
        """
        Dismiss with ``True`` when the user presses ``y``.
        """
        self.dismiss(True)

    def action_deny(self) -> None:
        """
        Dismiss with ``False`` on ``n`` or ``escape``.
        """
        self.dismiss(False)
