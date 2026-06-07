#!/usr/bin/env python3
"""
pi-agent unified test runner.

Supports three test layers:
  Layer 2  — Behavior tests  (mock LLM, deterministic)
  Layer 3  — Task evaluation (real LLM, outcome-verified)

Usage examples:

  # Layer 2: behavior tests against Rust and Go
  python tests/run_tests.py --layer 2 --impl rust,go

  # Layer 3: capability evaluation, Rust only
  python tests/run_tests.py --layer 3 --impl rust

  # Layer 3: compare Rust vs original pi
  python tests/run_tests.py --layer 3 --impl rust --compare pi

  # Layer 3: repeat each task 3 times to measure stability
  python tests/run_tests.py --layer 3 --impl rust --repeat 3

  # Run all layers for all available implementations
  python tests/run_tests.py --impl rust,go

  # Save a Markdown + JSON report
  python tests/run_tests.py --layer 3 --impl rust,go --report tests/report/latest

  # Use custom binary paths
  python tests/run_tests.py --layer 2 --impl rust --binary-rust path/to/pi

  # Verbose: print raw events
  python tests/run_tests.py --layer 2 --impl rust --verbose
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Make the harness importable when run from project root.
sys.path.insert(0, str(Path(__file__).parent))

from harness.adapter import resolve_adapters
from harness.report import ImplResult, Report
from harness.runner import load_scenario, run_behavior_scenario, run_task_scenario

TESTS_DIR = Path(__file__).parent
SCENARIOS = {
    2: TESTS_DIR / "scenarios" / "layer2-behavior",
    3: TESTS_DIR / "scenarios" / "layer3-tasks",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_scenarios(layer: int, filter_name: str | None = None) -> list[Path]:
    base = SCENARIOS[layer]
    if not base.exists():
        return []
    files = sorted(base.rglob("*.yaml"))
    if filter_name:
        files = [f for f in files if filter_name in f.stem]
    return files


def print_header(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def fmt_result(passed: bool) -> str:
    return "✓" if passed else "✗"


# ---------------------------------------------------------------------------
# Layer 2: behavior runner
# ---------------------------------------------------------------------------

def run_layer2(
    impl_names: list[str],
    binary_overrides: dict,
    scenario_filter: str | None,
    verbose: bool,
) -> list[ImplResult]:
    scenarios = collect_scenarios(2, scenario_filter)
    if not scenarios:
        print("  No layer-2 scenarios found.")
        return []

    adapters = resolve_adapters(impl_names, binary_overrides)
    results: list[ImplResult] = []

    for adapter in adapters:
        print_header(f"Layer 2 — Behavior Tests  [{adapter.name}]")
        impl_res = ImplResult(impl=adapter.name, layer=2)
        passed_total = 0

        for path in scenarios:
            scenario = load_scenario(path)
            name = scenario.get("name", path.stem)
            short = f"{path.parent.name}/{path.stem}"

            try:
                ok, msg = run_behavior_scenario(adapter, scenario, verbose=verbose)
            except Exception as exc:
                ok, msg = False, f"FAIL: exception — {exc}"

            icon = fmt_result(ok)
            print(f"  {icon}  {short}")
            if not ok:
                print(f"       {msg}")
            if ok:
                passed_total += 1
            impl_res.behavior.append((name, ok, msg))

        total = len(scenarios)
        print(f"\n  {passed_total}/{total} passed")
        results.append(impl_res)

    return results


# ---------------------------------------------------------------------------
# Layer 3: task evaluation runner
# ---------------------------------------------------------------------------

def run_layer3(
    impl_names: list[str],
    binary_overrides: dict,
    compare_impls: list[str],
    scenario_filter: str | None,
    repeat: int,
    verbose: bool,
) -> list[ImplResult]:
    all_impls = impl_names + [i for i in compare_impls if i not in impl_names]
    scenarios = collect_scenarios(3, scenario_filter)
    if not scenarios:
        print("  No layer-3 scenarios found.")
        return []

    adapters = resolve_adapters(all_impls, binary_overrides)
    results: list[ImplResult] = []

    for adapter in adapters:
        print_header(f"Layer 3 — Task Evaluation  [{adapter.name}]")
        impl_res = ImplResult(impl=adapter.name, layer=3)

        for path in scenarios:
            scenario = load_scenario(path)
            name = scenario.get("name", path.stem)
            diff = scenario.get("difficulty", "")
            short = f"[{diff}] {name}" if diff else name

            # Run repeat times, take best result (optimistic scoring).
            best: "TaskResult | None" = None
            for run_i in range(repeat):
                suffix = f"  (run {run_i+1}/{repeat})" if repeat > 1 else ""
                print(f"  ⟳  {short}{suffix}", end="\r", flush=True)
                try:
                    result = run_task_scenario(adapter, scenario, verbose=verbose)
                except Exception as exc:
                    from harness.verifier import TaskResult, VerifyResult
                    result = TaskResult(
                        task_name=name,
                        passed=False,
                        error_message=str(exc),
                    )
                if best is None or (result.passed and not best.passed):
                    best = result

            assert best is not None
            icon = fmt_result(best.passed)
            score_str = f"({best.verify_score})" if best.verify_results else ""
            timing = f"{best.latency_s:.1f}s  {best.turns}t"
            print(f"  {icon}  {short}  {score_str}  [{timing}]      ")

            if not best.passed:
                for step in best.verify_results:
                    if not step.passed:
                        detail = f": {step.detail[:100]}" if step.detail else ""
                        print(f"       ✗ [{step.strategy}] {step.name}{detail}")
                if best.error_message and not best.verify_results:
                    print(f"       ✗ {best.error_message[:120]}")

            impl_res.tasks.append(best)

        passed = sum(1 for t in impl_res.tasks if t.passed)
        total = len(impl_res.tasks)
        print(f"\n  {passed}/{total} tasks passed"
              f"  |  avg turns: {impl_res.avg_turns}"
              f"  |  avg latency: {impl_res.avg_latency}")
        results.append(impl_res)

    # Side-by-side comparison table.
    if len(adapters) > 1:
        _print_comparison_table(results, scenarios)

    return results


def _print_comparison_table(
    results: list[ImplResult],
    scenarios: list[Path],
) -> None:
    print_header("Comparison Summary")
    impls = [r.impl for r in results]
    name_col = 36
    print(f"  {'Task':<{name_col}}" + "".join(f"  {i:<8}" for i in impls))
    print(f"  {'─'*name_col}" + "".join(f"  {'─'*8}" for _ in impls))

    task_names = [load_scenario(p).get("name", p.stem) for p in scenarios]
    for tname in task_names:
        row = f"  {tname[:name_col-1]:<{name_col}}"
        for r in results:
            m = {t.task_name: t for t in r.tasks}
            if tname in m:
                cell = "✓" if m[tname].passed else "✗"
            else:
                cell = "—"
            row += f"  {cell:<8}"
        print(row)

    print(f"  {'─'*name_col}" + "".join(f"  {'─'*8}" for _ in impls))
    row = f"  {'Pass Rate':<{name_col}}"
    for r in results:
        row += f"  {r.task_pass_rate:<8}"
    print(row)
    row = f"  {'Avg Turns':<{name_col}}"
    for r in results:
        row += f"  {r.avg_turns:<8}"
    print(row)
    row = f"  {'Avg Latency':<{name_col}}"
    for r in results:
        row += f"  {r.avg_latency:<8}"
    print(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="pi-agent cross-language test runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--impl", default="rust",
        help="Comma-separated list of implementations to test: rust,go,python,pi",
    )
    parser.add_argument(
        "--layer", type=int, choices=[2, 3],
        help="Run only this layer (default: both 2 and 3)",
    )
    parser.add_argument(
        "--compare", default="",
        help="Additional implementation(s) to compare against (e.g. pi,go)",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Number of runs per Layer 3 task (best result counts)",
    )
    parser.add_argument(
        "--scenario", default="",
        help="Filter: only run scenarios whose filename contains this string",
    )
    parser.add_argument(
        "--report", default="",
        help="Save report to this path prefix (creates <path>.json and <path>.md)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print raw agent events",
    )
    # Per-implementation binary overrides.
    parser.add_argument("--binary-rust",   default="", help="Path to Rust binary")
    parser.add_argument("--binary-go",     default="", help="Path to Go binary")
    parser.add_argument("--binary-python", default="", help="Path to Python binary")

    args = parser.parse_args()

    impl_names = [i.strip() for i in args.impl.split(",") if i.strip()]
    compare_impls = [i.strip() for i in args.compare.split(",") if i.strip()]
    layers = [args.layer] if args.layer else [2, 3]
    scenario_filter = args.scenario or None

    binary_overrides: dict[str, str] = {}
    if args.binary_rust:   binary_overrides["rust"]   = args.binary_rust
    if args.binary_go:     binary_overrides["go"]     = args.binary_go
    if args.binary_python: binary_overrides["python"] = args.binary_python

    report = Report(
        model=os.environ.get("PI_MODEL", "claude-sonnet-4-6"),
    )
    all_results: list[ImplResult] = []
    overall_failed = False

    t_start = time.monotonic()

    if 2 in layers:
        l2_results = run_layer2(
            impl_names, binary_overrides, scenario_filter, args.verbose
        )
        all_results.extend(l2_results)
        for r in l2_results:
            if any(not ok for _, ok, _ in r.behavior):
                overall_failed = True

    if 3 in layers:
        l3_results = run_layer3(
            impl_names, binary_overrides, compare_impls,
            scenario_filter, args.repeat, args.verbose,
        )
        all_results.extend(l3_results)
        for r in l3_results:
            if any(not t.passed for t in r.tasks):
                overall_failed = True

    elapsed = time.monotonic() - t_start
    print(f"\n{'─'*60}")
    print(f"  Total time: {elapsed:.1f}s")

    if args.report:
        report.results = all_results
        report.save_json(args.report + ".json")
        report.save_markdown(args.report + ".md")
        print(f"  Report saved: {args.report}.json / .md")

    return 1 if overall_failed else 0


if __name__ == "__main__":
    sys.exit(main())
