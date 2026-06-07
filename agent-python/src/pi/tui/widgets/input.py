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

    def action_submit(self) -> None:
        text = self.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            self.clear()

    class Submitted(events.Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text
