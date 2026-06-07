# src/pi/tools/bash.py
from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from .base import Tool, ToolResult

MAX_OUTPUT_BYTES = 200 * 1024  # 200KB
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class BashTool(Tool):
    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. stdout and stderr are merged. "
            "Use timeout (seconds) to limit execution time."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (optional, no default)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_chunks: list[bytes] = []
        total_bytes = 0
        truncated = False

        async def read_output() -> None:
            nonlocal total_bytes, truncated
            assert proc.stdout is not None
            async for chunk in proc.stdout:
                if total_bytes + len(chunk) > MAX_OUTPUT_BYTES:
                    remaining = MAX_OUTPUT_BYTES - total_bytes
                    if remaining > 0:
                        output_chunks.append(chunk[:remaining])
                    truncated = True
                    break
                output_chunks.append(chunk)
                total_bytes += len(chunk)
                if on_update:
                    on_update(chunk.decode("utf-8", errors="replace"))

        try:
            coro = asyncio.gather(read_output(), proc.wait())
            if timeout is not None:
                await asyncio.wait_for(coro, timeout=float(timeout))
            else:
                await coro
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return ToolResult.err(f"Command timed out after {timeout}s")
        except asyncio.CancelledError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise

        raw = b"".join(output_chunks).decode("utf-8", errors="replace")
        output = _strip_ansi(raw)
        if truncated:
            output += f"\n[Output truncated at {MAX_OUTPUT_BYTES // 1024}KB]"

        if proc.returncode != 0:
            return ToolResult(
                content=output or f"Command exited with code {proc.returncode}",
                is_error=True,
            )

        return ToolResult.ok(output)
