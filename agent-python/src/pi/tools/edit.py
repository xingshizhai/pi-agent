# src/pi/tools/edit.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class EditTool(Tool):
    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing exact text. Each oldText must appear exactly once. "
            "All edits are validated before writing — no partial writes on failure."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {
                                "type": "string",
                                "description": "Exact text to replace — must be unique in file",
                            },
                            "newText": {"type": "string"},
                        },
                        "required": ["oldText", "newText"],
                    },
                },
            },
            "required": ["path", "edits"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path_str = args.get("path", "")
        edits = args.get("edits", [])

        if not edits:
            return ToolResult.err("'edits' array is empty")

        path = Path(path_str)
        try:
            original = path.read_text(encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot read {path_str}: {e}")

        for edit in edits:
            old = edit.get("oldText", "")
            if not old:
                return ToolResult.err("An edit is missing 'oldText'")
            if "newText" not in edit:
                return ToolResult.err("An edit is missing 'newText'")

            count = original.count(old)
            if count == 0:
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult.err(f"oldText not found in file: {preview!r}")
            if count > 1:
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult.err(
                    f"oldText appears {count} times (must be unique): {preview!r}"
                )

        content = original
        for edit in edits:
            content = content.replace(edit["oldText"], edit["newText"], 1)

        try:
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot write {path_str}: {e}")

        return ToolResult.ok(f"{len(edits)} edit(s) applied to {path_str}")
