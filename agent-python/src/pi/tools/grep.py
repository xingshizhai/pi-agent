# src/pi/tools/grep.py
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class GrepTool(Tool):
    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search for a regex pattern in a file or directory. Returns file:line:content."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "pattern": {"type": "string", "description": "Regex pattern"},
                "recursive": {"type": "boolean", "default": True},
                "ignore_case": {"type": "boolean", "default": False},
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
        path = Path(args.get("path", "."))
        pattern_str = args.get("pattern", "")
        recursive = args.get("recursive", True)
        ignore_case = args.get("ignore_case", False)

        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as e:
            return ToolResult.err(f"Invalid regex pattern: {e}")

        files: list[Path] = []
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(path.rglob("*") if recursive else path.iterdir())
            files = [f for f in files if f.is_file()]
        else:
            return ToolResult.err(f"Path not found: {path}")

        results: list[str] = []
        for file in files:
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{file}:{lineno}:{line}")

        if not results:
            return ToolResult.ok("No matches found.")
        return ToolResult.ok("\n".join(results))
