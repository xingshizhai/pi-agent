"""
Scenario runner: loads a YAML scenario and executes it against an adapter.

Layer 1 — tool unit tests (mock LLM, single tool call)
Layer 2 — behavior tests  (mock LLM, multi-turn scripted)
Layer 3 — task evaluation  (real LLM, verified by outcomes)
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from .adapter import AgentAdapter
from .assertions import (
    assert_agent_completed,
    assert_all_tool_results_success,
    assert_max_turns,
    assert_no_fatal_error,
    assert_tool_called,
    assert_tool_result,
    assert_turn_count,
    assert_workspace,
    assert_workspace_unchanged,
)
from .verifier import (
    TaskResult,
    VerifyResult,
    count_errors_recovered,
    count_tool_calls,
    count_turns,
    extract_agent_error,
    verify_task,
)
from .workspace import Workspace


def load_scenario(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Layer 1 / 2 runner — deterministic, assert-based
# ---------------------------------------------------------------------------

def run_behavior_scenario(
    adapter: AgentAdapter,
    scenario: dict,
    *,
    verbose: bool = False,
) -> tuple[bool, str]:
    """
    Run a Layer 1 or Layer 2 scenario.
    Returns (passed, message).
    """
    layer = scenario.get("layer", 1)
    env_overrides = scenario.get("env", {})

    if layer == 1:
        tc = scenario["tool_call"]
        mock_turns = [
            {
                "tool_calls": [
                    {"id": "t1", "name": tc["name"], "args": tc.get("args", {})}
                ],
                "stop_reason": "tool_use",
            },
            {"text": "Done.", "stop_reason": "end_turn"},
        ]
        prompt = scenario.get("prompt", f"Use the {tc['name']} tool")
    else:  # layer 2
        mock_turns = scenario.get("mock_turns")
        prompt = scenario.get("prompt", "complete the task")

    with Workspace() as ws:
        ws.setup(scenario.get("workspace", []))
        original_snap = ws.snapshot()

        try:
            events = adapter.run_headless(
                prompt, mock_turns, ws.dir, env_overrides=env_overrides
            )
        except (RuntimeError, ValueError) as exc:
            return False, f"FAIL: runtime error — {exc}"

        if verbose:
            for e in events:
                print(f"    event: {e}")

        try:
            _check_behavior(events, scenario, ws, original_snap)
        except AssertionError as exc:
            return False, f"FAIL: {exc}"

    return True, "PASS"


def _check_behavior(events, scenario, ws, original_snap):
    expect = scenario.get("expect", {})

    # Only treat error events as fatal if the scenario doesn't expect max_turns behaviour.
    if "max_turns" not in expect:
        assert_no_fatal_error(events)
    assert_agent_completed(events)

    # Layer 1 / Layer 2: single tool result check.
    if "tool_result" in expect:
        tr = expect["tool_result"]
        # Layer 1: tool name from tool_call key.
        # Layer 2: tool name from first mock_turns tool_call entry.
        tool_name = scenario.get("tool_call", {}).get("name", "")
        if not tool_name:
            mock_turns = scenario.get("mock_turns", [])
            for mt in mock_turns:
                calls = mt.get("tool_calls", [])
                if calls:
                    tool_name = calls[0].get("name", "")
                    break
        assert_tool_result(
            events, tool_name,
            is_error=tr.get("is_error", False),
            content_contains=tr.get("content_contains"),
            content_not_contains=tr.get("content_not_contains"),
        )

    # Layer 2: tool call count checks.
    for tc_exp in expect.get("tool_calls", []):
        assert_tool_called(events, tc_exp["name"], tc_exp.get("count", 1))

    if expect.get("tool_results_all_success"):
        assert_all_tool_results_success(events)

    if "turns" in expect:
        assert_turn_count(events, expect["turns"])

    if "max_turns" in expect:
        assert_max_turns(events, expect["max_turns"])

    # Workspace checks.
    if "workspace" in expect:
        assert_workspace(ws, expect["workspace"])

    if expect.get("workspace_unchanged"):
        assert_workspace_unchanged(ws, original_snap)


# ---------------------------------------------------------------------------
# Layer 3 runner — outcome-based evaluation
# ---------------------------------------------------------------------------

def run_task_scenario(
    adapter: AgentAdapter,
    scenario: dict,
    *,
    verbose: bool = False,
) -> TaskResult:
    """
    Run a Layer 3 task scenario with a real LLM.
    Evaluates completion via verify strategies, not code inspection.
    """
    task_name = scenario.get("name", "unnamed")
    env_overrides = scenario.get("env", {})
    timeout = scenario.get("timeout", 120)

    with Workspace() as ws:
        ws.setup(scenario.get("workspace", []))

        t0 = time.monotonic()
        error_msg = ""
        events: list[dict] = []
        try:
            events = adapter.run_headless(
                scenario["prompt"],
                mock_turns=None,   # real LLM
                workspace_dir=ws.dir,
                env_overrides=env_overrides,
                timeout=timeout,
            )
        except Exception as exc:
            error_msg = str(exc)

        latency = time.monotonic() - t0

        if verbose:
            for e in events:
                print(f"    event: {e}")

        # Analyse events.
        turns = count_turns(events)
        tool_call_count = count_tool_calls(events)
        errors_recovered = count_errors_recovered(events)
        if not error_msg:
            error_msg = extract_agent_error(events)

        # Run verify steps against the workspace.
        verify_steps = scenario.get("verify", [])
        verify_results: list[VerifyResult] = []
        if not error_msg and verify_steps:
            verify_results = verify_task(ws.dir, verify_steps, events)
        elif error_msg:
            verify_results = [
                VerifyResult("B", "agent_ran", False, 0.0, error_msg)
            ]

        passed = bool(verify_results) and all(r.passed for r in verify_results)

        return TaskResult(
            task_name=task_name,
            passed=passed,
            verify_results=verify_results,
            turns=turns,
            tool_calls=tool_call_count,
            errors_recovered=errors_recovered,
            latency_s=latency,
            error_message=error_msg,
        )
