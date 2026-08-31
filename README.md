# Pi Agent — 多语言复刻项目

对 [earendil-works/pi](https://github.com/earendil-works/pi) 的 Python / Go / Rust 三语言复刻。

每个实现均包含完整的 **TUI 界面**、**7 个内置工具**、**Agent 循环**、**会话持久化**和**测试套件**。

---

## 仓库结构

```
pi-agent/
├── README.md
├── docs/
│   ├── pi-architecture-analysis.md  # 原始 Pi 项目架构与分析
│   └── architecture.md              # 多语言复刻架构设计
├── agent-go/                     # Go 实现（bubbletea TUI）
├── agent-python/                 # Python 实现（Textual TUI）
├── agent-rust/                   # Rust 实现（ratatui TUI）
└── tests/                        # 跨语言测试套件（Layer 2/3）
```

---

## 各实现状态

| 语言 | TUI 框架 | 状态 | 测试 |
|------|----------|------|------|
| Go | bubbletea + lipgloss | ✅ 完整 | 23 个单元测试 |
| Python | Textual | ✅ 完整 | 44 个单元测试 |
| Rust | ratatui + crossterm | ✅ 完整 | 21 个单元测试 |

---

## 快速开始

### 前置条件

准备好 API Key（任选其一）：

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Anthropic Claude
# 或
export OPENAI_API_KEY=sk-...           # OpenAI GPT
```

---

### Go

```bash
cd agent-go

# 构建
go build -o pi ./cmd/pi

# 运行 TUI
./pi

# 指定模型
PI_MODEL=claude-opus-4-5 ./pi

# 使用 OpenAI
OPENAI_API_KEY=sk-... ./pi
```

### Python

```bash
cd agent-python

# 安装依赖（需要 Python 3.11+）
pip install -e ".[dev]"
# 或使用 uv
uv sync

# 运行 TUI
python -m pi
# 或（安装后）
pi

# 指定提供商和模型
pi --provider openai --model gpt-4o
pi --provider anthropic --model claude-sonnet-4-6
```

### Rust

```bash
cd agent-rust

# 构建（Release 模式）
cargo build --release

# 运行 TUI
./target/release/pi

# 指定模型
PI_MODEL=claude-opus-4-5 ./target/release/pi

# 使用 OpenAI
OPENAI_API_KEY=sk-... ./target/release/pi
```

---

## TUI 界面

所有三种实现的界面布局一致：

```
┌──────────────────────────────────────────────────────┐
│  Chat Area                                            │
│                                                       │
│  You: 帮我写一个二分搜索算法                            │
│                                                       │
│  Assistant: 我来帮你实现...（流式输出▊）                │
│                                                       │
│    ⟳ [bash]  python test.py          ← 工具执行中     │
│    ✓ [write] binary_search.py        ← 工具完成       │
│    ✗ [bash]  exit 1: syntax error    ← 工具出错       │
│                                                       │
└──────────────────────────────────────────────────────┘
│  Input (Ctrl+Enter to send, /help for commands)       │
│  > _                                                  │
└──────────────────────────────────────────────────────┘
  claude-sonnet-4-6  │  ↑1,234 ↓456 tokens  │  3.2s  │  ● streaming
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Alt+Enter` | 发送消息 |
| `Ctrl+C`（任务运行中） | 取消当前 Agent 任务 |
| `Ctrl+C`（空闲时） | 退出程序 |
| `↑` / `↓`（输入框为空） | 浏览输入历史 |
| `PageUp` / `PageDown` | 滚动聊天区域 |
| `Ctrl+L` | 清屏（不清空上下文） |

### 斜杠命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清空聊天显示 |
| `/exit` 或 `/quit` | 退出程序 |
| `/session`（Go） | 列出历史会话 |

---

## 内置工具

所有实现均包含以下 7 个工具：

| 工具 | 功能 |
|------|------|
| `read` | 读取文件，支持行号偏移和限制 |
| `write` | 写入文件 |
| `edit` | 批量文本替换（`edits` 数组） |
| `bash` | 执行 Shell 命令，带超时 |
| `find` | 按 glob 模式查找文件 |
| `grep` | 正则表达式搜索文件内容 |
| `ls` | 列出目录内容 |

---

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `PI_MODEL` | 覆盖默认模型 | `claude-sonnet-4-6` |
| `PI_MAX_TURNS` | 最大工具调用轮数 | `50` |
| `PI_PROVIDER` | 提供商选择（`anthropic`/`openai`） | 自动检测 |

---

## 测试

### 各语言单元测试

```bash
# Go
cd agent-go && go test ./tests/... -v

# Python
cd agent-python && pytest tests/ -v

# Rust
cd agent-rust && cargo test
```

### 跨语言集成测试

```bash
cd tests

# Layer 2：行为测试（使用 Mock LLM，无需 API Key）
python run_tests.py --impl go,python,rust --layer 2

# Layer 3：任务测试（使用真实 LLM，需要 API Key）
python run_tests.py --impl go,python,rust --layer 3

# 与原始 pi 对比
python run_tests.py --impl go --compare pi --layer 3

# 生成报告
python run_tests.py --impl go,python,rust --layer 2 --report report.json
```

---

## 会话持久化

三种实现均使用 NDJSON 格式（`.pi` 文件）保存对话记录，默认存储在 `~/.pi/sessions/`。

```bash
# Go：列出会话
./pi --list-sessions

# Python：列出会话
pi --list-sessions

# 恢复会话（Go / Python，支持完整 ID 或唯一前缀）
./pi --session <session-id>
pi --session <session-id>
```

---

## 架构文档

- [Pi 项目架构与分析](docs/pi-architecture-analysis.md) — 整体架构、分层设计、工具语义、复刻范围
- [多语言复刻架构设计](docs/architecture.md) — 数据类型、接口规范、工具行为
- [Go 实现说明](agent-go/README.md) — Go 特定架构和测试说明
- [Python 实现说明](agent-python/README.md) — Python 特定架构和测试说明
- [Rust 实现说明](agent-rust/README.md) — Rust 特定架构和测试说明
