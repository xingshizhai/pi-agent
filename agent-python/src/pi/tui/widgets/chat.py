# src/pi/tui/widgets/chat.py
from __future__ import annotations

from dataclasses import dataclass, field
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
        self._active_tools: dict[str, str] = {}  # tool_id → "name: summary"

    def add_message(self, msg: ChatMessage) -> None:
        self._messages.append(msg)
        self.refresh(layout=True)

    def append_stream(self, delta: str) -> None:
        self._stream_buf += delta
        self.refresh()

    def flush_stream(self) -> None:
        """Flush streaming buffer into a committed assistant message."""
        if self._stream_buf:
            self._messages.append(ChatMessage(role="assistant", content=self._stream_buf))
        self._stream_buf = ""
        self.refresh(layout=True)

    def tool_start(self, tool_id: str, name: str) -> None:
        self._active_tools[tool_id] = f"{name}…"
        self.refresh()

    def tool_end(self, tool_id: str, name: str, result: str, is_error: bool) -> None:
        self._active_tools.pop(tool_id, None)
        summary = result.replace("\n", " ")[:120]
        icon = "✗" if is_error else "✓"
        self._messages.append(ChatMessage(
            role="tool",
            content=f"{icon} [{name}] {summary}",
            tool_name=name,
            is_error=is_error,
        ))
        self.refresh(layout=True)

    def clear_messages(self) -> None:
        self._messages.clear()
        self._stream_buf = ""
        self._active_tools.clear()
        self.refresh(layout=True)

    def render(self) -> RenderResult:
        lines = []
        for msg in self._messages:
            if msg.role == "user":
                lines.append(Text(f"You: {msg.content}", style="bold cyan"))
            elif msg.role == "assistant":
                lines.append(Markdown(msg.content))
            elif msg.role == "tool":
                color = "bold red" if msg.is_error else "green"
                lines.append(Text(f"  {msg.content}", style=color))
            lines.append(Text(""))

        # Active (in-progress) tool executions.
        for summary in self._active_tools.values():
            lines.append(Text(f"  ⟳ {summary}", style="yellow"))

        # Streaming LLM output.
        if self._stream_buf:
            lines.append(Markdown(self._stream_buf + "▊"))

        return Group(*lines) if lines else Text("Start a conversation…", style="dim")
