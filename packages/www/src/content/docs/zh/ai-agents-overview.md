---
title: AI 代理集成概述
description: Claude Code、Cursor 和 Cline 等 AI 编程助手如何与 Rediacc 基础设施集成，实现自主部署和管理。
category: Guides
order: 30
language: zh
sourceHash: "2d8ab92216666d0e"
---

AI 编程助手可以通过 `rdc` CLI 自主管理 Rediacc 基础设施。本指南涵盖集成方法以及如何开始。

## 为什么选择自托管 + AI 代理

Rediacc 的架构天然适合代理使用：

- **CLI 优先**：每个操作都是一个 `rdc` 命令 — 无需 GUI
- **基于 SSH**：代理从训练数据中最熟悉的协议
- **JSON 输出**：所有命令都支持带一致信封的 `--output json`
- **Docker 隔离**：每个仓库拥有自己的守护进程和网络命名空间
- **可脚本化**：`--yes` 跳过确认，`--dry-run` 预览破坏性操作

## 集成方法

### 1. AGENTS.md / CLAUDE.md 模板

最快的入门方式。将我们的 [AGENTS.md 模板](/zh/docs/agents-md-template)复制到项目根目录：

- Claude Code 使用 `CLAUDE.md`
- Cursor 使用 `.cursorrules`
- Windsurf 使用 `.windsurfrules`

这为代理提供了关于可用命令、架构和约定的完整上下文。

### 2. JSON 输出管道

当代理在子 shell 中调用 `rdc` 时，输出会自动切换为 JSON（非 TTY 检测）。每个 JSON 响应使用一致的信封格式：

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

错误响应包含 `retryable` 和 `guidance` 字段：

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. 代理能力发现

`rdc agent` 子命令提供结构化内省功能：

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## 代理的关键标志

| 标志 | 用途 |
|------|---------|
| `--output json` / `-o json` | 机器可读的 JSON 输出 |
| `--yes` / `-y` | 跳过交互式确认 |
| `--quiet` / `-q` | 抑制信息性 stderr 输出 |
| `--fields name,status` | 将输出限制为特定字段 |
| `--dry-run` | 预览破坏性操作而不执行 |

## 后续步骤

- [Claude Code 设置指南](/zh/docs/ai-agents-claude-code) — 逐步 Claude Code 配置
- [Cursor 设置指南](/zh/docs/ai-agents-cursor) — Cursor IDE 集成
- [JSON 输出参考](/zh/docs/ai-agents-json-output) — 完整的 JSON 输出文档
- [AGENTS.md 模板](/zh/docs/agents-md-template) — 复制粘贴代理配置模板
