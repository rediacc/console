---
title: "監視と診断"
description: "マシンの状態確認、コンテナの検査、サービスの確認、診断の実行を一緒に見ていきましょう。"
category: "Tutorials"
order: 4
language: ja
sourceHash: "e121e29d9a6359bc"
---

# チュートリアル: 監視と診断

This tutorial demonstrates the monitoring and diagnostic commands available in `rdc`: health checks, container inspection, service status, vault overview, and environment diagnostics.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine with at least one running repository (see [Tutorial: Repository Lifecycle](/ja/docs/tutorial-repos))

## インタラクティブ録画

![Tutorial: Monitoring & Diagnostics](/assets/tutorials/monitoring-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: 診断を実行

```bash
rdc doctor
```

Checks your local environment: Node.js, CLI version, renet binary, configuration, and virtualization support. Each check reports **OK**, **Warning**, or **Error**.

### ステップ2: マシンヘルスチェック

```bash
rdc machine health server-1
```

システム稼働時間、ディスク使用量、データストア使用量、コンテナ数、ストレージSMARTステータス、特定された問題を含む包括的なヘルスレポートを取得します。

### ステップ3: 実行中のコンテナを表示

```bash
rdc machine containers server-1
```

Lists all running containers across all repositories on the machine, showing name, status, state, health, CPU usage, memory usage, and which repository owns each container.

### ステップ4: systemdサービスを確認

```bash
rdc machine services server-1
```

Lists Rediacc-related systemd services (Docker daemons, loopback aliases) with their state, sub-state, restart count, and memory usage.

### ステップ5: Vaultステータスの概要

```bash
rdc machine vault-status server-1
```

Provides a high-level overview of the machine: hostname, uptime, memory, disk, datastore, and total repository counts.

### ステップ6: ホストキーをスキャン

```bash
rdc config scan-keys server-1
```

Refreshes the SSH host key stored in your config for the machine. Useful after a machine rebuild or IP change.

### ステップ7: 接続を確認

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Quick SSH connectivity check by running inline commands on the remote machine.

## 次のステップ

- [Monitoring](/ja/docs/monitoring) — full reference for all monitoring commands
- [Troubleshooting](/ja/docs/troubleshooting) — common issues and solutions
- [Tutorial: Tools](/ja/docs/tutorial-tools) — terminal, file sync, and VS Code integration
