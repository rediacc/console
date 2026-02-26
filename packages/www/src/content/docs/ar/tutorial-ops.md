---
title: "توفير الأجهزة الافتراضية المحلية"
description: "شاهد وتابع أثناء توفير مجموعة أجهزة افتراضية محلية وتشغيل الأوامر عبر SSH وإزالتها."
category: "Tutorials"
order: 1
language: ar
sourceHash: "990c6fd433c7c847"
---

# درس تعليمي: توفير الأجهزة الافتراضية المحلية

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## المتطلبات الأساسية

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/ar/docs/experimental-vms) for setup instructions

## التسجيل التفاعلي

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## ما ستراه في هذا الدرس

The recording above walks through each step below. Use the playback bar to navigate between commands.

### الخطوة 1: التحقق من متطلبات النظام

```bash
rdc ops check
```

يتحقق من دعم المحاكاة الافتراضية للأجهزة والحزم المطلوبة (libvirt وQEMU) وتكوين الشبكة. يجب أن ينجح هذا قبل أن تتمكن من توفير الأجهزة الافتراضية.

### الخطوة 2: توفير مجموعة أجهزة افتراضية بسيطة

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### الخطوة 3: التحقق من حالة المجموعة

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### الخطوة 4: تشغيل الأوامر على جهاز افتراضي

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

يشغّل الأوامر على جهاز الجسر الافتراضي (المعرف `1`) عبر SSH. يمكنك تمرير أي أمر بعد معرف الجهاز. للحصول على واجهة تفاعلية، احذف الأمر: `rdc ops ssh 1`.

### الخطوة 5: إزالة المجموعة

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## الخطوات التالية

- [Experimental VMs](/ar/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/ar/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/ar/docs/quick-start) — deploy a containerized service end-to-end
