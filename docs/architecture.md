# Pi Agent — 多语言复刻架构总览

## 项目背景

本项目是对 [earendil-works/pi](https://github.com/earendil-works/pi) 的多语言复刻。
Pi 是一个极简终端编码代理框架，用户通过自然语言驱动 LLM，LLM 调用工具（read/write/edit/bash）完成编码任务。

## 仓库结构

```
pi-agent/
├── docs/                    # 共享文档
│   ├── architecture.md      # 本文件：整体架构说明
│   ├── spec-ai-layer.md     # AI 层接口规范
│   ├── spec-agent-loop.md   # 代理循环规范
│   └── spec-tools.md        # 工具系统规范
├── agent-python/            # Python 实现
├── agent-go/                # Go 实现
└── agent-rust/              # Rust 实现
```

## 核心分层架构（三种语言统一）

```
┌──────────────────────────────────────┐
│              CLI / TUI 层            │  交互界面、输入处理、流式输出渲染
├──────────────────────────────────────┤
│             代理循环层               │  消息历史、工具调用状态机、事件流
├──────────────────────────────────────┤
│             工具系统层               │  read / write / edit / bash
├──────────────────────────────────────┤
│              AI 层                   │  LLM 提供商抽象、流式 SSE 解析
├──────────────────────────────────────┤
│             会话管理层               │  持久化、历史记录、上下文压缩
└──────────────────────────────────────┘
```

## MVP 功能范围（三种语言一致）

### 必须实现（P0）
- [ ] AI 层：支持 Anthropic Claude API（流式）
- [ ] AI 层：支持 OpenAI API（流式）
- [ ] 代理循环：消息历史管理，工具调用解析/执行/结果回注
- [ ] 工具：`read`、`write`、`edit`、`bash` 四个内置工具
- [ ] TUI：流式输出渲染，用户输入处理
- [ ] 会话：本地 JSON 持久化

### 应该实现（P1）
- [ ] 会话分支（branching）
- [ ] 上下文压缩（compaction）
- [ ] 多模型切换（/model 命令）
- [ ] 工具并行执行模式

### 可选实现（P2）
- [ ] 更多 LLM 提供商（Google Gemini、DeepSeek 等）
- [ ] 扩展/插件系统
- [ ] RPC 模式（进程间通信）
- [ ] Markdown 渲染美化

## 核心数据结构（跨语言统一定义）

### 消息类型
```
Message:
  role: "user" | "assistant" | "tool_result"
  content: TextContent | ToolCallContent | ToolResultContent
  timestamp: int64

TextContent:
  type: "text"
  text: string

ToolCallContent:
  type: "tool_call"
  id: string
  name: string
  arguments: map<string, any>

ToolResultContent:
  type: "tool_result"
  tool_call_id: string
  tool_name: string
  content: string
  is_error: bool
```

### 工具定义
```
Tool:
  name: string
  description: string
  parameters: JsonSchema
  execute(id, args, signal) -> ToolResult

ToolResult:
  content: string
  is_error: bool
  terminate: bool  // 是否终止代理循环
```

### 代理事件流
```
AgentEvent:
  | agent_start
  | agent_end
  | turn_start
  | turn_end
  | message_start(message)
  | message_end(message)
  | stream_chunk(text)          // LLM 流式 token
  | tool_execution_start(tool_call)
  | tool_execution_update(partial_result)
  | tool_execution_end(tool_call, result)
  | error(message)
```

## 会话文件格式（JSON）
```json
{
  "id": "uuid",
  "created_at": 1234567890,
  "updated_at": 1234567890,
  "model": "claude-sonnet-4-6",
  "messages": [...],
  "cwd": "/path/to/project"
}
```

## 各语言任务书
- [Python 任务书](../agent-python/TASK.md)
- [Go 任务书](../agent-go/TASK.md)
- [Rust 任务书](../agent-rust/TASK.md)
