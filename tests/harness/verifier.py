"""
Verification strategies for Layer 3 task evaluation.

Each verify step in a scenario YAML maps to one of these strategies:
  A  file_exists      — required file was created
  B  run_no_error     — command exits 0
  C  stdout_contains  — command output contains expected strings
  D  run_tests        — inject test file(s), run test command, count passes
  E  llm_judge        — (future) LLM scores code quality 0–10
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerifyResult:
    strategy: str          # A/B/C/D/E
    name: str              # human-readable step name
    passed: bool
    score: float           # 0.0–1.0
    detail: str = ""       # failure reason or success note


@dataclass
class TaskResult:
    task_name: str
    passed: bool            # True if ALL verify steps pass
    verify_results: list[VerifyResult] = field(default_factory=list)
    turns: int = 0
    tool_calls: int = 0
    errors_recovered: int = 0
    latency_s: float = 0.0
    error_message: str = ""

    @property
    def verify_score(self) -> str:
        """e.g. '3/4'"""
        passed = sum(1 for r in self.verify_results if r.passed)
        return f"{passed}/{len(self.verify_results)}"

    def to_dict(self) -> dict:
        return {
            "task": self.task_name,
            "passed": self.passed,
            "verify_score": self.verify_score,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "errors_recovered": self.errors_recovered,
            "latency_s": round(self.latency_s, 2),
            "error_message": self.error_message,
            "steps": [
                {
                    "strategy": r.strategy,
                    "name": r.name,
                    "passed": r.passed,
                    "score": r.score,
                    "detail": r.detail,
                }
                for r in self.verify_results
            ],
        }


def verify_task(
    workspace_dir: str,
    verify_steps: list[dict],
    events: list[dict],
) -> list[VerifyResult]:
    """Run all verify steps and return results."""
    results = []
    for step in verify_steps:
        strategy = step.get("type", "")
        result = _run_step(strategy, step, workspace_dir)
        results.append(result)
    return results


def _run_step(strategy: str, step: dict, workspace_dir: str) -> VerifyResult:
    name = step.get("name", strategy)
    try:
        if strategy == "file_exists":
            return _file_exists(step, workspace_dir, name)
        elif strategy == "run_no_error":
            return _run_no_error(step, workspace_dir, name)
        elif strategy == "stdout_contains":
            return _stdout_contains(step, workspace_dir, name)
        elif strategy == "stdout_not_contains":
            return _stdout_not_contains(step, workspace_dir, name)
        elif strategy == "run_tests":
            return _run_tests(step, workspace_dir, name)
        elif strategy == "file_content_contains":
            return _file_content_contains(step, workspace_dir, name)
        elif strategy == "file_content_equals":
            return _file_content_equals(step, workspace_dir, name)
        else:
            return VerifyResult(strategy, name, False, 0.0,
                                f"Unknown strategy: {strategy!r}")
    except Exception as exc:
        return VerifyResult(strategy, name, False, 0.0, f"Exception: {exc}")


# ---------------------------------------------------------------------------
# Strategy A: file_exists
# ---------------------------------------------------------------------------

def _file_exists(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    path = Path(workspace_dir) / step["path"]
    ok = path.exists()
    return VerifyResult(
        "A", name, ok, 1.0 if ok else 0.0,
        "" if ok else f"File not found: {step['path']!r}",
    )


# ---------------------------------------------------------------------------
# Strategy B: run_no_error
# ---------------------------------------------------------------------------

def _run_no_error(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    r = _run_cmd(step["command"], workspace_dir, step.get("timeout", 30))
    ok = r.returncode == 0
    return VerifyResult(
        "B", name, ok, 1.0 if ok else 0.0,
        "" if ok else f"Exit {r.returncode}: {(r.stderr or r.stdout)[:300]}",
    )


# ---------------------------------------------------------------------------
# Strategy C: stdout_contains
# ---------------------------------------------------------------------------

def _stdout_contains(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    r = _run_cmd(step["command"], workspace_dir, step.get("timeout", 30))
    output = (r.stdout or "") + (r.stderr or "")
    expected: list[str] = step.get("expect", [])
    if isinstance(expected, str):
        expected = [expected]

    missing = [s for s in expected if s not in output]
    ok = not missing
    score = (len(expected) - len(missing)) / max(len(expected), 1)
    detail = "" if ok else f"Missing in output: {missing!r}\nGot: {output[:400]}"
    return VerifyResult("C", name, ok, score, detail)


# ---------------------------------------------------------------------------
# Strategy C-: stdout_not_contains
# ---------------------------------------------------------------------------

def _stdout_not_contains(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    r = _run_cmd(step["command"], workspace_dir, step.get("timeout", 30))
    output = (r.stdout or "") + (r.stderr or "")
    forbidden: list[str] = step.get("forbidden", [])
    if isinstance(forbidden, str):
        forbidden = [forbidden]

    found = [s for s in forbidden if s in output]
    ok = not found
    detail = "" if ok else f"Forbidden strings found: {found!r}"
    return VerifyResult("C", name, ok, 1.0 if ok else 0.0, detail)


# ---------------------------------------------------------------------------
# Strategy D: run_tests
# ---------------------------------------------------------------------------

def _run_tests(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    """
    Inject prewritten test files into the workspace, run the test command,
    and parse pass/fail counts from the output.
    """
    ws = Path(workspace_dir)

    # Inject test files.
    for tf in step.get("test_files", []):
        p = ws / tf["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tf["content"], encoding="utf-8")

    r = _run_cmd(step["command"], workspace_dir, step.get("timeout", 60))
    output = r.stdout + r.stderr

    # Try to extract pass/fail numbers from pytest / go test output.
    passed_n, failed_n, total_n = _parse_test_counts(output, r.returncode)

    ok = r.returncode == 0
    score = passed_n / total_n if total_n > 0 else (1.0 if ok else 0.0)
    detail = (
        f"{passed_n}/{total_n} tests passed" if total_n > 0
        else ("All tests passed" if ok else f"Exit {r.returncode}: {output[:300]}")
    )
    return VerifyResult("D", name, ok, score, detail)


def _parse_test_counts(output: str, returncode: int) -> tuple[int, int, int]:
    """Heuristically parse passed/failed/total from pytest or go test output."""
    import re
    # pytest: "3 passed, 1 failed" or "4 passed"
    m = re.search(r"(\d+) passed", output)
    passed = int(m.group(1)) if m else 0
    m2 = re.search(r"(\d+) failed", output)
    failed = int(m2.group(1)) if m2 else 0
    total = passed + failed

    # go test: "--- PASS" / "--- FAIL" counts
    if total == 0:
        passed = output.count("--- PASS")
        failed = output.count("--- FAIL")
        total = passed + failed

    # Fallback: if we can't parse, use exit code.
    if total == 0:
        passed = 1 if returncode == 0 else 0
        total = 1

    return passed, failed, total


# ---------------------------------------------------------------------------
# Strategy A-extra: file_content_contains / equals
# ---------------------------------------------------------------------------

def _file_content_contains(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    path = Path(workspace_dir) / step["path"]
    if not path.exists():
        return VerifyResult("A", name, False, 0.0, f"File not found: {step['path']!r}")
    content = path.read_text(encoding="utf-8")
    needle = step["contains"]
    ok = needle in content
    return VerifyResult("A", name, ok, 1.0 if ok else 0.0,
                        "" if ok else f"{needle!r} not in file")


def _file_content_equals(step: dict, workspace_dir: str, name: str) -> VerifyResult:
    path = Path(workspace_dir) / step["path"]
    if not path.exists():
        return VerifyResult("A", name, False, 0.0, f"File not found: {step['path']!r}")
    content = path.read_text(encoding="utf-8")
    expected = step["content"]
    ok = content == expected
    return VerifyResult("A", name, ok, 1.0 if ok else 0.0,
                        "" if ok else f"Content mismatch.\nExpected: {expected[:200]}\nGot: {content[:200]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cmd(command: str, cwd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Event analysis helpers
# ---------------------------------------------------------------------------

def count_turns(events: list[dict]) -> int:
    return sum(1 for e in events if e.get("type") == "turn_start")


def count_tool_calls(events: list[dict]) -> int:
    return sum(1 for e in events if e.get("type") == "tool_call")


def count_errors_recovered(events: list[dict]) -> int:
    """Count tool_result is_error=True events that were followed by more turns."""
    errors = 0
    seen_error = False
    for e in events:
        if e.get("type") == "tool_result" and e.get("is_error"):
            seen_error = True
        elif e.get("type") == "turn_start" and seen_error:
            errors += 1
            seen_error = False
    return errors


def extract_agent_error(events: list[dict]) -> str:
    for e in events:
        if e.get("type") == "error":
            return e.get("message", "unknown error")
    return ""
