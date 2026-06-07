from typing import Optional

def find_events(events: list[dict], type_: str) -> list[dict]:
    return [e for e in events if e.get("type") == type_]

def assert_no_error(events: list[dict]):
    errs = find_events(events, "error")
    assert not errs, f"Unexpected error events: {errs}"

def assert_agent_completed(events: list[dict]):
    ends = find_events(events, "agent_end")
    assert ends, f"No agent_end event found. Events: {events}"

def assert_tool_result(events: list[dict], tool_name: str,
                       is_error: bool = False,
                       content_contains: Optional[str] = None,
                       content_not_contains: Optional[str] = None):
    results = [e for e in events if e.get("type") == "tool_result" and e.get("name") == tool_name]
    assert results, f"No tool_result for tool '{tool_name}'. Events: {events}"
    r = results[0]
    assert r.get("is_error") == is_error, \
        f"Expected is_error={is_error} for {tool_name}, got {r.get('is_error')}. Content: {r.get('content')}"
    if content_contains:
        assert content_contains in r.get("content", ""), \
            f"Expected '{content_contains}' in tool_result content, got: {r.get('content')!r}"
    if content_not_contains:
        assert content_not_contains not in r.get("content", ""), \
            f"Did not expect '{content_not_contains}' in tool_result content"

def assert_workspace(workspace, expect: list[dict], original_snapshot: Optional[dict] = None):
    """Check workspace file expectations."""
    for entry in expect:
        path = entry["path"]
        if "content" in entry:
            assert workspace.exists(path), f"Expected file {path!r} to exist"
            actual = workspace.read(path)
            assert actual == entry["content"], \
                f"File {path!r}: expected {entry['content']!r}, got {actual!r}"
        if entry.get("absent"):
            assert not workspace.exists(path), f"Expected file {path!r} to be absent"

def assert_workspace_unchanged(workspace, original_snapshot: dict):
    current = workspace.snapshot()
    assert current == original_snapshot, \
        f"Workspace changed unexpectedly.\nBefore: {original_snapshot}\nAfter: {current}"

def assert_tool_calls(events: list[dict], name: str, count: int = 1):
    calls = [e for e in events if e.get("type") == "tool_call" and e.get("name") == name]
    assert len(calls) == count, \
        f"Expected {count} tool_call(s) for '{name}', got {len(calls)}"

def assert_turns(events: list[dict], count: int):
    starts = find_events(events, "turn_start")
    assert len(starts) == count, f"Expected {count} turn(s), got {len(starts)}"
