---
title: "دورة حياة المستودع"
description: "شاهد وتابع أثناء إنشاء مستودع مشفر ونشر تطبيق حاوية وفحص الحاويات والتنظيف."
category: "Tutorials"
order: 3
language: ar
sourceHash: "b692ef9f49ac4aa0"
---

# درس تعليمي: دورة حياة المستودع

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## المتطلبات الأساسية

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/ar/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## التسجيل التفاعلي

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## ما ستراه في هذا الدرس

The recording above walks through each step below. Use the playback bar to navigate between commands.

### الخطوة 1: إنشاء مستودع مشفر

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### الخطوة 2: عرض المستودعات

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### الخطوة 3: تحميل ملفات التطبيق

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### الخطوة 4: بدء الخدمات

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### الخطوة 5: عرض الحاويات العاملة

```bash
rdc machine containers server-1
```

يعرض جميع الحاويات العاملة عبر جميع المستودعات على الجهاز، بما في ذلك استخدام المعالج والذاكرة.

### الخطوة 6: الوصول إلى المستودع عبر الطرفية

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### الخطوة 7: إيقاف وتنظيف

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## الخطوات التالية

- [Services](/ar/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/ar/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/ar/docs/tools) — terminal, file sync, and VS Code integration
