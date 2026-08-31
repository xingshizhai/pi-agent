# Go 实现任务书

## 任务概述

用 Go 复刻 [earendil-works/pi](https://github.com/earendil-works/pi) —— 一个极简终端编码代理（Coding Agent）。
用户在终端输入自然语言，LLM 调用 `read/write/edit/bash` 工具完成编码任务，最终产出**单一静态二进制**，无需运行时依赖。

**参考原项目**：https://github.com/earendil-works/pi
**原始项目分析**：见 `../docs/pi-architecture-analysis.md`
**架构设计方案**：见 `../docs/architecture.md`（⚠️ 实现前必读，包含精确的工具参数规范）

---

## 技术选型

| 层 | 库 | 说明 |
|----|----|------|
| TUI 框架 | `github.com/charmbracelet/bubbletea` | Elm 架构，成熟稳定 |
| TUI 样式 | `github.com/charmbracelet/lipgloss` | 终端样式 DSL |
| Markdown 渲染 | `github.com/charmbracelet/glamour` | 终端 Markdown |
| HTTP 客户端 | 标准库 `net/http` | 手动实现 SSE 解析 |
| JSON Schema | `github.com/invopop/jsonschema` | 工具 Schema 生成 |
| JSON 处理 | 标准库 `encoding/json` | — |
| UUID | `github.com/google/uuid` | 会话 ID |
| 测试 | 标准库 `testing` | — |
| 代码质量 | `golangci-lint` | — |

**Go 版本要求**：≥ 1.22

---

## 项目目录结构

```
agent-go/
├── TASK.md                      # 本文件
├── README.md                    # 使用说明
├── go.mod
├── go.sum
├── cmd/
│   └── pi/
│       └── main.go              # 入口：解析 CLI 参数，启动 TUI
├── internal/
│   ├── ai/                      # AI 层
│   │   ├── types.go             # 消息、事件类型定义
│   │   ├── provider.go          # Provider 接口定义
│   │   ├── sse.go               # SSE 流解析通用工具
│   │   ├── anthropic/
│   │   │   └── provider.go      # Anthropic Claude 实现
│   │   └── openai/
│   │       └── provider.go      # OpenAI 实现
│   ├── agent/                   # 代理循环层
│   │   ├── types.go             # AgentContext、AgentEvent 类型
│   │   ├── loop.go              # 核心代理循环
│   │   └── tool_executor.go     # 工具执行（sequential/parallel）
│   ├── tools/                   # 工具系统层
│   │   ├── tool.go              # Tool 接口定义
│   │   ├── read.go              # read 工具
│   │   ├── write.go             # write 工具
│   │   ├── edit.go              # edit 工具
│   │   └── bash.go              # bash 工具
│   ├── session/                 # 会话管理层
│   │   ├── types.go             # Session 结构体
│   │   └── manager.go           # 读写、列表、压缩
│   └── tui/                     # TUI 层
│       ├── app.go               # bubbletea Model（顶层）
│       ├── model.go             # 应用状态定义
│       ├── update.go            # 消息处理（Update 函数）
│       ├── view.go              # 渲染（View 函数）
│       └── keymap.go            # 键盘映射
├── pkg/
│   └── ansi/
│       └── strip.go             # ANSI 转义码过滤
├── tests/
│   ├── ai_test.go
│   ├── agent_loop_test.go
│   └── tools_test.go
└── docs/
    └── providers.md
```

---

## 详细实现规范

### 1. AI 层（`internal/ai/`）

#### `types.go` — 核心类型
```go
type Role string
const (
    RoleUser      Role = "user"
    RoleAssistant Role = "assistant"
    RoleToolResult Role = "tool_result"
)

type TextContent struct {
    Type string `json:"type"` // "text"
    Text string `json:"text"`
}

type ToolCallContent struct {
    Type      string         `json:"type"` // "tool_call"
    ID        string         `json:"id"`
    Name      string         `json:"name"`
    Arguments map[string]any `json:"arguments"`
}

type ToolResultContent struct {
    Type      string `json:"type"` // "tool_result"
    ToolCallID string `json:"tool_call_id"`
    ToolName  string `json:"tool_name"`
    Content   string `json:"content"`
    IsError   bool   `json:"is_error"`
}

type Message struct {
    Role      Role           `json:"role"`
    Content   []any          `json:"content"` // TextContent | ToolCallContent | ToolResultContent
    Timestamp int64          `json:"timestamp"`
}

// 流式事件
type StreamEvent interface{ streamEvent() }
type TextDeltaEvent  struct{ Text string }
type ToolCallEvent   struct{ ToolCallContent }
type DoneEvent       struct{ StopReason string }
type ErrorEvent      struct{ Err error }
```

#### `provider.go` — Provider 接口
```go
type StreamOptions struct {
    APIKey      string
    Temperature float32
    MaxTokens   int
    Signal      <-chan struct{} // 取消信号
}

type Provider interface {
    Stream(
        ctx context.Context,
        messages []Message,
        systemPrompt string,
        tools []ToolDefinition,
        opts StreamOptions,
    ) (<-chan StreamEvent, error)
}
```

#### `sse.go` — SSE 解析（重点模块）
手动解析 `text/event-stream` 格式：
```go
// 解析 SSE 数据流，yield data 行内容
func ParseSSE(reader io.Reader) <-chan SSEEvent
// SSEEvent: { Event string, Data string }
```

#### `anthropic/provider.go` — Anthropic 实现要点
- 端点：`https://api.anthropic.com/v1/messages`
- 请求头：`x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`
- 请求体：`stream: true`, `tools` 数组按 Anthropic 格式
- SSE 事件映射：
  - `content_block_start` (type=tool_use) → 开始收集工具调用
  - `content_block_delta` (type=text_delta) → TextDeltaEvent
  - `content_block_delta` (type=input_json_delta) → 累积工具参数字符串
  - `content_block_stop` → 工具参数完整，解析 JSON → ToolCallEvent
  - `message_stop` → DoneEvent

#### `openai/provider.go` — OpenAI 实现要点
- 端点：`https://api.openai.com/v1/chat/completions`
- SSE 事件：解析 `delta.content` 和 `delta.tool_calls`
- 工具调用参数：通过多个 chunk 的 `arguments` 字段拼接

---

### 2. 代理循环层（`internal/agent/`）

#### `loop.go` — 核心循环
```go
type AgentLoopConfig struct {
    MaxTurns        int
    ExecutionMode   ToolExecutionMode // "sequential" | "parallel"
    BeforeToolCall  func(ctx AgentContext, call ToolCall) (block bool, reason string)
    AfterToolCall   func(ctx AgentContext, call ToolCall, result ToolResult) ToolResult
}

// Run 执行一轮代理循环
// events channel 持续推送 AgentEvent，循环结束后关闭
func Run(
    ctx context.Context,
    userMsg string,
    agentCtx *AgentContext,
    config AgentLoopConfig,
    events chan<- AgentEvent,
) error
```

循环逻辑：
```
1. 追加用户消息到 agentCtx.Messages
2. 发送 turn_start 事件
3. 调用 provider.Stream(...)
4. 消费流：
   a. TextDeltaEvent → 发送 stream_chunk 事件
   b. ToolCallEvent  → 收集工具调用列表
   c. DoneEvent      → 结束流
5. 将 assistant 消息追加到 Messages
6. 若有工具调用：
   a. 发送 tool_execution_start 事件
   b. 执行工具（sequential 或 parallel）
   c. 发送 tool_execution_end 事件
   d. 将 tool_result 消息追加到 Messages
   e. goto 步骤 3（继续调用 LLM）
7. 无工具调用 → 发送 turn_end 事件，循环结束
```

#### `tool_executor.go` — 并行执行
```go
// parallel 模式下使用 errgroup 并发执行工具
func executeParallel(
    ctx context.Context,
    calls []ToolCall,
    tools map[string]Tool,
) []ToolResult
```

---

### 3. 工具系统层（`internal/tools/`）

#### `tool.go` — Tool 接口
```go
type ToolResult struct {
    Content   string
    IsError   bool
    Terminate bool
}

type UpdateFunc func(partialOutput string)

type Tool interface {
    Name() string
    Description() string
    Schema() map[string]any  // JSON Schema
    Execute(ctx context.Context, id string, args map[string]any, update UpdateFunc) (ToolResult, error)
}
```

#### 七个内置工具规范

> ⚠️ 精确参数定义见 `../docs/architecture.md` 第五章

**`read.go`**
```
参数：path (必填), offset (行号, 1-indexed), limit (行数)
行为：带行号前缀 "1\t行内容\n"，默认 2000 行或 200KB
超限提示："[Showing lines X-Y of Z. Use offset=N to continue.]"
```

**`write.go`**
```
参数：path, content
行为：os.MkdirAll + os.WriteFile
```

**`edit.go`**
```
⚠️ 参数是 edits 数组，不是 old_string/new_string！
参数：path (string), edits []struct{ OldText, NewText string }
行为：
  - 每个 OldText 匹配原始文件（非增量）
  - 每个 OldText 在文件中必须恰好出现一次（strings.Count 验证）
  - 全部验证通过后原子写入
  - 返回 details.diff
错误：任一 OldText 不存在或出现多次 → isError=true
```

**`bash.go`**
```
参数：command (string), timeout (float64, 秒，可选，无默认值)
⚠️ timeout 单位是秒，不是毫秒，无默认值（nil 表示不限时）
实现：
  - exec.CommandContext + context.WithTimeout
  - stdout/stderr 合并：io.MultiWriter
  - 流式推送 chunk via update callback
  - 超时/取消 → killProcessTree
  - 输出截断：200KB，截尾并提示
  - ANSI 清理：pkg/ansi.Strip
```

**`find.go`**
```
参数：path, pattern (glob), type ("file"|"dir"|"any")
行为：filepath.WalkDir + filepath.Match，返回路径列表
```

**`grep.go`**
```
参数：path, pattern (regex), recursive (bool), ignore_case (bool)
行为：regexp + filepath.WalkDir，返回 "文件:行号:内容"
```

**`ls.go`**
```
参数：path
行为：os.ReadDir，返回 [{Name, Type, Size}]
```

---

### 4. 会话管理层（`internal/session/`）

> 会话文件格式：NDJSON 追加写入，扩展名 `.pi`，完整规范见 `../docs/architecture.md` 第七章。

```go
// 会话头（第一行）
type SessionHeader struct {
    Type      string `json:"type"`      // "session"
    Version   int    `json:"version"`   // 3
    ID        string `json:"id"`
    Timestamp string `json:"timestamp"` // ISO8601
    CWD       string `json:"cwd"`
}

// 条目（后续每行一个）
type EntryType string
const (
    EntryMessage       EntryType = "message"
    EntryModelChange   EntryType = "model_change"
    EntryCompaction    EntryType = "compaction"
    EntryBranchSummary EntryType = "branch_summary"
)

type Manager struct {
    dir string // 默认 ~/.pi/sessions
}

func (m *Manager) NewSession(cwd string) (*SessionHeader, error)
func (m *Manager) AppendEntry(id string, entry any) error  // 追加一行 NDJSON
func (m *Manager) Load(id string) (*LoadedSession, error)  // 读取并重建
func (m *Manager) List() ([]SessionMeta, error)
func (m *Manager) List() ([]SessionMeta, error)
func (m *Manager) Delete(id string) error
```

---

### 5. TUI 层（`internal/tui/`）

使用 **bubbletea** 的 Elm 架构（Model / Update / View）：

#### `model.go` — 应用状态
```go
type Model struct {
    // 布局
    width, height int

    // 对话历史（用于渲染）
    messages []RenderMessage

    // 输入框状态
    input     textarea.Model
    inputMode InputMode // normal | sending

    // 流式状态
    streamBuffer strings.Builder
    isStreaming   bool

    // 代理事件通道
    agentEvents <-chan AgentEvent

    // 会话
    session *session.Session
    
    // 状态栏信息
    modelName   string
    tokenCount  int
    elapsedTime time.Duration
}
```

#### `update.go` — 消息处理
处理的消息类型：
- `tea.KeyMsg`：Ctrl+Enter 发送，Ctrl+C 取消，方向键历史
- `AgentEventMsg`：代理循环事件（通过 `tea.Cmd` 订阅 channel）
- `tea.WindowSizeMsg`：窗口大小变化

#### `view.go` — 渲染
```go
func (m Model) View() string {
    chat := m.renderChat()    // glamour 渲染 Markdown
    input := m.renderInput()  // textarea + 提示文字
    status := m.renderStatus()
    return lipgloss.JoinVertical(lipgloss.Left, chat, input, status)
}
```

---

## 实现顺序（推荐）

```
第 1 步：搭建项目骨架（go.mod、目录结构、接口定义）        ≈ 0.5天
第 2 步：AI 层 — SSE 解析 + Anthropic 提供商              ≈ 2天
第 3 步：工具系统 — 四个内置工具                           ≈ 1天
第 4 步：代理循环 — 核心状态机                             ≈ 2天
第 5 步：会话管理                                          ≈ 0.5天
第 6 步：TUI — bubbletea App，最小可用界面                 ≈ 2天
第 7 步：集成联调，完成 MVP                                ≈ 1天
第 8 步：OpenAI 提供商                                     ≈ 1天
第 9 步：测试 + 文档                                       ≈ 1天
```

总计：约 **11~12 天**

---

## 验收标准

- [ ] `go build -o pi ./cmd/pi` 产出单一静态二进制
- [ ] `./pi` 可启动 TUI
- [ ] 支持 Anthropic Claude 3.5/3.7 Sonnet 流式对话
- [ ] LLM 可成功调用 read/write/edit/bash 工具完成一个真实编码任务
- [ ] 会话自动保存，重启后可恢复
- [ ] Ctrl+C 取消正在进行的 LLM 调用
- [ ] `go vet ./...` 无报错
- [ ] 核心模块有测试覆盖

---

## 环境变量

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PI_SESSION_DIR=~/.pi/sessions   # 可选
PI_MAX_TURNS=50                  # 可选
```

---

## 注意事项

1. **SSE 解析的边界条件**：HTTP 响应体是持续的 text/event-stream，必须按行读取，处理 `data:` 前缀，跳过空行，检测 `data: [DONE]` 结束标志。
2. **Anthropic 工具参数累积**：`input_json_delta` 事件的 `partial_json` 字段需要字符串拼接后再 `json.Unmarshal`，不能逐块解析。
3. **bubbletea 并发**：代理循环在独立 goroutine 运行，通过 `tea.Cmd` 返回的 channel 消息与主循环通信，禁止直接修改 Model。
4. **bash 工具输出合并**：`exec.Cmd` 的 `StdoutPipe` 和 `StderrPipe` 需要分 goroutine 读取，或使用 `CombinedOutput`（但后者不支持流式）。推荐使用 `cmd.Stdout = &buf; cmd.Stderr = &buf` 配合定时推送。
5. **静态二进制**：`CGO_ENABLED=0 go build` 确保无 cgo 依赖，可跨平台分发。
