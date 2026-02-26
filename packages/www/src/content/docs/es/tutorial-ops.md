---
title: "Aprovisionamiento de VM local"
description: "Observe y siga mientras aprovisionamos un clúster de VM local, ejecutamos comandos por SSH y lo eliminamos todo."
category: "Tutorials"
order: 1
language: es
sourceHash: "990c6fd433c7c847"
---

# Tutorial: Aprovisionamiento de VM local

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Requisitos previos

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/es/docs/experimental-vms) for setup instructions

## Grabación interactiva

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Verificar requisitos del sistema

```bash
rdc ops check
```

Verifica el soporte de virtualización de hardware, los paquetes requeridos (libvirt, QEMU) y la configuración de red. Esto debe pasar antes de poder aprovisionar VMs.

### Paso 2: Aprovisionar un clúster de VM mínimo

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Paso 3: Verificar estado del clúster

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Paso 4: Ejecutar comandos en una VM

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Ejecuta comandos en la VM puente (ID `1`) por SSH. Puede pasar cualquier comando después del ID de la VM. Para una sesión interactiva, omita el comando: `rdc ops ssh 1`.

### Paso 5: Eliminar el clúster

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Próximos pasos

- [Experimental VMs](/es/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/es/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/es/docs/quick-start) — deploy a containerized service end-to-end
