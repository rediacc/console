---
title: "Инструменты"
description: "Смотрите и повторяйте: использование терминала, синхронизация файлов, интеграция VS Code и команды обновления CLI."
category: "Tutorials"
order: 5
language: ru
sourceHash: "6cf8e14712148f7f"
---

# Руководство: Инструменты

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## Предварительные требования

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/ru/docs/tutorial-repos))

## Интерактивная запись

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## Что вы увидите

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Шаг 1: Подключение к машине

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### Шаг 2: Подключение к репозиторию

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Шаг 3: Предварительный просмотр синхронизации (пробный запуск)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### Шаг 4: Загрузка файлов

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### Шаг 5: Проверка загруженных файлов

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### Шаг 6: Проверка интеграции VS Code

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### Шаг 7: Проверка обновлений CLI

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## Следующие шаги

- [Tools](/ru/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/ru/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/ru/docs/services) — Rediaccfile reference and service networking
