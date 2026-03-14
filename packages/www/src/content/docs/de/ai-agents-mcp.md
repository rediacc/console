---
title: MCP-Server-Einrichtung
description: Verknüpfen Sie KI-Agenten über den Model Context Protocol (MCP) Server mit Ihrer Rediacc-Infrastruktur.
category: Guides
order: 33
language: de
sourceHash: "51c5a7f855ead072"
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

## Überblick

Der Befehl `rdc mcp serve` startet einen lokalen MCP-Server (Model Context Protocol), den KI-Agenten zur Verwaltung Ihrer Infrastruktur nutzen können. Der Server verwendet stdio-Transport — der KI-Agent startet ihn als Unterprozess und kommuniziert über JSON-RPC.

**Voraussetzungen:** `rdc` installiert und mit mindestens einer Maschine konfiguriert.

## Claude Code

Fügen Sie Folgendes zur `.mcp.json` Ihres Projekts hinzu:

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

Oder mit einer benannten Konfiguration:

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

Öffnen Sie Einstellungen → MCP Servers → Server hinzufügen:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Verfügbare Tools

### Lese-Tools (sicher, keine Seiteneffekte)

| Tool | Beschreibung |
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

### Schreib-Tools (destruktiv)

| Tool | Beschreibung |
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

## Beispiel-Workflows

**Maschinenstatus prüfen:**
> „Wie ist der Status meiner Produktionsmaschine?"

Der Agent ruft `machine_info` auf → gibt Systeminformationen, laufende Container, Dienste und Ressourcennutzung zurück.

**Eine Anwendung bereitstellen:**
> „Stelle GitLab auf meiner Staging-Maschine bereit"

Der Agent ruft `repo_up` mit `name: "gitlab"` und `machine: "staging"` auf → stellt das Repository bereit, gibt Erfolg/Fehler zurück.

**Einen fehlerhaften Dienst debuggen:**
> „Mein Nextcloud ist langsam, finde heraus, was los ist"

Der Agent ruft `machine_health` → `machine_containers` → `term_exec` auf, um Logs zu lesen → identifiziert das Problem und schlägt eine Lösung vor.

## Konfigurationsoptionen

| Option | Standard | Beschreibung |
|--------|---------|-------------|
| `--config <name>` | (Standardkonfiguration) | Benannte Konfiguration für alle Befehle |
| `--timeout <ms>` | `120000` | Standard-Befehls-Timeout in Millisekunden |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Sicherheit

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

Sie können die Umgebungsvariable `REDIACC_ALLOW_GRAND_REPO` auch auf einen bestimmten Repo-Namen oder auf `*` für alle Repos setzen.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Architektur

Der MCP-Server ist zustandslos. Jeder Tool-Aufruf startet `rdc` als isolierten Kindprozess mit den Flags `--output json --yes --quiet`. Das bedeutet:

- Kein Zustandsüberlauf zwischen Tool-Aufrufen
- Verwendet Ihre bestehende `rdc`-Konfiguration und SSH-Schlüssel
- Funktioniert sowohl mit dem lokalen als auch dem Cloud-Adapter
- Fehler in einem Befehl beeinflussen andere nicht
