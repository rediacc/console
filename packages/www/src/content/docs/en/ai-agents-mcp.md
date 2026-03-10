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
| `machine_info` | Get system info, containers, services, and resource usage for a machine |
| `machine_containers` | List Docker containers with status, health, resource usage, labels, and auto-route domain |
| `machine_services` | List rediacc-managed systemd services (name, state, sub-state, restart count, memory, owning repository) |
| `machine_repos` | List deployed repositories (name, GUID, size, mount status, Docker state, container count, disk usage, modified date, Rediaccfile present) |
| `machine_health` | Run health check on a machine (system, containers, services, storage) |
| `machine_list` | List all configured machines |
| `config_repositories` | List configured repositories with name-to-GUID mappings |
| `config_show_infra` | Show infrastructure configuration for a machine (base domain, public IPs, TLS, Cloudflare zone) |
| `config_providers` | List configured cloud providers for machine provisioning |
| `agent_capabilities` | List all available rdc CLI commands with their arguments and options |

### Write Tools (destructive)

| Tool | Description |
|------|-------------|
| `repo_create` | Create a new encrypted repository on a machine |
| `repo_up` | Deploy/update a repository (runs Rediaccfile up, starts containers). Use `mount` for first deploy or after pull |
| `repo_down` | Stop repository containers. Does NOT unmount by default. Use `unmount` to also close the LUKS container |
| `repo_delete` | Delete a repository (destroys containers, volumes, encrypted image). Credential archived for recovery |
| `repo_fork` | Create a CoW fork with new GUID and networkId (fully independent copy, online forking supported) |
| `backup_push` | Push repository backup to storage or another machine (same GUID -- backup/migration, not fork) |
| `backup_pull` | Pull repository backup from storage or machine. After pull, deploy with `repo_up` (mount=true) |
| `machine_provision` | Provision a new machine on a cloud provider using OpenTofu |
| `machine_deprovision` | Destroy a cloud-provisioned machine and remove from config |
| `config_add_provider` | Add a cloud provider configuration for machine provisioning |
| `config_remove_provider` | Remove a cloud provider configuration |
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
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Security

The MCP server enforces two layers of protection:

### Fork-only mode (default)

By default, the server runs in **fork-only mode** — write tools (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) can only operate on fork repositories. Grand (original) repositories are protected from agent modifications.

To allow an agent to modify grand repos, start with `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

You can also set the `REDIACC_ALLOW_GRAND_REPO` environment variable to a specific repo name or `*` for all repos.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Architecture

The MCP server is stateless. Each tool call spawns `rdc` as an isolated child process with `--output json --yes --quiet` flags. This means:

- No state leaks between tool calls
- Uses your existing `rdc` configuration and SSH keys
- Works with both local and cloud adapters
- Errors in one command don't affect others
