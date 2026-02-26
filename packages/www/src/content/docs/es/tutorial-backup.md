---
title: "Copia de seguridad y conexión de red"
description: "Observe y siga mientras configuramos programaciones de copias de seguridad, proveedores de almacenamiento e infraestructura de red."
category: "Tutorials"
order: 6
language: es
sourceHash: "d611f5597b819085"
---

# Tutorial: Copia de seguridad y redes

This tutorial covers backup scheduling, storage configuration, and infrastructure networking setup: the commands you use to protect data and expose services.

## Requisitos previos

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/es/docs/tutorial-setup))

## Grabación interactiva

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## Lo que verá

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Paso 1: Ver almacenamientos actuales

```bash
rdc config storages
```

Lists all configured storage providers (S3, B2, Google Drive, etc.) imported from rclone configs. Storages are used as backup destinations.

### Paso 2: Configurar programación de copias

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Sets an automated backup schedule: push all repositories to the `my-s3` storage every day at 2 AM. The schedule is stored in your config and can be deployed to machines as a systemd timer.

### Paso 3: Ver programación de copias

```bash
rdc backup schedule show
```

Shows the current backup schedule configuration: destination, cron expression, and enabled status.

### Paso 4: Configurar infraestructura

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Configures the machine's public networking: its external IP, base domain for auto-routes, and email for Let's Encrypt TLS certificates.

### Paso 5: Agregar puertos TCP/UDP

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Registers additional TCP/UDP ports for the reverse proxy. These create Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that can be referenced in Docker labels.

### Paso 6: Ver configuración de infraestructura

```bash
rdc config show-infra server-1
```

Displays the full infrastructure configuration for a machine: public IPs, domain, email, and registered ports.

### Paso 7: Desactivar programación de copias

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Disables the automated backup schedule. The configuration is preserved so it can be re-enabled later.

## Próximos pasos

- [Backup & Restore](/es/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/es/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/es/docs/tutorial-setup) — initial configuration and provisioning
