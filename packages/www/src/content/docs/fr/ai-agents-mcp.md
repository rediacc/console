---
title: Configuration du serveur MCP
description: Connectez des agents IA à l'infrastructure Rediacc en utilisant le serveur Model Context Protocol (MCP).
category: Guides
order: 33
language: fr
sourceHash: "f95b630692519da6"
---

## Aperçu

La commande `rdc mcp serve` lance un serveur MCP (Model Context Protocol) local que les agents IA peuvent utiliser pour gérer votre infrastructure. Le serveur utilise le transport stdio — l'agent IA le lance en tant que sous-processus et communique via JSON-RPC.

**Prérequis :** `rdc` installé et configuré avec au moins une machine.

## Claude Code

Ajoutez au fichier `.mcp.json` de votre projet :

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

Ou avec une configuration nommée :

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

Ouvrez Paramètres → MCP Servers → Add Server :

- **Name** : `rdc`
- **Command** : `rdc mcp serve`
- **Transport** : stdio

## Outils disponibles

### Outils de lecture (sans effets de bord)

| Outil | Description |
|-------|-------------|
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

### Outils d'écriture (destructifs)

| Outil | Description |
|-------|-------------|
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

## Exemples de workflows

**Vérifier l'état d'une machine :**
> « Quel est l'état de ma machine de production ? »

L'agent appelle `machine_info` → renvoie les informations système, les conteneurs en cours d'exécution, les services et l'utilisation des ressources.

**Déployer une application :**
> « Déploie gitlab sur ma machine de staging »

L'agent appelle `repo_up` avec `name: "gitlab"` et `machine: "staging"` → déploie le dépôt, renvoie le succès ou l'échec.

**Déboguer un service défaillant :**
> « Mon nextcloud est lent, trouve ce qui ne va pas »

L'agent appelle `machine_health` → `machine_containers` → `term_exec` pour lire les logs → identifie le problème et propose une solution.

## Options de configuration

| Option | Défaut | Description |
|--------|--------|-------------|
| `--config <name>` | (configuration par défaut) | Configuration nommée à utiliser pour toutes les commandes |
| `--timeout <ms>` | `120000` | Délai d'expiration par défaut des commandes en millisecondes |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Sécurité

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

Vous pouvez aussi définir la variable d'environnement `REDIACC_ALLOW_GRAND_REPO` sur un nom de dépôt précis ou sur `*` pour tous les dépôts.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Architecture

Le serveur MCP est sans état. Chaque appel d'outil lance `rdc` en tant que processus enfant isolé avec les flags `--output json --yes --quiet`. Cela signifie :

- Aucune fuite d'état entre les appels d'outils
- Utilise votre configuration `rdc` existante et vos clés SSH
- Fonctionne avec les adaptateurs local et cloud
- Les erreurs d'une commande n'affectent pas les autres
