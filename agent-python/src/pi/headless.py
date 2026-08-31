# src/pi/headless.py
"""
Headless mode: PI_HEADLESS=1

Reads JSON from stdin, runs the agent, emits NDJSON events to stdout.

Input (stdin):
    {"prompt": "...", "mock_turns": [...] | null, "cwd": "..."}

Output (stdout NDJSON):
    {"type": "agent_start"}
    {"type": "turn_start",  "turn": 1}
    {"type": "tool_call",   "id": "t1", "name": "read",   "args": {...}}
    {"type": "tool_result", "id": "t1", "name": "read",   "content": "...", "is_error": false}
    {"type": "turn_end",    "turn": 1}
    {"type": "agent_end",   "turns": 2}
    {"type": "error",       "message": "..."}
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from .agent.context import AgentContext, AgentConfig
from .agent.events import (
    AgentEnd, AgentError, AgentStart,
    ToolExecEnd, ToolExecStart, ToolExecUpdate,
    TurnEnd, TurnStart,
)
from .agent.loop import agent_loop
from .tools.base import Tool
from .tools.read import ReadTool
from .tools.write import WriteTool
from .tools.edit import EditTool
from .tools.bash import BashTool
from .tools.find import FindTool
from .tools.grep import GrepTool
from .tools.ls import LsTool

SYSTEM_PROMPT = (
    "You are a coding assistant. You have access to tools to read, write, and edit files, "
    "run bash commands, search for files and content, and list directories.\n\n"
    "Guidelines:\n"
    "- Use read to examine files before editing them.\n"
    "- Use edit (with the edits array) instead of write when making targeted changes.\n"
    "- Use bash for running tests, builds, and shell commands.\n"
    "- Work methodically. When you finish, summarise what you did."
)


def _build_tools(cwd: str) -> list[Tool]:
    # Python tools resolve paths relative to os.getcwd(),
    # so we chdir to the workspace before running.
    # The cwd is applied in _run() via os.chdir().
    return [
        ReadTool(),
        WriteTool(),
        EditTool(),
        BashTool(),
        FindTool(),
        GrepTool(),
        LsTool(),
    ]


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _make_mock_provider(mock_turns: list[dict]):
    """Return a mock LLMProvider that replays the given turns."""
    from .ai.base import LLMProvider, StreamOptions
    from .ai.types import (
        AssistantMessage, StreamDone, TextDelta,
        ToolCall, ToolCallEnd, ToolCallStart,
    )

    _EMPTY_ASSISTANT = AssistantMessage(content=[])

    class MockProvider(LLMProvider):
        def __init__(self, turns: list[dict]) -> None:
            self._turns = turns
            self._idx = 0

        async def stream(self, messages, system_prompt, tools, opts):
            if self._idx >= len(self._turns):
                yield StreamDone(stop_reason="stop", message=_EMPTY_ASSISTANT)
                return

            turn = self._turns[self._idx]
            self._idx += 1

            if text := turn.get("text"):
                yield TextDelta(index=0, delta=text, partial=_EMPTY_ASSISTANT)

            for i, tc in enumerate(turn.get("tool_calls", [])):
                tc_id = tc.get("id") or f"mock-{self._idx}-{i}"
                yield ToolCallStart(index=i, partial=_EMPTY_ASSISTANT)
                yield ToolCallEnd(
                    index=i,
                    partial=_EMPTY_ASSISTANT,
                    tool_call=ToolCall(
                        id=tc_id,
                        name=tc["name"],
                        arguments=tc.get("args", {}),
                    ),
                )

            stop = turn.get("stop_reason", "end_turn")
            if stop in ("tool_use", "tool_calls"):
                yield StreamDone(stop_reason="tool_use", message=_EMPTY_ASSISTANT)
            else:
                yield StreamDone(stop_reason="stop", message=_EMPTY_ASSISTANT)

    return MockProvider(mock_turns)


async def _run(
    prompt: str,
    provider,
    cwd: str,
    api_key: str,
    model_id: str,
    max_turns: int,
) -> None:
    # Change to workspace directory so tools resolve relative paths correctly.
    os.chdir(cwd)
    tools = _build_tools(cwd)
    config = AgentConfig(
        api_key=api_key,
        model_id=model_id,
        max_turns=max_turns,
    )
    ctx = AgentContext(
        system_prompt=SYSTEM_PROMPT,
        messages=[],
        tools=tools,
        config=config,
    )

    turn = 0

    def emit(event: Any) -> None:
        nonlocal turn
        if isinstance(event, AgentStart):
            _emit({"type": "agent_start"})
        elif isinstance(event, TurnStart):
            turn += 1
            _emit({"type": "turn_start", "turn": turn})
        elif isinstance(event, TurnEnd):
            _emit({"type": "turn_end", "turn": turn})
        elif isinstance(event, ToolExecStart):
            _emit({"type": "tool_call", "id": event.id, "name": event.name, "args": event.args})
        elif isinstance(event, ToolExecUpdate):
            pass  # skip partial updates in headless mode
        elif isinstance(event, ToolExecEnd):
            _emit({
                "type": "tool_result",
                "id": event.id,
                "name": event.name,
                "content": event.result.content if event.result else "",
                "is_error": event.is_error,
            })
        elif isinstance(event, AgentEnd):
            _emit({"type": "agent_end", "turns": turn})
        elif isinstance(event, AgentError):
            _emit({"type": "error", "message": str(event.message)})

    await agent_loop(prompt, ctx, provider, emit)


def run() -> None:
    """Entry point for headless mode. Reads stdin, writes stdout."""
    raw = sys.stdin.read()
    try:
        inp = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"type": "error", "message": f"invalid JSON input: {exc}"})
        sys.exit(1)

    prompt: str = inp.get("prompt", "")
    mock_turns = inp.get("mock_turns")   # None means real LLM
    cwd: str = inp.get("cwd") or os.getcwd()

    # API key — allow dummy when using mock provider.
    api_key = (
        os.environ.get("KIMI_API_KEY")
        or os.environ.get("MOONSHOT_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "sk-test-dummy"
    )
    model_id = os.environ.get("PI_MODEL", "kimi-for-coding")
    max_turns = int(os.environ.get("PI_MAX_TURNS", "50"))

    if mock_turns is not None:
        provider = _make_mock_provider(mock_turns)
    else:
        provider_name = os.environ.get("PI_PROVIDER", "kimi")
        if provider_name == "openai":
            from .ai.openai import OpenAIProvider
            provider = OpenAIProvider()
        elif provider_name == "kimi":
            from .ai.openai import KimiProvider
            provider = KimiProvider()
        elif provider_name == "openrouter":
            from .ai.openai import OpenRouterProvider
            provider = OpenRouterProvider()
        else:
            from .ai.anthropic import AnthropicProvider
            provider = AnthropicProvider()

    asyncio.run(_run(prompt, provider, cwd, api_key, model_id, max_turns))
