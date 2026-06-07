# src/pi/tools/base.py
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    terminate: bool = False
    details: Any = None

    @classmethod
    def ok(cls, content: str, details: Any = None) -> "ToolResult":
        return cls(content=content, details=details)

    @classmethod
    def err(cls, content: str) -> "ToolResult":
        return cls(content=content, is_error=True)


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema object for tool parameters."""
        ...

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult: ...
