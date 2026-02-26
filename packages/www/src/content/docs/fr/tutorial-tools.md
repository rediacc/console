---
title: "Outils"
description: "Regardez et suivez pendant que nous utilisons le terminal, la synchronisation de fichiers, l'intégration VS Code et les commandes de mise à jour CLI."
category: "Tutorials"
order: 5
language: fr
sourceHash: "6cf8e14712148f7f"
---

# Tutoriel : Outils

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## Prérequis

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/fr/docs/tutorial-repos))

## Enregistrement interactif

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Se connecter à une machine

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### Étape 2 : Se connecter à un dépôt

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Étape 3 : Aperçu de la synchronisation (simulation)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### Étape 4 : Télécharger des fichiers

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### Étape 5 : Vérifier les fichiers téléchargés

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### Étape 6 : Vérification de l'intégration VS Code

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### Étape 7 : Vérifier les mises à jour CLI

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## Étapes suivantes

- [Tools](/fr/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/fr/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/fr/docs/services) — Rediaccfile reference and service networking
