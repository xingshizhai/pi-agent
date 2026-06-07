"""
Deterministic assertions for Layer 1 (tool unit) and Layer 2 (behavior) tests.
These run against mock-provider output, so results are fully predictable.
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def find_events(events: list[dict], type_: str) -> list[dict]:
    return [e for e in events if e.get("type") == type_]


# ---------------------------------------------------------------------------
# Core assertions
# ---------------------------------------------------------------------------

def assert_no_fatal_error(events: list[dict]) -> None:
    """Fail if a fatal 'error' event was emitted (not tool-level errors)."""
    errs = find_events(events, "error")
    assert not errs, f"Fatal error event(s): {errs}"


def assert_agent_completed(events: list[dict]) -> None:
    ends = find_events(events, "agent_end")
    assert ends, f"No agent_end event. Got: {[e.get('type') for e in events]}"


def assert_turn_count(events: list[dict], expected: int) -> None:
    starts = find_events(events, "turn_start")
    assert len(starts) == expected, (
        f"Expected {expected} turn(s), got {len(starts)}"
    )


def assert_max_turns(events: list[dict], max_turns: int) -> None:
    starts = find_events(events, "turn_start")
    assert len(starts) <= max_turns, (
        f"Expected at most {max_turns} turn(s), got {len(starts)}"
    )


# ---------------------------------------------------------------------------
# Tool call assertions
# ---------------------------------------------------------------------------

def assert_tool_called(events: list[dict], name: str, count: int = 1) -> None:
    calls = [e for e in events if e.get("type") == "tool_call" and e.get("name") == name]
    assert len(calls) == count, (
        f"Expected {count} call(s) to '{name}', got {len(calls)}"
    )


def assert_tool_result(
    events: list[dict],
    tool_name: str,
    *,
    is_error: bool = False,
    content_contains: Optional[str] = None,
    content_not_contains: Optional[str] = None,
) -> None:
    results = [
        e for e in events
        if e.get("type") == "tool_result" and e.get("name") == tool_name
    ]
    assert results, (
        f"No tool_result for '{tool_name}'. "
        f"Events: {[e.get('type') for e in events]}"
    )
    r = results[0]
    assert r.get("is_error") == is_error, (
        f"Expected is_error={is_error} for '{tool_name}', "
        f"got {r.get('is_error')}. Content: {r.get('content', '')[:200]}"
    )
    content = r.get("content", "")
    if content_contains is not None:
        assert content_contains in content, (
            f"Expected {content_contains!r} in tool_result content.\n"
            f"Got: {content[:300]}"
        )
    if content_not_contains is not None:
        assert content_not_contains not in content, (
            f"Did not expect {content_not_contains!r} in tool_result content.\n"
            f"Got: {content[:300]}"
        )


def assert_all_tool_results_success(events: list[dict]) -> None:
    results = find_events(events, "tool_result")
    failed = [r for r in results if r.get("is_error")]
    assert not failed, (
        f"{len(failed)} tool result(s) had is_error=True: "
        + ", ".join(r.get("name", "?") for r in failed)
    )


# ---------------------------------------------------------------------------
# Workspace assertions
# ---------------------------------------------------------------------------

def assert_workspace(workspace, expect: list[dict]) -> None:
    """
    Check file expectations against a Workspace object.

    Each entry may have:
      path:    required
      content: exact file content (optional)
      absent:  true = file must NOT exist (optional)
    """
    for entry in expect:
        path = entry["path"]
        if entry.get("absent"):
            assert not workspace.exists(path), (
                f"Expected file {path!r} to be absent"
            )
        else:
            assert workspace.exists(path), (
                f"Expected file {path!r} to exist"
            )
            if "content" in entry:
                actual = workspace.read(path)
                assert actual == entry["content"], (
                    f"File {path!r}:\n"
                    f"  Expected: {entry['content']!r}\n"
                    f"  Got:      {actual!r}"
                )


def assert_workspace_unchanged(workspace, original_snapshot: dict) -> None:
    current = workspace.snapshot()
    assert current == original_snapshot, (
        f"Workspace changed unexpectedly.\n"
        f"Before: {list(original_snapshot)}\n"
        f"After:  {list(current)}"
    )
