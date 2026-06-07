# src/pi/ai/anthropic.py
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import anthropic as sdk

from .base import LLMProvider, StreamOptions
from .types import (
    AssistantMessage, Message, StreamEvent, TextContent, ThinkingContent,
    ToolCall, ToolResultMessage, UserMessage,
    StreamStart, TextStart, TextDelta, TextEnd,
    ToolCallStart, ToolCallDelta, ToolCallEnd,
    StreamDone, Usage,
)
from ..tools.base import Tool


def convert_messages(messages: list[Message]) -> list[dict]:
    """Convert internal Message list to Anthropic API wire format.

    Rules:
    - ToolResultMessages accumulate into a pending list, flushed as a single
      user message (content: list[tool_result blocks]) when a non-ToolResult
      message is encountered, or at the end.
    - AssistantMessage ToolCall blocks → type:tool_use with 'input' field.
    """
    result: list[dict] = []
    pending_tool_results: list[dict] = []

    for msg in messages:
        if isinstance(msg, ToolResultMessage):
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": [{"type": "text", "text": c.text} for c in msg.content],
                "is_error": msg.is_error,
            })
        else:
            if pending_tool_results:
                result.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

            if isinstance(msg, UserMessage):
                result.append({
                    "role": "user",
                    "content": msg.content
                    if isinstance(msg.content, str)
                    else [{"type": "text", "text": c.text} for c in msg.content],
                })
            elif isinstance(msg, AssistantMessage):
                content_blocks: list[dict] = []
                for block in msg.content:
                    if isinstance(block, TextContent):
                        content_blocks.append({"type": "text", "text": block.text})
                    elif isinstance(block, ThinkingContent):
                        content_blocks.append({
                            "type": "thinking",
                            "thinking": block.thinking,
                            "signature": block.thinking_signature or "",
                        })
                    elif isinstance(block, ToolCall):
                        content_blocks.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.arguments,
                        })
                result.append({"role": "assistant", "content": content_blocks})

    if pending_tool_results:
        result.append({"role": "user", "content": pending_tool_results})

    return result


def convert_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


class AnthropicProvider(LLMProvider):
    def __init__(self, *, trust_env: bool = False) -> None:
        import httpx
        self._http = httpx.AsyncClient(trust_env=trust_env)

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = sdk.AsyncAnthropic(
            api_key=options.api_key,
            http_client=self._http,
        )

        partial = AssistantMessage(content=[])
        yield StreamStart(partial=partial)

        current_block_type: str | None = None
        current_tool_id: str | None = None
        current_tool_name: str | None = None
        tool_args_buf: str = ""
        current_index: int = 0
        text_buf: str = ""

        stream_kwargs: dict[str, Any] = dict(
            model=options.model,
            max_tokens=options.max_tokens,
            system=system_prompt,
            messages=convert_messages(messages),
        )
        if tools:
            stream_kwargs["tools"] = convert_tools(tools)
        if options.temperature is not None:
            stream_kwargs["temperature"] = options.temperature

        async with client.messages.stream(**stream_kwargs) as s:
            async for event in s:
                etype = event.type

                if etype == "content_block_start":
                    current_index = event.index
                    cb = event.content_block
                    current_block_type = cb.type
                    if cb.type == "text":
                        text_buf = ""
                        yield TextStart(index=current_index, partial=partial)
                    elif cb.type == "tool_use":
                        current_tool_id = cb.id
                        current_tool_name = cb.name
                        tool_args_buf = ""
                        yield ToolCallStart(index=current_index, partial=partial)

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        text_buf += delta.text
                        yield TextDelta(index=current_index, delta=delta.text, partial=partial)
                    elif delta.type == "input_json_delta":
                        tool_args_buf += delta.partial_json
                        yield ToolCallDelta(index=current_index, delta=delta.partial_json, partial=partial)

                elif etype == "content_block_stop":
                    if current_block_type == "text" and text_buf:
                        yield TextEnd(index=current_index, content=text_buf, partial=partial)
                        partial.content.append(TextContent(text=text_buf))
                        text_buf = ""
                    elif current_block_type == "tool_use" and current_tool_id:
                        try:
                            arguments = json.loads(tool_args_buf) if tool_args_buf else {}
                        except json.JSONDecodeError:
                            arguments = {}
                        tc = ToolCall(id=current_tool_id, name=current_tool_name or "", arguments=arguments)
                        partial.content.append(tc)
                        yield ToolCallEnd(index=current_index, tool_call=tc, partial=partial)
                        current_tool_id = None
                        current_tool_name = None
                        tool_args_buf = ""
                    current_block_type = None

                elif etype == "message_stop":
                    final = await s.get_final_message()
                    partial.model = final.model
                    partial.stop_reason = final.stop_reason or "stop"
                    partial.usage = Usage(
                        input=final.usage.input_tokens,
                        output=final.usage.output_tokens,
                        cache_read=getattr(final.usage, "cache_read_input_tokens", 0) or 0,
                        cache_write=getattr(final.usage, "cache_creation_input_tokens", 0) or 0,
                    )
                    yield StreamDone(stop_reason=partial.stop_reason, message=partial)
