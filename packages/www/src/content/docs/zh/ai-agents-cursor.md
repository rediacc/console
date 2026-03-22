---
title: Cursor 设置指南
description: 使用 .cursorrules 和终端集成配置 Cursor IDE 以使用 Rediacc 基础设施。
category: Guides
order: 32
language: zh
sourceHash: "c6caf89e3bb3f461"
---

Cursor 通过终端命令和 `.cursorrules` 配置文件与 Rediacc 集成。

## 快速设置

1. 安装 CLI：`curl -fsSL https://www.rediacc.com/install.sh | bash`
2. 将 [AGENTS.md 模板](/zh/docs/agents-md-template)复制到项目根目录并命名为 `.cursorrules`
3. 在 Cursor 中打开项目

Cursor 在启动时读取 `.cursorrules`，并将其作为 AI 辅助开发的上下文。

## .cursorrules 配置

在项目根目录中创建包含 Rediacc 基础设施上下文的 `.cursorrules` 文件。完整版本请参阅 [AGENTS.md 模板](/zh/docs/agents-md-template)。

需要包含的关键部分：

- CLI 工具名称（`rdc`）和安装方法
- 带有 `--output json` 标志的常用命令
- 架构概述（仓库隔离、Docker 守护进程）
- 术语规则（适配器，而非模式）

## 终端集成

Cursor 可以通过其集成终端执行 `rdc` 命令。常见模式：

### 检查状态

询问 Cursor：*"检查我的生产服务器状态"*

Cursor 在终端中运行：
```bash
rdc machine query prod-1 -o json
```

### 部署更改

询问 Cursor：*"部署更新后的 nextcloud 配置"*

Cursor 在终端中运行：
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### 查看日志

询问 Cursor：*"显示最近的 mail 容器日志"*

Cursor 在终端中运行：
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
```

## 工作区设置

对于团队项目，将 Rediacc 特定的 Cursor 设置添加到 `.cursor/settings.json`：

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## 提示

- Cursor 的 Composer 模式非常适合多步骤基础设施任务
- 在 Cursor 聊天中使用 `@terminal` 引用最近的终端输出
- `rdc agent capabilities` 命令为 Cursor 提供完整的命令参考
- 将 `.cursorrules` 与 `CLAUDE.md` 文件结合使用，以实现跨 AI 工具的最大兼容性
