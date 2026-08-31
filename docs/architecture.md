# Pi Agent — 多语言复刻架构设计

> 基于 [pi-architecture-analysis.md](./pi-architecture-analysis.md) 对原始 Pi 项目的分析  
> 本文档定义 Python / Go / Rust 三种实现必须遵守的统一架构规范

---

## 项目背景

本仓库是对 [earendil-works/pi](https://github.com/earendil-works/pi) 的多语言复刻。Pi 是一个终端编码 Agent 框架：用户通过自然语言驱动 LLM，LLM 调用工具（read / write / edit / bash / find / grep / ls）完成编码任务。

三种语言实现共享相同的语义与行为，差异仅体现在各语言的惯用表达方式（异步模型、TUI 框架等）。

---

## 仓库结构

```
pi-agent/
├── docs/
│   ├── pi-architecture-analysis.md  # 原始 Pi 项目架构与分析
│   ├── architecture.md            # 本文：多语言复刻架构设计
│   └── superpowers/plans/         # 各语言实现计划
├── agent-python/                  # Python 实现（Textual TUI）
├── agent-go/                      # Go 实现（bubbletea TUI）
├── agent-rust/                    # Rust 实现（ratatui TUI）
└── tests/                         # 跨语言测试套件（Layer 1/2/3）
```

---

## 一、设计原则

1. **忠于原始语义**：工具参数、会话格式、代理循环行为与原项目保持一致
2. **语言惯用风格**：不强行把 TypeScript 模式直译，而是用各语言最自然的方式表达
3. **层间单向依赖**：`ai` ← `agent` ← `tools/session` ← `tui/cli`，禁止逆向依赖
4. **接口优先**：先定义接口/trait/protocol，再实现，方便测试 Mock

---

## 二、统一分层架构

```
┌─────────────────────────────────────────────────────┐
│                    CLI 入口层                         │
│   解析参数 · 初始化配置 · 启动 TUI 或非交互模式          │
├─────────────────────────────────────────────────────┤
│                    TUI 展示层                         │
│   流式渲染 · 用户输入 · 事件订阅 · 会话切换 UI          │
├──────────────┬──────────────────────────────────────┤
│  会话管理层   │           工具系统层                    │
│  持久化·分支  │  read·write·edit·bash·find·grep·ls   │
├──────────────┴──────────────────────────────────────┤
│                   代理循环层                           │
│   状态机 · 工具调度 · 事件流 · 生命周期钩子              │
├─────────────────────────────────────────────────────┤
│                    AI 抽象层                           │
│   Provider 接口 · SSE 解析 · 消息类型 · 流式事件协议    │
└─────────────────────────────────────────────────────┘
```

---

## 三、核心数据类型规范

以下是**跨语言统一定义**，各语言按惯用语法实现相同语义。

### 3.1 消息类型

```
# 内容块
TextContent       = { type: "text",       text: string }
ImageContent      = { type: "image",      data: base64_string, mime_type: string }
ThinkingContent   = { type: "thinking",   thinking: string, thinking_signature?: string }
ToolCall          = { type: "tool_call",  id: string, name: string, arguments: map }

# 消息
UserMessage       = { role: "user",        content: string | ContentBlock[], timestamp: i64 }
AssistantMessage  = { role: "assistant",   content: ContentBlock[],
                      api: string, provider: string, model: string,
                      usage: Usage, stop_reason: StopReason,
                      error_message?: string, timestamp: i64 }
ToolResultMessage = { role: "tool_result", tool_call_id: string, tool_name: string,
                      content: ContentBlock[], details: any,
                      is_error: bool, timestamp: i64 }

# 用量统计
Usage = { input: i64, output: i64, cache_read: i64, cache_write: i64 }

# 停止原因
StopReason = "stop" | "length" | "tool_use" | "error" | "aborted"
```

### 3.2 LLM 流式事件协议

```
StreamEvent =
  | StreamStart       { partial: AssistantMessage }
  | TextStart         { index: u32, partial: AssistantMessage }
  | TextDelta         { index: u32, delta: string, partial: AssistantMessage }
  | TextEnd           { index: u32, content: string, partial: AssistantMessage }
  | ThinkingStart     { index: u32, partial: AssistantMessage }
  | ThinkingDelta     { index: u32, delta: string, partial: AssistantMessage }
  | ThinkingEnd       { index: u32, content: string, partial: AssistantMessage }
  | ToolCallStart     { index: u32, partial: AssistantMessage }
  | ToolCallDelta     { index: u32, delta: string, partial: AssistantMessage }
  | ToolCallEnd       { index: u32, tool_call: ToolCall, partial: AssistantMessage }
  | Done              { stop_reason: StopReason, message: AssistantMessage }
  | StreamError       { stop_reason: StopReason, error: AssistantMessage }
```

### 3.3 工具接口规范

```
ToolDefinition = {
    name:         string
    description:  string
    parameters:   JsonSchema          # JSON Schema object
    label:        string              # UI 显示标签
    execution_mode?: "sequential" | "parallel"  # 单工具覆盖
}

ToolResult<TDetails> = {
    content:    ContentBlock[]        # 返回给 LLM 的内容
    details:    TDetails              # 结构化数据供 UI 渲染
    is_error:   bool
    terminate?: bool                  # 提示循环终止
}

Tool<TParams, TDetails>:
    name() → string
    definition() → ToolDefinition
    execute(id, args: TParams, signal, on_update?) → ToolResult<TDetails>
```

### 3.4 代理上下文与事件

```
AgentContext = {
    system_prompt:  string
    messages:       Message[]
    tools:          Tool[]
}

AgentConfig = {
    model_id:         string
    api_key:          string
    tool_execution:   "sequential" | "parallel"   # 默认 parallel
    max_turns:        u32                          # 默认 50
    before_tool_call? (ctx, call) → BlockResult   # 可选拦截
    after_tool_call?  (ctx, call, result) → ToolResult  # 可选修改
}

AgentEvent =
  | AgentStart
  | AgentEnd         { messages: Message[] }
  | TurnStart
  | TurnEnd          { message: AssistantMessage, tool_results: ToolResultMessage[] }
  | MessageStart     { message: Message }
  | MessageUpdate    { message: AssistantMessage, event: StreamEvent }
  | MessageEnd       { message: Message }
  | ToolExecStart    { id: string, name: string, args: map }
  | ToolExecUpdate   { id: string, partial: ToolResult }
  | ToolExecEnd      { id: string, name: string, result: ToolResult, is_error: bool }
  | Error            { message: string }
```

### 3.5 会话文件格式（NDJSON，与原项目完全兼容）

```jsonl
{"type":"session","version":3,"id":"<uuid>","timestamp":"<ISO8601>","cwd":"<path>"}
{"type":"message","id":"<uuid>","parentId":"<prev-uuid>|null","timestamp":"<ISO8601>","message":{...Message}}
{"type":"model_change","id":"<uuid>","parentId":"<uuid>","timestamp":"...","provider":"anthropic","modelId":"claude-sonnet-4-6"}
{"type":"thinking_level_change","id":"<uuid>","parentId":"<uuid>","timestamp":"...","thinkingLevel":"medium"}
{"type":"compaction","id":"<uuid>","parentId":"<uuid>","timestamp":"...","summary":"...","firstKeptEntryId":"<uuid>","tokensBefore":12345}
{"type":"branch_summary","id":"<uuid>","parentId":"<uuid>","timestamp":"...","fromId":"<uuid>","summary":"..."}
```

**约束**：

- 第一行必须是 `type=session` 的 SessionHeader
- 每行一个 JSON 对象（NDJSON 格式）
- 只追加，不修改已有行
- `parentId` 为 null 时表示链的起点
- 文件扩展名：`.pi`（路径：`~/.pi/sessions/<id>.pi`）

> 注意：会话格式为 NDJSON 追加写入，**不是**单个 JSON 文件。旧版草案中的 `{ "id", "messages": [...] }` 格式已废弃。

---

## 四、代理循环状态机规范

```
函数签名：
    run_agent_loop(
        user_message: string,
        ctx: AgentContext,
        config: AgentConfig,
        event_sink: fn(AgentEvent),
        cancel: CancelToken
    ) → Result<Vec<Message>>

状态机：
    1. 将 user_message 包装为 UserMessage，追加到 ctx.messages
    2. emit AgentStart
    3. 进入主循环（最多 config.max_turns 轮）：
       a. emit TurnStart
       b. 调用 LLM Provider.stream(ctx)
       c. 消费流：
          - StreamEvent::TextDelta  → emit MessageUpdate
          - StreamEvent::ToolCallEnd → 收集 tool_calls
          - StreamEvent::Done/Error  → 结束流，得到 AssistantMessage
       d. emit MessageEnd(assistant_msg)
       e. 将 assistant_msg 追加到 ctx.messages
       f. 如果没有 tool_calls → emit TurnEnd, emit AgentEnd, 返回
       g. 执行所有工具（sequential 或 parallel）：
          - emit ToolExecStart(call)
          - [可选] before_tool_call(call) → 若 block → 生成错误 ToolResult
          - tool.execute(id, args, cancel, on_update)
              on_update → emit ToolExecUpdate
          - [可选] after_tool_call(call, result) → 修改 result
          - emit ToolExecEnd(call, result)
          - 包装为 ToolResultMessage
       h. 将所有 ToolResultMessage 追加到 ctx.messages
       i. emit TurnEnd(assistant_msg, tool_results)
       j. 继续循环（goto 步骤 a）
    4. 超过 max_turns → 生成错误消息，emit AgentEnd

取消行为：
    - CancelToken 在任意步骤均可触发
    - LLM 流：中止 HTTP 请求，收到部分 AssistantMessage（stopReason: "aborted"）
    - 工具执行：传递给 tool.execute，工具负责响应
    - 发出 AgentEnd 后退出
```

---

## 五、工具系统规范

### 5.1 工具参数 Schema（精确定义）

```jsonschema
# read 工具
{
  "name": "read",
  "description": "Read the contents of a file...",
  "parameters": {
    "type": "object",
    "properties": {
      "path":   { "type": "string", "description": "Path to file (relative or absolute)" },
      "offset": { "type": "number", "description": "Line number to start reading from (1-indexed)" },
      "limit":  { "type": "number", "description": "Maximum number of lines to read" }
    },
    "required": ["path"]
  }
}

# write 工具
{
  "name": "write",
  "parameters": {
    "type": "object",
    "properties": {
      "path":    { "type": "string" },
      "content": { "type": "string" }
    },
    "required": ["path", "content"]
  }
}

# edit 工具（注意：批量 edits 数组，非 old_string/new_string）
{
  "name": "edit",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string" },
      "edits": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "oldText": { "type": "string", "description": "Exact text, must be unique in file" },
            "newText": { "type": "string" }
          },
          "required": ["oldText", "newText"]
        }
      }
    },
    "required": ["path", "edits"]
  }
}

# bash 工具（timeout 单位：秒，无默认值）
{
  "name": "bash",
  "parameters": {
    "type": "object",
    "properties": {
      "command": { "type": "string" },
      "timeout": { "type": "number", "description": "Timeout in seconds (optional)" }
    },
    "required": ["command"]
  }
}

# find 工具
{
  "name": "find",
  "parameters": {
    "type": "object",
    "properties": {
      "path":    { "type": "string", "description": "Directory to search in" },
      "pattern": { "type": "string", "description": "Filename glob pattern" },
      "type":    { "type": "string", "enum": ["file", "dir", "any"], "description": "Entry type filter" }
    },
    "required": ["path", "pattern"]
  }
}

# grep 工具
{
  "name": "grep",
  "parameters": {
    "type": "object",
    "properties": {
      "path":        { "type": "string" },
      "pattern":     { "type": "string", "description": "Regex pattern" },
      "recursive":   { "type": "boolean", "default": true },
      "ignore_case": { "type": "boolean", "default": false }
    },
    "required": ["path", "pattern"]
  }
}

# ls 工具
{
  "name": "ls",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string" }
    },
    "required": ["path"]
  }
}
```

### 5.2 工具行为规范

**read**

- `offset` 为 1-indexed 行号（第1行 = offset:1），不是字节偏移
- 默认最多读取 2000 行或 200KB（先到者为准）
- 超限时追加提示：`[Showing lines X-Y of Z. Use offset=N to continue.]`
- 成功返回带行号前缀的内容：`1\t内容\n2\t内容\n...`

**write**

- 自动创建父目录（`mkdir -p` 语义）
- 覆盖写入，无确认提示

**edit**

- 所有 `oldText` 匹配的是**原始文件**内容（非增量）
- 每个 `oldText` 在原文件中必须**恰好出现一次**
- 若任一 `oldText` 不存在或出现多次 → is_error=true，详细说明哪个匹配失败
- 所有匹配成功后一次性写入（原子操作）
- 返回 details 包含 diff 字符串

**bash**

- `timeout` 单位是秒（非毫秒）
- 无 `timeout` 参数时无超时限制
- 超时后强制终止整个进程树
- 输出合并 stdout+stderr，按时序顺序
- 输出截断：超过 200KB 时截取尾部，追加提示
- 过滤 ANSI 转义码

**find**

- 递归搜索 `path` 目录下匹配 `pattern` 的文件/目录
- 返回相对于 `path` 的路径列表

**grep**

- 在 `path`（文件或目录）中搜索 `pattern`（正则）
- 返回格式：`文件路径:行号:匹配行内容`

**ls**

- 列出 `path` 目录的直接子项（非递归）
- 返回每项的名称、类型（file/dir）、大小

---

## 六、AI 层实现规范

### 6.1 Anthropic Messages API（SSE 格式）

**请求格式**：

```
POST https://api.anthropic.com/v1/messages
Headers:
    x-api-key: <API_KEY>
    anthropic-version: 2023-06-01
    content-type: application/json
    accept: text/event-stream
Body:
{
    "model": "claude-sonnet-4-6",
    "max_tokens": 8192,
    "system": "<system_prompt>",
    "messages": [...],  // 转换后的 Message[]
    "tools": [...],     // 工具列表
    "stream": true
}
```

**SSE 事件 → StreamEvent 映射**：

```
content_block_start  (type=text)      → TextStart
content_block_delta  (type=text_delta)→ TextDelta（累积 text）
content_block_stop   (after text)     → TextEnd
content_block_start  (type=tool_use)  → ToolCallStart（记录 id, name）
content_block_delta  (type=input_json_delta) → ToolCallDelta（累积 partial_json 字符串）
content_block_stop   (after tool_use) → ToolCallEnd（解析累积的 JSON → arguments）
message_stop                          → Done
message_delta (stop_reason=error)     → StreamError

# 跨事件状态（必须维护）：
current_tool_index: int
current_tool_id:    string
current_tool_name:  string
tool_args_buffer:   string  ← input_json_delta 逐个追加
```

**工具格式（发送给 Anthropic）**：

```json
{
  "name": "read",
  "description": "...",
  "input_schema": { "type": "object", "properties": {...}, "required": [...] }
}
```

**消息格式转换（发送给 Anthropic）**：

```
UserMessage     → { "role": "user",      "content": string | [{type,text},...] }
AssistantMessage→ { "role": "assistant", "content": [{type:"text",text},{type:"tool_use",id,name,input},...] }
ToolResultMessage→ 合并到下一条 UserMessage 中作为 tool_result 块
              → { "role": "user", "content": [{"type":"tool_result","tool_use_id":id,"content":[{type,text}],"is_error":bool}] }
```

### 6.2 OpenAI Chat Completions API（SSE 格式）

**请求格式**：

```
POST https://api.openai.com/v1/chat/completions
Headers:
    Authorization: Bearer <API_KEY>
    content-type: application/json
Body:
{
    "model": "gpt-4o",
    "messages": [...],
    "tools": [...],
    "stream": true,
    "stream_options": { "include_usage": true }
}
```

**SSE 事件解析**：

```
# OpenAI 工具调用参数通过多个 chunk 增量拼接
delta.tool_calls[i].function.arguments → 字符串片段，需累积
delta.tool_calls[i].index              → 工具调用索引
delta.tool_calls[i].id                 → 仅在第一个 chunk 出现
finish_reason = "tool_calls"           → Done(ToolUse)
finish_reason = "stop"                 → Done(Stop)

# 工具格式（发送给 OpenAI）
{
  "type": "function",
  "function": {
    "name": "read",
    "description": "...",
    "parameters": { "type": "object", ... }
  }
}
```

### 6.3 消息发送前的转换规则

```
# 规则1：连续的 ToolResultMessage 必须合并为一条 user 消息（Anthropic 要求）
# 规则2：messages 必须以 user 消息结尾（LLM 约定）
# 规则3：ThinkingContent 的 thinkingSignature 必须在多轮对话中保持传递

转换顺序：
    AgentMessage[] → filter(非 LLM 消息) → 合并 ToolResult → Message[]
```

---

## 七、会话管理规范

### 7.1 会话操作接口

```
SessionManager:
    new_session(cwd: string) → Session
    save_header(session: Session) → void    # 写第一行
    append_entry(session_id, entry: Entry) → void  # 追加一行
    load_session(id: string) → Session      # 读取并重建
    list_sessions() → Vec<SessionMeta>      # 列出所有会话
    delete_session(id: string) → void

Session:
    id:          string (UUID v7，按时间排序)
    cwd:         string
    created_at:  timestamp
    messages:    Message[]   # 当前有效的消息链（已应用 compaction）
    entries:     Entry[]     # 原始条目链
    model_id:    string
    thinking_level: string
```

### 7.2 compaction 逻辑

```
触发条件（P1 实现）：
    估算 token 数 > model.context_window * 0.8

操作：
    1. 收集 compaction 节点之前的所有消息
    2. 调用 LLM 生成摘要（约 500 token）
    3. 写入 CompactionEntry { summary, firstKeptEntryId, tokensBefore }
    4. 将摘要注入为系统消息（下次加载时恢复）

MVP 阶段：手动触发（/compact 命令），不自动触发
```

### 7.3 会话文件路径约定

```
~/.pi/
├── sessions/
│   ├── <id>.pi         # 会话文件（NDJSON）
│   └── ...
├── settings.json        # 全局配置
└── agent/
    └── models.json      # 自定义模型（P2）
```

---

## 八、TUI 层规范

### 8.1 布局

```
┌──────────────────────────────────────────────────┐
│                                                  │
│   消息区（可滚动，流式渲染）                         │
│                                                  │
│   user: 你好                                      │
│   assistant: 你好！有什么可以帮你？ ▊               │
│                                                  │
│   [read] src/main.py                             │ ← 工具调用行
│   ┌────────────────────────────────┐             │
│   │ 1  import os                  │             │ ← 工具结果（折叠/展开）
│   │ 2  import sys                 │             │
│   └────────────────────────────────┘             │
│                                                  │
├──────────────────────────────────────────────────┤
│  > 输入框（支持换行，Ctrl+Enter 发送）               │ ← 固定 3~5 行高
├──────────────────────────────────────────────────┤
│  claude-sonnet-4-6 | 1234 tokens | 2.3s          │ ← 状态栏（1行）
└──────────────────────────────────────────────────┘
```

### 8.2 交互规范

| 快捷键 | 行为 |
|--------|------|
| `Ctrl+Enter` / `Alt+Enter` | 发送消息 |
| `Ctrl+C` | 取消当前 LLM 调用（不退出程序） |
| `Ctrl+C`（空输入时） | 退出程序 |
| `↑` / `↓`（空输入时） | 切换输入历史 |
| `PageUp` / `PageDown` | 滚动消息区 |
| `Ctrl+L` | 清屏（不清除历史） |

**slash 命令（P1）**：

```
/exit, /quit     → 退出
/clear           → 清空消息区（不清历史）
/model           → 切换模型
/session         → 列出/切换会话
/compact         → 手动压缩上下文
```

### 8.3 渲染规范

- **流式 token**：`MessageUpdate` 事件触发局部更新，不重绘全屏
- **Markdown**：代码块带语言标签时显示语法高亮（ANSI 颜色）
- **工具调用**：显示 `[工具名] 参数摘要`，结果默认折叠，可展开
- **错误**：红色 `[error]` 前缀，显示错误内容

---

## 九、配置规范

### 配置文件（`~/.pi/settings.json`）

```json
{
  "default_model": "claude-sonnet-4-6",
  "default_provider": "anthropic",
  "thinking_level": "medium",
  "tool_execution": "parallel",
  "max_turns": 50,
  "session_dir": "~/.pi/sessions",
  "theme": "default"
}
```

### 环境变量优先级（高于配置文件）

```
ANTHROPIC_API_KEY     → Anthropic 提供商
OPENAI_API_KEY        → OpenAI 提供商
PI_SESSION_DIR        → 会话目录
PI_MAX_TURNS          → 最大轮数
PI_MODEL              → 默认模型
```

---

## 十、功能范围

复刻范围以 [pi-architecture-analysis.md 第十二节](./pi-architecture-analysis.md#十二本仓库复刻范围) 为准。三种语言实现须保持一致：

| 阶段 | 内容 |
|------|------|
| **P0（MVP）** | Anthropic + OpenAI 流式 API；完整 Agent 循环；7 个内置工具；NDJSON 会话；TUI 流式渲染 |
| **P1** | 会话分支、自动 compaction、上下文裁剪钩子、更多 Provider、消息队列 |
| **不复刻** | 扩展系统、图片 I/O、RPC 模式、OAuth、sixel/kitty 渲染 |

---

## 十一、各语言实现差异

| 方面 | Python | Go | Rust |
|------|--------|----|------|
| 异步模型 | `asyncio` + `async/await` | goroutine + channel | `tokio` + `async/await` |
| 事件推送 | `asyncio.Queue` | `chan AgentEvent` | `mpsc::channel` |
| 取消信号 | `asyncio.Event` | `context.Context` | `CancellationToken` |
| LLM SDK | 官方 `anthropic` 库 | 手动 HTTP + SSE | `reqwest` 手动实现 |
| 工具 Schema | `pydantic` JSON Schema | `jsonschema` crate | `schemars` crate |
| TUI | `textual` | `bubbletea` | `ratatui` + `crossterm` |
| 会话序列化 | `json` 标准库 | `encoding/json` | `serde_json` |
| 并行工具执行 | `asyncio.gather` | `errgroup` / goroutines | `tokio::join!` / `JoinSet` |

---

## 十二、测试策略

### 单元测试（每种语言必须）

| 模块 | 测试内容 |
|------|---------|
| AI 层 | SSE 流解析（含边界条件），消息格式转换 |
| 代理循环 | 状态机正确性（Mock Provider），工具调度顺序 |
| 工具：read | 行号前缀，offset/limit，截断提示 |
| 工具：edit | 唯一性检查，多 edit 批量，失败回滚 |
| 工具：bash | 超时处理，输出截断，取消信号 |
| 会话管理 | NDJSON 写入/读取，compaction 重建 |

### 集成测试

跨语言测试套件位于 `tests/`，按 Layer 1（工具）/ Layer 2（行为，Mock LLM）/ Layer 3（任务，真实 LLM）分层运行。详见根目录 [README.md](../README.md#测试)。

---

## 十三、文档索引

| 文档 | 说明 |
|------|------|
| [pi-architecture-analysis.md](./pi-architecture-analysis.md) | 原始 Pi 项目架构与分析 |
| [architecture.md](./architecture.md) | 本文：多语言复刻架构设计 |
| [agent-python/TASK.md](../agent-python/TASK.md) | Python 实现任务书 |
| [agent-go/TASK.md](../agent-go/TASK.md) | Go 实现任务书 |
| [agent-rust/TASK.md](../agent-rust/TASK.md) | Rust 实现任务书 |
