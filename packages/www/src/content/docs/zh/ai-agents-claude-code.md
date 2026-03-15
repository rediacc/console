---
title: Claude Code 设置指南
description: 配置 Claude Code 进行自主 Rediacc 基础设施管理的分步指南。
category: Guides
order: 31
language: zh
sourceHash: "8b05c6da1e3fc662"
---

Claude Code 通过 `rdc` CLI 与 Rediacc 原生集成。本指南涵盖设置、权限和常见工作流程。

## 快速设置

1. 安装 CLI：`curl -fsSL https://www.rediacc.com/install.sh | bash`
2. 将 [AGENTS.md 模板](/zh/docs/agents-md-template)复制到项目根目录并命名为 `CLAUDE.md`
3. 在项目目录中启动 Claude Code

Claude Code 在启动时读取 `CLAUDE.md`，并将其作为所有交互的持久上下文。

## CLAUDE.md 配置

将此文件放在项目根目录。完整版本请参阅 [AGENTS.md 模板](/zh/docs/agents-md-template)。关键部分：

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine query <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## 工具权限

Claude Code 会请求运行 `rdc` 命令的权限。您可以通过在 Claude Code 设置中添加以下内容来预先授权常见操作：

- 允许 `rdc machine query *` — 只读状态检查
- 允许 `rdc machine containers *` — 容器列表
- 允许 `rdc machine health *` — 健康检查
- 允许 `rdc config repository list` — 仓库列表

对于破坏性操作（`rdc repo up`、`rdc repo delete`），除非您明确授权，否则 Claude Code 始终会请求确认。

## 示例工作流程

### 检查基础设施状态

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine query prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### 部署仓库

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### 诊断容器问题

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### 文件同步

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## 提示

- Claude Code 自动检测非 TTY 环境并切换到 JSON 输出 — 大多数情况下无需指定 `-o json`
- 使用 `rdc agent capabilities` 让 Claude Code 发现所有可用命令
- 使用 `rdc agent schema "命令名称"` 获取详细的参数/选项信息
- `--fields` 标志有助于在只需要特定数据时降低上下文窗口的使用量
