---
title: "Lokale VM-Bereitstellung"
description: "Sehen Sie zu und machen Sie mit, während wir einen lokalen VM-Cluster bereitstellen, Befehle über SSH ausführen und alles wieder abbauen."
category: "Tutorials"
order: 1
language: de
sourceHash: "990c6fd433c7c847"
---

# Tutorial: Lokale VM-Bereitstellung

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## Voraussetzungen

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/de/docs/experimental-vms) for setup instructions

## Interaktive Aufzeichnung

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## Was Sie sehen werden

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Schritt 1: Systemanforderungen überprüfen

```bash
rdc ops check
```

Prüft auf Hardware-Virtualisierungsunterstützung, benötigte Pakete (libvirt, QEMU) und Netzwerkkonfiguration. Dies muss erfolgreich sein, bevor Sie VMs bereitstellen können.

### Schritt 2: Minimalen VM-Cluster bereitstellen

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### Schritt 3: Cluster-Status prüfen

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### Schritt 4: Befehle auf einer VM ausführen

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Führt Befehle auf der Bridge-VM (ID `1`) über SSH aus. Sie können jeden Befehl nach der VM-ID übergeben. Für eine interaktive Shell lassen Sie den Befehl weg: `rdc ops ssh 1`.

### Schritt 5: Cluster abbauen

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## Nächste Schritte

- [Experimental VMs](/de/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/de/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/de/docs/quick-start) — deploy a containerized service end-to-end
