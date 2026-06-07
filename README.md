# Pi Agent — 多语言复刻项目

对 [earendil-works/pi](https://github.com/earendil-works/pi) 的 Python / Go / Rust 三语言复刻。

## 仓库结构

```
pi-agent/
├── README.md            # 本文件
├── docs/
│   ├── 01-original-analysis.md  # 原始项目深度分析（工具参数、会话格式、循环逻辑）
│   └── 02-architecture.md       # 统一架构设计方案（数据类型、接口规范、工具行为）
├── agent-python/
│   └── TASK.md          # Python 实现任务书（Agent 认领）
├── agent-go/
│   └── TASK.md          # Go 实现任务书（Agent 认领）
└── agent-rust/
    └── TASK.md          # Rust 实现任务书（Agent 认领）
```

## 各实现状态

| 语言 | 难度 | 预计工期 | 状态 |
|------|------|---------|------|
| Python | ⭐⭐ | 8~9 天 | 测试用例已就绪，待实现 |
| Go | ⭐⭐⭐ | 11~12 天 | 待开始 |
| Rust | ⭐⭐⭐⭐⭐ | 15~16 天 | ✅ 已完成（含完整测试套件） |

## Agent 认领说明

每个语言的任务书均为**自包含文档**，Agent 认领后只需阅读：
1. `docs/architecture.md` — 了解整体架构和统一数据结构
2. `<language>/TASK.md` — 该语言的完整实现规范

任务书包含：技术选型、目录结构、各层详细接口定义、实现顺序、验收标准、注意事项。

## MVP 核心功能（三种语言一致）

- Anthropic Claude / OpenAI API 流式对话
- 内置工具：`read` / `write` / `edit` / `bash`
- 代理循环：工具调用状态机，最多 50 轮
- TUI 界面：流式渲染，Ctrl+C 取消
- 会话持久化：本地 JSON 文件
