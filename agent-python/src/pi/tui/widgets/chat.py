# src/pi/tui/widgets/chat.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.scroll_view import ScrollView
from textual.app import RenderResult


@dataclass
class ChatMessage:
    role: str          # "user" | "assistant" | "tool"
    content: str
    tool_name: str = ""
    is_error: bool = False


class ChatView(ScrollView):
    DEFAULT_CSS = """
    ChatView {
        height: 1fr;
        border: none;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._messages: list[ChatMessage] = []
        self._stream_buf: str = ""

    def add_message(self, msg: ChatMessage) -> None:
        self._messages.append(msg)
        self._stream_buf = ""
        self.refresh(layout=True)

    def append_stream(self, delta: str) -> None:
        self._stream_buf += delta
        self.refresh()

    def flush_stream(self, final_text: str) -> None:
        self._stream_buf = ""
        self.refresh()

    def render(self) -> RenderResult:
        lines = []
        for msg in self._messages:
            if msg.role == "user":
                lines.append(Text(f"You: {msg.content}", style="bold white"))
            elif msg.role == "assistant":
                lines.append(Markdown(msg.content))
            elif msg.role == "tool":
                color = "red" if msg.is_error else "yellow"
                lines.append(Text(f"[{msg.tool_name}] {msg.content[:200]}", style=color))
            lines.append(Text(""))

        if self._stream_buf:
            lines.append(Markdown(self._stream_buf))

        return Group(*lines) if lines else Text("Start a conversation...")
