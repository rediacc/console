---
title: Cursor Setup Guide
description: Configure Cursor IDE to work with Rediacc infrastructure using .cursorrules and terminal integration.
category: Guides
order: 32
language: en
---

Cursor integrates with Rediacc through terminal commands and the `.cursorrules` configuration file.

## Quick Setup

1. Install the CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copy the [AGENTS.md template](/en/docs/agents-md-template) to your project root as `.cursorrules`
3. Open the project in Cursor

Cursor reads `.cursorrules` on startup and uses it as context for AI-assisted development.

## .cursorrules Configuration

Create `.cursorrules` in your project root with the Rediacc infrastructure context. See the full [AGENTS.md template](/en/docs/agents-md-template) for a complete version.

The key sections to include:

- CLI tool name (`rdc`) and installation
- Common commands with `--output json` flag
- Architecture overview (repository isolation, Docker daemons)
- Terminology rules (adapters, not modes)

## Terminal Integration

Cursor can execute `rdc` commands through its integrated terminal. Common patterns:

### Checking Status

Ask Cursor: *"Check the status of my production server"*

Cursor runs in terminal:
```bash
rdc machine info prod-1 -o json
```

### Deploying Changes

Ask Cursor: *"Deploy the updated nextcloud config"*

Cursor runs in terminal:
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### Viewing Logs

Ask Cursor: *"Show me the recent mail container logs"*

Cursor runs in terminal:
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
```

## Workspace Settings

For team projects, add Rediacc-specific Cursor settings to `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Tips

- Cursor's Composer mode works well for multi-step infrastructure tasks
- Use `@terminal` in Cursor chat to reference recent terminal output
- The `rdc agent capabilities` command gives Cursor a complete command reference
- Combine `.cursorrules` with a `CLAUDE.md` file for maximum compatibility across AI tools
