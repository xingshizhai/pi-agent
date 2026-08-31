# Pi 项目架构与分析

> 分析对象：[earendil-works/pi](https://github.com/earendil-works/pi)  
> 文档版本：2026-06-08（合并自原 `01-original-analysis.md` 与架构分析草稿）  
> 相关文档：[多语言复刻架构设计](./architecture.md)

---

## 一、项目定位

Pi 是一个开源的 **AI 编码 Agent 工具链**（Agent Harness），由 Mario（badlogicgames）维护。它不是一个单一 CLI，而是一套可组合、可扩展的分层库：

| 能力 | 说明 |
|------|------|
| 编码 Agent CLI | 终端交互式编码助手，用户通过自然语言驱动 LLM 调用工具完成开发任务 |
| 统一 LLM API | 屏蔽 OpenAI、Anthropic、Google、Bedrock 等 Provider 差异 |
| Agent 运行时 | 工具调用状态机、事件流、生命周期钩子 |
| TUI 组件库 | 差分渲染、Markdown、多行编辑器等终端 UI 原语 |

官网：[pi.dev](https://pi.dev) · 文档：[pi.dev/docs/latest](https://pi.dev/docs/latest) · License：MIT

Slack/聊天自动化在独立仓库 [earendil-works/pi-chat](https://github.com/earendil-works/pi-chat)。

---

## 二、整体架构

### 2.1 分层依赖关系

Pi 采用 TypeScript Monorepo，四个 npm 包严格分层，依赖**单向向下**：

```
┌─────────────────────────────────────────────────────────┐
│              @earendil-works/pi-coding-agent            │
│   CLI 入口 · 内置工具 · 会话管理 · 扩展系统 · TUI 应用    │
├─────────────────────────────────────────────────────────┤
│              @earendil-works/pi-agent-core              │
│        Agent 循环状态机 · 工具调度 · 事件流 · 钩子        │
├─────────────────────────────────────────────────────────┤
│                   @earendil-works/pi-ai                 │
│     Provider 抽象 · 消息类型 · SSE 流解析 · 模型注册      │
└─────────────────────────────────────────────────────────┘

        @earendil-works/pi-tui（独立包，被 coding-agent 使用）
        终端 UI 原语 · 差分渲染 · 键盘/输入处理
```

| 包 | npm 名称 | 核心职责 |
|----|---------|---------|
| `packages/ai` | `@earendil-works/pi-ai` | LLM 提供商抽象层，消息类型，SSE 流解析 |
| `packages/agent` | `@earendil-works/pi-agent-core` | 代理循环状态机，工具调用调度，事件流 |
| `packages/coding-agent` | `@earendil-works/pi-coding-agent` | 编码代理 CLI，7 个内置工具，TUI 界面，会话管理，扩展系统 |
| `packages/tui` | `@earendil-works/pi-tui` | 终端 UI 组件库（编辑器、Markdown 渲染、选择列表等） |

**设计意图**：上层只关心「做什么」（编码任务、会话、UI），下层只关心「怎么做」（LLM 通信、循环控制、终端渲染）。`pi-ai` 和 `pi-agent-core` 可被其他应用独立引用，不绑定 CLI。

### 2.2 运行时数据流

```
用户输入（TUI / CLI / RPC）
        │
        ▼
[CodingAgent / AgentSession]                    ← coding-agent
    │  buildSystemPrompt() → 系统提示词
    │  createAllToolDefinitions() → 工具列表
    │  loadSession() → 历史消息
    │
    ▼
[Agent.prompt(userMsg)]                         ← agent-core
    │  emit: agent_start
    │
    ▼
[agentLoop(prompts, context, config)]
    │
    ├──── LLM 调用 ──────────────────────────────────────────────
    │  streamSimple(model, {systemPrompt, messages, tools}, options)
    │                    │
    │              pi-ai Provider
    │                    │ HTTP POST + SSE
    │                    │ 解析 AssistantMessageEvent 流
    │                    ▼
    │          AssistantMessage（含 ToolCall[]）
    │
    ├──── 工具执行 ───────────────────────────────────────────────
    │  for each ToolCall:
    │      tool.execute(id, args, signal, onUpdate)
    │          ├── read   → fs.readFile
    │          ├── write  → fs.writeFile
    │          ├── edit   → readFile + computeEditsDiff + writeFile
    │          ├── bash   → spawn + OutputAccumulator
    │          └── ...
    │          ▼
    │      AgentToolResult { content, details, terminate? }
    │
    ├──── 消息追加 ───────────────────────────────────────────────
    │  context.messages.push(assistantMsg, ...toolResultMsgs)
    │  sessionManager.appendEntries(entries)  ← 实时持久化
    │
    └──── 继续/结束 ──────────────────────────────────────────────
         有 toolCalls → 继续循环
         无 toolCalls → emit: agent_end

事件流（全程通过 AgentEvent 推送给 TUI）：
    agent_start/end · turn_start/end
    message_start/update/end
    tool_execution_start/update/end
```

**核心模式**：全程事件驱动。LLM 流式输出、工具执行进度、消息生命周期都通过 `AgentEvent` 推送给 UI，UI 只做订阅和渲染，不参与业务逻辑。

---

## 三、pi-ai — LLM 抽象层

**职责**：统一多 Provider 的消息格式、流式协议和模型元数据。

### 3.1 目录结构（`packages/ai/src/`）

| 模块 | 说明 |
|------|------|
| `types.ts` | 消息类型、内容块、流式事件、Usage 等核心类型 |
| `stream.ts` | `EventStream<TEvent, TResult>` 自定义异步迭代器 |
| `api-registry.ts` | Provider 注册与查找 |
| `models.ts` / `models.generated.ts` | 模型目录（自动生成，勿手改） |
| `providers/` | 各 Provider 实现 |
| `env-api-keys.ts` | 从环境变量/OAuth 解析 API Key |

### 3.2 支持的 Provider

| Provider | 文件 |
|----------|------|
| Anthropic | `providers/anthropic.ts` |
| OpenAI Completions | `providers/openai-completions.ts` |
| OpenAI Responses / Codex | `providers/openai-responses.ts`, `openai-codex-responses.ts` |
| Google / Vertex | `providers/google.ts`, `google-vertex.ts` |
| Amazon Bedrock | `providers/amazon-bedrock.ts` |
| Mistral | `providers/mistral.ts` |
| Azure OpenAI | `providers/azure-openai-responses.ts` |
| Cloudflare | `providers/cloudflare.ts` |
| Faux（测试用 Mock） | `providers/faux.ts` |

### 3.3 消息类型体系

```typescript
// 三种基础消息
UserMessage      { role: "user";       content: string | (TextContent | ImageContent)[] }
AssistantMessage { role: "assistant";  content: (TextContent | ThinkingContent | ToolCall)[] }
ToolResultMessage{ role: "toolResult"; toolCallId, toolName, content, details, isError }

// 内容块类型
TextContent     { type: "text";     text: string }
ThinkingContent { type: "thinking"; thinking: string; thinkingSignature?: string }
ImageContent    { type: "image";    data: string; mimeType: string }  // base64
ToolCall        { type: "toolCall"; id, name, arguments: Record<string,any> }
```

### 3.4 LLM 流式事件协议（AssistantMessageEvent）

Provider 将各厂商 SSE 差异统一映射为以下事件序列：

```typescript
"start"           → 流开始，携带空 partial
"text_start"      → 文本块开始（contentIndex 标识位置）
"text_delta"      → 文本增量 token
"text_end"        → 文本块结束
"thinking_start"  → 思考块开始（Claude extended thinking）
"thinking_delta"  → 思考增量
"thinking_end"    → 思考块结束
"toolcall_start"  → 工具调用块开始
"toolcall_delta"  → 工具调用参数增量（JSON 字符串片段）
"toolcall_end"    → 工具调用参数完整，携带完整 ToolCall
"done"            → 正常结束（stopReason: stop | length | toolUse）
"error"           → 异常结束（stopReason: error | aborted）
```

**关键设计**：流返回的是 `EventStream<AssistantMessageEvent, AssistantMessage>`，一个自定义异步迭代器，在迭代过程中 yield 增量事件，最终 resolve 为完整的 `AssistantMessage`。上层（agent-core）只需消费统一协议，无需关心底层 HTTP 细节。

### 3.5 Provider 接口

```typescript
interface ApiProvider {
    stream(model, context, options): AssistantMessageEventStream
    streamSimple(model, context, options): AssistantMessageEventStream  // 带 reasoning 映射
}
```

---

## 四、pi-agent-core — Agent 运行时

**职责**：实现 Agent 循环状态机，调度 LLM 调用与工具执行，向外推送事件流。

### 4.1 目录结构（`packages/agent/src/`）

| 模块 | 说明 |
|------|------|
| `agent-loop.ts` | 核心循环：`agentLoop()` 状态机 |
| `agent.ts` | `Agent` 类，对外 `prompt()` 入口 |
| `types.ts` | `AgentContext`、`AgentTool`、`AgentEvent`、`AgentLoopConfig` |
| `proxy.ts` | Agent 代理（跨进程/远程场景） |
| `harness/` | 测试 harness |

### 4.2 AgentContext

```typescript
interface AgentContext {
    systemPrompt: string
    messages: AgentMessage[]   // LLM 消息 + 自定义消息的联合类型
    tools?: AgentTool[]
}
```

### 4.3 AgentTool

```typescript
interface AgentTool<TParameters, TDetails> extends Tool<TParameters> {
    label: string              // UI 显示标签
    prepareArguments?()        // 参数兼容性适配（旧版本 API 兼容）
    executionMode?             // "sequential" | "parallel" 单工具级别覆盖
    execute(
        toolCallId: string,
        params,
        signal?: AbortSignal,
        onUpdate?: AgentToolUpdateCallback  // 流式部分结果
    ): Promise<AgentToolResult>
}

interface AgentToolResult<T> {
    content: (TextContent | ImageContent)[]
    details: T                // 结构化数据，供 UI 渲染使用
    terminate?: boolean       // 提示循环提前终止
}
```

### 4.4 循环控制钩子（AgentLoopConfig）

```typescript
interface AgentLoopConfig {
    model: Model
    convertToLlm()            // AgentMessage[] → Message[]（过滤不发送给 LLM 的消息）
    transformContext?()        // 发送前变换上下文（裁剪、注入等）
    getApiKey?()              // 动态获取 API key（支持 OAuth 短期 token）
    shouldStopAfterTurn?()    // 每轮结束后决定是否继续
    prepareNextTurn?()        // 替换下一轮的 context/model/thinkingLevel
    getSteeringMessages?()    // 中途注入引导消息（用户可打断）
    getFollowUpMessages?()    // 循环将停时注入后续消息（消息队列机制）
    toolExecution?            // "sequential" | "parallel"（默认 parallel）
    beforeToolCall?()         // 工具执行前拦截（可 block）
    afterToolCall?()          // 工具执行后修改结果
}
```

| 钩子 | 用途 |
|------|------|
| `convertToLlm()` | AgentMessage[] → Message[]，过滤不发送给 LLM 的消息 |
| `transformContext()` | 发送前裁剪/注入上下文 |
| `getApiKey()` | 动态获取 API Key（支持 OAuth 短期 token） |
| `shouldStopAfterTurn()` | 每轮结束后决定是否继续 |
| `prepareNextTurn()` | 替换下一轮的 context/model/thinkingLevel |
| `getSteeringMessages()` | 中途注入引导消息（用户打断） |
| `getFollowUpMessages()` | 循环将停时注入后续消息（消息队列） |
| `beforeToolCall()` / `afterToolCall()` | 工具执行前后拦截/修改 |
| `toolExecution` | 全局 `"sequential"` \| `"parallel"`（默认 parallel） |

### 4.5 代理循环状态机

```
agentLoop(prompts, context, config)
│
├── emit: agent_start
├── emit: turn_start
├── for each prompt: emit message_start/end
│
└── runLoop() ─────────────────────────────────────────────────────┐
    │                                                               │
    ├── [可选] transformContext(messages)                            │
    ├── [可选] getApiKey()                                           │
    ├── streamSimple(model, context, options) → EventStream         │
    │   │                                                           │
    │   ├── 消费 AssistantMessageEvent:                             │
    │   │   ├── text_delta   → emit message_update                  │
    │   │   ├── toolcall_end → 收集 toolCalls[]                     │
    │   │   └── done/error   → 结束流                               │
    │   │                                                           │
    │   └── emit message_end(assistantMessage)                      │
    │                                                               │
    ├── [有工具调用] executeToolCalls(toolCalls):                    │
    │   │                                                           │
    │   ├── for each toolCall:                                      │
    │   │   ├── prepareToolCallArguments()  // prepareArguments钩子  │
    │   │   ├── validateToolArguments()     // typebox schema验证    │
    │   │   ├── beforeToolCall()            // 可 block              │
    │   │   │                                                       │
    │   │   ├── [sequential] execute 完成后再处理下一个               │
    │   │   └── [parallel]   所有工具同时 execute，按完成顺序 emit    │
    │   │       │                                                   │
    │   │       └── emit tool_execution_start/update/end            │
    │   │                                                           │
    │   ├── afterToolCall() → 可修改结果                             │
    │   ├── 追加 toolResultMessages 到 context                       │
    │   └── emit message_start/end for each toolResult              │
    │                                                               │
    ├── emit turn_end(assistantMessage, toolResults)                 │
    ├── shouldStopAfterTurn?() → true → emit agent_end, 退出         │
    ├── prepareNextTurn?() → 更新 context/model                      │
    ├── getSteeringMessages?() → 有消息 → 追加，继续循环 ─────────────┘
    ├── getFollowUpMessages?() → 有消息 → 追加，继续循环 ─────────────┘
    │
    └── 无工具调用且无后续消息 → emit agent_end，循环结束
```

TUI 和 RPC 模式均订阅同一事件流，保证交互模式与非交互模式行为一致。

---

## 五、pi-coding-agent — 编码 Agent CLI

**职责**：面向终端用户的完整编码 Agent 产品，整合工具、会话、扩展、配置和 UI。

### 5.1 目录结构

| 目录/文件 | 说明 |
|-----------|------|
| `main.ts` | CLI 主入口，参数解析，模式分发 |
| `cli/` | 命令行子命令 |
| `modes/` | 运行模式：interactive / print / rpc |
| `core/` | 核心业务逻辑 |
| `config.ts` | 全局配置 |
| `migrations.ts` | 配置/会话格式迁移 |

#### core/ 核心模块

| 模块 | 说明 |
|------|------|
| `agent-session.ts` | 会话编排中枢（~100KB，最大单文件） |
| `session-manager.ts` | NDJSON 会话持久化、加载、分支 |
| `tools/` | 7 个内置工具实现 |
| `extensions/` | 扩展系统（Extension/Skill/Theme/Package） |
| `compaction/` | 上下文压缩（token 超限时摘要历史） |
| `system-prompt.ts` | 系统提示词构建 |
| `model-registry.ts` / `model-resolver.ts` | 模型选择与解析 |
| `settings-manager.ts` | 用户设置 |
| `package-manager.ts` | 扩展包管理（安装/更新/卸载） |
| `skills.ts` | Skill 加载 |
| `auth-storage.ts` | OAuth/API Key 存储 |
| `sdk.ts` | 程序化 SDK 入口 |

### 5.2 运行模式

| 模式 | 说明 |
|------|------|
| **interactive** | 默认 TUI 交互模式 |
| **print** | 非交互，`pi -p "prompt"` 单次执行 |
| **rpc** | JSON-RPC 进程间通信，供 IDE/自动化集成 |

### 5.3 内置工具（7 个）

| 工具名 | 文件 | 关键参数 |
|--------|------|---------|
| `read` | `read.ts` | `path, offset(行号,1-indexed), limit` |
| `write` | `write.ts` | `path, content` |
| `edit` | `edit.ts` | `path, edits[]{oldText,newText}` |
| `bash` | `bash.ts` | `command, timeout(秒，无默认值)` |
| `find` | `find.ts` | 文件查找 |
| `grep` | `grep.ts` | 内容搜索 |
| `ls` | `ls.ts` | 目录列表 |

每个工具实现 `renderCall()` / `renderResult()` 供 TUI 定制渲染。

#### `edit` 工具的精确语义

> **注意**：参数不是 `old_string/new_string`，而是 `edits: [{oldText, newText}]` 数组。

```typescript
// 输入示例
{
  path: "src/foo.ts",
  edits: [
    { oldText: "const x = 1", newText: "const x = 2" },
    { oldText: "return false", newText: "return true" }
  ]
}
// oldText 之间不能重叠
// 所有 edit 同时匹配原文件（非顺序应用）
// 内部使用 edit-diff.ts 计算统一 patch，然后一次性写入
// 返回 diff + unified patch
```

#### `bash` 工具的精确语义

```typescript
// timeout 单位是「秒」，无默认值（不限时）
// 通过 spawn 执行，合并 stdout+stderr
// 超时/取消 → killProcessTree（杀进程树，不只是父进程）
// 输出限制：DEFAULT_MAX_LINES 行 或 DEFAULT_MAX_BYTES 字节
// 输出存到临时文件（如超出则提供路径）
// 支持可插拔的 BashOperations（用于 SSH/容器远程执行）
```

#### `read` 工具的精确语义

```typescript
// offset: 1-indexed 行号（不是字节偏移）
// limit: 最多读取行数
// 超限时追加提示："[Showing lines X-Y of Z. Use offset=N to continue.]"
// 支持图片（jpg/png/gif/webp），base64 发送给 LLM
// 图片自动缩放到 2000x2000 以内
// 支持可插拔的 ReadOperations
```

### 5.4 扩展系统

Pi 的可扩展性是其区别于简单 Agent CLI 的关键特性。原项目扩展系统相当复杂，本仓库 MVP 阶段**不复刻**，仅记录接口作为未来参考：

```typescript
interface Extension {
    onSessionStart?()        // 会话初始化
    onToolExecutionStart?()  // 工具执行前
    onToolExecutionEnd?()    // 工具执行后
    onTurnEnd?()             // 每轮结束
    onBeforeCompact?()       // 压缩前
    registerTools?()         // 注册额外工具
    registerSlashCommands?() // 注册 slash 命令
}

// 此外还有：
// Skill   → 类似 Cursor Skills，注入领域知识
// Theme   → TUI 主题
// Package → npm 包形式的扩展分发（package-manager 管理）
```

扩展通过 `resource-loader.ts` 从 `~/.pi/` 及项目本地 `.pi/` 目录加载。

---

## 六、pi-tui — 终端 UI 库

**职责**：提供高性能终端 UI 原语，与 Agent 逻辑完全解耦。

### 6.1 目录结构（`packages/tui/src/`）

| 模块 | 说明 |
|------|------|
| `tui.ts` | TUI 主框架（~51KB） |
| `terminal.ts` | 终端控制（尺寸、光标、清屏） |
| `components/editor.ts` | 多行编辑器（~75KB，支持自动补全、历史、语法高亮） |
| `components/markdown.ts` | Markdown 渲染（代码块、表格、链接） |
| `components/select-list.ts` | 模型/会话选择列表 |
| `keys.ts` / `keybindings.ts` | 键盘事件解析与绑定 |
| `stdin-buffer.ts` | stdin 缓冲与转义序列处理 |
| `terminal-image.ts` | sixel/kitty 协议图片渲染 |

### 6.2 组件列表

| 组件 | 用途 |
|------|------|
| `Editor` | 多行输入框，支持自动补全、历史记录、语法高亮 |
| `Markdown` | 终端 Markdown 渲染，支持代码块、表格、链接 |
| `SelectList` | 模型/会话选择列表 |
| `Loader` | 加载动画 |
| `Box/Text/Spacer` | 布局原语 |

### 6.3 渲染机制

- **差分渲染**（differential rendering）：比较前后帧差异，只重绘变化区域，避免全屏闪烁
- **流式局部更新**：`message_update` 事件触发对应消息块的增量重绘，不重绘整个聊天区域
- **工具渲染**：每个工具有独立的 `renderCall()` / `renderResult()` 方法
- **图片渲染**：支持 sixel/kitty 协议内联图片（终端支持时）

---

## 七、会话持久化

### 7.1 存储格式

会话文件为 **NDJSON**（Newline Delimited JSON），追加写入，路径：`~/.pi/sessions/<session-id>.pi`

```
# 第一行：SessionHeader
{"type":"session","version":3,"id":"uuid","timestamp":"ISO8601","cwd":"/path"}

# 后续行：SessionEntry（按时间顺序追加）
{"type":"message",        "id":"...", "parentId":"...", "message":{...AgentMessage}}
{"type":"thinking_level_change", ...}
{"type":"model_change",   "provider":"anthropic", "modelId":"..."}
{"type":"compaction",     "summary":"...", "firstKeptEntryId":"...", "tokensBefore":12345}
{"type":"branch_summary", "fromId":"...", "summary":"..."}
{"type":"custom",         "customType":"extension-specific", "data":{...}}
```

### 7.2 关键设计

| 特性 | 说明 |
|------|------|
| 追加写入 | append-only，不覆盖整个文件，崩溃安全 |
| parentId 链 | 构成有向链，支持会话分支（branching） |
| compaction | 超 token 限制时写入摘要 entry，加载时丢弃 `firstKeptEntryId` 之前的消息 |
| 实时持久化 | 每条消息/工具结果立即 append，不等到会话结束 |

### 7.3 加载流程

```
1. 读取第一行 → SessionHeader（验证 version）
2. 流式逐行读取 → 收集所有 Entry
3. 找最新 compaction Entry → 丢弃 firstKeptEntryId 之前的消息
4. 重建 AgentMessage[] 链
5. branch_summary Entry → 注入为系统消息（不发给 LLM）
```

---

## 八、配置与资源加载

Pi 的配置和资源采用**多层叠加**策略：

```
优先级（高 → 低）：
  项目本地 .pi/          → 项目级扩展、Skill、配置
  用户 ~/.pi/             → 全局扩展、OAuth、会话、设置
  内置 defaults           → 默认模型、键绑定、系统提示词
```

| 资源类型 | 典型路径 |
|----------|---------|
| 会话 | `~/.pi/sessions/*.pi` |
| 扩展/Skill | `~/.pi/extensions/`, `.pi/extensions/` |
| OAuth 凭据 | `~/.pi/auth/` |
| 用户设置 | `~/.pi/settings.json` |
| 键绑定 | 内置 `DEFAULT_APP_KEYBINDINGS` + 用户覆盖 |

`resource-loader.ts` 和 `settings-manager.ts` 负责统一加载与合并。

---

## 九、安全模型

Pi **不包含内置权限系统**。默认以启动用户/process 的完整权限运行，可读写文件系统、执行 Shell、访问网络。

如需隔离，官方文档提供三种容器化方案（`packages/coding-agent/docs/containerization.md`）：

| 方案 | 思路 |
|------|------|
| **OpenShell** | 整个 `pi` 进程在策略控制的沙箱中运行 |
| **Gondolin extension** | `pi` 和 Provider 认证留在宿主机，内置工具和 `!` 命令路由到本地 Linux micro-VM |
| **Plain Docker** | 整个 `pi` 进程在本地容器中运行 |

`trust-manager.ts` 提供有限的信任决策（如首次运行某扩展时的确认），但不是系统级沙箱。

---

## 十、工程实践

### 10.1 供应链加固

Pi 将 npm 依赖变更视为代码审查的一部分：

- 直接外部依赖精确 pin 到具体版本
- `.npmrc` 设置 `save-exact=true`、`min-release-age=2`
- `package-lock.json` 为依赖 ground truth；pre-commit 阻止意外 lockfile 提交
- 发布包包含 `npm-shrinkwrap.json`，pin 传递依赖
- CI 定期运行 `npm audit --omit=dev` 和 `npm audit signatures --omit=dev`
- 安装时使用 `--ignore-scripts`，lifecycle script 需显式 allowlist

### 10.2 版本与发布

- **Lockstep versioning**：四个包共享同一版本号
- `patch` = 修复 + 新增；`minor` = breaking changes；无 major release
- 发布流程：本地 smoke test → release script → CI OIDC 发布到 npm
- 支持 Node 和 Bun 两种运行时

### 10.3 测试策略

- `./test.sh`：运行非 e2e 测试（无 API Key 时跳过 LLM 依赖测试）
- `packages/coding-agent/test/suite/`：使用 faux provider 的集成测试 harness
- `./pi-test.sh`：从源码运行 pi（可在任意目录执行）

---

## 十一、架构设计要点总结

| 设计决策 | 理由 |
|----------|------|
| 四层分包 | LLM 抽象、Agent 逻辑、产品功能、UI 各自独立演进和复用 |
| 事件驱动 | UI、RPC、测试 harness 订阅同一 AgentEvent，行为一致 |
| 统一流式协议 | Provider 差异在 pi-ai 层消化，agent-core 只处理 AssistantMessageEvent |
| NDJSON 追加会话 | 崩溃安全、支持分支、compaction 无需重写整个文件 |
| 扩展系统 | Extension/Skill/Package 使 pi 从 CLI 升级为平台 |
| 差分 TUI 渲染 | 流式输出场景下避免全屏重绘导致的闪烁和性能问题 |
| 无内置沙箱 | 保持简单，隔离责任交给容器/外部工具 |
| 供应链 hardening | 编码 Agent 拥有完整用户权限，依赖投毒风险极高 |

---

## 十二、本仓库复刻范围

本仓库（pi-agent）是对 Pi 核心能力的 **Python / Go / Rust 三语言复刻**，聚焦于 7 个内置工具 + Agent 循环 + TUI + NDJSON 会话，并忠于原始语义（工具参数、会话格式、循环行为）。

### P0（MVP 必须实现）

- [ ] AI 层：Anthropic Messages API（SSE 流式）+ 完整事件协议
- [ ] AI 层：OpenAI Completions API（SSE 流式）
- [ ] 代理循环：完整状态机（含 sequential/parallel 工具执行）
- [ ] 内置工具：`read`、`write`、`edit`（批量 edits[]）、`bash`、`find`、`grep`、`ls`
- [ ] 会话：NDJSON 追加写入格式，compaction 支持
- [ ] TUI：流式渲染，输入框，基本 Markdown

### P1（第二阶段）

- [ ] 会话分支（branching）
- [ ] 自动 compaction（token 超限时触发）
- [ ] `transformContext` 钩子（上下文裁剪）
- [ ] 更多 LLM 提供商（Google、DeepSeek）
- [ ] `getSteeringMessages` / `getFollowUpMessages`（消息队列）

### 不复刻

- 扩展系统（Extension/Skill/Theme/Package）
- 图片输入/输出
- RPC 模式
- OAuth 登录（仅支持 API Key）
- 图片内联渲染（sixel/kitty）

复刻实现的统一规范见 [architecture.md](./architecture.md)。

---

## 十三、参考链接

| 资源 | URL |
|------|-----|
| GitHub 仓库 | https://github.com/earendil-works/pi |
| 官网 | https://pi.dev |
| 文档 | https://pi.dev/docs/latest |
| Slack/Chat 集成 | https://github.com/earendil-works/pi-chat |
| 会话分享工具 | https://github.com/badlogic/pi-share-hf |
| 容器化方案 | https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/containerization.md |
