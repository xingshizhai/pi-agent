# src/pi/ai/types.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Content blocks ────────────────────────────────────────────────────────────

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    thinking_signature: str | None = None


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


class Usage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


# ── Messages ──────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str | list[TextContent]
    timestamp: int = Field(default_factory=_now_ms)


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ThinkingContent | ToolCall]
    api: str = ""
    provider: str = ""
    model: str = ""
    usage: Usage = Field(default_factory=Usage)
    stop_reason: str = "stop"
    error_message: str | None = None
    timestamp: int = Field(default_factory=_now_ms)


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: list[TextContent]
    details: Any = None
    is_error: bool = False
    timestamp: int = Field(default_factory=_now_ms)


Message = UserMessage | AssistantMessage | ToolResultMessage


# ── Stream events (dataclasses for lightweight construction) ──────────────────

@dataclass
class StreamStart:
    partial: AssistantMessage


@dataclass
class TextStart:
    index: int
    partial: AssistantMessage


@dataclass
class TextDelta:
    index: int
    delta: str
    partial: AssistantMessage


@dataclass
class TextEnd:
    index: int
    content: str
    partial: AssistantMessage


@dataclass
class ToolCallStart:
    index: int
    partial: AssistantMessage


@dataclass
class ToolCallDelta:
    index: int
    delta: str
    partial: AssistantMessage


@dataclass
class ToolCallEnd:
    index: int
    tool_call: ToolCall
    partial: AssistantMessage


@dataclass
class StreamDone:
    stop_reason: str
    message: AssistantMessage


@dataclass
class StreamError:
    stop_reason: str
    error: AssistantMessage


StreamEvent = (
    StreamStart | TextStart | TextDelta | TextEnd |
    ToolCallStart | ToolCallDelta | ToolCallEnd |
    StreamDone | StreamError
)
