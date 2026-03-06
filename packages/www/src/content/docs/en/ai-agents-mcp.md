---
title: MCP Server Setup
description: Connect AI agents to Rediacc infrastructure using the Model Context Protocol (MCP) server.
category: Guides
order: 33
language: en
---

## Overview

The `rdc mcp serve` command starts a local MCP (Model Context Protocol) server that AI agents can use to manage your infrastructure. The server uses stdio transport — the AI agent spawns it as a subprocess and communicates via JSON-RPC.

**Prerequisites:** `rdc` installed and configured with at least one machine.

## Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Or with a named config:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Open Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Available Tools

### Read Tools (safe, no side effects)

| Tool | Description |
|------|-------------|
| `machine_info` | Get system info, containers, services, and resource usage |
| `machine_containers` | List Docker containers running on a machine |
| `machine_services` | List systemd services on a machine |
| `machine_repos` | List deployed repositories on a machine |
| `machine_health` | Run health check (system, containers, services, storage) |
| `config_repositories` | List configured repositories with name-to-GUID mappings |
| `agent_capabilities` | List all available rdc CLI commands |

### Write Tools (destructive)

| Tool | Description |
|------|-------------|
| `repo_up` | Deploy/update a repository on a machine |
| `repo_down` | Stop a repository on a machine |
| `term_exec` | Execute a command on a remote machine via SSH |

## Example Workflows

**Check machine status:**
> "What's the status of my production machine?"

The agent calls `machine_info` → returns system info, running containers, services, and resource usage.

**Deploy an application:**
> "Deploy gitlab on my staging machine"

The agent calls `repo_up` with `name: "gitlab"` and `machine: "staging"` → deploys the repository, returns success/failure.

**Debug a failing service:**
> "My nextcloud is slow, figure out what's wrong"

The agent calls `machine_health` → `machine_containers` → `term_exec` to read logs → identifies the issue and suggests a fix.

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config <name>` | (default config) | Named config to use for all commands |
| `--timeout <ms>` | `120000` | Default command timeout in milliseconds |

## Architecture

The MCP server is stateless. Each tool call spawns `rdc` as an isolated child process with `--output json --yes --quiet` flags. This means:

- No state leaks between tool calls
- Uses your existing `rdc` configuration and SSH keys
- Works with both local and cloud adapters
- Errors in one command don't affect others
