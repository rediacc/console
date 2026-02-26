---
title: "Sauvegarde et réseau"
description: "Regardez et suivez pendant que nous configurons les planifications de sauvegarde, les fournisseurs de stockage et l'infrastructure réseau."
category: "Tutorials"
order: 6
language: fr
sourceHash: "d611f5597b819085"
---

# Tutoriel : Sauvegarde et réseau

This tutorial covers backup scheduling, storage configuration, and infrastructure networking setup: the commands you use to protect data and expose services.

## Prérequis

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/fr/docs/tutorial-setup))

## Enregistrement interactif

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## Ce que vous verrez

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Étape 1 : Voir les stockages actuels

```bash
rdc config storages
```

Lists all configured storage providers (S3, B2, Google Drive, etc.) imported from rclone configs. Storages are used as backup destinations.

### Étape 2 : Configurer la planification de sauvegarde

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Sets an automated backup schedule: push all repositories to the `my-s3` storage every day at 2 AM. The schedule is stored in your config and can be deployed to machines as a systemd timer.

### Étape 3 : Voir la planification de sauvegarde

```bash
rdc backup schedule show
```

Shows the current backup schedule configuration: destination, cron expression, and enabled status.

### Étape 4 : Configurer l'infrastructure

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Configures the machine's public networking: its external IP, base domain for auto-routes, and email for Let's Encrypt TLS certificates.

### Étape 5 : Ajouter des ports TCP/UDP

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Registers additional TCP/UDP ports for the reverse proxy. These create Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that can be referenced in Docker labels.

### Étape 6 : Voir la configuration d'infrastructure

```bash
rdc config show-infra server-1
```

Displays the full infrastructure configuration for a machine: public IPs, domain, email, and registered ports.

### Étape 7 : Désactiver la planification de sauvegarde

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Disables the automated backup schedule. The configuration is preserved so it can be re-enabled later.

## Étapes suivantes

- [Backup & Restore](/fr/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/fr/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/fr/docs/tutorial-setup) — initial configuration and provisioning
