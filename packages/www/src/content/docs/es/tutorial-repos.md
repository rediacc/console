---
title: "Ciclo de vida del repositorio"
description: "Observe y siga mientras creamos un repositorio cifrado, desplegamos una aplicación en contenedores, inspeccionamos contenedores y limpiamos."
category: "Tutorials"
order: 3
language: es
sourceHash: "b692ef9f49ac4aa0"
---

# Tutorial: Ciclo de vida del repositorio

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## Requisitos previos

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/es/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## Grabación interactiva

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Crear un repositorio cifrado

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### Paso 2: Listar repositorios

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### Paso 3: Subir archivos de la aplicación

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### Paso 4: Iniciar servicios

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### Paso 5: Ver contenedores en ejecución

```bash
rdc machine containers server-1
```

Muestra todos los contenedores en ejecución en todos los repositorios de la máquina, incluyendo el uso de CPU y memoria.

### Paso 6: Acceder al repositorio por terminal

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### Paso 7: Detener y limpiar

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## Próximos pasos

- [Services](/es/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/es/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/es/docs/tools) — terminal, file sync, and VS Code integration
