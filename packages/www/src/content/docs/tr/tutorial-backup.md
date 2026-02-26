---
title: "Yedekleme ve Ağ"
description: "Yedekleme zamanlamalarını, depolama sağlayıcılarını ve ağ altyapısını yapılandırırken izleyin ve takip edin."
category: "Tutorials"
order: 6
language: tr
sourceHash: "d611f5597b819085"
---

# Öğretici: Yedekleme ve Ağ

This tutorial covers backup scheduling, storage configuration, and infrastructure networking setup: the commands you use to protect data and expose services.

## Ön Koşullar

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/tr/docs/tutorial-setup))

## Etkileşimli Kayıt

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## Neler Göreceksiniz

The recording above walks through each step below. Use the playback bar to navigate between commands.

### Adım 1: Mevcut depolamaları görüntüleyin

```bash
rdc config storages
```

Lists all configured storage providers (S3, B2, Google Drive, etc.) imported from rclone configs. Storages are used as backup destinations.

### Adım 2: Yedekleme zamanlamasını yapılandırın

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Sets an automated backup schedule: push all repositories to the `my-s3` storage every day at 2 AM. The schedule is stored in your config and can be deployed to machines as a systemd timer.

### Adım 3: Yedekleme zamanlamasını görüntüleyin

```bash
rdc backup schedule show
```

Shows the current backup schedule configuration: destination, cron expression, and enabled status.

### Adım 4: Altyapıyı yapılandırın

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Configures the machine's public networking: its external IP, base domain for auto-routes, and email for Let's Encrypt TLS certificates.

### Adım 5: TCP/UDP portları ekleyin

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Registers additional TCP/UDP ports for the reverse proxy. These create Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that can be referenced in Docker labels.

### Adım 6: Altyapı yapılandırmasını görüntüleyin

```bash
rdc config show-infra server-1
```

Displays the full infrastructure configuration for a machine: public IPs, domain, email, and registered ports.

### Adım 7: Yedekleme zamanlamasını devre dışı bırakın

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Disables the automated backup schedule. The configuration is preserved so it can be re-enabled later.

## Sonraki Adımlar

- [Backup & Restore](/tr/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/tr/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/tr/docs/tutorial-setup) — initial configuration and provisioning
