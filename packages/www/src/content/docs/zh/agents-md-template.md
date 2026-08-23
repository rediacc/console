---
title: AI 助手的 AGENTS.md 模板
description: 用于配置 Claude Code、Cursor 和其他 AI 编程助手以使用 Rediacc 基础设施的复制粘贴模板。
category: Reference
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 50
language: zh
sourceHash: "7592f803f8caf5f4"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

问题所在：AI 编程助手（Claude Code、Cursor、Cline、Windsurf）会不断发明不存在的 `rdc` 标志，而且每次都需要询问你某个 Rediacc 仓库名称对应哪个 GUID。这个模板解决了这个问题。将下面的内容粘贴到你项目的 `CLAUDE.md`、`.cursorrules` 或你的工具所使用的任何智能体配置文件中。

## 模板

```markdown
# Rediacc Infrastructure

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

## CLI Tool: rdc

Install: `curl -fsSL https://www.rediacc.com/install.sh | bash`

### Key Flags
- `--output json` (or `-o json`), machine-readable JSON output
- `--yes` (or `-y`), skip interactive confirmations
- `--quiet` (or `-q`), suppress informational output
- `--fields name,status`, limit output fields
- Auto-JSON: when piped (non-TTY), output defaults to JSON automatically

### JSON Envelope
All JSON output uses a consistent envelope:
{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}

On error: {"success": false, "command": "...", "data": null, "errors": [{"code": "...", "message": "...", "retryable": false, "guidance": "..."}], ...}

### Common Operations

# Machine status
rdc machine status <machine> -o json

# List containers on a machine
rdc machine status <machine> --containers -o json

# Machine health check
rdc machine health <machine> -o json

# Deploy a repository
rdc repo up <repo>@<machine> --yes

# Stop a repository
rdc repo down <repo>@<machine> --yes

# SSH terminal to machine
rdc term connect <machine> 
# SSH terminal to specific repo (sets DOCKER_HOST)
rdc term connect <repo>@<machine>

# Run command on machine
rdc term connect <machine> -c "command"

# File sync
rdc repo sync upload <repo>@<machine> --local ./local-path
rdc repo sync download <repo>@<machine> --local ./local-path

# List all available commands
rdc --help-all

### Architecture
- **Repository**: Isolated application deployment with its own Docker daemon at /var/run/rediacc/docker-<networkId>.sock, loopback IP range (127.0.x.x/26), and encrypted btrfs mount at /mnt/rediacc/mounts/<guid>/
- **Config**: CLI config at ~/.config/rediacc/rediacc.json. Auto-created on first use.
- One adapter: **local** (SSH-based)

### Rules
- Say "local adapter", never "local mode"
- S3 is a resource state backend, not a separate adapter
- Default config is created automatically on first use, do not tell users to run `rdc config init`
- Always use `--output json` when parsing output programmatically
- Always use `--yes` to skip confirmations in automated workflows
- Use `--dry-run` on destructive commands (repo delete, repo up, repo down) to preview before executing
```

## 自定义

将 `<machine>` 和 `<repo>` 替换为您实际的机器和仓库名称。运行 `rdc repo list` 可列出可用仓库及其名称到 GUID 的映射。

### 发现您的配置

```bash
# List configured machines
rdc machine status <machine-name>

# List repositories with GUIDs
rdc repo list

# Check what commands are available
rdc --help-all
```

## 各代理的配置

- **Claude Code**：在项目根目录保存为 `CLAUDE.md`
- **Cursor**：在项目根目录保存为 `.cursorrules`
- **Cline**：添加到 Cline 系统提示或项目指令中
- **Windsurf**：在项目根目录保存为 `.windsurfrules`
