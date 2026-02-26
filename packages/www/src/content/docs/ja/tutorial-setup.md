---
title: "マシンセットアップ"
description: "設定の作成、マシンの追加、接続テスト、診断の実行、インフラストラクチャの設定を一緒に見ていきましょう。"
category: "Tutorials"
order: 2
language: ja
sourceHash: "743a5b6abe79a1af"
---

# チュートリアル: マシンセットアップ

This tutorial walks through the complete setup workflow: creating a config, registering a remote machine, verifying SSH connectivity, running diagnostics, and configuring infrastructure settings.

## 前提条件

- The `rdc` CLI installed
- A remote server (or local VM) reachable via SSH
- An SSH private key that can authenticate to the server

## インタラクティブ録画

![Tutorial: Machine setup and configuration](/assets/tutorials/setup-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: 新しい設定を作成

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Creates a named config file at `~/.config/rediacc/tutorial-demo.json`. Each config stores machine definitions, SSH credentials, and infrastructure settings.

### ステップ2: 設定を表示

```bash
rdc config list
```

Lists all available configs with their adapter type (local or cloud) and machine count.

### ステップ3: マシンを追加

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

Registers a machine in the config. The CLI automatically runs `ssh-keyscan` to fetch and store the server's host keys.

### ステップ4: マシンを表示

```bash
rdc config machines --config tutorial-demo
```

Shows all machines in the current config with their connection details.

### ステップ5: デフォルトマシンを設定

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

デフォルトマシンを設定します。これにより、以降のコマンドで`-m bridge-vm`を省略できます。

### ステップ6: 接続をテスト

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Runs commands on the machine over SSH to verify connectivity is working.

### ステップ7: 診断を実行

```bash
rdc doctor
```

Checks your environment: CLI version, Docker, renet binary, config status, SSH key, and virtualization prerequisites.

### ステップ8: インフラストラクチャを設定

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

## 次のステップ

- [Machine Setup](/ja/docs/setup) — full reference for all config and setup commands
- [Quick Start](/ja/docs/quick-start) — deploy a containerized application end-to-end
- [Tutorial: Repository Lifecycle](/ja/docs/tutorial-repos) — create, deploy, and manage repositories
