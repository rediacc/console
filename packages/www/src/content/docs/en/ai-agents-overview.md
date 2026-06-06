---
title: AI Agent Integration Overview
description: "How Claude Code, Cursor, and Cline manage Rediacc infrastructure via rdc: JSON output, agent introspection, and safety guardrails."
category: Guides
order: 30
language: en
---

Honestly, `rdc` is agent-aware by design. Claude Code, Cursor, Cline: any AI assistant calling `rdc` in a subshell gets structured JSON output, machine-readable errors, and the guardrails you'd want for autonomous Rediacc infrastructure management. Here's how the integration works.

## Why Self-Hosted + AI Agents

Rediacc's architecture works well for agents:

- **CLI-first**: Every operation is a `rdc` command, no GUI required
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

Drop it in and the agent has the full command reference, the architecture context, and the conventions it needs to work without guessing.

### 2. JSON Output Pipeline

When agents call `rdc` in a subshell, output automatically switches to JSON (non-TTY detection). Every JSON response uses a consistent envelope:

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

Error responses include `retryable` and `guidance` fields:

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

### 3. Agent Capabilities Discovery

The `rdc agent` subcommand provides structured introspection:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Key Flags for Agents

| Flag | Purpose |
|------|---------|
| `--output json` / `-o json` | Machine-readable JSON output |
| `--yes` / `-y` | Skip interactive confirmations |
| `--quiet` / `-q` | Suppress informational stderr output |
| `--fields name,status` | Limit output to specific fields |
| `--dry-run` | Preview destructive operations without executing |

## Safety & Guardrails

Look, the CLI doesn't treat agents the same as a human at the terminal. Sensitive operations need proof you already know the current state (the `--current` flag), interactive-editor flows are refused by default, and every refusal is audit-logged. The [AI Agent Safety & Guardrails](/en/docs/ai-agents-safety) reference covers the full firewall table, the knowledge-gate model, the `REDIACC_ALLOW_CONFIG_EDIT` scope-override, and the hash-chained audit log.

## Next Steps

- [AI Agent Safety & Guardrails](/en/docs/ai-agents-safety), What agents can and can't do, knowledge-gate, audit log
- [Claude Code Setup Guide](/en/docs/ai-agents-claude-code), Step-by-step Claude Code configuration
- [Cursor Setup Guide](/en/docs/ai-agents-cursor), Cursor IDE integration
- [JSON Output Reference](/en/docs/ai-agents-json-output), Complete JSON output documentation
- [AGENTS.md Template](/en/docs/agents-md-template), Copy-paste agent configuration template
