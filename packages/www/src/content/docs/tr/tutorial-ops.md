---
title: "Yerel VM Hazırlama"
description: "Yerel bir VM kümesi hazırlarken, SSH üzerinden komut çalıştırırken ve her şeyi kaldırırken izleyin ve takip edin."
category: "Tutorials"
order: 1
language: tr
sourceHash: "990c6fd433c7c847"
---

# Öğretici: Yerel VM Hazırlama

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Ön Koşullar

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/tr/docs/experimental-vms) for setup instructions

## Etkileşimli Kayıt

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Sistem gereksinimlerini doğrulayın

```bash
rdc ops check
```

Donanım sanallaştırma desteğini, gerekli paketleri (libvirt, QEMU) ve ağ yapılandırmasını kontrol eder. VM hazırlamadan önce bu kontrolün başarılı olması gerekir.

### Adım 2: Minimal bir VM kümesi hazırlayın

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Adım 3: Küme durumunu kontrol edin

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Adım 4: VM üzerinde komut çalıştırın

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Köprü VM'de (ID `1`) SSH üzerinden komut çalıştırır. VM ID'sinden sonra herhangi bir komut geçirebilirsiniz. Etkileşimli bir kabuk için komutu atlayın: `rdc ops ssh 1`.

### Adım 5: Kümeyi kaldırın

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Sonraki Adımlar

- [Experimental VMs](/tr/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/tr/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/tr/docs/quick-start) — deploy a containerized service end-to-end
