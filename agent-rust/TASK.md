# Rust 实现任务书

## 任务概述

用 Rust 复刻 [earendil-works/pi](https://github.com/earendil-works/pi) —— 一个极简终端编码代理（Coding Agent）。
目标：最高运行时性能，内存安全，单一静态二进制，`tokio` 驱动的异步架构。

**参考原项目**：https://github.com/earendil-works/pi
**原始项目分析**：见 `../docs/pi-architecture-analysis.md`
**架构设计方案**：见 `../docs/architecture.md`（⚠️ 实现前必读，包含精确的工具参数规范）

---

## 技术选型

| 层 | crate | 说明 |
|----|-------|------|
| 异步运行时 | `tokio` (full features) | 异步 I/O、任务调度 |
| HTTP 客户端 | `reqwest` (stream feature) | SSE 流式请求 |
| TUI 框架 | `ratatui` | 终端 UI，差分渲染 |
| TUI 事件 | `crossterm` | 键盘/鼠标/窗口事件 |
| JSON | `serde` + `serde_json` | 序列化/反序列化 |
| Schema 验证 | `schemars` | JSON Schema 生成 |
| Markdown | `termimad` | 终端 Markdown 渲染 |
| UUID | `uuid` (v4) | 会话 ID |
| 错误处理 | `anyhow` | 统一 Error 类型 |
| 日志 | `tracing` + `tracing-subscriber` | 结构化日志 |
| 测试 | 标准库 `#[tokio::test]` | — |

**Rust 版本要求**：stable ≥ 1.80（2024 edition）

---

## 项目目录结构

```
agent-rust/
├── TASK.md                       # 本文件
├── README.md                     # 使用说明
├── Cargo.toml                    # workspace 根
├── Cargo.lock
├── src/
│   ├── main.rs                   # 入口：解析 CLI 参数，启动 TUI
│   ├── ai/                       # AI 层
│   │   ├── mod.rs
│   │   ├── types.rs              # 消息、事件类型（serde 派生）
│   │   ├── provider.rs           # Provider trait 定义
│   │   ├── sse.rs                # SSE 流解析
│   │   ├── anthropic.rs          # Anthropic Claude 实现
│   │   └── openai.rs             # OpenAI 实现
│   ├── agent/                    # 代理循环层
│   │   ├── mod.rs
│   │   ├── types.rs              # AgentContext、AgentEvent 类型
│   │   ├── loop.rs               # 核心代理循环
│   │   └── executor.rs           # 工具执行（sequential/parallel）
│   ├── tools/                    # 工具系统层
│   │   ├── mod.rs                # Tool trait 定义
│   │   ├── read.rs
│   │   ├── write.rs
│   │   ├── edit.rs
│   │   └── bash.rs
│   ├── session/                  # 会话管理层
│   │   ├── mod.rs
│   │   ├── types.rs
│   │   └── manager.rs
│   ├── tui/                      # TUI 层
│   │   ├── mod.rs
│   │   ├── app.rs                # 顶层 App 状态机
│   │   ├── state.rs              # AppState 结构体
│   │   ├── render.rs             # ratatui 渲染函数
│   │   ├── events.rs             # 键盘/代理事件处理
│   │   └── widgets/
│   │       ├── chat.rs           # 对话消息组件
│   │       ├── input.rs          # 输入框组件
│   │       └── status.rs         # 状态栏组件
│   └── utils/
│       ├── ansi.rs               # ANSI 转义码过滤
│       └── truncate.rs           # 输出截断工具
├── tests/
│   ├── ai_test.rs
│   ├── agent_loop_test.rs
│   └── tools_test.rs
└── docs/
    └── providers.md
```

---

## 详细实现规范

### 1. AI 层（`src/ai/`）

#### `types.rs` — 核心类型
```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Role { User, Assistant, ToolResult }

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MessageContent {
    Text { text: String },
    ToolCall { id: String, name: String, arguments: serde_json::Value },
    ToolResult {
        tool_call_id: String,
        tool_name: String,
        content: String,
        is_error: bool,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: Role,
    pub content: Vec<MessageContent>,
    pub timestamp: i64,
}

// 流式事件 — 通过 tokio::sync::mpsc 传递
#[derive(Debug)]
pub enum StreamEvent {
    TextDelta(String),
    ToolCall { id: String, name: String, arguments: serde_json::Value },
    Done { stop_reason: String },
    Error(anyhow::Error),
}
```

#### `provider.rs` — Provider trait
```rust
use async_trait::async_trait;
use tokio::sync::mpsc;

#[derive(Debug, Clone)]
pub struct StreamOptions {
    pub api_key: String,
    pub temperature: Option<f32>,
    pub max_tokens: Option<u32>,
}

#[async_trait]
pub trait Provider: Send + Sync {
    async fn stream(
        &self,
        messages: &[Message],
        system_prompt: &str,
        tools: &[ToolDefinition],
        opts: StreamOptions,
    ) -> anyhow::Result<mpsc::Receiver<StreamEvent>>;
}
```

> **注意**：`async_trait` crate 是必需的，因为 Rust 原生 async trait 在 1.80 仍需它处理 object safety。

#### `sse.rs` — SSE 解析
```rust
use futures_util::StreamExt;
use reqwest::Response;

pub struct SseStream {
    inner: reqwest::Response,
}

impl SseStream {
    // 从 reqwest::Response 构造
    pub fn new(resp: Response) -> Self { ... }

    // 迭代产出 data 行内容（跳过注释行和空行，检测 [DONE]）
    pub async fn next_data(&mut self) -> Option<anyhow::Result<String>> { ... }
}
```

#### `anthropic.rs` — Anthropic 实现要点
- 请求体结构：
  ```json
  {
    "model": "claude-sonnet-4-6",
    "messages": [...],
    "system": "...",
    "tools": [...],
    "stream": true,
    "max_tokens": 8192
  }
  ```
- SSE 事件处理（关键逻辑）：
  ```rust
  // 需要维护跨事件状态
  struct AnthropicStreamState {
      current_tool_id:   Option<String>,
      current_tool_name: Option<String>,
      current_tool_args: String,  // 累积 input_json_delta
  }
  ```
- 事件类型映射：
  - `content_block_start` + `type=tool_use` → 记录工具 id/name
  - `content_block_delta` + `type=text_delta` → `StreamEvent::TextDelta`
  - `content_block_delta` + `type=input_json_delta` → 追加到 `current_tool_args`
  - `content_block_stop` + 有工具状态 → 解析 JSON → `StreamEvent::ToolCall`
  - `message_stop` → `StreamEvent::Done`

---

### 2. 代理循环层（`src/agent/`）

#### `types.rs`
```rust
#[derive(Debug, Clone)]
pub struct AgentContext {
    pub messages: Vec<Message>,
    pub system_prompt: String,
    pub tools: Vec<Arc<dyn Tool>>,
    pub model_id: String,
}

#[derive(Debug, Clone)]
pub enum AgentEvent {
    AgentStart,
    AgentEnd,
    TurnStart,
    TurnEnd,
    StreamChunk(String),
    ToolExecutionStart { id: String, name: String, args: serde_json::Value },
    ToolExecutionUpdate { id: String, partial: String },
    ToolExecutionEnd { id: String, result: ToolResult },
    Error(String),
}
```

#### `loop.rs` — 核心循环
```rust
pub async fn run(
    user_msg: String,
    ctx: &mut AgentContext,
    provider: Arc<dyn Provider>,
    event_tx: mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,         // tokio_util::sync::CancellationToken
    max_turns: usize,
) -> anyhow::Result<()>
```

状态机：
```
loop (最多 max_turns 次) {
    1. select! { provider.stream(), cancel.cancelled() }
    2. 消费 StreamEvent:
       - TextDelta  → event_tx.send(StreamChunk)
       - ToolCall   → 收集
       - Done       → break 内层循环
    3. 追加 assistant 消息
    4. 若 tool_calls 为空 → break 外层循环（循环结束）
    5. tokio::task::JoinSet 执行工具（并行模式）
    6. 追加 tool_result 消息
}
```

#### `executor.rs` — 并行工具执行
```rust
// 使用 tokio::task::JoinSet 并发执行所有工具调用
pub async fn execute_parallel(
    calls: Vec<ToolCall>,
    tools: &HashMap<String, Arc<dyn Tool>>,
    event_tx: mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,
) -> Vec<(String, ToolResult)>  // (tool_call_id, result)
```

---

### 3. 工具系统层（`src/tools/`）

#### `mod.rs` — Tool trait
```rust
use async_trait::async_trait;
use schemars::JsonSchema;

#[derive(Debug, Clone)]
pub struct ToolResult {
    pub content: String,
    pub is_error: bool,
    pub terminate: bool,
}

pub type UpdateFn = Box<dyn Fn(String) + Send + Sync>;

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn schema(&self) -> serde_json::Value;  // JSON Schema

    async fn execute(
        &self,
        id: &str,
        args: serde_json::Value,
        cancel: CancellationToken,
        on_update: Option<&UpdateFn>,
    ) -> anyhow::Result<ToolResult>;
}
```

#### 七个内置工具规范

> ⚠️ 精确参数定义见 `../docs/architecture.md` 第五章

**`read.rs`**
```
参数：path: String (必填), offset: Option<usize> (1-indexed), limit: Option<usize>
行为：tokio::fs::read_to_string，按行分割，带行号前缀 "N\t内容\n"
超限提示："[Showing lines X-Y of Z. Use offset=N to continue.]"
默认上限：2000 行或 200KB
```

**`write.rs`**
```
参数：path: String, content: String
行为：tokio::fs::create_dir_all(parent) + tokio::fs::write
```

**`edit.rs`**
```
⚠️ 参数是 edits 数组，不是 old_string/new_string！
参数：
  path: String
  edits: Vec<EditItem>  →  struct EditItem { old_text: String, new_text: String }

行为：
  读取原始文件内容
  for each edit:
    count = content.matches(&edit.old_text).count()
    count == 0 → return ToolResult { is_error: true, "未找到: old_text=..." }
    count > 1  → return ToolResult { is_error: true, "出现 N 次: old_text=..." }
  全部验证通过 → 顺序应用所有替换（content.replacen 各一次）→ 写回文件
  返回 details.diff 字符串
```

**`bash.rs`**
```
参数：command: String, timeout: Option<f64>  (秒，无默认值)
⚠️ timeout 单位是秒，不是毫秒，None 表示不限时

实现：
  tokio::process::Command::new("bash").arg("-c")
  stdout(Stdio::piped()) + stderr(Stdio::piped())
  tokio::io::BufReader::new(stdout).lines() 流式读取
  on_update 推送每行
  超时：tokio::time::timeout(Duration::from_secs_f64(t))
  取消：select! { cmd.wait(), cancel.cancelled() } → cmd.kill()
  输出截断：200KB，截尾并提示
  ANSI 过滤：utils::ansi::strip
```

**`find.rs`**
```
参数：path: String, pattern: String, r#type: Option<String> ("file"|"dir"|"any")
行为：walkdir::WalkDir + glob::Pattern::matches，返回路径列表
```

**`grep.rs`**
```
参数：path: String, pattern: String, recursive: bool, ignore_case: bool
行为：regex::Regex + walkdir，返回 "文件:行号:内容"
```

**`ls.rs`**
```
参数：path: String
行为：tokio::fs::read_dir，返回 Vec<{name, entry_type, size}>
```

---

### 4. 会话管理层（`src/session/`）

> 会话文件格式：NDJSON 追加写入，扩展名 `.pi`，完整规范见 `../docs/architecture.md` 第七章。

```rust
// 会话头（第一行）
#[derive(Debug, Serialize, Deserialize)]
pub struct SessionHeader {
    pub r#type: String,      // "session"
    pub version: u32,        // 3
    pub id: String,
    pub timestamp: String,   // ISO8601
    pub cwd: String,
}

// 条目（每行一个，按 type 字段区分）
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SessionEntry {
    Message { id: String, parent_id: Option<String>, timestamp: String, message: Message },
    ModelChange { id: String, parent_id: Option<String>, timestamp: String, provider: String, model_id: String },
    Compaction { id: String, parent_id: Option<String>, timestamp: String, summary: String, first_kept_entry_id: String, tokens_before: u64 },
}

pub struct SessionManager {
    dir: PathBuf,  // 默认 ~/.pi/sessions
}

impl SessionManager {
    pub async fn new_session(&self, cwd: &str) -> anyhow::Result<SessionHeader>;
    pub async fn append_entry(&self, session_id: &str, entry: &SessionEntry) -> anyhow::Result<()>;
    pub async fn load(&self, id: &str) -> anyhow::Result<LoadedSession>;
    pub async fn list(&self) -> anyhow::Result<Vec<SessionMeta>>;
    pub async fn delete(&self, id: &str) -> anyhow::Result<()>;
}
```

---

### 5. TUI 层（`src/tui/`）

使用 **ratatui** + **crossterm** 的事件驱动架构：

#### `app.rs` — 主循环
```rust
pub async fn run(
    terminal: &mut Terminal<CrosstermBackend<Stdout>>,
    agent_ctx: AgentContext,
    provider: Arc<dyn Provider>,
    session_mgr: Arc<SessionManager>,
) -> anyhow::Result<()> {
    // 主事件循环：
    // select! {
    //   crossterm 键盘事件 → handle_key_event
    //   代理事件 channel  → handle_agent_event
    //   定时器 16ms       → terminal.draw(render)
    // }
}
```

#### `state.rs` — 应用状态
```rust
pub struct AppState {
    pub messages: Vec<RenderMessage>,
    pub input_buf: String,
    pub input_cursor: usize,
    pub is_streaming: bool,
    pub stream_buf: String,         // 当前流式输出缓冲
    pub scroll_offset: u16,
    pub terminal_size: Rect,
    pub status: StatusInfo,
    pub cancel_tx: Option<CancellationToken>,
}

pub struct StatusInfo {
    pub model_name: String,
    pub token_count: u32,
    pub elapsed_ms: u64,
}
```

#### `render.rs` — 渲染函数
```rust
pub fn render(f: &mut Frame, state: &AppState) {
    // 布局切分
    let chunks = Layout::vertical([
        Constraint::Min(1),       // 消息区（自适应）
        Constraint::Length(5),    // 输入框
        Constraint::Length(1),    // 状态栏
    ]).split(f.area());

    render_chat(f, state, chunks[0]);
    render_input(f, state, chunks[1]);
    render_status(f, state, chunks[2]);
}
```

键盘快捷键：
- `Ctrl+Enter` / `Alt+Enter`：发送消息
- `Ctrl+C`：取消当前调用（触发 CancellationToken）
- `PageUp/PageDown`：滚动消息区
- `Ctrl+L`：清屏
- `/exit`：退出

---

## 实现顺序（推荐）

```
第 1 步：搭建项目骨架（Cargo.toml、目录、trait 定义）         ≈ 1天
第 2 步：AI 层 — SSE 解析 + Anthropic 提供商                  ≈ 3天
第 3 步：工具系统 — 四个内置工具                               ≈ 1.5天
第 4 步：代理循环 — 核心状态机，CancellationToken              ≈ 2.5天
第 5 步：会话管理                                              ≈ 0.5天
第 6 步：TUI — ratatui App，最小可用界面                       ≈ 3天
第 7 步：集成联调，完成 MVP                                    ≈ 1.5天
第 8 步：OpenAI 提供商                                         ≈ 1天
第 9 步：测试 + 文档                                           ≈ 1.5天
```

总计：约 **15~16 天**

---

## 验收标准

- [ ] `cargo build --release` 产出单一静态二进制（推荐 `x86_64-unknown-linux-musl` target）
- [ ] `./pi` 可启动 TUI
- [ ] 支持 Anthropic Claude 3.5/3.7 Sonnet 流式对话
- [ ] LLM 可成功调用 read/write/edit/bash 工具完成一个真实编码任务
- [ ] 会话自动保存，重启后可恢复
- [ ] Ctrl+C 可取消正在进行的 LLM 调用（CancellationToken 正确传播）
- [ ] `cargo clippy -- -D warnings` 无报错
- [ ] 核心模块有 `#[tokio::test]` 测试覆盖

---

## 环境变量

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PI_SESSION_DIR=~/.pi/sessions
PI_MAX_TURNS=50
```

---

## 注意事项与设计决策

### 1. Provider trait 的 Object Safety
`async fn` 在 trait 中需要 `async_trait` 宏才能实现 dyn trait：
```rust
// 必须这样定义：
#[async_trait]
pub trait Provider: Send + Sync { ... }
```

### 2. 扩展系统的取舍
原项目有完整的 TypeScript 扩展系统（动态 import）。Rust 中**不实现**动态插件，改为：
- 工具注册表（`HashMap<String, Arc<dyn Tool>>`）在启动时静态注入
- 未来可通过 WASM 扩展，但 MVP 阶段不做

### 3. TUI 与代理循环的通信
```rust
// 代理循环在独立 tokio task 中运行
// 通过 mpsc channel 向 TUI 发送事件
let (event_tx, event_rx) = mpsc::channel::<AgentEvent>(256);
tokio::spawn(agent::run(ctx, provider, event_tx, cancel.clone()));

// TUI 主循环中 select! 消费事件
```

### 4. Bash 工具的流式输出
ratatui 是批量渲染（每帧重绘），不是真正的流式追加。需要：
- bash 输出通过 `event_tx` 发送 `AgentEvent::ToolExecutionUpdate`
- TUI 收到后追加到 `stream_buf`
- 下一帧渲染时更新

### 5. 跨平台 bash 工具
Windows 上需要将 `bash -c` 替换为 `cmd /C` 或 `powershell -Command`，
或要求用户安装 Git Bash / WSL。MVP 阶段可以仅支持 Unix（Linux/macOS）。

### 6. 内存管理
消息历史随会话增长，注意：
- `Session.messages` 使用 `Vec<Message>`，无上限
- 渲染时只展示最近 N 条或通过滚动查看
- compaction 逻辑：当 messages 超过阈值时，用 LLM 生成摘要替换旧消息
