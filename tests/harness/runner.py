import subprocess, json, os, sys
from pathlib import Path
from typing import Optional

TIMEOUT = 30  # seconds

def run_binary(binary: str, prompt: str, mock_turns=None, cwd: str = ".") -> list[dict]:
    """Run agent binary in headless mode, return parsed NDJSON events."""
    inp = {"prompt": prompt}
    if mock_turns is not None:
        inp["mock_turns"] = mock_turns

    env = {**os.environ, "PI_HEADLESS": "1"}
    # Ensure a dummy key exists so key-check in main() passes
    env.setdefault("OPENROUTER_API_KEY", "sk-test-dummy")

    result = subprocess.run(
        [binary],
        input=json.dumps(inp),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=TIMEOUT,
    )

    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"Binary exited {result.returncode}: {result.stderr[:500]}")

    events = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Bad NDJSON line: {line!r}: {e}")
    return events


def run_scenario(binary: str, scenario: dict, workspace_dir: str) -> list[dict]:
    """Run a full scenario (layer 1 or 2) against a binary."""
    layer = scenario.get("layer", 1)

    if layer == 1:
        # Auto-generate mock_turns from single tool_call
        tc = scenario["tool_call"]
        mock_turns = [
            {
                "tool_calls": [{"id": "t1", "name": tc["name"], "args": tc.get("args", {})}],
                "stop_reason": "tool_use",
            },
            {
                "text": "done",
                "stop_reason": "end_turn",
            },
        ]
        prompt = scenario.get("prompt", f"call the {tc['name']} tool")
    elif layer == 2:
        mock_turns = scenario.get("mock_turns")
        prompt = scenario.get("prompt", "do the task")
    else:
        mock_turns = None  # real LLM
        prompt = scenario["prompt"]

    return run_binary(binary, prompt, mock_turns=mock_turns, cwd=workspace_dir)
