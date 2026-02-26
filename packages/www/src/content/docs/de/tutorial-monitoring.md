---
title: "Überwachung & Diagnose"
description: "Sehen Sie zu und machen Sie mit, während wir den Maschinenzustand prüfen, Container inspizieren, Dienste überprüfen und Diagnosen ausführen."
category: "Tutorials"
order: 4
language: de
sourceHash: "e121e29d9a6359bc"
---

# Tutorial: Überwachung & Diagnose

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Voraussetzungen

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/de/docs/tutorial-repos))

## Interaktive Aufzeichnung

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## Was Sie sehen werden

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Schritt 1: Diagnose ausführen

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Schritt 2: Maschinengesundheitsprüfung

```bash
rdc machine health server-1
```

Ruft einen umfassenden Gesundheitsbericht ab, einschließlich Systembetriebszeit, Festplattennutzung, Datastore-Nutzung, Container-Anzahl, Speicher-SMART-Status und erkannten Problemen.

### Schritt 3: Laufende Container anzeigen

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Schritt 4: systemd-Dienste prüfen

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Schritt 5: Vault-Statusübersicht

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Schritt 6: Host-Schlüssel scannen

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Schritt 7: Konnektivität überprüfen

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Nächste Schritte

- [Monitoring](/de/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/de/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/de/docs/tutorial-tools) — terminal, file sync, and VS Code integration
