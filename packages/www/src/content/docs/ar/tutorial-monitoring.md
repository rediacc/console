---
title: "المراقبة والتشخيص"
description: "شاهد وتابع أثناء فحص صحة الجهاز وفحص الحاويات ومراجعة الخدمات وتشغيل التشخيصات."
category: "Tutorials"
order: 4
language: ar
sourceHash: "e121e29d9a6359bc"
---

# درس تعليمي: المراقبة والتشخيص

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## المتطلبات الأساسية

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/ar/docs/tutorial-repos))

## التسجيل التفاعلي

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## ما ستراه في هذا الدرس

The recording above walks through each step below. Use the playback bar to navigate between commands.

### الخطوة 1: تشغيل التشخيصات

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### الخطوة 2: فحص صحة الجهاز

```bash
rdc machine health server-1
```

يجلب تقريراً شاملاً عن الصحة يتضمن وقت تشغيل النظام واستخدام القرص واستخدام مخزن البيانات وعدد الحاويات وحالة SMART للتخزين وأي مشكلات محددة.

### الخطوة 3: عرض الحاويات العاملة

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### الخطوة 4: فحص خدمات systemd

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### الخطوة 5: نظرة عامة على حالة الخزنة

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### الخطوة 6: فحص مفاتيح المضيف

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### الخطوة 7: التحقق من الاتصال

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## الخطوات التالية

- [Monitoring](/ar/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/ar/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/ar/docs/tutorial-tools) — terminal, file sync, and VS Code integration
