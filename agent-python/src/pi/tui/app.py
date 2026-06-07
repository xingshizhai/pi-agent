# src/pi/tui/app.py
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from ..agent.context import AgentContext, AgentConfig
from ..agent.events import (
    AgentEnd, MessageUpdate, ToolExecEnd, ToolExecStart,
)
from ..agent.loop import agent_loop
from ..ai.anthropic import AnthropicProvider
from ..session.manager import SessionManager
from ..tools.bash import BashTool
from ..tools.edit import EditTool
from ..tools.find import FindTool
from ..tools.grep import GrepTool
from ..tools.ls import LsTool
from ..tools.read import ReadTool
from ..tools.write import WriteTool
from .widgets.chat import ChatMessage, ChatView
from .widgets.input import InputWidget
from .widgets.status import StatusBar

SYSTEM_PROMPT = """You are a skilled coding assistant. You help users with programming tasks.
You have access to tools to read, write, and edit files, run bash commands, and search code.
Always think step by step and use tools to accomplish tasks."""


class PiApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_quit", "Cancel/Quit", show=True),
        Binding("ctrl+l", "clear_screen", "Clear", show=False),
    ]

    def __init__(self, model_id: str, api_key: str, cwd: str) -> None:
        super().__init__()
        self._model_id = model_id
        self._api_key = api_key
        self._cwd = cwd
        self._cancel_signal: asyncio.Event | None = None
        self._agent_task: asyncio.Task | None = None
        self._session_mgr = SessionManager()
        self._session = self._session_mgr.new_session(cwd)
        self._start_time: float = 0.0

        self._provider = AnthropicProvider()
        self._tools = [
            ReadTool(), WriteTool(), EditTool(), BashTool(),
            FindTool(), GrepTool(), LsTool(),
        ]
        self._ctx = AgentContext(
            system_prompt=SYSTEM_PROMPT,
            messages=[],
            tools=self._tools,
            config=AgentConfig(model_id=model_id, api_key=api_key),
        )

    def compose(self) -> ComposeResult:
        yield ChatView(id="chat")
        yield InputWidget(id="input")
        yield StatusBar(id="status")

    def on_input_widget_submitted(self, event: InputWidget.Submitted) -> None:
        self._start_turn(event.text)

    def _start_turn(self, user_text: str) -> None:
        chat = self.query_one(ChatView)
        chat.add_message(ChatMessage(role="user", content=user_text))

        status = self.query_one(StatusBar)
        status.model_name = self._model_id
        status.is_streaming = True
        self._start_time = time.monotonic()

        self._cancel_signal = asyncio.Event()
        self._agent_task = asyncio.create_task(
            self._run_agent(user_text, self._cancel_signal)
        )

    async def _run_agent(self, user_text: str, signal: asyncio.Event) -> None:
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        assistant_buf: list[str] = []

        def emit(event) -> None:
            if isinstance(event, MessageUpdate):
                assistant_buf.append(event.delta)
                chat.append_stream(event.delta)
            elif isinstance(event, ToolExecStart):
                chat.add_message(ChatMessage(
                    role="tool",
                    content=f"Running {event.name}...",
                    tool_name=event.name,
                ))
            elif isinstance(event, ToolExecEnd):
                chat.add_message(ChatMessage(
                    role="tool",
                    content=event.result.content[:500],
                    tool_name=event.name,
                    is_error=event.is_error,
                ))
            elif isinstance(event, AgentEnd):
                full_text = "".join(assistant_buf)
                if full_text:
                    chat.flush_stream(full_text)
                    chat.add_message(ChatMessage(role="assistant", content=full_text))
                elapsed = int((time.monotonic() - self._start_time) * 1000)
                status.elapsed_ms = elapsed
                status.is_streaming = False

        await agent_loop(user_text, self._ctx, self._provider, emit, signal=signal)

        for msg in self._ctx.messages[-10:]:
            self._session_mgr.append_message(self._session, msg)

    def action_cancel_or_quit(self) -> None:
        status = self.query_one(StatusBar)
        if self._cancel_signal and not self._cancel_signal.is_set() and status.is_streaming:
            self._cancel_signal.set()
        else:
            self.exit()

    def action_clear_screen(self) -> None:
        chat = self.query_one(ChatView)
        chat._messages.clear()
        chat.refresh()
