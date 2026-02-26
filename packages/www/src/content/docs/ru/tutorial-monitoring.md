---
title: "Мониторинг и диагностика"
description: "Смотрите и повторяйте: проверка состояния машины, инспекция контейнеров, обзор служб и выполнение диагностики."
category: "Tutorials"
order: 4
language: ru
sourceHash: "e121e29d9a6359bc"
---

# Руководство: Мониторинг и диагностика

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Предварительные требования

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/ru/docs/tutorial-repos))

## Интерактивная запись

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## Что вы увидите

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Шаг 1: Выполнение диагностики

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Шаг 2: Проверка состояния машины

```bash
rdc machine health server-1
```

Получает подробный отчёт о состоянии, включая время работы системы, использование дисков, использование хранилища данных, количество контейнеров, статус SMART хранилища и выявленные проблемы.

### Шаг 3: Просмотр запущенных контейнеров

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Шаг 4: Проверка служб systemd

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Шаг 5: Обзор состояния хранилища

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Шаг 6: Сканирование ключей хоста

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Шаг 7: Проверка подключения

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Следующие шаги

- [Monitoring](/ru/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/ru/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/ru/docs/tutorial-tools) — terminal, file sync, and VS Code integration
