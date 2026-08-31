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
    """OpenAI Chat Completions provider.

    Pass ``base_url`` to use an OpenAI-compatible endpoint (e.g. OpenRouter).
    """

    def __init__(
        self,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url
        self._default_headers = default_headers

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = sdk.AsyncOpenAI(
            api_key=options.api_key,
            base_url=self._base_url,
            default_headers=self._default_headers,
        )

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


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Kimi Code（Coding Plan，sk-kimi- 密钥）— 见 https://www.kimi.com/code/docs
KIMI_CODING_BASE_URL = "https://api.kimi.com/coding/v1"
# Kimi Platform（按量计费，Moonshot 开放平台）
MOONSHOT_PLATFORM_BASE_URL = "https://api.moonshot.ai/v1"


def kimi_base_url() -> str:
    import os
    return os.environ.get("KIMI_API_BASE_URL", KIMI_CODING_BASE_URL)


KIMI_CODING_USER_AGENT = "claude-code/0.1.0"


class KimiProvider(OpenAIProvider):
    """Kimi Code API（Coding Plan）或 Kimi Platform，均为 OpenAI 兼容协议。

    Coding Plan（api.kimi.com/coding）要求客户端 User-Agent 在白名单内
    （如 Kimi CLI、Claude Code）；可通过 KIMI_USER_AGENT 覆盖。
    """

    def __init__(self, base_url: str | None = None) -> None:
        import os
        url = base_url or kimi_base_url()
        headers: dict[str, str] | None = None
        if "api.kimi.com/coding" in url:
            ua = os.environ.get("KIMI_USER_AGENT", KIMI_CODING_USER_AGENT)
            headers = {"User-Agent": ua}
        super().__init__(base_url=url, default_headers=headers)


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter provider — OpenAI-compatible endpoint at openrouter.ai.

    Uses ``OPENROUTER_API_KEY`` (or falls back to ``OPENAI_API_KEY``).
    Model names follow OpenRouter convention, e.g.:
      - anthropic/claude-sonnet-4-5
      - openai/gpt-4o
      - google/gemma-2-9b-it:free
    """

    def __init__(self) -> None:
        super().__init__(base_url=OPENROUTER_BASE_URL)
