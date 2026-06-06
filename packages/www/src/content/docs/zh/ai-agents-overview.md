---
title: AI 代理集成概述
description: "Claude Code、Cursor 和 Cline 如何通过 rdc 管理 Rediacc 基础设施：JSON 输出、代理内省以及安全防护机制。"
category: Guides
order: 30
language: zh
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

说真的，`rdc` 从设计之初就考虑到了代理场景。Claude Code、Cursor、Cline：任何在子 shell 中调用 `rdc` 的 AI 助手，都能获得结构化 JSON 输出、机器可读的错误信息，以及自主管理 Rediacc 基础设施所需的安全防护机制。下面介绍集成的具体方式。

## 为什么选择自托管 + AI 代理

Rediacc 的架构天然适合代理使用：

- **CLI 优先**：每个操作都是一个 `rdc` 命令，无需 GUI
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

放入后，代理即拥有完整的命令参考、架构上下文以及所需的约定规范，无需靠猜测行事。

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
rdc agent schema --command "machine query"

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

## 安全与防护机制

CLI 对代理和终端前的人类操作员采用不同的处理方式。敏感操作需要提供已知当前状态的证明（`--current` 标志），交互式编辑器流程默认拒绝执行，每次拒绝都会记录审计日志。[AI 代理安全与防护机制](/zh/docs/ai-agents-safety)文档涵盖完整的权限防火墙表、知识门控模型、`REDIACC_ALLOW_CONFIG_EDIT` 作用域覆盖，以及哈希链式审计日志的详细说明。

## 后续步骤

- [AI 代理安全与防护机制](/zh/docs/ai-agents-safety)，代理的权限边界、知识门控、审计日志
- [Claude Code 设置指南](/zh/docs/ai-agents-claude-code)，Claude Code 配置步骤详解
- [Cursor 设置指南](/zh/docs/ai-agents-cursor)，Cursor IDE 集成
- [JSON 输出参考](/zh/docs/ai-agents-json-output)，完整的 JSON 输出文档
- [AGENTS.md 模板](/zh/docs/agents-md-template)，可直接复制的代理配置模板
