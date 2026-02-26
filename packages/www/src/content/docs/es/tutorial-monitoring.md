---
title: "Monitoreo y diagnósticos"
description: "Observe y siga mientras verificamos el estado de la máquina, inspeccionamos contenedores, revisamos servicios y ejecutamos diagnósticos."
category: "Tutorials"
order: 4
language: es
sourceHash: "e121e29d9a6359bc"
---

# Tutorial: Monitoreo y diagnósticos

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## Requisitos previos

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/es/docs/tutorial-repos))

## Grabación interactiva

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Ejecutar diagnósticos

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### Paso 2: Verificación de estado de la máquina

```bash
rdc machine health server-1
```

Obtiene un informe de salud completo que incluye el tiempo de actividad del sistema, uso de disco, uso del almacén de datos, recuento de contenedores, estado SMART del almacenamiento y cualquier problema identificado.

### Paso 3: Ver contenedores en ejecución

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### Paso 4: Verificar servicios systemd

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### Paso 5: Resumen del estado de la bóveda

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### Paso 6: Escanear claves de host

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### Paso 7: Verificar conectividad

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## Próximos pasos

- [Monitoring](/es/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/es/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/es/docs/tutorial-tools) — terminal, file sync, and VS Code integration
