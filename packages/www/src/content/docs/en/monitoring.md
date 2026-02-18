---
title: "Monitoring"
description: "Monitor machine health, containers, services, repositories, and run diagnostics."
category: "Guides"
order: 9
language: en
---

# Monitoring

Rediacc provides built-in monitoring commands to inspect machine health, running containers, services, repository status, and system diagnostics.

## Machine Health

Get a comprehensive health report for a machine:

```bash
rdc machine health server-1
```

This reports:
- **System**: uptime, memory usage, disk usage
- **Datastore**: capacity and usage
- **Containers**: running, healthy, unhealthy counts
- **Services**: status and restart counts
- **Storage**: SMART health and temperature
- **Repositories**: mount status and Docker daemon status
- **Issues**: identified problems

Use `--output json` for machine-readable output.

## List Containers

View all running containers across all repositories on a machine:

```bash
rdc machine containers server-1
```

| Column | Description |
|--------|-------------|
| Name | Container name |
| Status | Running, stopped, etc. |
| Health | Healthy, unhealthy, none |
| CPU | CPU usage percentage |
| Memory | Memory usage |
| Repository | Which repository owns the container |

Options:
- `--health-check` — Perform active health checks on containers
- `--output json` — Machine-readable JSON output

## List Services

View systemd services related to Rediacc on a machine:

```bash
rdc machine services server-1
```

| Column | Description |
|--------|-------------|
| Name | Service name |
| State | Active, inactive, failed |
| Sub-state | Running, dead, etc. |
| Restarts | Restart count |
| Memory | Service memory usage |
| Repository | Associated repository |

Options:
- `--stability-check` — Flag unstable services (failed, >3 restarts, auto-restart)
- `--output json` — Machine-readable JSON output

## List Repositories

View repositories on a machine with detailed stats:

```bash
rdc machine repos server-1
```

| Column | Description |
|--------|-------------|
| Name | Repository name |
| Size | Disk image size |
| Mount | Mounted or unmounted |
| Docker | Docker daemon running or stopped |
| Containers | Container count |
| Disk Usage | Actual disk usage within the repository |
| Modified | Last modification time |

Options:
- `--search <text>` — Filter by name or mount path
- `--output json` — Machine-readable JSON output

## Vault Status

Get a complete overview of a machine including deployment information:

```bash
rdc machine vault-status server-1
```

This provides:
- Hostname and uptime
- Memory, disk, and datastore usage
- Total repositories, mounted count, Docker running count
- Detailed per-repository information

Use `--output json` for machine-readable output.

## Test Connection

Verify SSH connectivity to a machine:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reports:
- Connection status (success/failed)
- Authentication method used
- SSH key configuration
- Public key deployment status
- Known hosts entry

Options:
- `--port <number>` — SSH port (default: 22)
- `--save -m server-1` — Save verified host key to machine config

## Diagnostics (doctor)

Run a comprehensive diagnostic check of your Rediacc environment:

```bash
rdc doctor
```

| Category | Checks |
|----------|--------|
| **Environment** | Node.js version, CLI version, SEA mode, Go installation, Docker availability |
| **Renet** | Binary location, version, CRIU, rsync, SEA embedded assets |
| **Configuration** | Active context, mode, machines, SSH key |
| **Authentication** | Login status, user email |

Each check reports **OK**, **Warning**, or **Error**. Use this as a first step when troubleshooting any issue.

Exit codes: `0` = all passed, `1` = warnings, `2` = errors.
