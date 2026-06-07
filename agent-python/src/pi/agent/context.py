# src/pi/agent/context.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ai.types import Message
    from ..tools.base import Tool


@dataclass
class AgentConfig:
    model_id: str
    api_key: str
    provider_name: str = "anthropic"
    tool_execution: str = "parallel"   # "sequential" | "parallel"
    max_turns: int = 50


@dataclass
class AgentContext:
    system_prompt: str
    messages: list["Message"]
    tools: list["Tool"]
    config: AgentConfig

    def tool_map(self) -> dict[str, "Tool"]:
        return {t.name: t for t in self.tools}
