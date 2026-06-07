# 原始项目深度分析

> 分析对象：https://github.com/earendil-works/pi  
> 分析时间：2026-06-07

---

## 一、整体包结构

原项目是一个 TypeScript Monorepo，四个包严格分层，依赖单向向下：

```
pi-coding-agent
    └── depends on → pi-agent-core
                         └── depends on → pi-ai
                                              └── (no internal deps)
pi-tui (独立，被 coding-agent 使用)
```

### 各包职责

| 包 | npm 名称 | 核心职责 |
|----|---------|---------|
| `packages/ai` | `@earendil-works/pi-ai` | LLM 提供商抽象层，消息类型，SSE 流解析 |
| `packages/agent` | `@earendil-works/pi-agent-core` | 代理循环状态机，工具调用调度，事件流 |
| `packages/coding-agent` | `@earendil-works/pi-coding-agent` | 编码代理 CLI，四个内置工具，TUI 界面，会话管理，扩展系统 |
| `packages/tui` | `@earendil-works/pi-tui` | 终端 UI 组件库（编辑器、Markdown 渲染、选择列表等） |

---

## 二、AI 层（pi-ai）核心类型

### 消息类型体系

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

### LLM 流式事件协议（AssistantMessageEvent）

```typescript
// 完整事件序列
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

### Provider 接口

```typescript
interface ApiProvider {
    stream(model, context, options): AssistantMessageEventStream
    streamSimple(model, context, options): AssistantMessageEventStream  // 带 reasoning 映射
}
```

**关键设计**：流返回的是 `EventStream<AssistantMessageEvent, AssistantMessage>`，
一个自定义异步迭代器，最终 resolve 为完整的 AssistantMessage。

---

## 三、Agent 层（pi-agent-core）核心设计

### AgentContext（传入循环的快照）

```typescript
interface AgentContext {
    systemPrompt: string
    messages: AgentMessage[]   // LLM 消息 + 自定义消息的联合类型
    tools?: AgentTool[]
}
```

### AgentTool（工具定义）

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

### 代理循环（AgentLoopConfig）关键钩子

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

### 代理循环状态机（详细）

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
    │   │   ├── beforeToolCall()            // 可block               │
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

---

## 四、Coding Agent 层核心设计

### 内置工具（7个，不是4个）

原项目工具比文档多，完整列表：

| 工具名 | 文件 | 关键参数 |
|--------|------|---------|
| `read` | `read.ts` | `path, offset(行号,1-indexed), limit` |
| `write` | `write.ts` | `path, content` |
| `edit` | `edit.ts` | `path, edits[]{oldText,newText}` |
| `bash` | `bash.ts` | `command, timeout(秒，无默认值)` |
| `find` | `find.ts` | 文件查找 |
| `grep` | `grep.ts` | 内容搜索 |
| `ls` | `ls.ts` | 目录列表 |

> **注意**：`edit` 工具的参数设计与文档不同！
> - 不是 `old_string/new_string`，而是 `edits: [{oldText, newText}]` 数组
> - 支持**批量编辑**（一次调用多个替换）
> - 每个 `oldText` 在原文件中必须唯一（不重叠）
> - 匹配针对**原始文件**，不是增量应用
> - 内部使用 `edit-diff.ts` 计算统一 patch，然后一次性写入

### `edit` 工具的精确语义

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
// 返回 diff + unified patch
```

### `bash` 工具的精确语义

```typescript
// timeout 单位是「秒」，无默认值（不限时）
// 通过 spawn 执行，合并 stdout+stderr
// 超时/取消 → killProcessTree（杀进程树，不只是父进程）
// 输出限制：DEFAULT_MAX_LINES 行 或 DEFAULT_MAX_BYTES 字节
// 输出存到临时文件（如超出则提供路径）
// 支持可插拔的 BashOperations（用于 SSH/容器远程执行）
```

### `read` 工具的精确语义

```typescript
// offset: 1-indexed 行号（不是字节偏移）
// limit: 最多读取行数
// 超限时追加提示："[Showing lines X-Y of Z. Use offset=N to continue.]"
// 支持图片（jpg/png/gif/webp），base64 发送给 LLM
// 图片自动缩放到 2000x2000 以内
// 支持可插拔的 ReadOperations
```

### 会话文件格式（NDJSON，追加写入）

```
# 第一行：SessionHeader（固定）
{"type":"session","version":3,"id":"uuid","timestamp":"ISO8601","cwd":"/path"}

# 后续行：SessionEntry（按时间顺序追加）
{"type":"message","id":"uuid","parentId":"prev-uuid","timestamp":"...","message":{...AgentMessage}}
{"type":"thinking_level_change","id":"uuid","parentId":"...","thinkingLevel":"medium"}
{"type":"model_change","id":"uuid","parentId":"...","provider":"anthropic","modelId":"..."}
{"type":"compaction","id":"uuid","parentId":"...","summary":"...","firstKeptEntryId":"...","tokensBefore":12345}
{"type":"branch_summary","id":"uuid","parentId":"...","fromId":"...","summary":"..."}
{"type":"custom","id":"uuid","parentId":"...","customType":"extension-specific","data":{...}}
```

**关键设计**：
- 追加写入（append-only），不覆盖整个文件
- `parentId` 构成有向链，支持分支
- `compaction` 条目指向 `firstKeptEntryId`，之前的消息被摘要替代
- 会话文件路径：`~/.pi/sessions/<session-id>.pi`

### 会话加载逻辑

```
1. 读取第一行 → SessionHeader（验证 version）
2. 流式逐行读取 → 收集所有 Entry
3. 找最新 compaction Entry → 丢弃 firstKeptEntryId 之前的消息
4. 重建 AgentMessage[] 链
5. branch_summary Entry → 注入为系统消息（不发给 LLM 显示）
```

---

## 五、数据流总览

```
用户输入
    │
    ▼
[CodingAgent / AgentSession]
    │  buildSystemPrompt() → 系统提示词
    │  createAllToolDefinitions() → 工具列表
    │  loadSession() → 历史消息
    │
    ▼
[Agent.prompt(userMsg)]         ← pi-agent-core
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
    │          │
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
    agent_start/end
    turn_start/end
    message_start/update/end
    tool_execution_start/update/end
```

---

## 六、TUI 层关键设计

### 组件列表（pi-tui）

| 组件 | 用途 |
|------|------|
| `Editor` (2231行) | 多行输入框，支持自动补全、历史记录、语法高亮 |
| `Markdown` (814行) | 终端 Markdown 渲染，支持代码块、表格、链接 |
| `SelectList` | 模型/会话选择列表 |
| `Loader` | 加载动画 |
| `Box/Text/Spacer` | 布局原语 |

### 渲染机制

- **差分渲染**（differential rendering）：只重绘变化的部分，减少闪烁
- 工具调用渲染：每个工具有 `renderCall()` 和 `renderResult()` 方法
- 流式输出：`message_update` 事件触发局部重绘（不重绘整个屏幕）
- 图片渲染：支持 sixel/kitty 协议内联图片（终端支持时）

---

## 七、扩展系统（coding-agent 独有）

原项目的扩展系统相当复杂，MVP 阶段**不复刻**，仅记录接口作为未来参考：

```typescript
// Extension 可以：
interface Extension {
    onSessionStart?()        // 会话初始化
    onToolExecutionStart?()  // 工具执行前
    onToolExecutionEnd?()    // 工具执行后
    onTurnEnd?()             // 每轮结束
    onBeforeCompact?()       // 压缩前
    registerTools?()         // 注册额外工具
    registerSlashCommands?() // 注册 slash 命令
}
```

---

## 八、我们的复刻范围决策

基于以上分析，各语言复刻的**精确范围**：

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
