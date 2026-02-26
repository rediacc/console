---
title: "الأدوات"
description: "شاهد وتابع أثناء استخدام الطرفية ومزامنة الملفات وتكامل VS Code وأوامر تحديث CLI."
category: "Tutorials"
order: 5
language: ar
sourceHash: "6cf8e14712148f7f"
---

# درس تعليمي: الأدوات

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## المتطلبات الأساسية

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/ar/docs/tutorial-repos))

## التسجيل التفاعلي

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## ما ستراه في هذا الدرس

The recording above walks through each step below. Use the playback bar to navigate between commands.

### الخطوة 1: الاتصال بجهاز

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### الخطوة 2: الاتصال بمستودع

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### الخطوة 3: معاينة مزامنة الملفات (تجريبي)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### الخطوة 4: تحميل الملفات

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### الخطوة 5: التحقق من الملفات المحملة

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### الخطوة 6: فحص تكامل VS Code

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### الخطوة 7: التحقق من تحديثات CLI

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## الخطوات التالية

- [Tools](/ar/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/ar/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/ar/docs/services) — Rediaccfile reference and service networking
