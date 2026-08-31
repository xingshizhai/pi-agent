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
| `PI_MODEL` | 覆盖默认模型 | `kimi-for-coding`（Coding Plan） |
| `PI_MAX_TURNS` | 最大工具调用轮数 | `50` |
| `PI_PROVIDER` | 提供商 | `kimi` |
| `KIMI_API_KEY` | Kimi Code / Platform API Key | — |
| `KIMI_API_BASE_URL` | Kimi API 地址 | `https://api.kimi.com/coding/v1` |

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

## 故障排除

### `uv sync` 失败：`pi.exe` 拒绝访问 (os error 5)

**原因**：后台仍有 `pi` 进程在运行（例如之前启动的 TUI 未退出），`uv` 无法覆盖 `.venv\Scripts\pi.exe`。

**处理**：

```powershell
# 查看占用进程
Get-Process pi, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*pi-agent*" }

# 结束 pi 进程（将 PID 换成上一步看到的）
Stop-Process -Name pi -Force -ErrorAction SilentlyContinue

# 若 .venv 已损坏（uv 报 pyvenv.cfg 找不到），整目录删除后重建
Remove-Item -Recurse -Force .venv
uv sync
```

之后用 `uv run pi` 启动；退出 TUI 时按 `/exit` 或空闲时 `Ctrl+C`，避免残留进程。

### `ImportError: cannot import name '__version__' from 'pydantic_core'`

这是 `.venv` 中 `pydantic-core` **安装不完整**（常见于 Windows 上文件被占用导致安装中断）。

**处理步骤**（在 `agent-python` 目录下）：

1. 关闭所有正在运行的 `pi` / Python 进程（包括 TUI 窗口、IDE 调试会话）
2. 删除虚拟环境并重建：

```powershell
# PowerShell
Remove-Item -Recurse -Force .venv
uv sync
uv run pi --help
```

若 `Remove-Item` 提示「拒绝访问」，先结束占用进程后再删，或重启终端/IDE 后重试。

项目已在 `pyproject.toml` 中设置 `tool.uv.link-mode = "copy"`，减少 Windows 上 hardlink 导致的安装问题。

### Kimi Coding Plan 返回 403

若使用 **Kimi Code 会员（Coding Plan，`sk-kimi-` 密钥）**，端点应为：

```
KIMI_API_BASE_URL=https://api.kimi.com/coding/v1
PI_MODEL=kimi-for-coding
```

Coding Plan 还会校验客户端 `User-Agent`。`KimiProvider` 在访问 `api.kimi.com/coding` 时会自动发送白名单 UA（默认 `claude-code/0.1.0`），也可通过 `KIMI_USER_AGENT` 覆盖（如 `KimiCLI/1.0`）。

若仍收到 403，请确认密钥类型与端点匹配；Platform 按量 Key 应使用 `https://api.moonshot.ai/v1` 与模型如 `kimi-k2.6`。
