# src/pi/agent/events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentStart:
    pass


@dataclass
class AgentEnd:
    messages: list[Any]


@dataclass
class TurnStart:
    pass


@dataclass
class TurnEnd:
    message: Any
    tool_results: list[Any]


@dataclass
class MessageStart:
    message: Any


@dataclass
class MessageUpdate:
    delta: str


@dataclass
class MessageEnd:
    message: Any


@dataclass
class ToolExecStart:
    id: str
    name: str
    args: dict


@dataclass
class ToolExecUpdate:
    id: str
    partial: str


@dataclass
class ToolExecEnd:
    id: str
    name: str
    result: Any
    is_error: bool


@dataclass
class AgentError:
    message: str


AgentEvent = (
    AgentStart | AgentEnd | TurnStart | TurnEnd |
    MessageStart | MessageUpdate | MessageEnd |
    ToolExecStart | ToolExecUpdate | ToolExecEnd |
    AgentError
)
