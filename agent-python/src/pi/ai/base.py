# src/pi/ai/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator

from .types import Message, StreamEvent
from ..tools.base import Tool


@dataclass
class StreamOptions:
    api_key: str
    model: str
    max_tokens: int = 8192
    temperature: float | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamEvent objects as the LLM responds."""
        ...
