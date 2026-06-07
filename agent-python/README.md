# pi-agent (Python)

Python 实现的极简终端编码代理，复刻自 [earendil-works/pi](https://github.com/earendil-works/pi)。

基于 **Textual** 框架构建 TUI，使用 **asyncio** 驱动 Agent 循环，支持 Anthropic 和 OpenAI 两种提供商。

## 快速开始

```bash
# 安装依赖（需要 Python 3.11+）
pip install -e ".[dev]"
# 或使用 uv
uv sync

# 设置 API Key
export ANTHROPIC_API_KEY=sk-ant-...
# 或
export OPENAI_API_KEY=sk-...

# 运行 TUI
python -m pi
# 或（安装后）
pi
```

## 命令行参数

```bash
pi [--provider anthropic|openai] [--model MODEL_ID] [--session SESSION_ID] [--list-sessions]

# 示例
pi --provider openai --model gpt-4o
pi --provider anthropic --model claude-opus-4-5
pi --list-sessions
pi --session abc12345
```

## TUI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Ctrl+J` | 发送消息 |
| `Ctrl+C`（任务运行中） | 取消当前 Agent 任务 |
| `Ctrl+C`（空闲时） | 退出程序 |
| `↑` / `↓`（输入框为空） | 浏览输入历史 |
| `Ctrl+L` | 清屏（不清空上下文） |

## 斜杠命令

在输入框内输入并发送（Ctrl+Enter）：

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清空聊天显示 |
| `/exit` 或 `/quit` | 退出程序 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `PI_MODEL` | 覆盖默认模型 | `claude-sonnet-4-6` |
| `PI_MAX_TURNS` | 最大工具调用轮数 | `50` |
| `PI_PROVIDER` | 提供商（`anthropic`/`openai`） | 自动检测 |

## 架构

```
src/pi/
  main.py             — 入口，CLI 参数解析，TUI/headless 路由
  headless.py         — Headless 模式（PI_HEADLESS=1，用于测试）
  ai/
    anthropic.py      — Anthropic AsyncAnthropic 流式提供商
    openai.py         — OpenAI AsyncOpenAI 流式提供商
    types.py          — Pydantic 消息模型，流式事件 dataclass
  agent/
    loop.py           — Agent 循环 async coroutine
    context.py        — AgentContext / AgentConfig dataclass
    events.py         — Agent 事件类型（ToolExecStart/End, AgentEnd 等）
  tools/              — 7 个内置工具（read/write/edit/bash/find/grep/ls）
  session/            — NDJSON 会话持久化
  tui/
    app.py            — Textual App 主体（PiApp）
    widgets/
      chat.py         — ChatView (ScrollView)，流式渲染，工具显示
      input.py        — InputWidget (TextArea)，历史导航，提交事件
      status.py       — StatusBar，模型名/tokens/延迟/流式状态
```

## 运行测试

```bash
# 单元测试（44 个）
pytest tests/ -v

# Layer 2 集成测试（Mock LLM，无需 API Key）
cd ../tests
python run_tests.py --impl python --layer 2
```

## 依赖

| 包 | 用途 |
|----|------|
| `textual` | TUI 框架 |
| `anthropic` | Anthropic API 客户端 |
| `openai` | OpenAI API 客户端 |
| `pydantic` | 数据模型验证 |
| `rich` | 富文本渲染（Markdown） |
