"""
Binary adapters for each agent implementation.

Every adapter exposes:
    adapter.run_headless(prompt, mock_turns, workspace_dir, env_overrides) -> list[Event]

The original pi agent (TypeScript) uses a different protocol and requires
a thin translation layer.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parents[2]

# Default timeout for headless runs (seconds).
DEFAULT_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class AgentAdapter(ABC):
    """Common interface for all agent implementations."""

    name: str  # e.g. "rust", "go", "python", "pi"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the binary / runtime exists."""

    @abstractmethod
    def run_headless(
        self,
        prompt: str,
        mock_turns: list[dict] | None,
        workspace_dir: str,
        env_overrides: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> list[dict]:
        """
        Run the agent and return a list of NDJSON event dicts.

        mock_turns=None → use real LLM.
        mock_turns=[]   → mock provider with zero turns (immediate end).
        """


# ---------------------------------------------------------------------------
# Standard headless adapter (Rust / Go / future Python)
# ---------------------------------------------------------------------------

class HeadlessAdapter(AgentAdapter):
    """
    Adapter for binaries that implement the standard PI_HEADLESS=1 protocol:
      stdin  → JSON: {"prompt": "...", "mock_turns": [...] | null}
      stdout → NDJSON events
    """

    def __init__(self, name: str, binary: str | Path):
        self.name = name
        self.binary = Path(binary)

    def is_available(self) -> bool:
        return self.binary.exists()

    def run_headless(
        self,
        prompt: str,
        mock_turns: list[dict] | None,
        workspace_dir: str,
        env_overrides: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> list[dict]:
        payload: dict[str, Any] = {"prompt": prompt}
        if mock_turns is not None:
            payload["mock_turns"] = mock_turns

        env = {**os.environ, "PI_HEADLESS": "1"}
        env.setdefault("ANTHROPIC_API_KEY", "sk-test-dummy")
        env.setdefault("OPENAI_API_KEY", "sk-test-dummy")
        if env_overrides:
            env.update({k: str(v) for k, v in env_overrides.items()})

        result = subprocess.run(
            [str(self.binary)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=workspace_dir,
            env=env,
            timeout=timeout,
        )

        stdout = result.stdout.strip()
        if result.returncode != 0 and not stdout:
            raise RuntimeError(
                f"[{self.name}] exited {result.returncode}: {result.stderr[:500]}"
            )

        events = []
        for lineno, line in enumerate(stdout.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"[{self.name}] bad NDJSON on line {lineno}: {line!r}: {exc}"
                ) from exc
        return events


# ---------------------------------------------------------------------------
# Original pi (TypeScript) adapter
# ---------------------------------------------------------------------------

class OriginalPiAdapter(AgentAdapter):
    """
    Adapter for the original earendil-works/pi agent.

    pi supports a --print flag that outputs JSON responses, but the event
    schema differs from our standard protocol.  We translate here.

    Requires: npx @earendil-works/pi-coding-agent to be resolvable.
    Mock mode is NOT supported for the original pi (it uses real LLM only).
    """

    name = "pi"

    def is_available(self) -> bool:
        return shutil.which("npx") is not None

    def run_headless(
        self,
        prompt: str,
        mock_turns: list[dict] | None,
        workspace_dir: str,
        env_overrides: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> list[dict]:
        if mock_turns is not None:
            raise NotImplementedError(
                "Original pi does not support mock_turns. "
                "Use layer=3 (real LLM) for pi comparison."
            )

        env = {**os.environ}
        if env_overrides:
            env.update({k: str(v) for k, v in env_overrides.items()})

        # Run pi in non-interactive print mode (JSON output).
        # pi --print outputs a stream of JSON messages.
        result = subprocess.run(
            ["npx", "--yes", "@earendil-works/pi-coding-agent",
             "--print", "--", prompt],
            capture_output=True,
            text=True,
            cwd=workspace_dir,
            env=env,
            timeout=timeout,
        )

        stdout = result.stdout.strip()
        if not stdout:
            raise RuntimeError(f"[pi] no output. stderr: {result.stderr[:500]}")

        return _translate_pi_output(stdout)


def _translate_pi_output(raw: str) -> list[dict]:
    """
    Translate original pi's JSON output to our standard NDJSON event schema.

    Original pi --print outputs a single JSON object or an array of turn objects.
    We map its fields to our event types as best-effort.
    """
    events: list[dict] = [{"type": "agent_start"}]
    turn = 0

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try NDJSON fallback.
        data = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    items = data if isinstance(data, list) else [data]

    for item in items:
        role = item.get("role", "")
        if role == "assistant":
            turn += 1
            events.append({"type": "turn_start", "turn": turn})
            # Extract tool calls.
            for block in item.get("content", []):
                if block.get("type") == "toolCall":
                    events.append({
                        "type": "tool_call",
                        "id":   block.get("id", ""),
                        "name": block.get("name", ""),
                        "args": block.get("arguments", {}),
                    })
        elif role == "toolResult":
            events.append({
                "type":     "tool_result",
                "id":       item.get("toolCallId", ""),
                "name":     item.get("toolName", ""),
                "content":  _extract_text(item.get("content", [])),
                "is_error": item.get("isError", False),
            })
            events.append({"type": "turn_end", "turn": turn})

    events.append({"type": "agent_end", "turns": turn})
    return events


def _extract_text(blocks: list[dict]) -> str:
    return "\n".join(
        b.get("text", "") for b in blocks if b.get("type") == "text"
    )


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def build_adapter(impl: str, binary_override: str | None = None) -> AgentAdapter:
    """
    Return an adapter for the named implementation.

    impl values: "rust", "go", "python", "pi"
    binary_override: explicit path to binary (optional).
    """
    if impl == "rust":
        binary = binary_override or REPO_ROOT / "agent-rust" / "target" / "release" / "pi"
        return HeadlessAdapter("rust", binary)

    if impl == "go":
        binary = binary_override or REPO_ROOT / "agent-go" / "pi"
        # Windows
        if not Path(str(binary)).exists():
            binary = str(binary) + ".exe"
        return HeadlessAdapter("go", binary)

    if impl == "python":
        # Python agent uses `uv run pi` — wrap in a shell script equivalent.
        binary = binary_override or REPO_ROOT / "agent-python" / "pi"
        return HeadlessAdapter("python", binary)

    if impl == "pi":
        return OriginalPiAdapter()

    raise ValueError(f"Unknown implementation: {impl!r}. Choose from: rust, go, python, pi")


def resolve_adapters(impls: list[str], binary_overrides: dict[str, str] | None = None) -> list[AgentAdapter]:
    """Build and validate a list of adapters, skipping unavailable ones."""
    adapters = []
    for impl in impls:
        override = (binary_overrides or {}).get(impl)
        adapter = build_adapter(impl, override)
        if adapter.is_available():
            adapters.append(adapter)
        else:
            print(f"  ⚠  [{impl}] binary not found — skipped")
    return adapters
