# src/pi/tools/ls.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class LsTool(Tool):
    @property
    def name(self) -> str:
        return "ls"

    @property
    def description(self) -> str:
        return "List the direct contents of a directory (non-recursive)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path = Path(args.get("path", "."))
        if not path.exists():
            return ToolResult.err(f"Path not found: {path}")
        if not path.is_dir():
            return ToolResult.err(f"Not a directory: {path}")

        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines: list[str] = []
        for entry in entries:
            kind = "file" if entry.is_file() else "dir"
            size = entry.stat().st_size if entry.is_file() else 0
            lines.append(f"{kind}\t{entry.name}\t{size}")

        if not lines:
            return ToolResult.ok("(empty directory)")
        return ToolResult.ok("\n".join(lines))
