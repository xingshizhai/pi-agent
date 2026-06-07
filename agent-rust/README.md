# pi-agent (Rust)

Rust 实现的极简终端编码代理，复刻自 [earendil-works/pi](https://github.com/earendil-works/pi)。

基于 **ratatui + crossterm** 构建 TUI，使用 **tokio** 异步运行时驱动 Agent 循环，支持 Anthropic 和 OpenAI 两种提供商。

## 快速开始

```bash
# 构建（Debug）
cargo build

# 构建（Release，推荐）
cargo build --release

# 设置 API Key
export ANTHROPIC_API_KEY=sk-ant-...
# 或
export OPENAI_API_KEY=sk-...

# 运行 TUI
./target/release/pi
# 或直接用 cargo
cargo run --release
```

## 命令行参数

```bash
pi [OPTIONS]

Options:
  --model <MODEL>      模型 ID（也可通过 PI_MODEL 设置）
  --provider <NAME>    提供商：anthropic 或 openai
  --max-turns <N>      最大工具调用轮数（默认 50）
  --help               显示帮助

# 示例
PI_MODEL=claude-opus-4-5 ./pi
OPENAI_API_KEY=sk-... ./pi --provider openai --model gpt-4o
```

## TUI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Alt+Enter` | 发送消息 |
| `Ctrl+C`（任务运行中） | 取消当前 Agent 任务 |
| `Ctrl+C`（空闲时，输入为空） | 退出程序 |
| `Ctrl+C`（有输入内容时） | 清空输入框 |
| `↑` / `↓`（输入框为空） | 浏览输入历史 |
| `PageUp` / `PageDown` | 滚动聊天区域 |
| `Home` | 滚动到顶部 |
| `End` | 滚动到底部 |
| `Ctrl+L` | 清屏（不清空上下文） |

## 斜杠命令

在输入框内输入后按 `Ctrl+Enter` 执行：

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息和快捷键 |
| `/clear` | 清空聊天显示 |
| `/exit` 或 `/quit` | 退出程序 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `PI_MODEL` | 覆盖默认模型 | `claude-sonnet-4-6` |
| `PI_MAX_TURNS` | 最大工具调用轮数 | `50` |

## 架构

```
src/
  main.rs             — 入口，配置加载，TUI/headless 路由
  headless.rs         — Headless 模式（PI_HEADLESS=1，用于测试）
  ai/
    anthropic.rs      — Anthropic SSE 流式提供商
    openai.rs         — OpenAI 流式提供商
    types.rs          — Message、StreamEvent 等核心类型
  agent/
    loop.rs           — Agent 循环状态机
    types.rs          — AgentContext、AgentEvent 枚举
  tools/              — 7 个内置工具（read/write/edit/bash/find/grep/ls）
  session/            — NDJSON 会话持久化
  tui/
    app.rs            — 主事件循环（tokio::select! 驱动）
    state.rs          — AppState：消息列表、流式 buf、历史、active tools
    events.rs         — 键盘事件处理、斜杠命令解析、历史导航
    render.rs         — ratatui 渲染（聊天区 / 输入框 / 状态栏）
```

## 运行测试

```bash
# 单元测试（21 个）
cargo test

# Layer 2 集成测试（Mock LLM，无需 API Key）
cd ../tests
python run_tests.py --impl rust --layer 2
```

## 依赖

| crate | 用途 |
|-------|------|
| `ratatui` | TUI 渲染框架 |
| `crossterm` | 终端控制 / 事件流 |
| `tokio` | 异步运行时 |
| `reqwest` | HTTP 客户端（SSE 流） |
| `serde_json` | JSON 序列化 |
| `anyhow` | 错误处理 |
| `tokio-util` | CancellationToken |
