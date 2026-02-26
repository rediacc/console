---
title: "Herramientas"
description: "Observe y siga mientras usamos el terminal, la sincronización de archivos, la integración con VS Code y los comandos de actualización de CLI."
category: "Tutorials"
order: 5
language: es
sourceHash: "6cf8e14712148f7f"
---

# Tutorial: Herramientas

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## Requisitos previos

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/es/docs/tutorial-repos))

## Grabación interactiva

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Conectar a una máquina

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### Paso 2: Conectar a un repositorio

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### Paso 3: Vista previa de sincronización (simulación)

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### Paso 4: Subir archivos

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### Paso 5: Verificar archivos subidos

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### Paso 6: Verificación de integración VS Code

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### Paso 7: Verificar actualizaciones de CLI

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## Próximos pasos

- [Tools](/es/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/es/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/es/docs/services) — Rediaccfile reference and service networking
