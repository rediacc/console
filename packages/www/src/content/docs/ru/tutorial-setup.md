---
title: "Настройка машины"
description: "Смотрите и повторяйте: создание конфигурации, добавление машины, тестирование подключения, диагностика и настройка инфраструктуры."
category: "Tutorials"
order: 2
language: ru
sourceHash: "743a5b6abe79a1af"
---

# Руководство: Настройка машины

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Предварительные требования

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Интерактивная запись

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## Что вы увидите

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Шаг 1: Создание новой конфигурации

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Шаг 2: Просмотр конфигураций

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Шаг 3: Добавление машины

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Шаг 4: Просмотр машин

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Шаг 5: Установка машины по умолчанию

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Устанавливает машину по умолчанию, чтобы можно было опускать `-m bridge-vm` в последующих командах.

### Шаг 6: Проверка подключения

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Шаг 7: Выполнение диагностики

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Шаг 8: Настройка инфраструктуры

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Sets the infrastructure configuration for public-facing services. After setting infra, view the configuration:

```bash
rdc config show-infra bridge-vm
```

Deploy the generated Traefik proxy config to the server with `rdc config push-infra bridge-vm`.

## Следующие шаги

- [Machine Setup](/ru/docs/setup) — full reference for all config and setup commands
- [Quick Start](/ru/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/ru/docs/tutorial-repos) — create, deploy, and manage repositories
