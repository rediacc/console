---
title: قالب AGENTS.md لمساعدي الذكاء الاصطناعي
description: >-
  قالب جاهز للنسخ واللصق لتهيئة Claude Code وCursor ومساعدي البرمجة الذكية
  الأخرى للعمل مع بنية Rediacc التحتية.
category: Reference
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 50
language: ar
sourceHash: "7592f803f8caf5f4"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

هذه هي المشكلة: مساعدو البرمجة الذكية (Claude Code، Cursor، Cline، Windsurf) يخترعون باستمرار أعلاماً لـ `rdc` غير موجودة، ولا يستطيعون معرفة اسم مستودع Rediacc المرتبط بأي GUID دون سؤالك في كل مرة. هذا القالب يحل ذلك. الصق الكتلة أدناه في ملف `CLAUDE.md` أو `.cursorrules` أو أي ملف تهيئة وكيل تستخدمه أداتك.

## القالب

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

## التخصيص

استبدل `<machine>` و`<repo>` بأسماء الأجهزة والمستودعات الفعلية الخاصة بك. شغّل `rdc repo list` لعرض المستودعات المتاحة مع تعيين الاسم إلى GUID.

### اكتشاف إعداداتك

```bash
# List configured machines
rdc machine status <machine-name>

# List repositories with GUIDs
rdc repo list

# Check what commands are available
rdc --help-all
```

## إعداد كل وكيل

- **Claude Code**: احفظه كملف `CLAUDE.md` في جذر مشروعك
- **Cursor**: احفظه كملف `.cursorrules` في جذر مشروعك
- **Cline**: أضفه إلى تعليمات نظام Cline أو تعليمات المشروع
- **Windsurf**: احفظه كملف `.windsurfrules` في جذر مشروعك
