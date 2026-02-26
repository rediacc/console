---
title: "Surveillance et diagnostics"
description: "Regardez et suivez pendant que nous vérifions l'état de la machine, inspectons les conteneurs, examinons les services et exécutons les diagnostics."
category: "Tutorials"
order: 4
language: fr
sourceHash: "e121e29d9a6359bc"
---

# Tutoriel : Surveillance et diagnostics

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Prérequis

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/fr/docs/tutorial-repos))

## Enregistrement interactif

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Exécuter les diagnostics

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Étape 2 : Vérification de la santé de la machine

```bash
rdc machine health server-1
```

Récupère un rapport de santé complet comprenant le temps de fonctionnement du système, l'utilisation du disque, l'utilisation du datastore, le nombre de conteneurs, l'état SMART du stockage et les problèmes identifiés.

### Étape 3 : Voir les conteneurs en cours

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Étape 4 : Vérifier les services systemd

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Étape 5 : Vue d'ensemble de l'état du coffre

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Étape 6 : Scanner les clés de l'hôte

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Étape 7 : Vérifier la connectivité

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Étapes suivantes

- [Monitoring](/fr/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/fr/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/fr/docs/tutorial-tools) — terminal, file sync, and VS Code integration
