---
title: "Локальное развёртывание ВМ"
description: "Смотрите и повторяйте: развёртывание локального кластера ВМ, выполнение команд по SSH и удаление кластера."
category: "Tutorials"
order: 1
language: ru
sourceHash: "990c6fd433c7c847"
---

# Руководство: Локальное развёртывание ВМ

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Предварительные требования

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/ru/docs/experimental-vms) for setup instructions

## Интерактивная запись

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## Что вы увидите

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Шаг 1: Проверка системных требований

```bash
rdc ops check
```

Проверяет поддержку аппаратной виртуализации, необходимые пакеты (libvirt, QEMU) и сетевую конфигурацию. Проверка должна пройти успешно перед развёртыванием ВМ.

### Шаг 2: Развёртывание минимального кластера ВМ

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Шаг 3: Проверка состояния кластера

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Шаг 4: Выполнение команд на ВМ

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Выполняет команды на мостовой ВМ (ID `1`) по SSH. Вы можете передать любую команду после ID ВМ. Для интерактивной оболочки опустите команду: `rdc ops ssh 1`.

### Шаг 5: Удаление кластера

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Следующие шаги

- [Experimental VMs](/ru/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/ru/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/ru/docs/quick-start) — deploy a containerized service end-to-end
