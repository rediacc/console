---
title: "Werkzeuge"
description: "Sehen Sie zu und machen Sie mit, während wir das Terminal, die Dateisynchronisation, die VS Code-Integration und CLI-Aktualisierungsbefehle verwenden."
category: "Tutorials"
order: 5
language: de
sourceHash: "6cf8e14712148f7f"
---

# Tutorial: Werkzeuge

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## Voraussetzungen

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/de/docs/tutorial-repos))

## Interaktive Aufzeichnung

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## Was Sie sehen werden

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Schritt 1: Mit einer Maschine verbinden

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### Schritt 2: Mit einem Repository verbinden

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Schritt 3: Dateisynchronisation vorschauen (Probelauf)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### Schritt 4: Dateien hochladen

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### Schritt 5: Hochgeladene Dateien überprüfen

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### Schritt 6: VS Code-Integrationsprüfung

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### Schritt 7: Nach CLI-Updates suchen

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## Nächste Schritte

- [Tools](/de/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/de/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/de/docs/services) — Rediaccfile reference and service networking
