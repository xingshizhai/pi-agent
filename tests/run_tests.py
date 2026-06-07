#!/usr/bin/env python3
"""
Test runner for pi-agent cross-language test suite.

Usage:
  python tests/run_tests.py --binary agent-rust/target/release/pi
  python tests/run_tests.py --binary agent-rust/target/release/pi --layer 1
  python tests/run_tests.py --binary agent-rust/target/release/pi --layer 2
  python tests/run_tests.py --binary agent-rust/target/release/pi --compare agent-go/pi
"""
import argparse, sys, os, yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness.runner import run_scenario
from harness.workspace import Workspace
from harness import assertions as A

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

LAYER_DIRS = {
    1: SCENARIOS_DIR / "layer1-tools",
    2: SCENARIOS_DIR / "layer2-loop",
}

def run_assertion(events, scenario, ws, original_snap):
    expect = scenario.get("expect", {})

    A.assert_no_error(events)
    A.assert_agent_completed(events)

    # tool_result assertions (layer 1)
    if "tool_result" in expect:
        tr = expect["tool_result"]
        tool_name = scenario.get("tool_call", {}).get("name", "")
        A.assert_tool_result(
            events, tool_name,
            is_error=tr.get("is_error", False),
            content_contains=tr.get("content_contains"),
            content_not_contains=tr.get("content_not_contains"),
        )

    # workspace assertions
    if "workspace" in expect:
        A.assert_workspace(ws, expect["workspace"])

    if expect.get("workspace_unchanged"):
        A.assert_workspace_unchanged(ws, original_snap)

    # tool_calls count assertions (layer 2)
    for tc_expect in expect.get("tool_calls", []):
        A.assert_tool_calls(events, tc_expect["name"], tc_expect.get("count", 1))

    # all tool results succeeded
    if expect.get("tool_results_all_success"):
        results = A.find_events(events, "tool_result")
        failed = [r for r in results if r.get("is_error")]
        assert not failed, f"Some tool calls failed: {failed}"

    # turn count
    if "turns" in expect:
        A.assert_turns(events, expect["turns"])

    # max_turns check
    if "max_turns" in expect:
        actual = A.find_events(events, "turn_start")
        assert len(actual) <= expect["max_turns"], \
            f"Expected at most {expect['max_turns']} turns, got {len(actual)}"


def run_test(binary: str, scenario_path: Path, extra_env: dict = None) -> tuple[bool, str]:
    """Returns (passed, message)."""
    with open(scenario_path) as f:
        scenario = yaml.safe_load(f)

    # Apply scenario-level env overrides
    env_overrides = {**scenario.get("env", {}), **(extra_env or {})}
    saved_env = {}
    for k, v in env_overrides.items():
        saved_env[k] = os.environ.get(k)
        os.environ[k] = str(v)

    try:
        with Workspace() as ws:
            ws.setup(scenario.get("workspace", []))
            original_snap = ws.snapshot()

            events = run_scenario(binary, scenario, ws.dir)
            run_assertion(events, scenario, ws, original_snap)

        return True, "PASS"
    except (AssertionError, RuntimeError, ValueError) as e:
        return False, f"FAIL: {e}"
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    parser = argparse.ArgumentParser(description="pi-agent test runner")
    parser.add_argument("--binary", required=True, help="Path to agent binary")
    parser.add_argument("--layer", type=int, choices=[1, 2], help="Only run this layer")
    parser.add_argument("--compare", help="Second binary to compare against")
    parser.add_argument("--scenario", help="Run a single scenario file")
    args = parser.parse_args()

    binary = str(Path(args.binary).resolve())
    args.binary = binary
    if not Path(binary).exists():
        print(f"ERROR: binary not found: {binary}", file=sys.stderr)
        sys.exit(1)

    # Collect scenario files
    if args.scenario:
        scenario_files = [Path(args.scenario)]
    elif args.layer:
        scenario_files = sorted(LAYER_DIRS[args.layer].glob("*.yaml"))
    else:
        scenario_files = []
        for d in LAYER_DIRS.values():
            scenario_files.extend(sorted(d.glob("*.yaml")))

    passed = failed = 0
    for path in scenario_files:
        ok, msg = run_test(args.binary, path)
        status = "✓" if ok else "✗"
        print(f"  {status} [{path.parent.name}/{path.stem}] {msg}")
        if ok: passed += 1
        else: failed += 1

    print(f"\n{passed}/{passed+failed} passed", end="")

    # Comparison mode
    if args.compare and Path(args.compare).exists():
        print(f"\n\n--- Comparing {Path(args.binary).name} vs {Path(args.compare).name} ---")
        compare_failed = 0
        for path in scenario_files:
            ok1, _ = run_test(args.binary, path)
            ok2, _ = run_test(args.compare, path)
            match = "=" if ok1 == ok2 else "≠"
            b1 = "✓" if ok1 else "✗"
            b2 = "✓" if ok2 else "✗"
            print(f"  {match} [{path.stem}] {Path(args.binary).name}:{b1}  {Path(args.compare).name}:{b2}")
            if ok1 != ok2: compare_failed += 1
        if compare_failed:
            print(f"\n{compare_failed} scenario(s) differ between implementations")

    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
