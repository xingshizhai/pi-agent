# Python Pi Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Python 复刻 earendil-works/pi —— 一个极简终端编码代理，LLM 流式对话 + 7个内置工具 + NDJSON 会话持久化 + Textual TUI。

**Architecture:** 五层单向依赖：`ai`（LLM 抽象）← `agent`（循环状态机）← `tools`/`session`（工具+持久化）← `tui`（Textual UI）← `main`（CLI 入口）。每层通过 ABC 接口隔离，方便 Mock 测试。

**Tech Stack:** Python 3.12+, pydantic v2, anthropic SDK ≥0.40, openai SDK ≥1.50, textual ≥1.0, rich, pytest + pytest-asyncio, ruff, uv

---

## 文件结构

```
agent-python/
├── pyproject.toml
├── src/
│   └── pi/
│       ├── __init__.py
│       ├── main.py              # CLI 入口，argparse，启动 TUI
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── types.py         # Pydantic 消息类型 + StreamEvent dataclasses
│       │   ├── base.py          # LLMProvider ABC
│       │   ├── anthropic.py     # Anthropic 实现（SDK streaming）
│       │   └── openai.py        # OpenAI 实现（SDK streaming）
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── context.py       # AgentContext dataclass + AgentConfig
│       │   ├── events.py        # AgentEvent dataclasses
│       │   └── loop.py          # agent_loop 核心状态机
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py          # Tool ABC + ToolResult dataclass
│       │   ├── read.py
│       │   ├── write.py
│       │   ├── edit.py
│       │   ├── bash.py
│       │   ├── find.py
│       │   ├── grep.py
│       │   └── ls.py
│       ├── session/
│       │   ├── __init__.py
│       │   └── manager.py       # NDJSON 读写，SessionManager
│       └── tui/
│           ├── __init__.py
│           ├── app.py           # Textual App 主体
│           └── widgets/
│               ├── __init__.py
│               ├── chat.py      # 消息区 Widget
│               ├── input.py     # 输入框 Widget
│               └── status.py    # 状态栏 Widget
└── tests/
    ├── conftest.py
    ├── test_tools.py
    ├── test_ai_types.py
    ├── test_anthropic.py
    ├── test_agent_loop.py
    └── test_session.py
```

---

## Task 1: 项目骨架

**Files:**
- Create: `agent-python/pyproject.toml`
- Create: `agent-python/src/pi/__init__.py` (and all sub-package `__init__.py`)
- Create: `agent-python/tests/conftest.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "pi"
version = "0.1.0"
description = "A minimal terminal coding agent"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40",
    "openai>=1.50",
    "textual>=1.0",
    "rich>=13.0",
    "pydantic>=2.0",
    "httpx>=0.27",
    "difflib",
]

[project.scripts]
pi = "pi.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pi"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.4",
]
```

> 注意：`difflib` 是标准库，不需要在 dependencies 中，去掉它。

实际 pyproject.toml（无 difflib）：

```toml
[project]
name = "pi"
version = "0.1.0"
description = "A minimal terminal coding agent"
requires-python = ">=3.12"
dependencies = [
    "anthropic>=0.40",
    "openai>=1.50",
    "textual>=1.0",
    "rich>=13.0",
    "pydantic>=2.0",
    "httpx>=0.27",
]

[project.scripts]
pi = "pi.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pi"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.4",
]
```

- [ ] **Step 2: 创建所有空目录和 `__init__.py`**

```bash
cd /home/ether/Work/pi-agent/agent-python
mkdir -p src/pi/{ai,agent,tools,session,tui/widgets}
touch src/pi/__init__.py
touch src/pi/ai/__init__.py
touch src/pi/agent/__init__.py
touch src/pi/tools/__init__.py
touch src/pi/session/__init__.py
touch src/pi/tui/__init__.py
touch src/pi/tui/widgets/__init__.py
mkdir -p tests
touch tests/__init__.py
touch tests/conftest.py
```

- [ ] **Step 3: 创建 conftest.py**

```python
# tests/conftest.py
import pytest
```

- [ ] **Step 4: 安装依赖**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv sync --group dev
```

Expected: 输出 "Resolved N packages"，无报错。

- [ ] **Step 5: 验证环境**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run python -c "import pydantic; print(pydantic.__version__)"
```

Expected: `2.x.x`

- [ ] **Step 6: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/
git commit -m "feat(python): project scaffold — pyproject.toml + empty modules"
```

---

## Task 2: AI 类型定义

**Files:**
- Create: `agent-python/src/pi/ai/types.py`
- Create: `agent-python/tests/test_ai_types.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_ai_types.py
import time
import pytest
from pi.ai.types import (
    TextContent, ToolCall, Usage,
    UserMessage, AssistantMessage, ToolResultMessage,
    TextDelta, ToolCallEnd, StreamDone,
)


def test_text_content_type_literal():
    tc = TextContent(text="hello")
    assert tc.type == "text"
    assert tc.text == "hello"


def test_tool_call_fields():
    tc = ToolCall(id="tc_1", name="read", arguments={"path": "/tmp/foo"})
    assert tc.type == "tool_call"
    assert tc.name == "read"
    assert tc.arguments == {"path": "/tmp/foo"}


def test_user_message_defaults():
    msg = UserMessage(content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp > 0


def test_assistant_message_defaults():
    msg = AssistantMessage(content=[TextContent(text="hi")])
    assert msg.role == "assistant"
    assert msg.stop_reason == "stop"
    assert msg.usage.input == 0


def test_tool_result_message():
    msg = ToolResultMessage(
        tool_call_id="tc_1",
        tool_name="read",
        content=[TextContent(text="file contents")],
    )
    assert msg.role == "tool_result"
    assert not msg.is_error


def test_stream_events_are_dataclasses():
    msg = AssistantMessage(content=[])
    delta = TextDelta(index=0, delta="hello", partial=msg)
    assert delta.delta == "hello"
    assert delta.index == 0

    done = StreamDone(stop_reason="stop", message=msg)
    assert done.stop_reason == "stop"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_ai_types.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'pi.ai.types'`

- [ ] **Step 3: 实现 `types.py`**

```python
# src/pi/ai/types.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Content blocks ────────────────────────────────────────────────────────────

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ThinkingContent(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str
    thinking_signature: str | None = None


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


class Usage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


# ── Messages ──────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str | list[TextContent]
    timestamp: int = Field(default_factory=_now_ms)


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[TextContent | ThinkingContent | ToolCall]
    api: str = ""
    provider: str = ""
    model: str = ""
    usage: Usage = Field(default_factory=Usage)
    stop_reason: str = "stop"
    error_message: str | None = None
    timestamp: int = Field(default_factory=_now_ms)


class ToolResultMessage(BaseModel):
    role: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: list[TextContent]
    details: Any = None
    is_error: bool = False
    timestamp: int = Field(default_factory=_now_ms)


Message = UserMessage | AssistantMessage | ToolResultMessage


# ── Stream events (dataclasses for lightweight construction) ──────────────────

@dataclass
class StreamStart:
    partial: AssistantMessage


@dataclass
class TextStart:
    index: int
    partial: AssistantMessage


@dataclass
class TextDelta:
    index: int
    delta: str
    partial: AssistantMessage


@dataclass
class TextEnd:
    index: int
    content: str
    partial: AssistantMessage


@dataclass
class ToolCallStart:
    index: int
    partial: AssistantMessage


@dataclass
class ToolCallDelta:
    index: int
    delta: str
    partial: AssistantMessage


@dataclass
class ToolCallEnd:
    index: int
    tool_call: ToolCall
    partial: AssistantMessage


@dataclass
class StreamDone:
    stop_reason: str
    message: AssistantMessage


@dataclass
class StreamError:
    stop_reason: str
    error: AssistantMessage


StreamEvent = (
    StreamStart | TextStart | TextDelta | TextEnd |
    ToolCallStart | ToolCallDelta | ToolCallEnd |
    StreamDone | StreamError
)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_ai_types.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/ai/types.py agent-python/tests/test_ai_types.py
git commit -m "feat(python): AI message types + stream events"
```

---

## Task 3: Tool 基类

**Files:**
- Create: `agent-python/src/pi/tools/base.py`

- [ ] **Step 1: 实现 `base.py`（无单独测试，基类通过子类测试覆盖）**

```python
# src/pi/tools/base.py
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    terminate: bool = False
    details: Any = None

    @classmethod
    def ok(cls, content: str, details: Any = None) -> "ToolResult":
        return cls(content=content, details=details)

    @classmethod
    def err(cls, content: str) -> "ToolResult":
        return cls(content=content, is_error=True)


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema object for tool parameters."""
        ...

    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult: ...
```

- [ ] **Step 2: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/base.py
git commit -m "feat(python): Tool ABC + ToolResult"
```

---

## Task 4: read 工具

**Files:**
- Create: `agent-python/src/pi/tools/read.py`
- Modify: `agent-python/tests/test_tools.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tools.py
import asyncio
import os
import tempfile
import pytest
from pi.tools.read import ReadTool
from pi.tools.write import WriteTool
from pi.tools.edit import EditTool
from pi.tools.bash import BashTool
from pi.tools.find import FindTool
from pi.tools.grep import GrepTool
from pi.tools.ls import LsTool


# ── read ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    lines = [f"line {i}" for i in range(1, 11)]  # 10 lines
    f.write_text("\n".join(lines))
    return f


@pytest.mark.asyncio
async def test_read_basic(tmp_file):
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(tmp_file)})
    assert not result.is_error
    assert "1\tline 1" in result.content
    assert "10\tline 10" in result.content


@pytest.mark.asyncio
async def test_read_with_offset_and_limit(tmp_file):
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(tmp_file), "offset": 3, "limit": 2})
    assert not result.is_error
    assert "3\tline 3" in result.content
    assert "4\tline 4" in result.content
    assert "5\tline 5" not in result.content


@pytest.mark.asyncio
async def test_read_truncation_hint(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 2100)))
    tool = ReadTool()
    result = await tool.execute("id1", {"path": str(f)})
    assert not result.is_error
    assert "Showing lines" in result.content
    assert "Use offset=" in result.content


@pytest.mark.asyncio
async def test_read_missing_file():
    tool = ReadTool()
    result = await tool.execute("id1", {"path": "/nonexistent/file.txt"})
    assert result.is_error
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py::test_read_basic -v 2>&1 | head -10
```

Expected: `ImportError` 或 `ModuleNotFoundError`

- [ ] **Step 3: 实现 `read.py`**

```python
# src/pi/tools/read.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult

MAX_LINES = 2000
MAX_BYTES = 200 * 1024  # 200KB


class ReadTool(Tool):
    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Returns line-numbered content. "
            "Use offset and limit for large files."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to file (relative or absolute)"},
                "offset": {"type": "number", "description": "Line number to start from (1-indexed)"},
                "limit": {"type": "number", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path_str = args.get("path", "")
        offset = int(args.get("offset", 1))
        limit = args.get("limit")

        path = Path(path_str)
        if not path.exists():
            return ToolResult.err(f"File not found: {path_str}")
        if not path.is_file():
            return ToolResult.err(f"Not a file: {path_str}")

        try:
            raw = path.read_bytes()
        except OSError as e:
            return ToolResult.err(f"Cannot read {path_str}: {e}")

        # Byte truncation check (200KB)
        byte_truncated = len(raw) > MAX_BYTES
        if byte_truncated:
            raw = raw[:MAX_BYTES]

        text = raw.decode("utf-8", errors="replace")
        all_lines = text.splitlines()
        total = len(all_lines)

        # offset is 1-indexed
        start = max(0, offset - 1)
        end = start + (int(limit) if limit is not None else MAX_LINES)
        end = min(end, start + MAX_LINES)  # cap at MAX_LINES regardless
        slice_lines = all_lines[start:end]

        lines_shown_start = start + 1
        lines_shown_end = start + len(slice_lines)

        numbered = "\n".join(f"{lines_shown_start + i}\t{line}" for i, line in enumerate(slice_lines))

        truncated = end < total or byte_truncated
        if truncated:
            numbered += f"\n[Showing lines {lines_shown_start}-{lines_shown_end} of {total}. Use offset={lines_shown_end + 1} to continue.]"

        return ToolResult.ok(numbered)
```

- [ ] **Step 4: 运行 read 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py::test_read_basic tests/test_tools.py::test_read_with_offset_and_limit tests/test_tools.py::test_read_truncation_hint tests/test_tools.py::test_read_missing_file -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/read.py agent-python/tests/test_tools.py
git commit -m "feat(python): read tool with line numbers, offset/limit, truncation"
```

---

## Task 5: write 工具

**Files:**
- Create: `agent-python/src/pi/tools/write.py`

- [ ] **Step 1: 在 test_tools.py 追加写工具测试**

```python
# 追加到 tests/test_tools.py

# ── write ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_creates_file(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "out.txt"
    result = await tool.execute("id1", {"path": str(dest), "content": "hello world"})
    assert not result.is_error
    assert dest.read_text() == "hello world"


@pytest.mark.asyncio
async def test_write_creates_parent_dirs(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "a" / "b" / "c.txt"
    result = await tool.execute("id1", {"path": str(dest), "content": "nested"})
    assert not result.is_error
    assert dest.read_text() == "nested"


@pytest.mark.asyncio
async def test_write_overwrites_existing(tmp_path):
    tool = WriteTool()
    dest = tmp_path / "file.txt"
    dest.write_text("old content")
    result = await tool.execute("id1", {"path": str(dest), "content": "new content"})
    assert not result.is_error
    assert dest.read_text() == "new content"
```

- [ ] **Step 2: 实现 `write.py`**

```python
# src/pi/tools/write.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class WriteTool(Tool):
    @property
    def name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return "Write content to a file, creating parent directories as needed. Overwrites existing files."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path_str = args.get("path", "")
        content = args.get("content", "")

        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot write {path_str}: {e}")

        return ToolResult.ok(f"Written {len(content)} bytes to {path_str}")
```

- [ ] **Step 3: 运行 write 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py::test_write_creates_file tests/test_tools.py::test_write_creates_parent_dirs tests/test_tools.py::test_write_overwrites_existing -v
```

Expected: `3 passed`

- [ ] **Step 4: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/write.py agent-python/tests/test_tools.py
git commit -m "feat(python): write tool"
```

---

## Task 6: edit 工具

**Files:**
- Create: `agent-python/src/pi/tools/edit.py`

- [ ] **Step 1: 在 test_tools.py 追加 edit 测试**

```python
# 追加到 tests/test_tools.py

# ── edit ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def editable_file(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("x = 1\ny = 2\nreturn False\n")
    return f


@pytest.mark.asyncio
async def test_edit_single_replacement(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [{"oldText": "x = 1", "newText": "x = 42"}],
    })
    assert not result.is_error
    assert editable_file.read_text() == "x = 42\ny = 2\nreturn False\n"


@pytest.mark.asyncio
async def test_edit_multiple_replacements(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [
            {"oldText": "x = 1", "newText": "x = 10"},
            {"oldText": "return False", "newText": "return True"},
        ],
    })
    assert not result.is_error
    content = editable_file.read_text()
    assert "x = 10" in content
    assert "return True" in content


@pytest.mark.asyncio
async def test_edit_not_found_error(editable_file):
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(editable_file),
        "edits": [{"oldText": "nonexistent string", "newText": "x"}],
    })
    assert result.is_error
    assert "not found" in result.content.lower()


@pytest.mark.asyncio
async def test_edit_duplicate_error(tmp_path):
    f = tmp_path / "dup.py"
    f.write_text("foo\nfoo\n")
    tool = EditTool()
    result = await tool.execute("id1", {
        "path": str(f),
        "edits": [{"oldText": "foo", "newText": "bar"}],
    })
    assert result.is_error
    assert "2 times" in result.content or "twice" in result.content or "2" in result.content


@pytest.mark.asyncio
async def test_edit_no_partial_write_on_first_failure(tmp_path):
    f = tmp_path / "partial.py"
    f.write_text("a = 1\nb = 2\n")
    tool = EditTool()
    # Second edit will fail (not found), so first should NOT be applied
    result = await tool.execute("id1", {
        "path": str(f),
        "edits": [
            {"oldText": "a = 1", "newText": "a = 99"},
            {"oldText": "DOES_NOT_EXIST", "newText": "x"},
        ],
    })
    assert result.is_error
    assert f.read_text() == "a = 1\nb = 2\n"  # unchanged
```

- [ ] **Step 2: 实现 `edit.py`**

```python
# src/pi/tools/edit.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class EditTool(Tool):
    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing exact text. Each oldText must appear exactly once. "
            "All edits are validated before writing — no partial writes on failure."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {
                                "type": "string",
                                "description": "Exact text to replace — must be unique in file",
                            },
                            "newText": {"type": "string"},
                        },
                        "required": ["oldText", "newText"],
                    },
                },
            },
            "required": ["path", "edits"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path_str = args.get("path", "")
        edits = args.get("edits", [])

        if not edits:
            return ToolResult.err("'edits' array is empty")

        path = Path(path_str)
        try:
            original = path.read_text(encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot read {path_str}: {e}")

        # Validate ALL edits against the original before writing anything
        for edit in edits:
            old = edit.get("oldText", "")
            if not old:
                return ToolResult.err("An edit is missing 'oldText'")
            if "newText" not in edit:
                return ToolResult.err("An edit is missing 'newText'")

            count = original.count(old)
            if count == 0:
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult.err(f"oldText not found in file: {preview!r}")
            if count > 1:
                preview = old[:80] + ("..." if len(old) > 80 else "")
                return ToolResult.err(
                    f"oldText appears {count} times (must be unique): {preview!r}"
                )

        # All valid — apply sequentially to original content
        content = original
        for edit in edits:
            content = content.replace(edit["oldText"], edit["newText"], 1)

        try:
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"Cannot write {path_str}: {e}")

        return ToolResult.ok(f"{len(edits)} edit(s) applied to {path_str}")
```

- [ ] **Step 3: 运行 edit 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py -k "edit" -v
```

Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/edit.py agent-python/tests/test_tools.py
git commit -m "feat(python): edit tool — batch edits, uniqueness validation, atomic write"
```

---

## Task 7: bash 工具

**Files:**
- Create: `agent-python/src/pi/tools/bash.py`

- [ ] **Step 1: 在 test_tools.py 追加 bash 测试**

```python
# 追加到 tests/test_tools.py

# ── bash ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bash_simple_command():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "echo hello"})
    assert not result.is_error
    assert "hello" in result.content


@pytest.mark.asyncio
async def test_bash_stderr_merged():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "echo out && echo err >&2"})
    assert not result.is_error
    assert "out" in result.content
    assert "err" in result.content


@pytest.mark.asyncio
async def test_bash_exit_code_nonzero():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "exit 1"})
    assert result.is_error


@pytest.mark.asyncio
async def test_bash_timeout():
    tool = BashTool()
    result = await tool.execute("id1", {"command": "sleep 10", "timeout": 0.2})
    assert result.is_error
    assert "timed out" in result.content.lower() or "timeout" in result.content.lower()


@pytest.mark.asyncio
async def test_bash_strips_ansi():
    tool = BashTool()
    result = await tool.execute("id1", {"command": r"printf '\033[31mred\033[0m'"})
    assert not result.is_error
    assert "\033[" not in result.content
    assert "red" in result.content
```

- [ ] **Step 2: 实现 `bash.py`**

```python
# src/pi/tools/bash.py
from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from .base import Tool, ToolResult

MAX_OUTPUT_BYTES = 200 * 1024  # 200KB
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class BashTool(Tool):
    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. stdout and stderr are merged. "
            "Use timeout (seconds) to limit execution time."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (optional, no default)",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        command = args.get("command", "")
        timeout = args.get("timeout")

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        output_chunks: list[bytes] = []
        total_bytes = 0
        truncated = False

        async def read_output() -> None:
            nonlocal total_bytes, truncated
            assert proc.stdout is not None
            async for chunk in proc.stdout:
                if total_bytes + len(chunk) > MAX_OUTPUT_BYTES:
                    remaining = MAX_OUTPUT_BYTES - total_bytes
                    if remaining > 0:
                        output_chunks.append(chunk[:remaining])
                    truncated = True
                    break
                output_chunks.append(chunk)
                total_bytes += len(chunk)
                if on_update:
                    on_update(chunk.decode("utf-8", errors="replace"))

        try:
            coro = asyncio.gather(read_output(), proc.wait())
            if timeout is not None:
                await asyncio.wait_for(coro, timeout=float(timeout))
            else:
                await coro
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return ToolResult.err(f"Command timed out after {timeout}s")
        except asyncio.CancelledError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise

        raw = b"".join(output_chunks).decode("utf-8", errors="replace")
        output = _strip_ansi(raw)
        if truncated:
            output += f"\n[Output truncated at {MAX_OUTPUT_BYTES // 1024}KB]"

        if proc.returncode != 0:
            return ToolResult(
                content=output or f"Command exited with code {proc.returncode}",
                is_error=True,
            )

        return ToolResult.ok(output)
```

- [ ] **Step 3: 运行 bash 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py -k "bash" -v
```

Expected: `5 passed`

- [ ] **Step 4: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/bash.py agent-python/tests/test_tools.py
git commit -m "feat(python): bash tool — subprocess, timeout, ANSI strip, output truncation"
```

---

## Task 8: find / grep / ls 工具

**Files:**
- Create: `agent-python/src/pi/tools/find.py`
- Create: `agent-python/src/pi/tools/grep.py`
- Create: `agent-python/src/pi/tools/ls.py`

- [ ] **Step 1: 在 test_tools.py 追加三个工具的测试**

```python
# 追加到 tests/test_tools.py

# ── find ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def dir_tree(tmp_path):
    (tmp_path / "a.py").write_text("# a")
    (tmp_path / "b.py").write_text("# b")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("# c")
    (tmp_path / "sub" / "d.txt").write_text("text")
    return tmp_path


@pytest.mark.asyncio
async def test_find_all_py(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*.py"})
    assert not result.is_error
    assert "a.py" in result.content
    assert "c.py" in result.content


@pytest.mark.asyncio
async def test_find_type_file(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*", "type": "file"})
    assert not result.is_error
    assert "sub" not in result.content.split("\n")[0]  # first result is a file


@pytest.mark.asyncio
async def test_find_type_dir(dir_tree):
    tool = FindTool()
    result = await tool.execute("id1", {"path": str(dir_tree), "pattern": "*", "type": "dir"})
    assert not result.is_error
    assert "sub" in result.content


# ── grep ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def grep_dir(tmp_path):
    (tmp_path / "a.py").write_text("hello world\nfoo bar\n")
    (tmp_path / "b.py").write_text("HELLO WORLD\ntest\n")
    return tmp_path


@pytest.mark.asyncio
async def test_grep_basic(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {"path": str(grep_dir), "pattern": "hello"})
    assert not result.is_error
    assert "a.py" in result.content
    assert "hello world" in result.content


@pytest.mark.asyncio
async def test_grep_ignore_case(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {
        "path": str(grep_dir), "pattern": "hello", "ignore_case": True
    })
    assert not result.is_error
    assert "a.py" in result.content
    assert "b.py" in result.content


@pytest.mark.asyncio
async def test_grep_single_file(grep_dir):
    tool = GrepTool()
    result = await tool.execute("id1", {
        "path": str(grep_dir / "a.py"),
        "pattern": "foo",
        "recursive": False,
    })
    assert not result.is_error
    assert "foo bar" in result.content


# ── ls ────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ls_basic(dir_tree):
    tool = LsTool()
    result = await tool.execute("id1", {"path": str(dir_tree)})
    assert not result.is_error
    assert "a.py" in result.content
    assert "sub" in result.content


@pytest.mark.asyncio
async def test_ls_not_recursive(dir_tree):
    tool = LsTool()
    result = await tool.execute("id1", {"path": str(dir_tree)})
    assert not result.is_error
    assert "c.py" not in result.content  # inside sub/, not shown at top level
```

- [ ] **Step 2: 实现 `find.py`**

```python
# src/pi/tools/find.py
from __future__ import annotations

import asyncio
import fnmatch
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class FindTool(Tool):
    @property
    def name(self) -> str:
        return "find"

    @property
    def description(self) -> str:
        return "Recursively find files or directories matching a glob pattern."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Filename glob pattern (e.g. *.py)"},
                "type": {
                    "type": "string",
                    "enum": ["file", "dir", "any"],
                    "description": "Filter by entry type",
                },
            },
            "required": ["path", "pattern"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        root = Path(args.get("path", "."))
        pattern = args.get("pattern", "*")
        type_filter = args.get("type", "any")

        if not root.exists():
            return ToolResult.err(f"Path not found: {root}")

        matches: list[str] = []
        for entry in root.rglob("*"):
            if not fnmatch.fnmatch(entry.name, pattern):
                continue
            if type_filter == "file" and not entry.is_file():
                continue
            if type_filter == "dir" and not entry.is_dir():
                continue
            matches.append(str(entry.relative_to(root)))

        matches.sort()
        if not matches:
            return ToolResult.ok("No matches found.")
        return ToolResult.ok("\n".join(matches))
```

- [ ] **Step 3: 实现 `grep.py`**

```python
# src/pi/tools/grep.py
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class GrepTool(Tool):
    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search for a regex pattern in a file or directory. Returns file:line:content."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "pattern": {"type": "string", "description": "Regex pattern"},
                "recursive": {"type": "boolean", "default": True},
                "ignore_case": {"type": "boolean", "default": False},
            },
            "required": ["path", "pattern"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path = Path(args.get("path", "."))
        pattern_str = args.get("pattern", "")
        recursive = args.get("recursive", True)
        ignore_case = args.get("ignore_case", False)

        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as e:
            return ToolResult.err(f"Invalid regex pattern: {e}")

        files: list[Path] = []
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(path.rglob("*") if recursive else path.iterdir())
            files = [f for f in files if f.is_file()]
        else:
            return ToolResult.err(f"Path not found: {path}")

        results: list[str] = []
        for file in files:
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{file}:{lineno}:{line}")

        if not results:
            return ToolResult.ok("No matches found.")
        return ToolResult.ok("\n".join(results))
```

- [ ] **Step 4: 实现 `ls.py`**

```python
# src/pi/tools/ls.py
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from .base import Tool, ToolResult


class LsTool(Tool):
    @property
    def name(self) -> str:
        return "ls"

    @property
    def description(self) -> str:
        return "List the direct contents of a directory (non-recursive)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        }

    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        path = Path(args.get("path", "."))
        if not path.exists():
            return ToolResult.err(f"Path not found: {path}")
        if not path.is_dir():
            return ToolResult.err(f"Not a directory: {path}")

        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines: list[str] = []
        for entry in entries:
            kind = "file" if entry.is_file() else "dir"
            size = entry.stat().st_size if entry.is_file() else 0
            lines.append(f"{kind}\t{entry.name}\t{size}")

        if not lines:
            return ToolResult.ok("(empty directory)")
        return ToolResult.ok("\n".join(lines))
```

- [ ] **Step 5: 运行所有工具测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_tools.py -v
```

Expected: 全部通过（约 22 个测试）

- [ ] **Step 6: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tools/
git commit -m "feat(python): find/grep/ls tools"
```

---

## Task 9: LLMProvider 基类 + Anthropic 实现

**Files:**
- Create: `agent-python/src/pi/ai/base.py`
- Create: `agent-python/src/pi/ai/anthropic.py`
- Create: `agent-python/tests/test_anthropic.py`

- [ ] **Step 1: 实现 `base.py`**

```python
# src/pi/ai/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator

from .types import AssistantMessage, Message, StreamEvent
from ..tools.base import Tool


@dataclass
class StreamOptions:
    api_key: str
    model: str
    max_tokens: int = 8192
    temperature: float | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamEvent objects as the LLM responds."""
        ...
```

- [ ] **Step 2: 写失败的 Anthropic provider 测试（使用 Mock）**

```python
# tests/test_anthropic.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pi.ai.types import (
    UserMessage, TextContent, TextDelta, ToolCallEnd, StreamDone,
)
from pi.ai.anthropic import AnthropicProvider, convert_messages, convert_tools
from pi.ai.base import StreamOptions
from pi.tools.read import ReadTool


def test_convert_messages_user():
    msgs = [UserMessage(content="hello")]
    result = convert_messages(msgs)
    assert result == [{"role": "user", "content": "hello"}]


def test_convert_messages_tool_results_merged():
    from pi.ai.types import AssistantMessage, ToolCall, ToolResultMessage
    msgs = [
        UserMessage(content="hello"),
        AssistantMessage(content=[
            ToolCall(id="tc1", name="read", arguments={"path": "/tmp/x"}),
        ]),
        ToolResultMessage(
            tool_call_id="tc1",
            tool_name="read",
            content=[TextContent(text="file contents")],
        ),
    ]
    result = convert_messages(msgs)
    assert len(result) == 3
    # last item should be user role with tool_result content
    assert result[2]["role"] == "user"
    assert result[2]["content"][0]["type"] == "tool_result"


def test_convert_tools():
    tools = [ReadTool()]
    result = convert_tools(tools)
    assert len(result) == 1
    assert result[0]["name"] == "read"
    assert "input_schema" in result[0]
    assert result[0]["input_schema"]["type"] == "object"
```

- [ ] **Step 3: 运行确认失败**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_anthropic.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'AnthropicProvider'`

- [ ] **Step 4: 实现 `anthropic.py`**

```python
# src/pi/ai/anthropic.py
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import anthropic as sdk

from .base import LLMProvider, StreamOptions
from .types import (
    AssistantMessage, Message, StreamEvent, TextContent, ThinkingContent,
    ToolCall, ToolResultMessage, UserMessage,
    StreamStart, TextStart, TextDelta, TextEnd,
    ToolCallStart, ToolCallDelta, ToolCallEnd,
    StreamDone, StreamError, Usage,
)
from ..tools.base import Tool


def convert_messages(messages: list[Message]) -> list[dict]:
    """Convert internal Message list to Anthropic API format.

    Key rules:
    - ToolResultMessages are merged into a single user message as tool_result blocks.
    - AssistantMessage ToolCall → type:tool_use with input field.
    - Consecutive ToolResultMessages → one user message (Anthropic requirement).
    """
    result: list[dict] = []
    pending_tool_results: list[dict] = []

    for msg in messages:
        if isinstance(msg, ToolResultMessage):
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": [{"type": "text", "text": c.text} for c in msg.content],
                "is_error": msg.is_error,
            })
        else:
            if pending_tool_results:
                result.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

            if isinstance(msg, UserMessage):
                result.append({"role": "user", "content": msg.content
                               if isinstance(msg.content, str)
                               else [{"type": "text", "text": c.text} for c in msg.content]})
            elif isinstance(msg, AssistantMessage):
                content_blocks: list[dict] = []
                for block in msg.content:
                    if isinstance(block, TextContent):
                        content_blocks.append({"type": "text", "text": block.text})
                    elif isinstance(block, ThinkingContent):
                        content_blocks.append({
                            "type": "thinking",
                            "thinking": block.thinking,
                            "signature": block.thinking_signature or "",
                        })
                    elif isinstance(block, ToolCall):
                        content_blocks.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.arguments,
                        })
                result.append({"role": "assistant", "content": content_blocks})

    if pending_tool_results:
        result.append({"role": "user", "content": pending_tool_results})

    return result


def convert_tools(tools: list[Tool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


class AnthropicProvider(LLMProvider):
    def __init__(self, *, trust_env: bool = False) -> None:
        import httpx
        self._http = httpx.AsyncClient(trust_env=trust_env)

    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = sdk.AsyncAnthropic(
            api_key=options.api_key,
            http_client=self._http,
        )

        partial = AssistantMessage(content=[])
        yield StreamStart(partial=partial)

        # Accumulate state across SSE events
        current_block_type: str | None = None
        current_tool_id: str | None = None
        current_tool_name: str | None = None
        tool_args_buf: str = ""
        current_index: int = 0
        text_buf: str = ""

        kwargs: dict[str, Any] = dict(
            model=options.model,
            max_tokens=options.max_tokens,
            system=system_prompt,
            messages=convert_messages(messages),
            stream=True,
        )
        if tools:
            kwargs["tools"] = convert_tools(tools)
        if options.temperature is not None:
            kwargs["temperature"] = options.temperature

        async with client.messages.stream(**{k: v for k, v in kwargs.items() if k != "stream"}) as s:
            async for event in s:
                etype = event.type

                if etype == "content_block_start":
                    current_index = event.index
                    cb = event.content_block
                    current_block_type = cb.type
                    if cb.type == "text":
                        text_buf = ""
                        yield TextStart(index=current_index, partial=partial)
                    elif cb.type == "tool_use":
                        current_tool_id = cb.id
                        current_tool_name = cb.name
                        tool_args_buf = ""
                        yield ToolCallStart(index=current_index, partial=partial)

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        text_buf += delta.text
                        partial = AssistantMessage(
                            content=partial.content + [TextContent(text=text_buf)],
                            model=options.model,
                        )
                        yield TextDelta(index=current_index, delta=delta.text, partial=partial)
                    elif delta.type == "input_json_delta":
                        tool_args_buf += delta.partial_json
                        yield ToolCallDelta(index=current_index, delta=delta.partial_json, partial=partial)

                elif etype == "content_block_stop":
                    if current_block_type == "text":
                        yield TextEnd(index=current_index, content=text_buf, partial=partial)
                        partial.content.append(TextContent(text=text_buf))
                        text_buf = ""
                    elif current_block_type == "tool_use" and current_tool_id:
                        try:
                            arguments = json.loads(tool_args_buf) if tool_args_buf else {}
                        except json.JSONDecodeError:
                            arguments = {}
                        tc = ToolCall(id=current_tool_id, name=current_tool_name or "", arguments=arguments)
                        partial.content.append(tc)
                        yield ToolCallEnd(index=current_index, tool_call=tc, partial=partial)
                        current_tool_id = None
                        current_tool_name = None
                        tool_args_buf = ""
                    current_block_type = None

                elif etype == "message_delta":
                    stop_reason = getattr(event.delta, "stop_reason", None) or "stop"
                    usage = getattr(event, "usage", None)
                    if usage:
                        partial.usage = Usage(
                            input=getattr(usage, "input_tokens", 0),
                            output=getattr(usage, "output_tokens", 0),
                        )
                    partial.stop_reason = stop_reason

                elif etype == "message_stop":
                    final = await s.get_final_message()
                    partial.model = final.model
                    partial.stop_reason = final.stop_reason or "stop"
                    partial.usage = Usage(
                        input=final.usage.input_tokens,
                        output=final.usage.output_tokens,
                        cache_read=getattr(final.usage, "cache_read_input_tokens", 0) or 0,
                        cache_write=getattr(final.usage, "cache_creation_input_tokens", 0) or 0,
                    )
                    yield StreamDone(stop_reason=partial.stop_reason, message=partial)
```

- [ ] **Step 5: 运行 anthropic 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_anthropic.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/ai/
git commit -m "feat(python): LLMProvider ABC + Anthropic SSE streaming provider"
```

---

## Task 10: Agent Context + Events

**Files:**
- Create: `agent-python/src/pi/agent/context.py`
- Create: `agent-python/src/pi/agent/events.py`

- [ ] **Step 1: 实现 `context.py`**

```python
# src/pi/agent/context.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ai.types import Message
    from ..tools.base import Tool


@dataclass
class AgentConfig:
    model_id: str
    api_key: str
    provider_name: str = "anthropic"        # "anthropic" | "openai"
    tool_execution: str = "parallel"        # "sequential" | "parallel"
    max_turns: int = 50


@dataclass
class AgentContext:
    system_prompt: str
    messages: list["Message"]
    tools: list["Tool"]
    config: AgentConfig

    def tool_map(self) -> dict[str, "Tool"]:
        return {t.name: t for t in self.tools}
```

- [ ] **Step 2: 实现 `events.py`**

```python
# src/pi/agent/events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..ai.types import AssistantMessage, ToolResultMessage
    from ..tools.base import ToolResult


@dataclass
class AgentStart:
    pass


@dataclass
class AgentEnd:
    messages: list[Any]  # all new messages added this turn


@dataclass
class TurnStart:
    pass


@dataclass
class TurnEnd:
    message: Any  # AssistantMessage
    tool_results: list[Any]  # list[ToolResultMessage]


@dataclass
class MessageStart:
    message: Any


@dataclass
class MessageUpdate:
    delta: str


@dataclass
class MessageEnd:
    message: Any


@dataclass
class ToolExecStart:
    id: str
    name: str
    args: dict


@dataclass
class ToolExecUpdate:
    id: str
    partial: str


@dataclass
class ToolExecEnd:
    id: str
    name: str
    result: Any  # ToolResult
    is_error: bool


@dataclass
class AgentError:
    message: str


AgentEvent = (
    AgentStart | AgentEnd | TurnStart | TurnEnd |
    MessageStart | MessageUpdate | MessageEnd |
    ToolExecStart | ToolExecUpdate | ToolExecEnd |
    AgentError
)
```

- [ ] **Step 3: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/agent/context.py agent-python/src/pi/agent/events.py
git commit -m "feat(python): AgentContext + AgentEvent types"
```

---

## Task 11: Agent Loop

**Files:**
- Create: `agent-python/src/pi/agent/loop.py`
- Create: `agent-python/tests/test_agent_loop.py`

- [ ] **Step 1: 写失败的 agent loop 测试（Mock Provider）**

```python
# tests/test_agent_loop.py
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncGenerator

from pi.ai.types import (
    AssistantMessage, TextContent, ToolCall, ToolResultMessage,
    UserMessage, StreamDone, TextDelta, TextStart, TextEnd, StreamStart,
)
from pi.agent.context import AgentContext, AgentConfig
from pi.agent.events import (
    AgentStart, AgentEnd, TurnStart, TurnEnd,
    MessageUpdate, ToolExecStart, ToolExecEnd,
)
from pi.agent.loop import agent_loop
from pi.tools.base import Tool, ToolResult


class EchoTool(Tool):
    """Test tool that echoes the 'message' arg."""
    @property
    def name(self): return "echo"
    @property
    def description(self): return "Echo a message"
    @property
    def parameters(self):
        return {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}

    async def execute(self, tool_call_id, args, signal=None, on_update=None):
        return ToolResult.ok(f"echo: {args.get('message', '')}")


def make_provider(events: list):
    """Create a mock provider that yields a fixed list of StreamEvents."""
    from pi.ai.base import LLMProvider, StreamOptions

    class MockProvider(LLMProvider):
        async def stream(self, messages, system_prompt, tools, options) -> AsyncGenerator:
            for e in events:
                yield e
                await asyncio.sleep(0)

    return MockProvider()


def make_context(tools=None):
    return AgentContext(
        system_prompt="You are a helpful assistant.",
        messages=[],
        tools=tools or [],
        config=AgentConfig(model_id="claude-sonnet-4-6", api_key="test-key"),
    )


@pytest.mark.asyncio
async def test_simple_text_response():
    partial = AssistantMessage(content=[TextContent(text="Hello!")], stop_reason="stop")
    provider = make_provider([
        StreamStart(partial=AssistantMessage(content=[])),
        TextStart(index=0, partial=partial),
        TextDelta(index=0, delta="Hello!", partial=partial),
        TextEnd(index=0, content="Hello!", partial=partial),
        StreamDone(stop_reason="stop", message=partial),
    ])

    events = []
    ctx = make_context()
    await agent_loop("hi", ctx, provider, lambda e: events.append(e))

    assert any(isinstance(e, AgentStart) for e in events)
    assert any(isinstance(e, AgentEnd) for e in events)
    assert any(isinstance(e, MessageUpdate) and "Hello!" in e.delta for e in events)
    # assistant message should be in ctx.messages
    assert any(isinstance(m, AssistantMessage) for m in ctx.messages)


@pytest.mark.asyncio
async def test_tool_call_execution():
    tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "world"})
    partial_with_tool = AssistantMessage(content=[tool_call], stop_reason="tool_use")
    final_text = AssistantMessage(content=[TextContent(text="Done!")], stop_reason="stop")

    call_count = [0]

    class CountingProvider:
        from pi.ai.base import LLMProvider, StreamOptions
        async def stream(self, messages, system_prompt, tools, options):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return a tool call
                yield StreamStart(partial=AssistantMessage(content=[]))
                yield StreamDone(stop_reason="tool_use", message=partial_with_tool)
            else:
                # Second call: return final text
                yield StreamStart(partial=AssistantMessage(content=[]))
                yield TextDelta(index=0, delta="Done!", partial=final_text)
                yield StreamDone(stop_reason="stop", message=final_text)

    events = []
    ctx = make_context(tools=[EchoTool()])
    await agent_loop("say world", ctx, CountingProvider(), lambda e: events.append(e))

    assert call_count[0] == 2  # LLM was called twice
    assert any(isinstance(e, ToolExecStart) and e.name == "echo" for e in events)
    assert any(isinstance(e, ToolExecEnd) and not e.is_error for e in events)
    # Tool result should be in messages
    assert any(isinstance(m, ToolResultMessage) for m in ctx.messages)


@pytest.mark.asyncio
async def test_max_turns_exceeded():
    tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "loop"})
    looping_msg = AssistantMessage(content=[tool_call], stop_reason="tool_use")

    class InfiniteProvider:
        async def stream(self, *a, **kw):
            yield StreamStart(partial=AssistantMessage(content=[]))
            yield StreamDone(stop_reason="tool_use", message=looping_msg)

    events = []
    ctx = make_context(tools=[EchoTool()])
    ctx.config.max_turns = 3
    await agent_loop("loop", ctx, InfiniteProvider(), lambda e: events.append(e))

    assert any(isinstance(e, AgentEnd) for e in events)


@pytest.mark.asyncio
async def test_cancellation():
    signal = asyncio.Event()

    async def slow_stream(*a, **kw):
        yield StreamStart(partial=AssistantMessage(content=[]))
        await asyncio.sleep(10)  # simulates slow LLM
        yield StreamDone(stop_reason="stop", message=AssistantMessage(content=[]))

    class SlowProvider:
        stream = slow_stream

    events = []
    ctx = make_context()

    async def run():
        await agent_loop("go", ctx, SlowProvider(), lambda e: events.append(e), signal=signal)

    task = asyncio.create_task(run())
    await asyncio.sleep(0.05)
    signal.set()  # signal cancellation
    await asyncio.wait_for(task, timeout=1.0)

    assert any(isinstance(e, AgentEnd) for e in events)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_agent_loop.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'agent_loop'`

- [ ] **Step 3: 实现 `loop.py`**

```python
# src/pi/agent/loop.py
from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from ..ai.types import (
    AssistantMessage, Message, TextContent, ToolCall, ToolResultMessage, UserMessage,
    StreamDone, StreamError, TextDelta, ToolCallEnd, StreamStart,
)
from ..ai.base import LLMProvider, StreamOptions
from ..tools.base import ToolResult
from .context import AgentContext
from .events import (
    AgentEnd, AgentError, AgentEvent, AgentStart,
    MessageEnd, MessageStart, MessageUpdate,
    ToolExecEnd, ToolExecStart, ToolExecUpdate,
    TurnEnd, TurnStart,
)

Emit = Callable[[AgentEvent], None]


async def agent_loop(
    user_message: str,
    ctx: AgentContext,
    provider: LLMProvider,
    emit: Emit,
    signal: asyncio.Event | None = None,
) -> list[Message]:
    """Execute one agent turn: user message → LLM → tool calls → repeat → final response."""
    new_messages: list[Message] = []

    user_msg = UserMessage(content=user_message)
    ctx.messages.append(user_msg)
    new_messages.append(user_msg)

    emit(AgentStart())

    for turn in range(ctx.config.max_turns):
        emit(TurnStart())

        opts = StreamOptions(
            api_key=ctx.config.api_key,
            model=ctx.config.model_id,
        )

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        assistant_msg: AssistantMessage | None = None

        try:
            async for event in provider.stream(ctx.messages, ctx.system_prompt, ctx.tools, opts):
                # Check cancellation before each event
                if signal and signal.is_set():
                    emit(AgentEnd(messages=new_messages))
                    return new_messages

                if isinstance(event, TextDelta):
                    text_parts.append(event.delta)
                    emit(MessageUpdate(delta=event.delta))
                elif isinstance(event, ToolCallEnd):
                    tool_calls.append(event.tool_call)
                elif isinstance(event, (StreamDone, StreamError)):
                    assistant_msg = event.message
        except asyncio.CancelledError:
            emit(AgentEnd(messages=new_messages))
            return new_messages

        if assistant_msg is None:
            # Build from accumulated parts if provider didn't emit a final Done
            content = []
            if text_parts:
                content.append(TextContent(text="".join(text_parts)))
            content.extend(tool_calls)
            assistant_msg = AssistantMessage(content=content)

        ctx.messages.append(assistant_msg)
        new_messages.append(assistant_msg)
        emit(MessageEnd(message=assistant_msg))

        if not tool_calls:
            # No tools → conversation turn is complete
            emit(TurnEnd(message=assistant_msg, tool_results=[]))
            break

        # Execute tools
        tool_results: list[ToolResultMessage] = []
        tool_map = ctx.tool_map()

        if ctx.config.tool_execution == "parallel":
            tasks = [
                _execute_tool(tc, tool_map, emit, signal)
                for tc in tool_calls
            ]
            results = await asyncio.gather(*tasks)
            tool_results = [r for r in results if r is not None]
        else:
            for tc in tool_calls:
                r = await _execute_tool(tc, tool_map, emit, signal)
                if r is not None:
                    tool_results.append(r)

        for tr in tool_results:
            ctx.messages.append(tr)
            new_messages.append(tr)

        emit(TurnEnd(message=assistant_msg, tool_results=tool_results))
        # Continue loop — LLM will see tool results
    else:
        emit(AgentError(message=f"Max turns ({ctx.config.max_turns}) exceeded"))

    emit(AgentEnd(messages=new_messages))
    return new_messages


async def _execute_tool(
    tc: ToolCall,
    tool_map: dict,
    emit: Emit,
    signal: asyncio.Event | None,
) -> ToolResultMessage | None:
    emit(ToolExecStart(id=tc.id, name=tc.name, args=tc.arguments))

    tool = tool_map.get(tc.name)
    if tool is None:
        result = ToolResult.err(f"Unknown tool: {tc.name}")
    else:
        def on_update(partial: str) -> None:
            emit(ToolExecUpdate(id=tc.id, partial=partial))

        try:
            result = await tool.execute(tc.id, tc.arguments, signal=signal, on_update=on_update)
        except Exception as e:
            result = ToolResult.err(f"Tool execution error: {e}")

    emit(ToolExecEnd(id=tc.id, name=tc.name, result=result, is_error=result.is_error))

    return ToolResultMessage(
        tool_call_id=tc.id,
        tool_name=tc.name,
        content=[TextContent(text=result.content)],
        is_error=result.is_error,
        details=result.details,
    )
```

- [ ] **Step 4: 运行 agent loop 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_agent_loop.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/agent/
git commit -m "feat(python): agent loop — state machine, parallel tool execution, cancellation"
```

---

## Task 12: Session Manager

**Files:**
- Create: `agent-python/src/pi/session/manager.py`
- Create: `agent-python/tests/test_session.py`

- [ ] **Step 1: 写失败的 session 测试**

```python
# tests/test_session.py
import pytest
import json
from pathlib import Path
from pi.session.manager import SessionManager, Session
from pi.ai.types import UserMessage, AssistantMessage, TextContent


def test_new_session_creates_file(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    session_file = tmp_path / f"{session.id}.pi"
    assert session_file.exists()
    # First line must be session header
    first_line = session_file.read_text().splitlines()[0]
    header = json.loads(first_line)
    assert header["type"] == "session"
    assert header["version"] == 3
    assert header["id"] == session.id


def test_append_message_entry(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    msg = UserMessage(content="hello")
    mgr.append_message(session, msg)

    lines = (tmp_path / f"{session.id}.pi").read_text().splitlines()
    assert len(lines) == 2  # header + message
    entry = json.loads(lines[1])
    assert entry["type"] == "message"
    assert entry["message"]["role"] == "user"


def test_load_session_restores_messages(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    mgr.append_message(session, UserMessage(content="hi"))
    mgr.append_message(session, AssistantMessage(content=[TextContent(text="hello!")]))

    loaded = mgr.load_session(session.id)
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"


def test_list_sessions(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    s1 = mgr.new_session(cwd="/tmp")
    s2 = mgr.new_session(cwd="/home")
    sessions = mgr.list_sessions()
    ids = [s.id for s in sessions]
    assert s1.id in ids
    assert s2.id in ids


def test_delete_session(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    mgr.delete_session(session.id)
    assert not (tmp_path / f"{session.id}.pi").exists()
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_session.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'SessionManager'`

- [ ] **Step 3: 实现 `manager.py`**

```python
# src/pi/session/manager.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ai.types import (
    AssistantMessage, Message, TextContent, ThinkingContent,
    ToolCall, ToolResultMessage, UserMessage, Usage,
)

DEFAULT_SESSION_DIR = Path.home() / ".pi" / "sessions"


@dataclass
class Session:
    id: str
    cwd: str
    created_at: str
    messages: list[Message] = field(default_factory=list)
    model_id: str = ""
    thinking_level: str = "none"


@dataclass
class SessionMeta:
    id: str
    cwd: str
    created_at: str
    message_count: int


class SessionManager:
    def __init__(self, session_dir: Path | str | None = None) -> None:
        self.dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.pi"

    def new_session(self, cwd: str) -> Session:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = Session(id=session_id, cwd=cwd, created_at=now)

        header = {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": now,
            "cwd": cwd,
        }
        self._path(session_id).write_text(json.dumps(header) + "\n", encoding="utf-8")
        return session

    def append_message(self, session: Session, message: Message) -> None:
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Get parent id (last entry's id, or None)
        lines = self._path(session.id).read_text().splitlines()
        parent_id = None
        if len(lines) > 1:
            try:
                last = json.loads(lines[-1])
                parent_id = last.get("id")
            except (json.JSONDecodeError, KeyError):
                pass

        msg_dict = _message_to_dict(message)

        entry = {
            "type": "message",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": now,
            "message": msg_dict,
        }
        with self._path(session.id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        session.messages.append(message)

    def load_session(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        lines = path.read_text(encoding="utf-8").splitlines()
        header = json.loads(lines[0])

        session = Session(
            id=header["id"],
            cwd=header.get("cwd", ""),
            created_at=header.get("timestamp", ""),
        )

        for line in lines[1:]:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("type") == "message":
                msg = _dict_to_message(entry["message"])
                if msg:
                    session.messages.append(msg)
            elif entry.get("type") == "model_change":
                session.model_id = entry.get("modelId", "")

        return session

    def list_sessions(self) -> list[SessionMeta]:
        metas: list[SessionMeta] = []
        for path in sorted(self.dir.glob("*.pi"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                header = json.loads(lines[0])
                if header.get("type") != "session":
                    continue
                msg_count = sum(
                    1 for line in lines[1:]
                    if line.strip() and json.loads(line).get("type") == "message"
                )
                metas.append(SessionMeta(
                    id=header["id"],
                    cwd=header.get("cwd", ""),
                    created_at=header.get("timestamp", ""),
                    message_count=msg_count,
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return metas

    def delete_session(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()


def _message_to_dict(msg: Message) -> dict:
    if isinstance(msg, UserMessage):
        return {"role": "user", "content": msg.content, "timestamp": msg.timestamp}
    if isinstance(msg, AssistantMessage):
        blocks = []
        for block in msg.content:
            if isinstance(block, TextContent):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolCall):
                blocks.append({"type": "tool_call", "id": block.id, "name": block.name, "arguments": block.arguments})
            elif isinstance(block, ThinkingContent):
                blocks.append({"type": "thinking", "thinking": block.thinking})
        return {
            "role": "assistant",
            "content": blocks,
            "model": msg.model,
            "stop_reason": msg.stop_reason,
            "usage": {"input": msg.usage.input, "output": msg.usage.output},
            "timestamp": msg.timestamp,
        }
    if isinstance(msg, ToolResultMessage):
        return {
            "role": "tool_result",
            "tool_call_id": msg.tool_call_id,
            "tool_name": msg.tool_name,
            "content": [{"type": "text", "text": c.text} for c in msg.content],
            "is_error": msg.is_error,
            "timestamp": msg.timestamp,
        }
    return {}


def _dict_to_message(d: dict) -> Message | None:
    role = d.get("role")
    if role == "user":
        content = d.get("content", "")
        return UserMessage(content=content, timestamp=d.get("timestamp", 0))
    if role == "assistant":
        content_blocks = []
        for block in d.get("content", []):
            btype = block.get("type")
            if btype == "text":
                content_blocks.append(TextContent(text=block["text"]))
            elif btype == "tool_call":
                content_blocks.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("arguments", {}),
                ))
            elif btype == "thinking":
                content_blocks.append(ThinkingContent(thinking=block["thinking"]))
        usage_raw = d.get("usage", {})
        return AssistantMessage(
            content=content_blocks,
            model=d.get("model", ""),
            stop_reason=d.get("stop_reason", "stop"),
            usage=Usage(input=usage_raw.get("input", 0), output=usage_raw.get("output", 0)),
            timestamp=d.get("timestamp", 0),
        )
    if role == "tool_result":
        content = [TextContent(text=c.get("text", "")) for c in d.get("content", [])]
        return ToolResultMessage(
            tool_call_id=d.get("tool_call_id", ""),
            tool_name=d.get("tool_name", ""),
            content=content,
            is_error=d.get("is_error", False),
            timestamp=d.get("timestamp", 0),
        )
    return None
```

- [ ] **Step 4: 运行 session 测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/test_session.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/session/
git commit -m "feat(python): session manager — NDJSON read/write, compaction-ready"
```

---

## Task 13: TUI（Textual）

**Files:**
- Create: `agent-python/src/pi/tui/app.py`
- Create: `agent-python/src/pi/tui/widgets/chat.py`
- Create: `agent-python/src/pi/tui/widgets/input.py`
- Create: `agent-python/src/pi/tui/widgets/status.py`

- [ ] **Step 1: 实现 `widgets/status.py`**

```python
# src/pi/tui/widgets/status.py
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary-background;
        color: $text-muted;
        padding: 0 1;
    }
    """

    model_name: reactive[str] = reactive("—")
    token_count: reactive[int] = reactive(0)
    elapsed_ms: reactive[int] = reactive(0)
    is_streaming: reactive[bool] = reactive(False)

    def render(self) -> Text:
        spinner = "⠋" if self.is_streaming else " "
        elapsed = f"{self.elapsed_ms / 1000:.1f}s" if self.elapsed_ms else "—"
        return Text(
            f" {spinner} {self.model_name}  |  {self.token_count} tokens  |  {elapsed}",
            style="dim",
        )
```

- [ ] **Step 2: 实现 `widgets/chat.py`**

```python
# src/pi/tui/widgets/chat.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.widget import Widget
from textual.scroll_view import ScrollView
from textual import events
from textual.app import RenderResult


@dataclass
class ChatMessage:
    role: str          # "user" | "assistant" | "tool"
    content: str
    tool_name: str = ""
    is_error: bool = False


class ChatView(ScrollView):
    DEFAULT_CSS = """
    ChatView {
        height: 1fr;
        border: none;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._messages: list[ChatMessage] = []
        self._stream_buf: str = ""

    def add_message(self, msg: ChatMessage) -> None:
        self._messages.append(msg)
        self._stream_buf = ""
        self.refresh(layout=True)

    def append_stream(self, delta: str) -> None:
        self._stream_buf += delta
        self.refresh()

    def flush_stream(self, final_text: str) -> None:
        self._stream_buf = ""
        self.refresh()

    def render(self) -> RenderResult:
        from rich.console import Group
        from rich.rule import Rule

        lines = []
        for msg in self._messages:
            if msg.role == "user":
                lines.append(Text(f"You: {msg.content}", style="bold white"))
            elif msg.role == "assistant":
                lines.append(Markdown(msg.content))
            elif msg.role == "tool":
                color = "red" if msg.is_error else "yellow"
                lines.append(Text(f"[{msg.tool_name}] {msg.content[:200]}", style=color))
            lines.append(Text(""))

        if self._stream_buf:
            lines.append(Markdown(self._stream_buf))

        return Group(*lines) if lines else Text("Start a conversation...")
```

- [ ] **Step 3: 实现 `widgets/input.py`**

```python
# src/pi/tui/widgets/input.py
from __future__ import annotations

from textual.widgets import TextArea
from textual.binding import Binding
from textual import events


class InputWidget(TextArea):
    DEFAULT_CSS = """
    InputWidget {
        height: 5;
        border: solid $primary;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+enter", "submit", "Send", show=True),
        Binding("ctrl+j", "submit", "Send", show=False),
    ]

    def action_submit(self) -> None:
        text = self.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            self.clear()

    class Submitted(events.Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text
```

- [ ] **Step 4: 实现 `app.py`**

```python
# src/pi/tui/app.py
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from ..agent.context import AgentContext, AgentConfig
from ..agent.events import (
    AgentEnd, MessageUpdate, ToolExecEnd, ToolExecStart,
)
from ..agent.loop import agent_loop
from ..ai.anthropic import AnthropicProvider
from ..session.manager import SessionManager
from ..tools.bash import BashTool
from ..tools.edit import EditTool
from ..tools.find import FindTool
from ..tools.grep import GrepTool
from ..tools.ls import LsTool
from ..tools.read import ReadTool
from ..tools.write import WriteTool
from .widgets.chat import ChatMessage, ChatView
from .widgets.input import InputWidget
from .widgets.status import StatusBar

SYSTEM_PROMPT = """You are a skilled coding assistant. You help users with programming tasks.
You have access to tools to read, write, and edit files, run bash commands, and search code.
Always think step by step and use tools to accomplish tasks."""


class PiApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel_or_quit", "Cancel/Quit", show=True),
        Binding("ctrl+l", "clear_screen", "Clear", show=False),
    ]

    def __init__(self, model_id: str, api_key: str, cwd: str) -> None:
        super().__init__()
        self._model_id = model_id
        self._api_key = api_key
        self._cwd = cwd
        self._cancel_signal: asyncio.Event | None = None
        self._agent_task: asyncio.Task | None = None
        self._session_mgr = SessionManager()
        self._session = self._session_mgr.new_session(cwd)
        self._start_time: float = 0.0

        self._provider = AnthropicProvider()
        self._tools = [
            ReadTool(), WriteTool(), EditTool(), BashTool(),
            FindTool(), GrepTool(), LsTool(),
        ]
        self._ctx = AgentContext(
            system_prompt=SYSTEM_PROMPT,
            messages=[],
            tools=self._tools,
            config=AgentConfig(model_id=model_id, api_key=api_key),
        )

    def compose(self) -> ComposeResult:
        yield ChatView(id="chat")
        yield InputWidget(id="input")
        yield StatusBar(id="status")

    def on_input_widget_submitted(self, event: InputWidget.Submitted) -> None:
        self._start_turn(event.text)

    def _start_turn(self, user_text: str) -> None:
        chat = self.query_one(ChatView)
        chat.add_message(ChatMessage(role="user", content=user_text))

        status = self.query_one(StatusBar)
        status.model_name = self._model_id
        status.is_streaming = True
        self._start_time = time.monotonic()

        self._cancel_signal = asyncio.Event()
        self._agent_task = asyncio.create_task(
            self._run_agent(user_text, self._cancel_signal)
        )

    async def _run_agent(self, user_text: str, signal: asyncio.Event) -> None:
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        assistant_buf: list[str] = []
        current_tool: str = ""

        def emit(event) -> None:
            if isinstance(event, MessageUpdate):
                assistant_buf.append(event.delta)
                chat.append_stream(event.delta)
            elif isinstance(event, ToolExecStart):
                nonlocal current_tool
                current_tool = event.name
                chat.add_message(ChatMessage(
                    role="tool",
                    content=f"Running {event.name}...",
                    tool_name=event.name,
                ))
            elif isinstance(event, ToolExecEnd):
                chat.add_message(ChatMessage(
                    role="tool",
                    content=event.result.content[:500],
                    tool_name=event.name,
                    is_error=event.is_error,
                ))
                # Update token count if available
            elif isinstance(event, AgentEnd):
                full_text = "".join(assistant_buf)
                if full_text:
                    chat.flush_stream(full_text)
                    chat.add_message(ChatMessage(role="assistant", content=full_text))
                elapsed = int((time.monotonic() - self._start_time) * 1000)
                status.elapsed_ms = elapsed
                status.is_streaming = False

        await agent_loop(user_text, self._ctx, self._provider, emit, signal=signal)

        for msg in self._ctx.messages[-10:]:  # persist recent messages
            self._session_mgr.append_message(self._session, msg)

    def action_cancel_or_quit(self) -> None:
        if self._cancel_signal and not self._cancel_signal.is_set() and self.query_one(StatusBar).is_streaming:
            self._cancel_signal.set()
        else:
            self.exit()

    def action_clear_screen(self) -> None:
        self.query_one(ChatView)._messages.clear()
        self.query_one(ChatView).refresh()
```

- [ ] **Step 5: Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/tui/
git commit -m "feat(python): Textual TUI — ChatView, InputWidget, StatusBar, PiApp"
```

---

## Task 14: CLI 入口 + OpenAI Provider + 集成

**Files:**
- Create: `agent-python/src/pi/main.py`
- Create: `agent-python/src/pi/ai/openai.py`

- [ ] **Step 1: 实现 `openai.py`（简化版，与 Anthropic 相同接口）**

```python
# src/pi/ai/openai.py
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import openai as sdk

from .base import LLMProvider, StreamOptions
from .types import (
    AssistantMessage, Message, StreamEvent, TextContent, ToolCall,
    ToolResultMessage, UserMessage,
    StreamStart, TextDelta, ToolCallEnd, StreamDone, Usage,
)
from ..tools.base import Tool


def _convert_messages_openai(messages: list[Message]) -> list[dict]:
    result: list[dict] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            result.append({"role": "user", "content": msg.content
                          if isinstance(msg.content, str)
                          else " ".join(c.text for c in msg.content)})
        elif isinstance(msg, AssistantMessage):
            tool_calls = []
            text_parts = []
            for block in msg.content:
                if isinstance(block, TextContent):
                    text_parts.append(block.text)
                elif isinstance(block, ToolCall):
                    tool_calls.append({
                        "id": block.id,
                        "type": "function",
                        "function": {"name": block.name, "arguments": json.dumps(block.arguments)},
                    })
            entry: dict = {"role": "assistant", "content": " ".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)
        elif isinstance(msg, ToolResultMessage):
            result.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": "\n".join(c.text for c in msg.content),
            })
    return result


class OpenAIProvider(LLMProvider):
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[Tool],
        options: StreamOptions,
    ) -> AsyncGenerator[StreamEvent, None]:
        client = sdk.AsyncOpenAI(api_key=options.api_key)

        oai_tools = [
            {"type": "function", "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }}
            for t in tools
        ]

        oai_messages = [{"role": "system", "content": system_prompt}]
        oai_messages.extend(_convert_messages_openai(messages))

        kwargs: dict[str, Any] = dict(
            model=options.model,
            messages=oai_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        if oai_tools:
            kwargs["tools"] = oai_tools

        partial = AssistantMessage(content=[])
        yield StreamStart(partial=partial)

        tool_args: dict[int, dict] = {}  # index → {id, name, args_buf}
        text_buf = ""

        async for chunk in await client.chat.completions.create(**kwargs):
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            if delta.content:
                text_buf += delta.content
                yield TextDelta(index=0, delta=delta.content, partial=partial)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_args:
                        tool_args[idx] = {"id": tc_delta.id or "", "name": tc_delta.function.name or "", "args_buf": ""}
                    if tc_delta.id:
                        tool_args[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_args[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_args[idx]["args_buf"] += tc_delta.function.arguments

            if choice.finish_reason in ("stop", "tool_calls", "length"):
                stop_reason = "stop" if choice.finish_reason == "stop" else "tool_use"
                # Finalize tool calls
                for tc_info in tool_args.values():
                    try:
                        arguments = json.loads(tc_info["args_buf"]) if tc_info["args_buf"] else {}
                    except json.JSONDecodeError:
                        arguments = {}
                    tc = ToolCall(id=tc_info["id"], name=tc_info["name"], arguments=arguments)
                    partial.content.append(tc)
                    yield ToolCallEnd(index=0, tool_call=tc, partial=partial)

                if text_buf:
                    partial.content.append(TextContent(text=text_buf))

                if chunk.usage:
                    partial.usage = Usage(
                        input=chunk.usage.prompt_tokens,
                        output=chunk.usage.completion_tokens,
                    )
                partial.stop_reason = stop_reason
                yield StreamDone(stop_reason=stop_reason, message=partial)
                break
```

- [ ] **Step 2: 实现 `main.py`**

```python
# src/pi/main.py
from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="pi — terminal coding agent")
    parser.add_argument("--model", default=os.environ.get("PI_MODEL", "claude-sonnet-4-6"),
                        help="Model ID (default: claude-sonnet-4-6)")
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai"],
                        help="LLM provider")
    parser.add_argument("--session", help="Resume session by ID")
    parser.add_argument("--list-sessions", action="store_true", help="List saved sessions")
    args = parser.parse_args()

    if args.provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
            sys.exit(1)
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
            sys.exit(1)

    if args.list_sessions:
        from .session.manager import SessionManager
        mgr = SessionManager()
        for meta in mgr.list_sessions():
            print(f"{meta.id[:8]}  {meta.cwd}  ({meta.message_count} messages)")
        return

    from .tui.app import PiApp
    cwd = os.getcwd()
    app = PiApp(model_id=args.model, api_key=api_key, cwd=cwd)
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行全量测试**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run pytest tests/ -v --tb=short
```

Expected: 全部通过（约 35 个测试）

- [ ] **Step 4: ruff 检查**

```bash
cd /home/ether/Work/pi-agent/agent-python
uv run ruff check src/
```

Expected: 无报错，或只有可忽略的样式提示

- [ ] **Step 5: 验证可启动（无 API key 时应打印错误退出）**

```bash
cd /home/ether/Work/pi-agent/agent-python
ANTHROPIC_API_KEY="" uv run pi --help
```

Expected: 显示 help 文字无崩溃

- [ ] **Step 6: Final Commit**

```bash
cd /home/ether/Work/pi-agent
git add agent-python/src/pi/main.py agent-python/src/pi/ai/openai.py
git commit -m "feat(python): OpenAI provider + CLI entry point — MVP complete"
```

---

## 验收检查

完成所有 Task 后运行：

```bash
cd /home/ether/Work/pi-agent/agent-python

# 1. 所有测试通过
uv run pytest tests/ -v

# 2. 代码质量
uv run ruff check src/

# 3. 基本启动测试
uv run pi --help
uv run pi --list-sessions
```

最终验收（需要真实 API key）：
```bash
ANTHROPIC_API_KEY=sk-ant-... uv run pi
# 在 TUI 中输入: "列出当前目录的文件"
# 预期: LLM 调用 ls 工具，返回文件列表
```
