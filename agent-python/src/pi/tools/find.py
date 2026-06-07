# src/pi/tools/find.py
from __future__ import annotations

import asyncio
import fnmatch
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class FindTool(Tool):
    @property
    def name(self) -> str:
        return "find"

    @property
    def description(self) -> str:
        return "Recursively find files or directories matching a glob pattern."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Filename glob pattern (e.g. *.py)"},
                "type": {
                    "type": "string",
                    "enum": ["file", "dir", "any"],
                    "description": "Filter by entry type",
                },
            },
            "required": ["path", "pattern"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        root = Path(args.get("path", "."))
        pattern = args.get("pattern", "*")
        type_filter = args.get("type", "any")

        if not root.exists():
            return ToolResult.err(f"Path not found: {root}")

        matches: list[str] = []
        for entry in root.rglob("*"):
            if not fnmatch.fnmatch(entry.name, pattern):
                continue
            if type_filter == "file" and not entry.is_file():
                continue
            if type_filter == "dir" and not entry.is_dir():
                continue
            matches.append(str(entry.relative_to(root)))

        matches.sort()
        if not matches:
            return ToolResult.ok("No matches found.")
        return ToolResult.ok("\n".join(matches))
