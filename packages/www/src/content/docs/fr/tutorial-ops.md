---
title: "Provisionnement de VM locales"
description: "Regardez et suivez pendant que nous provisionnons un cluster de VM local, exécutons des commandes via SSH et le démontons."
category: "Tutorials"
order: 1
language: fr
sourceHash: "990c6fd433c7c847"
---

# Tutoriel : Provisionnement de VM locales

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Prérequis

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/fr/docs/experimental-vms) for setup instructions

## Enregistrement interactif

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Vérifier les prérequis système

```bash
rdc ops check
```

Vérifie le support de la virtualisation matérielle, les paquets requis (libvirt, QEMU) et la configuration réseau. Cette vérification doit réussir avant de pouvoir provisionner des VM.

### Étape 2 : Provisionner un cluster de VM minimal

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Étape 3 : Vérifier le statut du cluster

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Étape 4 : Exécuter des commandes sur une VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Exécute des commandes sur la VM pont (ID `1`) via SSH. Vous pouvez passer n'importe quelle commande après l'ID de la VM. Pour un shell interactif, omettez la commande : `rdc ops ssh 1`.

### Étape 5 : Démonter le cluster

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Étapes suivantes

- [Experimental VMs](/fr/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/fr/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/fr/docs/quick-start) — deploy a containerized service end-to-end
