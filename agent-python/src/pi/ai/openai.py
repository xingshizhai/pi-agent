# src/pi/ai/openai.py
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import openai as sdk

from .base import LLMProvider, StreamOptions
from .types import (
    AssistantMessage, Message, StreamEvent, TextContent, ToolCall,
    ToolResultMessage, UserMessage,
    StreamStart, TextDelta, ToolCallEnd, StreamDone, Usage,
)
from ..tools.base import Tool


def _convert_messages_openai(messages: list[Message]) -> list[dict]:
    result: list[dict] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, str) else " ".join(c.text for c in msg.content)
            result.append({"role": "user", "content": content})
        elif isinstance(msg, AssistantMessage):
            tool_calls = []
            text_parts = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    text_parts.append(block.text)
                elif isinstance(block, ToolCall):
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {"name": block.name, "arguments": json.dumps(block.arguments)},
                    })
            entry: dict[str, Any] = {"role": "assistant", "content": " ".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)
        elif isinstance(msg, ToolResultMessage):
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": "\n".join(c.text for c in msg.content),
            })
    return result


class OpenAIProvider(LLMProvider):
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = sdk.AsyncOpenAI(api_key=options.api_key)

        oai_tools = [
            {"type": "function", "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }}
            for t in tools
        ]

        oai_messages = [{"role": "system", "content": system_prompt}]
        oai_messages.extend(_convert_messages_openai(messages))

        kwargs: dict[str, Any] = dict(
            model=options.model,
            messages=oai_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        if oai_tools:
            kwargs["tools"] = oai_tools

        partial = AssistantMessage(content=[])
        yield StreamStart(partial=partial)

        tool_args: dict[int, dict] = {}
        text_buf = ""

        async for chunk in await client.chat.completions.create(**kwargs):
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            if delta.content:
                text_buf += delta.content
                yield TextDelta(index=0, delta=delta.content, partial=partial)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_args:
                        tool_args[idx] = {"id": "", "name": "", "args_buf": ""}
                    if tc_delta.id:
                        tool_args[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_args[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_args[idx]["args_buf"] += tc_delta.function.arguments

            if choice.finish_reason in ("stop", "tool_calls", "length"):
                stop_reason = "stop" if choice.finish_reason == "stop" else "tool_use"
                for tc_info in tool_args.values():
                    try:
                        arguments = json.loads(tc_info["args_buf"]) if tc_info["args_buf"] else {}
                    except json.JSONDecodeError:
                        arguments = {}
                    tc = ToolCall(id=tc_info["id"], name=tc_info["name"], arguments=arguments)
                    partial.content.append(tc)
                    yield ToolCallEnd(index=0, tool_call=tc, partial=partial)

                if text_buf:
                    partial.content.append(TextContent(text=text_buf))

                if chunk.usage:
                    partial.usage = Usage(
                        input=chunk.usage.prompt_tokens,
                        output=chunk.usage.completion_tokens,
                    )
                partial.stop_reason = stop_reason
                yield StreamDone(stop_reason=stop_reason, message=partial)
                break
