---
title: "Cycle de vie des dépôts"
description: "Regardez et suivez pendant que nous créons un dépôt chiffré, déployons une application conteneurisée, inspectons les conteneurs et nettoyons."
category: "Tutorials"
order: 3
language: fr
sourceHash: "b692ef9f49ac4aa0"
---

# Tutoriel : Cycle de vie des dépôts

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Prérequis

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/fr/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Enregistrement interactif

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Créer un dépôt chiffré

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Étape 2 : Lister les dépôts

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Étape 3 : Télécharger les fichiers de l'application

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Étape 4 : Démarrer les services

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Étape 5 : Voir les conteneurs en cours

```bash
rdc machine containers server-1
```

Affiche tous les conteneurs en cours d'exécution sur tous les dépôts de la machine, y compris l'utilisation du processeur et de la mémoire.

### Étape 6 : Accéder au dépôt via le terminal

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Étape 7 : Arrêter et nettoyer

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Étapes suivantes

- [Services](/fr/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/fr/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/fr/docs/tools) — terminal, file sync, and VS Code integration
