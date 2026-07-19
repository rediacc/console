---
title: Claude Code Setup Guide
description: Step-by-step guide to configuring Claude Code for autonomous Rediacc infrastructure management.
category: Guides
order: 31
language: en
---

Claude Code works natively with Rediacc through the `rdc` CLI. This guide covers setup, permissions, and common workflows.

> **Safety first**: Before wiring an agent into anything that touches secrets, read [AI Agent Safety & Guardrails](/en/docs/ai-agents-safety). Claude Code running under `rdc` is detected as an agent. Sensitive mutations require either `--current <previous-value>` (passwd-style precondition) or `--rotate-secret` (acknowledged rotation, audited). Symmetric for humans and agents. Interactive editor, `--reveal`, and direct machine SSH are refused by default unless you explicitly open them via `REDIACC_ALLOW_CONFIG_EDIT`. When a precondition fails, the JSON envelope's `errors[].next.options[].run` field tells the agent the exact CLI command to suggest the user run. Relay it verbatim.

## Quick Setup

1. Install the CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copy the [AGENTS.md template](/en/docs/agents-md-template) to your project root as `CLAUDE.md`
3. Start Claude Code in the project directory

Claude Code reads `CLAUDE.md` on startup and uses it as persistent context for all interactions.

## CLAUDE.md Configuration

Place this at your project root. See the full [AGENTS.md template](/en/docs/agents-md-template) for a complete version. Key sections:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine|repo-ref>

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Tool Permissions

Claude Code will request permission to run `rdc` commands. You can pre-authorize common operations by adding to your Claude Code settings:

- Allow `rdc machine status *`, read-only status checks
- Allow `rdc machine status * --containers`, container listing
- Allow `rdc machine health *`, health checks
- Allow `rdc repo list`, repository listing

For destructive operations (`rdc repo up`, `rdc repo delete`), Claude Code will always ask for confirmation unless you explicitly authorize them.

## Example Workflows

### Check Infrastructure Status

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Deploy a Repository

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### Diagnose Container Issues

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc repo logs nextcloud@prod-1 -c nextcloud-app --lines 50
→ Checks recent logs
```

### File Sync

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## Tips

- Claude Code auto-detects non-TTY and switches to JSON output, no need to specify `-o json` in most cases
- Run `rdc --help-all` to let Claude Code discover all available commands
- The `--fields` flag helps keep context window usage low when you only need specific data
