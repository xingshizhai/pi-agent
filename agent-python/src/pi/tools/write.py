# src/pi/tools/write.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class WriteTool(Tool):
    @property
    def name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return "Write content to a file, creating parent directories as needed. Overwrites existing files."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path_str = args.get("path", "")
        content = args.get("content", "")

        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot write {path_str}: {e}")

        return ToolResult.ok(f"Written {len(content)} bytes to {path_str}")
