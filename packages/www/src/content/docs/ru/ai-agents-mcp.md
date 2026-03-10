---
title: Настройка MCP-сервера
description: Подключение AI-агентов к инфраструктуре Rediacc с помощью сервера Model Context Protocol (MCP).
category: Guides
order: 33
language: ru
sourceHash: "f95b630692519da6"
---

## Обзор

Команда `rdc mcp serve` запускает локальный MCP-сервер (Model Context Protocol), который AI-агенты могут использовать для управления вашей инфраструктурой. Сервер использует транспорт stdio — AI-агент запускает его как подпроцесс и обменивается данными через JSON-RPC.

**Требования:** установленный и настроенный `rdc` с хотя бы одной машиной.

## Claude Code

Добавьте в файл `.mcp.json` вашего проекта:

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

Или с именованной конфигурацией:

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

Откройте Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Доступные инструменты

### Инструменты чтения (безопасные, без побочных эффектов)

| Tool | Описание |
|------|----------|
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

### Инструменты записи (деструктивные)

| Tool | Описание |
|------|----------|
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

## Примеры рабочих процессов

**Проверка состояния машины:**
> «Какой статус моей production-машины?»

Агент вызывает `machine_info` → возвращает системную информацию, запущенные контейнеры, сервисы и использование ресурсов.

**Развёртывание приложения:**
> «Разверни gitlab на моей staging-машине»

Агент вызывает `repo_up` с параметрами `name: "gitlab"` и `machine: "staging"` → развёртывает репозиторий, возвращает результат успеха/ошибки.

**Отладка неисправного сервиса:**
> «Мой nextcloud работает медленно, разберись, в чём проблема»

Агент вызывает `machine_health` → `machine_containers` → `term_exec` для чтения логов → определяет проблему и предлагает решение.

## Параметры конфигурации

| Option | Default | Описание |
|--------|---------|----------|
| `--config <name>` | (конфигурация по умолчанию) | Именованная конфигурация для всех команд |
| `--timeout <ms>` | `120000` | Таймаут команды по умолчанию в миллисекундах |
| `--allow-grand` | off | Allow destructive operations on grand (non-fork) repositories |

## Безопасность

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

Вы также можете задать переменной окружения `REDIACC_ALLOW_GRAND_REPO` имя конкретного репозитория или `*` для всех репозиториев.

### Kernel-level filesystem sandbox (Landlock)

When `term_exec` runs a command on a repository, the command is wrapped with `renet sandbox-exec` on the remote machine. This applies Linux Landlock LSM restrictions at the kernel level:

- **Allowed**: the repository's own mount path, `/tmp`, system binaries (`/usr`, `/bin`, `/etc`), the repo's Docker socket
- **Blocked**: other repositories' mount paths, home directory writes, arbitrary filesystem access

This prevents lateral movement — even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) is not sandboxed.

## Архитектура

MCP-сервер не хранит состояние. Каждый вызов инструмента запускает `rdc` как изолированный дочерний процесс с флагами `--output json --yes --quiet`. Это означает:

- Нет утечки состояния между вызовами инструментов
- Используются ваши существующие настройки `rdc` и SSH-ключи
- Работает как с локальным, так и с облачным адаптером
- Ошибки в одной команде не влияют на другие
