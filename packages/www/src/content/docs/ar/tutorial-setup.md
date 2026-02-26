---
title: "إعداد الجهاز"
description: "شاهد وتابع أثناء إنشاء إعداد وإضافة جهاز واختبار الاتصال وتشغيل التشخيصات وتكوين البنية التحتية."
category: "Tutorials"
order: 2
language: ar
sourceHash: "743a5b6abe79a1af"
---

# درس تعليمي: إعداد الجهاز

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## المتطلبات الأساسية

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## التسجيل التفاعلي

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## ما ستراه في هذا الدرس

The recording above walks through each step below. Use the playback bar to navigate between commands.

### الخطوة 1: إنشاء إعداد جديد

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### الخطوة 2: عرض الإعدادات

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### الخطوة 3: إضافة جهاز

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### الخطوة 4: عرض الأجهزة

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### الخطوة 5: تعيين الجهاز الافتراضي

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

يعيّن جهازاً افتراضياً حتى تتمكن من حذف `-m bridge-vm` من الأوامر اللاحقة.

### الخطوة 6: اختبار الاتصال

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### الخطوة 7: تشغيل التشخيصات

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### الخطوة 8: تكوين البنية التحتية

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

## الخطوات التالية

- [Machine Setup](/ar/docs/setup) — full reference for all config and setup commands
- [Quick Start](/ar/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/ar/docs/tutorial-repos) — create, deploy, and manage repositories
