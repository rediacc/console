---
title: AI Agent Integration Overview
description: How AI coding assistants like Claude Code, Cursor, and Cline integrate with Rediacc infrastructure for autonomous deployment and management.
category: Guides
order: 30
language: en
---

AI coding assistants can manage Rediacc infrastructure autonomously through the `rdc` CLI. This guide covers the integration approaches and how to get started.

## Why Self-Hosted + AI Agents

Rediacc's architecture is naturally agent-friendly:

- **CLI-first**: Every operation is a `rdc` command — no GUI required
- **SSH-based**: The protocol agents know best from training data
- **JSON output**: All commands support `--output json` with a consistent envelope
- **Docker isolation**: Each repository gets its own daemon and network namespace
- **Scriptable**: `--yes` skips confirmations, `--dry-run` previews destructive operations

## Integration Approaches

### 1. AGENTS.md / CLAUDE.md Template

The fastest way to get started. Copy our [AGENTS.md template](/en/docs/agents-md-template) into your project root:

- `CLAUDE.md` for Claude Code
- `.cursorrules` for Cursor
- `.windsurfrules` for Windsurf

This gives the agent full context about available commands, architecture, and conventions.

### 2. JSON Output Pipeline

When agents call `rdc` in a subshell, output automatically switches to JSON (non-TTY detection). Every JSON response uses a consistent envelope:

```json
{
  "success": true,
  "command": "machine info",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Error responses include `retryable` and `guidance` fields:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
  }]
}
```

### 3. Agent Capabilities Discovery

The `rdc agent` subcommand provides structured introspection:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine info"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine info"
```

## Key Flags for Agents

| Flag | Purpose |
|------|---------|
| `--output json` / `-o json` | Machine-readable JSON output |
| `--yes` / `-y` | Skip interactive confirmations |
| `--quiet` / `-q` | Suppress informational stderr output |
| `--fields name,status` | Limit output to specific fields |
| `--dry-run` | Preview destructive operations without executing |

## Next Steps

- [Claude Code Setup Guide](/en/docs/ai-agents-claude-code) — Step-by-step Claude Code configuration
- [Cursor Setup Guide](/en/docs/ai-agents-cursor) — Cursor IDE integration
- [JSON Output Reference](/en/docs/ai-agents-json-output) — Complete JSON output documentation
- [AGENTS.md Template](/en/docs/agents-md-template) — Copy-paste agent configuration template
