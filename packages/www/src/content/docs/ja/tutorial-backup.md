---
title: "バックアップとネットワーク"
description: "バックアップスケジュール、ストレージプロバイダー、ネットワークインフラストラクチャの設定を一緒に見ていきましょう。"
category: "Tutorials"
order: 6
language: ja
sourceHash: "d611f5597b819085"
---

# チュートリアル: バックアップとネットワーク

This tutorial covers backup scheduling, storage configuration, and infrastructure networking setup: the commands you use to protect data and expose services.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/ja/docs/tutorial-setup))

## インタラクティブ録画

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: 現在のストレージを表示

```bash
rdc config storages
```

Lists all configured storage providers (S3, B2, Google Drive, etc.) imported from rclone configs. Storages are used as backup destinations.

### ステップ2: バックアップスケジュールを設定

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

Sets an automated backup schedule: push all repositories to the `my-s3` storage every day at 2 AM. The schedule is stored in your config and can be deployed to machines as a systemd timer.

### ステップ3: バックアップスケジュールを表示

```bash
rdc backup schedule show
```

Shows the current backup schedule configuration: destination, cron expression, and enabled status.

### ステップ4: インフラストラクチャを設定

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Configures the machine's public networking: its external IP, base domain for auto-routes, and email for Let's Encrypt TLS certificates.

### ステップ5: TCP/UDPポートを追加

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Registers additional TCP/UDP ports for the reverse proxy. These create Traefik entrypoints (`tcp-25`, `udp-53`, etc.) that can be referenced in Docker labels.

### ステップ6: インフラストラクチャ設定を表示

```bash
rdc config show-infra server-1
```

Displays the full infrastructure configuration for a machine: public IPs, domain, email, and registered ports.

### ステップ7: バックアップスケジュールを無効化

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

Disables the automated backup schedule. The configuration is preserved so it can be re-enabled later.

## 次のステップ

- [Backup & Restore](/ja/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/ja/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/ja/docs/tutorial-setup) — initial configuration and provisioning
