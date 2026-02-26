---
title: "Жизненный цикл репозитория"
description: "Смотрите и повторяйте: создание зашифрованного репозитория, развёртывание контейнерного приложения, инспекция контейнеров и очистка."
category: "Tutorials"
order: 3
language: ru
sourceHash: "b692ef9f49ac4aa0"
---

# Руководство: Жизненный цикл репозитория

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Предварительные требования

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/ru/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Интерактивная запись

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## Что вы увидите

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Шаг 1: Создание зашифрованного репозитория

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Шаг 2: Список репозиториев

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Шаг 3: Загрузка файлов приложения

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Шаг 4: Запуск сервисов

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Шаг 5: Просмотр запущенных контейнеров

```bash
rdc machine containers server-1
```

Показывает все запущенные контейнеры во всех репозиториях на машине, включая использование ЦП и памяти.

### Шаг 6: Доступ к репозиторию через терминал

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Шаг 7: Остановка и очистка

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Следующие шаги

- [Services](/ru/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/ru/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/ru/docs/tools) — terminal, file sync, and VS Code integration
