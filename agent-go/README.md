# pi-agent (Go)

Go 实现的极简终端编码代理，复刻自 [earendil-works/pi](https://github.com/earendil-works/pi)。

## 快速开始

```bash
# 设置 API Key
export ANTHROPIC_API_KEY=sk-ant-...
# 或
export OPENAI_API_KEY=sk-...

# 构建
go build -o pi ./cmd/pi

# 运行
./pi
```

## TUI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Alt+Enter` | 发送消息 |
| `Ctrl+C`（任务运行中） | 取消当前 Agent 任务 |
| `Ctrl+C`（空闲时） | 退出程序 |
| `↑` / `↓`（输入框为空） | 浏览输入历史 |
| `PageUp` / `PageDown` | 滚动聊天区域 |
| `Ctrl+L` | 清屏（不清空上下文） |

## 斜杠命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清空聊天显示 |
| `/session` | 列出历史会话 |
| `/exit` 或 `/quit` | 退出程序 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `PI_SESSION_DIR` | 会话文件目录 | `~/.pi/sessions` |
| `PI_MAX_TURNS` | 最大工具调用轮数 | `50` |
| `PI_MODEL` | 覆盖默认模型 | — |

## 架构

```
cmd/pi/           — 入口，配置加载，依赖组装
internal/
  ai/             — LLM 提供商抽象（Anthropic + OpenAI）
    anthropic/    — Anthropic Messages API + SSE 解析
    openai/       — OpenAI Chat Completions API
  agent/          — 代理循环状态机，工具调度
  tools/          — 7 个内置工具（read/write/edit/bash/find/grep/ls）
  session/        — 会话持久化（NDJSON .pi 格式）
  tui/            — bubbletea TUI 界面
pkg/ansi/         — ANSI 转义码过滤
tests/            — 单元测试（23 个）
```

## 构建验证

```bash
go build -o pi ./cmd/pi   # 构建
go vet ./...              # 静态检查
go test ./tests/... -v    # 运行测试（23 个）
```
