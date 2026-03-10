---
title: Configuración del Servidor MCP
description: Conecta agentes de IA a la infraestructura de Rediacc mediante el servidor de Model Context Protocol (MCP).
category: Guides
order: 33
language: es
sourceHash: "f95b630692519da6"
---

## Descripción general

El comando `rdc mcp serve` inicia un servidor MCP (Model Context Protocol) local que los agentes de IA pueden usar para gestionar tu infraestructura. El servidor utiliza transporte stdio — el agente de IA lo ejecuta como un subproceso y se comunica mediante JSON-RPC.

**Requisitos previos:** `rdc` instalado y configurado con al menos una máquina.

## Claude Code

Añade a tu archivo `.mcp.json` del proyecto:

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

O con una configuración con nombre:

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

Abre Configuración → MCP Servers → Añadir servidor:

- **Nombre**: `rdc`
- **Comando**: `rdc mcp serve`
- **Transporte**: stdio

## Herramientas disponibles

### Herramientas de lectura (seguras, sin efectos secundarios)

| Herramienta | Descripción |
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

### Herramientas de escritura (destructivas)

| Herramienta | Descripción |
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

## Flujos de trabajo de ejemplo

**Verificar el estado de la máquina:**
> "¿Cuál es el estado de mi máquina de producción?"

El agente llama a `machine_info` → devuelve información del sistema, contenedores en ejecución, servicios y uso de recursos.

**Desplegar una aplicación:**
> "Despliega gitlab en mi máquina de staging"

El agente llama a `repo_up` con `name: "gitlab"` y `machine: "staging"` → despliega el repositorio, devuelve éxito/error.

**Depurar un servicio con fallos:**
> "Mi nextcloud va lento, averigua qué pasa"

El agente llama a `machine_health` → `machine_containers` → `term_exec` para leer logs → identifica el problema y sugiere una solución.

## Opciones de configuración

| Opción | Predeterminado | Descripción |
|--------|---------|-------------|
| `--config <name>` | (configuración predeterminada) | Configuración con nombre a usar para todos los comandos |
| `--timeout <ms>` | `120000` | Tiempo de espera predeterminado para comandos en milisegundos |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Seguridad

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

También puede establecer la variable de entorno `REDIACC_ALLOW_GRAND_REPO` en un nombre de repositorio específico o en `*` para todos los repositorios.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Arquitectura

El servidor MCP no tiene estado. Cada llamada a una herramienta ejecuta `rdc` como un proceso hijo aislado con las flags `--output json --yes --quiet`. Esto significa:

- No hay fugas de estado entre llamadas a herramientas
- Utiliza tu configuración de `rdc` y claves SSH existentes
- Funciona tanto con el adaptador local como con el de nube
- Los errores en un comando no afectan a otros
