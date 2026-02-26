---
title: "Maschineneinrichtung"
description: "Sehen Sie zu und machen Sie mit, während wir eine Konfiguration erstellen, eine Maschine hinzufügen, die Konnektivität testen, Diagnosen ausführen und die Infrastruktur konfigurieren."
category: "Tutorials"
order: 2
language: de
sourceHash: "743a5b6abe79a1af"
---

# Tutorial: Maschineneinrichtung

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Voraussetzungen

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Interaktive Aufzeichnung

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## Was Sie sehen werden

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Schritt 1: Neue Konfiguration erstellen

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Schritt 2: Konfigurationen anzeigen

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Schritt 3: Maschine hinzufügen

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Schritt 4: Maschinen anzeigen

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Schritt 5: Standardmaschine festlegen

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Legt eine Standardmaschine fest, sodass Sie `-m bridge-vm` bei nachfolgenden Befehlen weglassen können.

### Schritt 6: Konnektivität testen

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Schritt 7: Diagnose ausführen

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Schritt 8: Infrastruktur konfigurieren

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

## Nächste Schritte

- [Machine Setup](/de/docs/setup) — full reference for all config and setup commands
- [Quick Start](/de/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/de/docs/tutorial-repos) — create, deploy, and manage repositories
