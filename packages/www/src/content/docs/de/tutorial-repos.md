---
title: "Repository-Lebenszyklus"
description: "Sehen Sie zu und machen Sie mit, während wir ein verschlüsseltes Repository erstellen, eine containerisierte App bereitstellen, Container inspizieren und aufräumen."
category: "Tutorials"
order: 3
language: de
sourceHash: "b692ef9f49ac4aa0"
---

# Tutorial: Repository-Lebenszyklus

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Voraussetzungen

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/de/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Interaktive Aufzeichnung

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## Was Sie sehen werden

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Schritt 1: Verschlüsseltes Repository erstellen

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Schritt 2: Repositories auflisten

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Schritt 3: Anwendungsdateien hochladen

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Schritt 4: Dienste starten

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Schritt 5: Laufende Container anzeigen

```bash
rdc machine containers server-1
```

Zeigt alle laufenden Container über alle Repositories auf der Maschine, einschließlich CPU- und Speichernutzung.

### Schritt 6: Auf das Repository über das Terminal zugreifen

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Schritt 7: Stoppen und aufräumen

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Nächste Schritte

- [Services](/de/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/de/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/de/docs/tools) — terminal, file sync, and VS Code integration
