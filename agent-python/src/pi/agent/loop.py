# src/pi/agent/loop.py
from __future__ import annotations

import asyncio
from typing import Any, Callable

from ..ai.types import (
    AssistantMessage, Message, TextContent, ToolCall, ToolResultMessage, UserMessage,
    StreamDone, StreamError, TextDelta, ToolCallEnd, StreamStart,
)
from ..ai.base import LLMProvider, StreamOptions
from ..tools.base import ToolResult
from .context import AgentContext
from .events import (
    AgentEnd, AgentError, AgentStart,
    MessageEnd, MessageUpdate,
    ToolExecEnd, ToolExecStart, ToolExecUpdate,
    TurnEnd, TurnStart,
)

Emit = Callable[[Any], None]


async def agent_loop(
    user_message: str,
    ctx: AgentContext,
    provider: LLMProvider,
    emit: Emit,
    signal: asyncio.Event | None = None,
) -> list[Message]:
    """Execute one agent turn: user message → LLM → tool calls → repeat → done."""
    new_messages: list[Message] = []

    user_msg = UserMessage(content=user_message)
    ctx.messages.append(user_msg)
    new_messages.append(user_msg)

    emit(AgentStart())

    for _turn in range(ctx.config.max_turns):
        emit(TurnStart())

        opts = StreamOptions(
            api_key=ctx.config.api_key,
            model=ctx.config.model_id,
        )

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        assistant_msg: AssistantMessage | None = None

        try:
            async for event in provider.stream(ctx.messages, ctx.system_prompt, ctx.tools, opts):
                if signal and signal.is_set():
                    emit(AgentEnd(messages=new_messages))
                    return new_messages

                if isinstance(event, TextDelta):
                    text_parts.append(event.delta)
                    emit(MessageUpdate(delta=event.delta))
                elif isinstance(event, ToolCallEnd):
                    tool_calls.append(event.tool_call)
                elif isinstance(event, (StreamDone, StreamError)):
                    assistant_msg = event.message
        except asyncio.CancelledError:
            emit(AgentEnd(messages=new_messages))
            return new_messages

        if assistant_msg is None:
            content: list[Any] = []
            if text_parts:
                content.append(TextContent(text="".join(text_parts)))
            content.extend(tool_calls)
            assistant_msg = AssistantMessage(content=content)

        ctx.messages.append(assistant_msg)
        new_messages.append(assistant_msg)
        emit(MessageEnd(message=assistant_msg))

        if not tool_calls:
            emit(TurnEnd(message=assistant_msg, tool_results=[]))
            break

        # Execute tools
        tool_results: list[ToolResultMessage] = []
        tool_map = ctx.tool_map()

        if ctx.config.tool_execution == "parallel":
            tasks = [
                _execute_tool(tc, tool_map, emit, signal)
                for tc in tool_calls
            ]
            results = await asyncio.gather(*tasks)
            tool_results = [r for r in results if r is not None]
        else:
            for tc in tool_calls:
                r = await _execute_tool(tc, tool_map, emit, signal)
                if r is not None:
                    tool_results.append(r)

        for tr in tool_results:
            ctx.messages.append(tr)
            new_messages.append(tr)

        emit(TurnEnd(message=assistant_msg, tool_results=tool_results))
    else:
        emit(AgentError(message=f"Max turns ({ctx.config.max_turns}) exceeded"))

    emit(AgentEnd(messages=new_messages))
    return new_messages


async def _execute_tool(
    tc: ToolCall,
    tool_map: dict,
    emit: Emit,
    signal: asyncio.Event | None,
) -> ToolResultMessage | None:
    emit(ToolExecStart(id=tc.id, name=tc.name, args=tc.arguments))

    tool = tool_map.get(tc.name)
    if tool is None:
        result = ToolResult.err(f"Unknown tool: {tc.name}")
    else:
        def on_update(partial: str) -> None:
            emit(ToolExecUpdate(id=tc.id, partial=partial))

        try:
            result = await tool.execute(tc.id, tc.arguments, signal=signal, on_update=on_update)
        except Exception as e:
            result = ToolResult.err(f"Tool execution error: {e}")

    emit(ToolExecEnd(id=tc.id, name=tc.name, result=result, is_error=result.is_error))

    return ToolResultMessage(
        tool_call_id=tc.id,
        tool_name=tc.name,
        content=[TextContent(text=result.content)],
        is_error=result.is_error,
        details=result.details,
    )
