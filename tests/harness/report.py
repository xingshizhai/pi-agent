"""
Test report generation: JSON + Markdown table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .verifier import TaskResult


@dataclass
class ImplResult:
    impl: str
    layer: int
    # Layer 2: list of (scenario_name, passed, msg)
    behavior: list[tuple[str, bool, str]] = field(default_factory=list)
    # Layer 3: list of TaskResult
    tasks: list[TaskResult] = field(default_factory=list)

    # ---- Layer 2 summary ----
    @property
    def behavior_pass_rate(self) -> str:
        if not self.behavior:
            return "—"
        p = sum(1 for _, ok, _ in self.behavior if ok)
        return f"{p}/{len(self.behavior)}"

    # ---- Layer 3 summary ----
    @property
    def task_pass_rate(self) -> str:
        if not self.tasks:
            return "—"
        p = sum(1 for t in self.tasks if t.passed)
        return f"{p}/{len(self.tasks)}"

    @property
    def avg_turns(self) -> str:
        if not self.tasks:
            return "—"
        return f"{sum(t.turns for t in self.tasks) / len(self.tasks):.1f}"

    @property
    def avg_latency(self) -> str:
        if not self.tasks:
            return "—"
        return f"{sum(t.latency_s for t in self.tasks) / len(self.tasks):.1f}s"


@dataclass
class Report:
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    model: str = "claude-sonnet-4-6"
    results: list[ImplResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "results": [
                {
                    "impl": r.impl,
                    "layer": r.layer,
                    "behavior_pass_rate": r.behavior_pass_rate,
                    "task_pass_rate": r.task_pass_rate,
                    "avg_turns": r.avg_turns,
                    "avg_latency": r.avg_latency,
                    "behavior": [
                        {"name": n, "passed": ok, "message": m}
                        for n, ok, m in r.behavior
                    ],
                    "tasks": [t.to_dict() for t in r.tasks],
                }
                for r in self.results
            ],
        }

    def save_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_markdown(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_markdown(), encoding="utf-8")

    def to_markdown(self) -> str:
        lines = [
            f"# pi-agent Capability Report",
            f"",
            f"**Generated:** {self.timestamp}  ",
            f"**Model:** `{self.model}`",
            f"",
        ]

        # ---- Layer 2 behavior summary ----
        l2 = [r for r in self.results if r.layer == 2 and r.behavior]
        if l2:
            lines += ["## Layer 2 — Behavior Tests (Mock LLM)", ""]
            # Collect all unique scenario names.
            all_names: list[str] = []
            seen: set[str] = set()
            for r in l2:
                for name, _, _ in r.behavior:
                    if name not in seen:
                        all_names.append(name)
                        seen.add(name)

            impls = [r.impl for r in l2]
            header = "| Scenario | " + " | ".join(impls) + " |"
            sep    = "|---|" + "---|" * len(impls)
            lines += [header, sep]

            for name in all_names:
                row = f"| {name} |"
                for r in l2:
                    m = {n: ok for n, ok, _ in r.behavior}
                    cell = "✓" if m.get(name, False) else "✗"
                    row += f" {cell} |"
                lines.append(row)

            lines += [""]
            # Summary row.
            sumrow = "| **Pass Rate** |"
            for r in l2:
                sumrow += f" **{r.behavior_pass_rate}** |"
            lines += [sumrow, ""]

        # ---- Layer 3 task summary ----
        l3 = [r for r in self.results if r.layer == 3 and r.tasks]
        if l3:
            lines += ["## Layer 3 — Task Evaluation (Real LLM)", ""]
            all_tasks: list[str] = []
            seen = set()
            for r in l3:
                for t in r.tasks:
                    if t.task_name not in seen:
                        all_tasks.append(t.task_name)
                        seen.add(t.task_name)

            impls = [r.impl for r in l3]
            header = "| Task | Difficulty | " + " | ".join(impls) + " |"
            sep    = "|---|---|" + "---|" * len(impls)
            lines += [header, sep]

            for tname in all_tasks:
                # Find difficulty tag from first impl that has it.
                diff = "—"
                row = f"| {tname} | {diff} |"
                for r in l3:
                    m = {t.task_name: t for t in r.tasks}
                    if tname in m:
                        cell = "✓" if m[tname].passed else "✗"
                        score = m[tname].verify_score
                        cell += f" ({score})"
                    else:
                        cell = "—"
                    row += f" {cell} |"
                lines.append(row)

            lines += [""]
            # Summary rows.
            for metric, label in [
                ("task_pass_rate", "Pass Rate"),
                ("avg_turns", "Avg Turns"),
                ("avg_latency", "Avg Latency"),
            ]:
                row = f"| **{label}** | |"
                for r in l3:
                    row += f" **{getattr(r, metric)}** |"
                lines.append(row)

            lines += [""]

            # ---- Per-implementation task detail ----
            for r in l3:
                if not r.tasks:
                    continue
                lines += [f"### {r.impl} — Task Details", ""]
                for t in r.tasks:
                    icon = "✓" if t.passed else "✗"
                    lines += [
                        f"#### {icon} {t.task_name}",
                        f"- Verify: {t.verify_score}  "
                        f"Turns: {t.turns}  "
                        f"Tool calls: {t.tool_calls}  "
                        f"Latency: {t.latency_s:.1f}s",
                    ]
                    if t.error_message:
                        lines.append(f"- ⚠ Error: `{t.error_message[:120]}`")
                    for step in t.verify_results:
                        s = "✓" if step.passed else "✗"
                        lines.append(
                            f"  - {s} [{step.strategy}] {step.name}"
                            + (f": {step.detail}" if step.detail else "")
                        )
                    lines.append("")

        return "\n".join(lines)
