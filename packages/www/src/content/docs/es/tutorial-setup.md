---
title: "Configuración de máquina"
description: "Observe y siga mientras creamos una configuración, agregamos una máquina, probamos la conectividad, ejecutamos diagnósticos y configuramos la infraestructura."
category: "Tutorials"
order: 2
language: es
sourceHash: "743a5b6abe79a1af"
---

# Tutorial: Configuración de máquina

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## Requisitos previos

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## Grabación interactiva

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Crear nueva configuración

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### Paso 2: Ver configuraciones

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### Paso 3: Agregar una máquina

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### Paso 4: Ver máquinas

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### Paso 5: Establecer máquina predeterminada

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

Establece una máquina predeterminada para poder omitir `-m bridge-vm` en los comandos siguientes.

### Paso 6: Probar conectividad

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### Paso 7: Ejecutar diagnósticos

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### Paso 8: Configurar infraestructura

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

## Próximos pasos

- [Machine Setup](/es/docs/setup) — full reference for all config and setup commands
- [Quick Start](/es/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/es/docs/tutorial-repos) — create, deploy, and manage repositories
