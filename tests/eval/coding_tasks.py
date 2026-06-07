#!/usr/bin/env python3
"""
Coding ability evaluation: run 5 real-LLM tasks and verify output.

Usage:
  python tests/eval/coding_tasks.py
  python tests/eval/coding_tasks.py --task 1   # run single task
"""
import argparse, json, os, subprocess, sys, tempfile, shutil, time
from pathlib import Path

# --- config ---
REPO = Path(__file__).parents[2]
BINARY = REPO / "agent-rust" / "target" / "release" / "pi"
ENV_FILE = REPO / "agent-rust" / ".env"

# Load .env so OPENROUTER_API_KEY is available to subprocesses
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# --- tasks ---
TASKS = [
    # ── Task 1: write from scratch ──────────────────────────────────────────
    {
        "name": "write palindrome checker",
        "workspace": {},
        "prompt": (
            "Write a Python file `solution.py` with a function `is_palindrome(s)` "
            "that returns True if s is a palindrome, ignoring case and spaces. "
            "In the main block print the result for each of these three inputs on "
            "its own line: 'racecar', 'hello', 'A man a plan a canal Panama'"
        ),
        "verify": "python3 solution.py",
        "expect_contains": ["True", "False"],
    },

    # ── Task 2: fix a bug ────────────────────────────────────────────────────
    {
        "name": "fix binary search off-by-one",
        "workspace": {
            "buggy.py": (
                "def binary_search(arr, target):\n"
                "    left, right = 0, len(arr)   # BUG: off-by-one\n"
                "    while left <= right:\n"
                "        mid = (left + right) // 2\n"
                "        if arr[mid] == target:\n"
                "            return mid\n"
                "        elif arr[mid] < target:\n"
                "            left = mid + 1\n"
                "        else:\n"
                "            right = mid - 1\n"
                "    return -1\n"
            )
        },
        "prompt": (
            "There is a bug in `buggy.py` — an IndexError can occur. "
            "Find and fix it. Then add a main block that prints the return value of:\n"
            "  binary_search([1,3,5,7,9], 5)   # expect 2\n"
            "  binary_search([1,3,5,7,9], 1)   # expect 0\n"
            "  binary_search([1,3,5,7,9], 99)  # expect -1"
        ),
        "verify": "python3 buggy.py",
        "expect_contains": ["2", "0", "-1"],
    },

    # ── Task 3: complete partial code ────────────────────────────────────────
    {
        "name": "complete Stack class",
        "workspace": {
            "stack.py": (
                "class Stack:\n"
                "    def __init__(self):\n"
                "        self.items = []\n\n"
                "    def push(self, item):\n"
                "        self.items.append(item)\n\n"
                "    # TODO: pop() — raises IndexError if empty\n"
                "    # TODO: peek() — returns top without removing; raises IndexError if empty\n"
                "    # TODO: is_empty() -> bool\n"
                "    # TODO: size() -> int\n"
            )
        },
        "prompt": (
            "Complete the Stack class in `stack.py` by implementing the four TODO methods. "
            "Add a main block that:\n"
            "  s = Stack()\n"
            "  s.push(1); s.push(2); s.push(3)\n"
            "  print(s.size())       # 3\n"
            "  print(s.peek())       # 3\n"
            "  print(s.pop())        # 3\n"
            "  print(s.size())       # 2\n"
            "  print(s.is_empty())   # False"
        ),
        "verify": "python3 stack.py",
        "expect_contains": ["3", "2", "False"],
    },

    # ── Task 4: multi-step script ────────────────────────────────────────────
    {
        "name": "word frequency counter",
        "workspace": {},
        "prompt": (
            "Write a Python script `word_freq.py` that:\n"
            "1. Creates `sample.txt` with this exact content (one line):\n"
            "   the quick brown fox jumps over the lazy dog the fox\n"
            "2. Reads `sample.txt` and counts word frequencies.\n"
            "3. Prints the top 3 most frequent words as 'word: count', "
            "one per line, sorted by count descending."
        ),
        "verify": "python3 word_freq.py",
        "expect_contains": ["the: 3", "fox: 2"],
    },

    # ── Task 5: algorithm from spec ──────────────────────────────────────────
    {
        "name": "matrix multiplication",
        "workspace": {},
        "prompt": (
            "Write a Python file `matrix.py` that implements `matmul(A, B)` "
            "for two 2D lists (assume valid dimensions). "
            "Add a main block that multiplies [[1,2],[3,4]] by [[5,6],[7,8]] "
            "and prints the result. Expected: [[19, 22], [43, 50]]"
        ),
        "verify": "python3 matrix.py",
        "expect_contains": ["19", "22", "43", "50"],
    },
]


# --- runner ---

def stream_run(prompt: str, cwd: str) -> tuple[list[dict], float]:
    """Run agent in headless mode with real LLM; stream events to stdout."""
    inp = json.dumps({"prompt": prompt})
    env = {**os.environ, "PI_HEADLESS": "1"}
    t0 = time.time()

    proc = subprocess.Popen(
        [str(BINARY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=cwd,
        env=env,
    )
    proc.stdin.write(inp)
    proc.stdin.close()

    events = []
    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        try:
            evt = json.loads(raw)
            events.append(evt)
            _print_event(evt)
        except json.JSONDecodeError:
            pass

    try:
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("    [timeout — killed]")

    return events, time.time() - t0


def _print_event(evt: dict):
    t = evt.get("type", "")
    if t == "tool_call":
        name = evt.get("name", "")
        args = evt.get("args", {})
        brief = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in list(args.items())[:2])
        print(f"    → {name}({brief})")
    elif t == "tool_result" and evt.get("is_error"):
        print(f"    ✗ tool error: {evt.get('content','')[:100]}")
    elif t == "agent_end":
        print(f"    [agent done — {evt.get('turns','?')} turn(s)]")
    elif t == "error":
        print(f"    [agent error: {evt.get('message','')}]")


def run_verify(cmd: str, cwd: str, expect: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=cwd, timeout=15)
        out = r.stdout + r.stderr
        if r.returncode != 0:
            return False, f"exit {r.returncode}: {out[:150]}"
        missing = [s for s in expect if s not in out]
        if missing:
            return False, f"missing {missing!r} in output: {out[:150]}"
        return True, out.strip()[:120]
    except subprocess.TimeoutExpired:
        return False, "verify command timed out"
    except Exception as e:
        return False, str(e)


def run_task(task: dict) -> tuple[bool, str, float]:
    tmpdir = tempfile.mkdtemp(prefix="pi-eval-")
    try:
        for fname, content in task.get("workspace", {}).items():
            (Path(tmpdir) / fname).write_text(content)

        _, elapsed = stream_run(task["prompt"], tmpdir)
        ok, msg = run_verify(task["verify"], tmpdir, task["expect_contains"])
        return ok, msg, elapsed
    except Exception as e:
        return False, f"exception: {e}", 0.0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=int, help="Run single task (1-based)")
    args = parser.parse_args()

    if not BINARY.exists():
        print(f"Binary not found: {BINARY}\nRun: cargo build --release", file=sys.stderr)
        sys.exit(1)

    tasks = TASKS if not args.task else [TASKS[args.task - 1]]
    offset = (args.task - 1) if args.task else 0

    print(f"Binary : {BINARY}")
    print(f"Model  : {os.environ.get('PI_MODEL', 'anthropic/claude-sonnet-4-5')}")
    print(f"Tasks  : {len(tasks)}")
    print("─" * 60)

    results = []
    for i, task in enumerate(tasks, offset + 1):
        print(f"\nTask {i}/{len(TASKS)}: {task['name']}")
        ok, msg, elapsed = run_task(task)
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  ({elapsed:.1f}s)")
        print(f"  verify: {msg}")
        results.append((task["name"], ok, elapsed))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"Result: {passed}/{len(results)} passed\n")
    for name, ok, elapsed in results:
        print(f"  {'✓' if ok else '✗'}  {name}  ({elapsed:.1f}s)")

    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
