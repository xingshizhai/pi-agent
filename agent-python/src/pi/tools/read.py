# src/pi/tools/read.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult

MAX_LINES = 2000
MAX_BYTES = 200 * 1024  # 200KB


class ReadTool(Tool):
    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Returns line-numbered content. "
            "Use offset and limit for large files."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file (relative or absolute)"},
                "offset": {"type": "number", "description": "Line number to start from (1-indexed)"},
                "limit": {"type": "number", "description": "Maximum number of lines to read"},
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
        path_str = args.get("path", "")
        offset = int(args.get("offset", 1))
        limit = args.get("limit")

        path = Path(path_str)
        if not path.exists():
            return ToolResult.err(f"File not found: {path_str}")
        if not path.is_file():
            return ToolResult.err(f"Not a file: {path_str}")

        try:
            raw = path.read_bytes()
        except OSError as e:
            return ToolResult.err(f"Cannot read {path_str}: {e}")

        byte_truncated = len(raw) > MAX_BYTES
        if byte_truncated:
            raw = raw[:MAX_BYTES]

        text = raw.decode("utf-8", errors="replace")
        all_lines = text.splitlines()
        total = len(all_lines)

        start = max(0, offset - 1)
        end = start + (int(limit) if limit is not None else MAX_LINES)
        end = min(end, start + MAX_LINES)
        slice_lines = all_lines[start:end]

        lines_shown_start = start + 1
        lines_shown_end = start + len(slice_lines)

        numbered = "\n".join(f"{lines_shown_start + i}\t{line}" for i, line in enumerate(slice_lines))

        truncated = end < total or byte_truncated
        if truncated:
            numbered += f"\n[Showing lines {lines_shown_start}-{lines_shown_end} of {total}. Use offset={lines_shown_end + 1} to continue.]"

        return ToolResult.ok(numbered)
