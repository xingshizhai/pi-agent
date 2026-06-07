#!/usr/bin/env python3
"""
Coding ability evaluation for the Python Pi agent.

Tests the agent's ability to solve programming problems using read/write/edit/bash tools.
All tasks are verified by running the generated code and checking stdout.

Usage:
  # After building the Python agent:
  python tests/eval/coding_tasks_python.py
  python tests/eval/coding_tasks_python.py --task 3
  python tests/eval/coding_tasks_python.py --binary /path/to/pi
"""
import argparse, json, os, subprocess, sys, tempfile, shutil, time
from pathlib import Path

# --- config ---
REPO = Path(__file__).parents[2]

# Python agent binary: either `uv run pi` (script) or a compiled entry point.
# Override with --binary or PYTHON_PI_BINARY env var.
DEFAULT_BINARY_CANDIDATES = [
    REPO / "agent-python" / ".venv" / "bin" / "pi",   # after `uv install`
    REPO / "agent-python" / "pi",                       # explicit wrapper script
]

ENV_FILE = REPO / "agent-python" / ".env"

# Load .env so API keys are available
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# --- tasks ---
TASKS = [
    # ── Task 1: write from scratch (basic) ──────────────────────────────────
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

    # ── Task 6: recursive algorithm with memoization ─────────────────────────
    {
        "name": "fibonacci with memoization",
        "workspace": {},
        "prompt": (
            "Write `fib.py` implementing `fib(n)` using memoization (not iterative). "
            "It must compute fib(0)=0, fib(1)=1, fib(n)=fib(n-1)+fib(n-2). "
            "In the main block, print fib(10), fib(20), fib(30) each on its own line. "
            "Also verify fib(35) completes in under 1 second (memoization ensures this). "
            "Use python3 to run and check it works."
        ),
        "verify": "python3 fib.py",
        "expect_contains": ["55", "6765", "832040"],  # fib(10), fib(20), fib(30)
    },

    # ── Task 7: iterative debugging via bash ─────────────────────────────────
    {
        "name": "debug divide-by-zero in stats module",
        "workspace": {
            "stats.py": (
                "def mean(nums):\n"
                "    return sum(nums) / len(nums)\n\n"
                "def variance(nums):\n"
                "    m = mean(nums)\n"
                "    return sum((x - m) ** 2 for x in nums) / len(nums)\n\n"
                "if __name__ == '__main__':\n"
                "    print(mean([1, 2, 3, 4, 5]))\n"
                "    print(variance([]))          # BUG: crashes here\n"
                "    print(variance([2, 4, 4, 4, 5, 5, 7, 9]))\n"
            )
        },
        "prompt": (
            "Run `python3 stats.py`. It will crash. Fix `stats.py` so that:\n"
            "- `mean([])` raises ValueError with message 'mean requires at least one value'\n"
            "- `variance([])` also raises ValueError with the same message\n"
            "- In the main block, wrap ONLY the `variance([])` call in try/except and "
            "print 'error: <message>' when it raises. The other two calls must still run.\n"
            "Then run again to confirm it works. "
            "Expected output (three lines): '3.0', 'error: mean requires at least one value', '4.0'"
        ),
        "verify": "python3 stats.py",
        "expect_contains": ["3.0", "error: mean requires at least one value", "4.0"],
    },

    # ── Task 8: multi-file project ────────────────────────────────────────────
    {
        "name": "create geometry module used by main script",
        "workspace": {},
        "prompt": (
            "Create two Python files:\n"
            "1. `geometry.py` — a module with:\n"
            "   - `circle_area(r)`: returns π*r² (use math.pi)\n"
            "   - `rect_area(w, h)`: returns w*h\n"
            "   - `triangle_area(b, h)`: returns 0.5*b*h\n"
            "2. `main.py` — imports from geometry and prints:\n"
            "   Circle r=5: <area rounded to 2 decimal places>\n"
            "   Rectangle 4x6: 24\n"
            "   Triangle base=3 height=8: 12.0\n"
            "Run `python3 main.py` to verify."
        ),
        "verify": "python3 main.py",
        "expect_contains": ["78.54", "24", "12.0"],
    },

    # ── Task 9: sorting algorithm + test ─────────────────────────────────────
    {
        "name": "implement merge sort and self-test",
        "workspace": {},
        "prompt": (
            "Write `mergesort.py` with:\n"
            "- `merge_sort(arr)` — in-place or returning a new sorted list\n"
            "- A main block that runs these assertions and prints 'all tests passed' if correct:\n"
            "  assert merge_sort([]) == []\n"
            "  assert merge_sort([1]) == [1]\n"
            "  assert merge_sort([3, 1, 4, 1, 5, 9, 2, 6]) == [1, 1, 2, 3, 4, 5, 6, 9]\n"
            "  assert merge_sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]\n"
            "Use python3 to verify it passes."
        ),
        "verify": "python3 mergesort.py",
        "expect_contains": ["all tests passed"],
    },

    # ── Task 10: CSV parsing + data pipeline ─────────────────────────────────
    {
        "name": "parse sales CSV and compute summary",
        "workspace": {
            "sales.csv": (
                "date,product,quantity,price\n"
                "2024-01-01,apple,10,1.5\n"
                "2024-01-01,banana,5,0.8\n"
                "2024-01-02,apple,8,1.5\n"
                "2024-01-02,cherry,20,3.0\n"
                "2024-01-03,banana,15,0.8\n"
                "2024-01-03,apple,12,1.5\n"
            )
        },
        "prompt": (
            "Write `analyze.py` that reads `sales.csv` (no external libs, use csv module) and prints:\n"
            "1. Total revenue (sum of quantity*price for all rows), formatted as 'Total revenue: XX.XX'\n"
            "2. Best-selling product by total quantity, as 'Best seller: <name> (<qty> units)'\n"
            "3. Revenue per product, one per line as '<product>: XX.XX', sorted by revenue descending.\n"
            "Run it to verify."
        ),
        "verify": "python3 analyze.py",
        "expect_contains": [
            "Total revenue:",
            "Best seller: apple",
            "apple:",
        ],
    },
]


# --- runner ---

def stream_run(binary: str, prompt: str, cwd: str) -> tuple[list[dict], float]:
    """Run agent in headless mode with real LLM; stream events to stdout."""
    inp = json.dumps({"prompt": prompt})
    env = {**os.environ, "PI_HEADLESS": "1"}
    t0 = time.time()

    proc = subprocess.Popen(
        binary if isinstance(binary, list) else [binary],
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
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        print("    [timeout — killed after 300s]")

    return events, time.time() - t0


def _print_event(evt: dict):
    t = evt.get("type", "")
    if t == "tool_call":
        name = evt.get("name", "")
        args = evt.get("args", {})
        brief = ", ".join(f"{k}={str(v)[:40]!r}" for k, v in list(args.items())[:2])
        print(f"    → {name}({brief})")
    elif t == "tool_result" and evt.get("is_error"):
        print(f"    ✗ tool error: {evt.get('content', '')[:100]}")
    elif t == "agent_end":
        print(f"    [agent done — {evt.get('turns', '?')} turn(s)]")
    elif t == "error":
        print(f"    [agent error: {evt.get('message', '')}]")


def run_verify(cmd: str, cwd: str, expect: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=15
        )
        out = r.stdout + r.stderr
        if r.returncode != 0:
            return False, f"exit {r.returncode}: {out[:200]}"
        missing = [s for s in expect if s not in out]
        if missing:
            return False, f"missing {missing!r} in output:\n{out[:200]}"
        return True, out.strip()[:160]
    except subprocess.TimeoutExpired:
        return False, "verify command timed out"
    except Exception as e:
        return False, str(e)


def run_task(binary, task: dict) -> tuple[bool, str, float]:
    tmpdir = tempfile.mkdtemp(prefix="pi-eval-py-")
    try:
        for fname, content in task.get("workspace", {}).items():
            (Path(tmpdir) / fname).write_text(content, encoding="utf-8")

        _, elapsed = stream_run(binary, task["prompt"], tmpdir)
        ok, msg = run_verify(task["verify"], tmpdir, task["expect_contains"])
        return ok, msg, elapsed
    except Exception as e:
        return False, f"exception: {e}", 0.0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def resolve_binary(override: str | None) -> str:
    if override:
        p = Path(override)
        if not p.exists():
            print(f"ERROR: binary not found: {p}", file=sys.stderr)
            sys.exit(1)
        return str(p)

    env_val = os.environ.get("PYTHON_PI_BINARY")
    if env_val:
        return env_val

    for candidate in DEFAULT_BINARY_CANDIDATES:
        if candidate.exists():
            return str(candidate)

    print(
        "ERROR: Python Pi agent binary not found.\n"
        "Build it first with:\n"
        "  cd agent-python && uv install\n"
        "Then retry, or pass --binary /path/to/pi",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Python Pi agent coding eval")
    parser.add_argument("--task", type=int, help="Run a single task by number (1-based)")
    parser.add_argument("--binary", help="Path to the pi agent binary")
    parser.add_argument("--model", help="LLM model to use (sets PI_MODEL env var)")
    args = parser.parse_args()

    binary = resolve_binary(args.binary)

    if args.model:
        os.environ["PI_MODEL"] = args.model

    tasks_to_run = TASKS if not args.task else [TASKS[args.task - 1]]
    offset = (args.task - 1) if args.task else 0

    print(f"Binary : {binary}")
    print(f"Model  : {os.environ.get('PI_MODEL', '(default)')}")
    print(f"Tasks  : {len(tasks_to_run)}/{len(TASKS)}")
    print("─" * 60)

    results = []
    for i, task in enumerate(tasks_to_run, offset + 1):
        print(f"\nTask {i}/{len(TASKS)}: {task['name']}")
        ok, msg, elapsed = run_task(binary, task)
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  ({elapsed:.1f}s)")
        print(f"  verify: {msg}")
        results.append((task["name"], ok, elapsed))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total_time = sum(t for _, _, t in results)
    print(f"Result: {passed}/{len(results)} passed  ({total_time:.0f}s total)\n")
    for name, ok, elapsed in results:
        print(f"  {'✓' if ok else '✗'}  {name}  ({elapsed:.1f}s)")

    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
