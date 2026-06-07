# src/pi/tui/widgets/input.py
from __future__ import annotations

from textual.widgets import TextArea
from textual.binding import Binding
from textual import events


class InputWidget(TextArea):
    DEFAULT_CSS = """
    InputWidget {
        height: 5;
        border: solid $primary;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+enter", "submit", "Send", show=True),
        Binding("ctrl+j", "submit", "Send", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._history_idx: int = -1
        self._saved_draft: str = ""

    def add_to_history(self, text: str) -> None:
        """Called by the app after a message is submitted."""
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_idx = -1

    def action_submit(self) -> None:
        text = self.text.strip()
        if text:
            self._history_idx = -1
            self._saved_draft = ""
            self.post_message(self.Submitted(text))
            self.clear()

    def on_key(self, event: events.Key) -> None:
        """Navigate input history with Up/Down when the input box is empty (or at boundary)."""
        if event.key == "up" and not self.text.strip():
            event.prevent_default()
            if self._history:
                if self._history_idx == -1:
                    self._saved_draft = self.text
                    self._history_idx = len(self._history) - 1
                elif self._history_idx > 0:
                    self._history_idx -= 1
                self.load_text(self._history[self._history_idx])
                self.move_cursor(self.document.end)
            return

        if event.key == "down" and self._history_idx >= 0:
            event.prevent_default()
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
                self.load_text(self._history[self._history_idx])
            else:
                self._history_idx = -1
                self.load_text(self._saved_draft)
            self.move_cursor(self.document.end)
            return

    class Submitted(events.Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text
