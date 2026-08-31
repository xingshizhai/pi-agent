# src/pi/tui/app.py
"""PiApp — TUI 主应用，组装各层并驱动 Agent 任务。

职责：
  1. 初始化 AgentContext、Provider、Tools、Session
  2. 用户输入 → agent_loop()（asyncio Task 后台运行）
  3. 注入 emit 回调，将 AgentEvent 映射为 UI 更新
  4. AgentEnd 时持久化会话

布局（architecture.md §8.1）：
  ChatView（1fr）+ InputWidget（5 行）+ StatusBar（1 行）
"""
from __future__ import annotations

import asyncio
import os
import time

from textual.app import App, ComposeResult
from textual.binding import Binding

from ..agent.context import AgentContext, AgentConfig
from ..agent.events import (
    AgentEnd, AgentError, MessageUpdate,
    ToolExecEnd, ToolExecStart, TurnEnd,
)
from ..agent.loop import agent_loop
from ..ai.types import AssistantMessage, TextContent, ToolResultMessage, UserMessage
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

HELP_TEXT = """\
**Available slash commands:**
- `/clear` — clear the chat display (context is preserved)
- `/help`  — show this help message
- `/exit`  — quit pi

**Key bindings:**
- `Ctrl+Enter` or `Ctrl+J` — send message
- `Ctrl+C` — cancel current task (or quit if idle)
- `Ctrl+L` — clear screen
- `↑` / `↓` — browse input history (when input is empty)
"""


def _build_provider(provider_name: str):
    if provider_name == "openai":
        from ..ai.openai import OpenAIProvider
        return OpenAIProvider()
    if provider_name == "openrouter":
        from ..ai.openai import OpenRouterProvider
        return OpenRouterProvider()
    if provider_name == "kimi":
        from ..ai.openai import KimiProvider
        return KimiProvider()
    from ..ai.anthropic import AnthropicProvider
    return AnthropicProvider()


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

    def __init__(
        self, model_id: str, api_key: str, cwd: str,
        provider: str = "anthropic", session_id: str | None = None,
    ) -> None:
        super().__init__()
        self._model_id = model_id
        self._api_key = api_key
        self._cwd = cwd
        self._provider_name = provider

        self._cancel_signal: asyncio.Event | None = None
        self._agent_task: asyncio.Task | None = None
        self._session_mgr = SessionManager()
        if session_id:
            self._session = self._session_mgr.load_session(session_id)
        else:
            self._session = self._session_mgr.new_session(cwd)
        self._persisted_count = len(self._session.messages)
        self._start_time: float = 0.0

        self._provider = _build_provider(provider)
        self._tools = [
            ReadTool(), WriteTool(), EditTool(), BashTool(),
            FindTool(), GrepTool(), LsTool(),
        ]
        self._ctx = AgentContext(
            system_prompt=SYSTEM_PROMPT,
            messages=list(self._session.messages),
            tools=self._tools,
            config=AgentConfig(model_id=model_id, api_key=api_key),
        )

    def compose(self) -> ComposeResult:
        yield ChatView(id="chat")
        yield InputWidget(id="input")
        yield StatusBar(id="status")

    def on_mount(self) -> None:
        status = self.query_one(StatusBar)
        status.model_name = self._model_id
        if self._ctx.messages:
            self._load_history_into_chat()

    def _load_history_into_chat(self) -> None:
        """将恢复会话中的历史 messages 渲染为 ChatMessage（仅用于显示）。"""
        chat = self.query_one(ChatView)
        for msg in self._ctx.messages:
            if isinstance(msg, UserMessage):
                content = msg.content if isinstance(msg.content, str) else " ".join(
                    c.text for c in msg.content if isinstance(c, TextContent)
                )
                chat.add_message(ChatMessage(role="user", content=content))
            elif isinstance(msg, AssistantMessage):
                text = "".join(b.text for b in msg.content if isinstance(b, TextContent))
                if text:
                    chat.add_message(ChatMessage(role="assistant", content=text))
            elif isinstance(msg, ToolResultMessage):
                summary = "\n".join(c.text for c in msg.content).replace("\n", " ")[:120]
                icon = "✗" if msg.is_error else "✓"
                chat.add_message(ChatMessage(
                    role="tool",
                    content=f"{icon} [{msg.tool_name}] {summary}",
                    tool_name=msg.tool_name,
                    is_error=msg.is_error,
                ))

    def on_input_widget_submitted(self, event: InputWidget.Submitted) -> None:
        """InputWidget 通过 post_message(Submitted) 触发此 handler。"""
        text = event.text.strip()
        if not text:
            return

        if text.startswith("/"):
            self._handle_slash(text)
            return

        self.query_one(InputWidget).add_to_history(text)
        self._start_turn(text)

    def _handle_slash(self, cmd: str) -> None:
        input_widget = self.query_one(InputWidget)
        chat = self.query_one(ChatView)
        cmd = cmd.strip().lower()
        if cmd in ("/exit", "/quit"):
            self.exit()
        elif cmd == "/clear":
            chat.clear_messages()   # 只清 UI，ctx.messages 保留
        elif cmd == "/help":
            chat.add_message(ChatMessage(role="assistant", content=HELP_TEXT))
        else:
            chat.add_message(ChatMessage(
                role="tool", content=f"Unknown command: {cmd}. Type /help for help.", is_error=True
            ))

    def _start_turn(self, user_text: str) -> None:
        """启动一轮 Agent 任务：显示用户消息，创建后台 asyncio Task。"""
        chat = self.query_one(ChatView)
        chat.add_message(ChatMessage(role="user", content=user_text))

        status = self.query_one(StatusBar)
        status.is_streaming = True
        self._start_time = time.monotonic()

        self._cancel_signal = asyncio.Event()
        self._agent_task = asyncio.create_task(
            self._run_agent(user_text, self._cancel_signal)
        )

    async def _run_agent(self, user_text: str, cancel: asyncio.Event) -> None:
        """后台协程：运行 agent_loop，通过 emit 桥接 AgentEvent → UI。"""
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)

        def emit(event) -> None:
            # AgentEvent → UI 更新的映射表（TUI 只订阅关心的子集）
            if isinstance(event, MessageUpdate):
                chat.append_stream(event.delta)

            elif isinstance(event, ToolExecStart):
                chat.tool_start(event.id, event.name)

            elif isinstance(event, ToolExecEnd):
                result_content = event.result.content if event.result else ""
                chat.tool_end(event.id, event.name, result_content, event.is_error)

            elif isinstance(event, TurnEnd):
                if hasattr(event, "input_tokens") and event.input_tokens:
                    status.input_tokens += event.input_tokens
                if hasattr(event, "output_tokens") and event.output_tokens:
                    status.output_tokens += event.output_tokens

            elif isinstance(event, AgentEnd):
                chat.flush_stream()
                elapsed = int((time.monotonic() - self._start_time) * 1000)
                status.elapsed_ms = elapsed
                status.is_streaming = False
                for msg in self._ctx.messages[self._persisted_count:]:
                    self._session_mgr.append_message(self._session, msg)
                self._persisted_count = len(self._ctx.messages)

            elif isinstance(event, AgentError):
                chat.add_message(ChatMessage(
                    role="tool",
                    content=f"Error: {event.message}",
                    is_error=True,
                ))
                status.is_streaming = False

        await agent_loop(user_text, self._ctx, self._provider, emit, signal=cancel)

    def action_cancel_or_quit(self) -> None:
        """Ctrl+C：任务运行中 → 取消；空闲时 → 退出。"""
        status = self.query_one(StatusBar)
        if self._cancel_signal and not self._cancel_signal.is_set() and status.is_streaming:
            self._cancel_signal.set()
            status.is_streaming = False
        else:
            self.exit()

    def action_clear_screen(self) -> None:
        self.query_one(ChatView).clear_messages()
