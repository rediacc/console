---
title: "Configuration de la machine"
description: "Regardez et suivez pendant que nous créons une configuration, ajoutons une machine, testons la connectivité, exécutons les diagnostics et configurons l'infrastructure."
category: "Tutorials"
order: 2
language: fr
sourceHash: "743a5b6abe79a1af"
---

# Tutoriel : Configuration de la machine

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Prérequis

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Enregistrement interactif

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Créer une nouvelle configuration

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Étape 2 : Voir les configurations

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Étape 3 : Ajouter une machine

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Étape 4 : Voir les machines

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Étape 5 : Définir la machine par défaut

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Définit une machine par défaut pour pouvoir omettre `-m bridge-vm` dans les commandes suivantes.

### Étape 6 : Tester la connectivité

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Étape 7 : Exécuter les diagnostics

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Étape 8 : Configurer l'infrastructure

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

## Étapes suivantes

- [Machine Setup](/fr/docs/setup) — full reference for all config and setup commands
- [Quick Start](/fr/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/fr/docs/tutorial-repos) — create, deploy, and manage repositories
