# tests/test_agent_loop.py
from __future__ import annotations

import asyncio
import pytest
from typing import AsyncGenerator

from pi.ai.types import (
    AssistantMessage, TextContent, ToolCall, ToolResultMessage,
    UserMessage, StreamDone, TextDelta, TextStart, TextEnd, StreamStart,
    ToolCallEnd,
)
from pi.agent.context import AgentContext, AgentConfig
from pi.agent.events import (
    AgentStart, AgentEnd, TurnStart, TurnEnd,
    MessageUpdate, ToolExecStart, ToolExecEnd,
)
from pi.agent.loop import agent_loop
from pi.tools.base import Tool, ToolResult


class EchoTool(Tool):
    @property
    def name(self): return "echo"
    @property
    def description(self): return "Echo a message"
    @property
    def parameters(self):
        return {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}

    async def execute(self, tool_call_id, args, signal=None, on_update=None):
        return ToolResult.ok(f"echo: {args.get('message', '')}")


def make_context(tools=None):
    return AgentContext(
        system_prompt="You are helpful.",
        messages=[],
        tools=tools or [],
        config=AgentConfig(model_id="claude-sonnet-4-6", api_key="test-key"),
    )


class SimpleTextProvider:
    """Provider that returns a single text response."""
    async def stream(self, messages, system_prompt, tools, options) -> AsyncGenerator:
        partial = AssistantMessage(content=[TextContent(text="Hello!")], stop_reason="stop")
        yield StreamStart(partial=AssistantMessage(content=[]))
        yield TextDelta(index=0, delta="Hello!", partial=partial)
        yield StreamDone(stop_reason="stop", message=partial)


class ToolCallProvider:
    """Provider that first returns a tool call, then a text response."""
    def __init__(self):
        self.call_count = 0

    async def stream(self, messages, system_prompt, tools, options) -> AsyncGenerator:
        self.call_count += 1
        if self.call_count == 1:
            tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "world"})
            msg = AssistantMessage(content=[tool_call], stop_reason="tool_use")
            yield StreamStart(partial=AssistantMessage(content=[]))
            yield ToolCallEnd(index=0, tool_call=tool_call, partial=msg)
            yield StreamDone(stop_reason="tool_use", message=msg)
        else:
            final = AssistantMessage(content=[TextContent(text="Done!")], stop_reason="stop")
            yield StreamStart(partial=AssistantMessage(content=[]))
            yield TextDelta(index=0, delta="Done!", partial=final)
            yield StreamDone(stop_reason="stop", message=final)


class InfiniteToolProvider:
    """Provider that always returns a tool call (tests max_turns)."""
    async def stream(self, messages, system_prompt, tools, options) -> AsyncGenerator:
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "loop"})
        msg = AssistantMessage(content=[tool_call], stop_reason="tool_use")
        yield StreamStart(partial=AssistantMessage(content=[]))
        yield ToolCallEnd(index=0, tool_call=tool_call, partial=msg)
        yield StreamDone(stop_reason="tool_use", message=msg)


@pytest.mark.asyncio
async def test_simple_text_response():
    events = []
    ctx = make_context()
    await agent_loop("hi", ctx, SimpleTextProvider(), lambda e: events.append(e))

    assert any(isinstance(e, AgentStart) for e in events)
    assert any(isinstance(e, AgentEnd) for e in events)
    assert any(isinstance(e, MessageUpdate) and "Hello!" in e.delta for e in events)
    assert any(isinstance(m, AssistantMessage) for m in ctx.messages)


@pytest.mark.asyncio
async def test_tool_call_execution():
    provider = ToolCallProvider()
    events = []
    ctx = make_context(tools=[EchoTool()])
    await agent_loop("say world", ctx, provider, lambda e: events.append(e))

    assert provider.call_count == 2
    assert any(isinstance(e, ToolExecStart) and e.name == "echo" for e in events)
    assert any(isinstance(e, ToolExecEnd) and not e.is_error for e in events)
    assert any(isinstance(m, ToolResultMessage) for m in ctx.messages)


@pytest.mark.asyncio
async def test_max_turns_exceeded():
    events = []
    ctx = make_context(tools=[EchoTool()])
    ctx.config.max_turns = 3
    await agent_loop("loop", ctx, InfiniteToolProvider(), lambda e: events.append(e))
    assert any(isinstance(e, AgentEnd) for e in events)


@pytest.mark.asyncio
async def test_cancellation():
    signal = asyncio.Event()

    class SlowProvider:
        async def stream(self, *a, **kw) -> AsyncGenerator:
            yield StreamStart(partial=AssistantMessage(content=[]))
            await asyncio.sleep(10)
            yield StreamDone(stop_reason="stop", message=AssistantMessage(content=[]))

    events = []
    ctx = make_context()

    async def run():
        await agent_loop("go", ctx, SlowProvider(), lambda e: events.append(e), signal=signal)

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    signal.set()
    await asyncio.wait_for(task, timeout=2.0)

    assert any(isinstance(e, AgentEnd) for e in events)
