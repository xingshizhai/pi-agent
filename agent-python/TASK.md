# Python 实现任务书

## 任务概述

用 Python 复刻 [earendil-works/pi](https://github.com/earendil-works/pi) —— 一个极简终端编码代理（Coding Agent）。
用户在终端输入自然语言，LLM 调用 `read/write/edit/bash` 工具完成编码任务，实现与原项目相同的核心体验。

**参考原项目**：https://github.com/earendil-works/pi
**原始项目分析**：见 `../docs/01-original-analysis.md`
**架构设计方案**：见 `../docs/02-architecture.md`（⚠️ 实现前必读，包含精确的工具参数规范）

---

## 技术选型

| 层 | 库 | 版本要求 |
|----|----|---------|
| 包管理 | `uv` | 最新 |
| LLM | `anthropic` | ≥0.40 |
| LLM | `openai` | ≥1.50 |
| TUI | `textual` | ≥1.0 |
| 渲染 | `rich` | ≥13.0 |
| Schema 验证 | `pydantic` | v2 |
| 异步 | 标准库 `asyncio` | — |
| 测试 | `pytest` + `pytest-asyncio` | — |
| 代码质量 | `ruff` | — |

---

## 项目目录结构

```
agent-python/
├── TASK.md                  # 本文件
├── README.md                # 使用说明
├── pyproject.toml           # 项目配置（uv 管理）
├── uv.lock                  # 依赖锁定
├── src/
│   ├── pi/                  # 主包
│   │   ├── __init__.py
│   │   ├── main.py          # 入口：CLI 参数解析，启动 TUI
│   │   ├── ai/              # AI 层：LLM 提供商抽象
│   │   │   ├── __init__.py
│   │   │   ├── types.py     # 消息类型、事件类型定义（Pydantic 模型）
│   │   │   ├── base.py      # Provider 抽象基类
│   │   │   ├── anthropic.py # Anthropic Claude 实现
│   │   │   └── openai.py    # OpenAI 实现
│   │   ├── agent/           # 代理循环层
│   │   │   ├── __init__.py
│   │   │   ├── loop.py      # 核心代理循环（agent_loop 协程）
│   │   │   ├── context.py   # AgentContext 数据类
│   │   │   └── events.py    # AgentEvent 类型定义
│   │   ├── tools/           # 工具系统层
│   │   │   ├── __init__.py
│   │   │   ├── base.py      # Tool 抽象基类
│   │   │   ├── read.py      # read 工具
│   │   │   ├── write.py     # write 工具
│   │   │   ├── edit.py      # edit 工具（精确字符串替换）
│   │   │   └── bash.py      # bash 工具（子进程 + 流式输出）
│   │   ├── session/         # 会话管理层
│   │   │   ├── __init__.py
│   │   │   ├── manager.py   # 会话读写、列表
│   │   │   └── compaction.py# 上下文压缩逻辑
│   │   └── tui/             # TUI 层
│   │       ├── __init__.py
│   │       ├── app.py       # Textual App 主体
│   │       ├── widgets/
│   │       │   ├── chat.py  # 对话消息展示区
│   │       │   ├── input.py # 用户输入框
│   │       │   └── status.py# 底部状态栏
│   │       └── theme.py     # 主题定义
├── tests/
│   ├── test_ai.py
│   ├── test_agent_loop.py
│   ├── test_tools.py
│   └── test_session.py
└── docs/
    └── providers.md         # 各提供商配置说明
```

---

## 详细实现规范

### 1. AI 层（`src/pi/ai/`）

#### `types.py` — 核心数据结构
```python
# 使用 Pydantic v2 定义所有消息类型
class TextContent(BaseModel):
    type: Literal["text"]
    text: str

class ToolCallContent(BaseModel):
    type: Literal["tool_call"]
    id: str
    name: str
    arguments: dict[str, Any]

class ToolResultContent(BaseModel):
    type: Literal["tool_result"]
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False

class Message(BaseModel):
    role: Literal["user", "assistant", "tool_result"]
    content: list[TextContent | ToolCallContent | ToolResultContent]
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
```

#### `base.py` — Provider 抽象基类
```python
class LLMProvider(ABC):
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: list[ToolDefinition],
        options: StreamOptions,
    ) -> AsyncGenerator[AssistantEvent, None]:
        """流式生成，yield AssistantEvent"""
        ...
```

#### `anthropic.py` — Anthropic 实现要点
- 使用 `anthropic.AsyncAnthropic`
- 流式处理：`async with client.messages.stream(...)` 
- 事件映射：`text_delta` → `StreamChunkEvent`，`tool_use` block → `ToolCallEvent`
- 错误处理：网络错误、API 限流（429）自动重试

#### `openai.py` — OpenAI 实现要点
- 使用 `openai.AsyncOpenAI`
- 流式：`await client.chat.completions.create(stream=True)`
- 解析 `delta.tool_calls` 的增量拼接逻辑（OpenAI 工具调用分多个 chunk）

---

### 2. 代理循环层（`src/pi/agent/`）

#### `loop.py` — 核心循环
实现以下状态机：
```
[用户输入] → [调用 LLM 流式] → [解析 assistant 消息]
                                        ↓
                          有工具调用？ ──Yes──→ [执行工具] → [注入 tool_result] → 回到调用 LLM
                                        ↓
                                       No
                                        ↓
                                  [循环结束，等待用户输入]
```

关键接口：
```python
async def agent_loop(
    user_message: str,
    context: AgentContext,
    emit: Callable[[AgentEvent], Awaitable[None]],
    signal: asyncio.Event | None = None,
) -> list[Message]:
    """
    执行一轮代理循环。
    通过 emit 回调发送事件给 TUI 层。
    返回本轮新增的所有消息。
    """
```

约束：
- 最大工具调用轮数：默认 50 轮（防止无限循环）
- 工具执行支持 sequential 和 parallel 两种模式
- 工具执行期间响应 signal（取消信号）

---

### 3. 工具系统层（`src/pi/tools/`）

#### `base.py` — Tool 基类
```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(
        self,
        tool_call_id: str,
        args: dict[str, Any],
        signal: asyncio.Event | None,
        on_update: Callable[[str], None] | None = None,
    ) -> ToolResult:
        ...
```

#### 七个内置工具规范

> ⚠️ 精确参数定义见 `../docs/02-architecture.md` 第五章，以下为实现要点摘要

**`read.py`**
```
参数：path (必填), offset (行号, 1-indexed), limit (行数)
行为：带行号前缀 "1\t内容\n"，默认最多 2000 行或 200KB
超限提示："[Showing lines X-Y of Z. Use offset=N to continue.]"
```

**`write.py`**
```
参数：path, content
行为：pathlib.Path.mkdir(parents=True) + Path.write_text
```

**`edit.py`**
```
⚠️ 参数是 edits 数组，不是 old_string/new_string！
参数：path, edits: list[{oldText: str, newText: str}]
行为：
  - 每个 oldText 匹配原始文件（非增量）
  - 每个 oldText 必须在文件中恰好出现一次
  - 全部验证通过后原子写入
  - 返回 details.diff 字符串
错误：任一 oldText 不存在或出现多次 → is_error=True，说明哪个失败
```

**`bash.py`**
```
参数：command, timeout (秒，无默认值，None 表示无限制)
⚠️ timeout 单位是秒，不是毫秒
行为：
  - asyncio.create_subprocess_shell，合并 stdout+stderr
  - 流式推送：每读到输出块调用 on_update
  - 超时：asyncio.wait_for + proc.kill()
  - 输出截断：超过 200KB 截尾并提示
  - 过滤 ANSI：re.sub(r'\x1b\[[0-9;]*m', '', output)
```

**`find.py`**
```
参数：path (目录), pattern (glob), type ("file"|"dir"|"any")
行为：Path(path).rglob(pattern)，按类型过滤，返回路径列表
```

**`grep.py`**
```
参数：path, pattern (正则), recursive (默认true), ignore_case (默认false)
行为：用 re 模块搜索，返回 "文件:行号:内容" 格式
```

**`ls.py`**
```
参数：path
行为：列出直接子项，返回 [{name, type, size}]
```

---

### 4. 会话管理层（`src/pi/session/`）

会话文件保存路径：`~/.pi/sessions/<session_id>.pi`（NDJSON 格式，与原项目兼容）
完整格式规范见 `../docs/02-architecture.md` 第七章。

```python
class Session(BaseModel):
    id: str
    created_at: int
    updated_at: int
    model_id: str
    messages: list[Message]
    cwd: str
    title: str = ""  # 自动从首条消息提取前 50 字

class SessionManager:
    def save(self, session: Session) -> None: ...
    def load(self, session_id: str) -> Session: ...
    def list(self) -> list[SessionMeta]: ...
    def delete(self, session_id: str) -> None: ...
    def compact(self, session: Session, summary: str) -> Session: ...
```

---

### 5. TUI 层（`src/pi/tui/`）

使用 `textual` 框架，布局：
```
┌─────────────────────────────────┐
│  消息区（滚动，Markdown 渲染）    │ ← ChatView（占满剩余高度）
│  用户消息：白色                  │
│  AI 消息：绿色，Markdown 渲染    │
│  工具调用：黄色折叠块            │
├─────────────────────────────────┤
│  输入框（多行，Ctrl+Enter 发送）  │ ← InputWidget（固定 5 行高）
├─────────────────────────────────┤
│  状态栏：模型名 | token 数 | 耗时 │ ← StatusBar（1 行）
└─────────────────────────────────┘
```

键盘快捷键：
- `Ctrl+Enter` 或 `Ctrl+J`：发送消息
- `Ctrl+C`：取消当前 LLM 调用
- `Ctrl+L`：清屏（不清除历史）
- `↑/↓`：输入框历史记录导航
- `/exit` 或 `/quit`：退出

---

## 实现顺序（推荐）

```
第 1 步：搭建项目骨架（pyproject.toml、目录、空模块）         ≈ 0.5天
第 2 步：AI 层 — Anthropic 提供商 + 类型定义                  ≈ 1天
第 3 步：工具系统 — 四个内置工具                               ≈ 1天
第 4 步：代理循环 — 核心状态机                                 ≈ 1.5天
第 5 步：会话管理                                              ≈ 0.5天
第 6 步：TUI — Textual App，最小可用界面                       ≈ 1.5天
第 7 步：集成联调，完成 MVP                                    ≈ 1天
第 8 步：补充 OpenAI 提供商                                    ≈ 0.5天
第 9 步：测试 + 文档                                           ≈ 1天
```

总计：约 **8~9 天**

---

## 验收标准

- [ ] `uv run pi` 可启动 TUI
- [ ] 支持 Anthropic Claude 3.5/3.7 Sonnet 流式对话
- [ ] LLM 可成功调用 read/write/edit/bash 工具完成一个真实编码任务
- [ ] 会话自动保存，重启后可恢复
- [ ] Ctrl+C 可取消正在进行的 LLM 调用
- [ ] 所有工具有单元测试覆盖
- [ ] `ruff check` 无警告

---

## 环境变量

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PI_SESSION_DIR=~/.pi/sessions   # 可选，默认值
PI_MAX_TURNS=50                  # 可选，最大工具调用轮数
```

---

## 注意事项

1. **流式工具调用拼接**：Anthropic API 的工具调用参数通过多个 `input_json_delta` 事件拼接，必须正确累积后再解析 JSON。
2. **并发安全**：TUI 渲染（主线程）与代理循环（asyncio）共享状态，必须通过 asyncio Queue 传递事件，禁止直接修改 UI 组件。
3. **bash 工具安全**：不做权限限制（与原项目一致），但需要过滤掉会破坏终端的控制字符。
4. **edit 工具唯一性**：old_string 非唯一时必须报错，这是原项目的核心设计，防止错误替换。
