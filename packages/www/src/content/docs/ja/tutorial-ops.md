---
title: "ローカルVM プロビジョニング"
description: "ローカルVMクラスターのプロビジョニング、SSH経由でのコマンド実行、クリーンアップを一緒に見ていきましょう。"
category: "Tutorials"
order: 1
language: ja
sourceHash: "990c6fd433c7c847"
---

# チュートリアル: ローカルVMプロビジョニング

This tutorial walks through the complete `rdc ops` workflow: checking system requirements, provisioning a minimal VM cluster, running commands on VMs over SSH, and tearing everything down.

## 前提条件

- A Linux or macOS workstation with hardware virtualization enabled
- The `rdc` CLI installed and a config initialized with the local adapter
- KVM/libvirt (Linux) or QEMU (macOS) installed — see [Experimental VMs](/ja/docs/experimental-vms) for setup instructions

## インタラクティブ録画

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: システム要件の確認

```bash
rdc ops check
```

ハードウェア仮想化のサポート、必要なパッケージ（libvirt、QEMU）、ネットワーク構成を確認します。VMをプロビジョニングする前に、これが成功する必要があります。

### ステップ2: 最小構成のVMクラスターをプロビジョニング

```bash
rdc ops up --basic --skip-orchestration
```

Creates a two-VM cluster: a **bridge** VM (1 CPU, 1024 MB RAM, 8 GB disk) and a **worker** VM (2 CPU, 4096 MB RAM, 16 GB disk). The `--skip-orchestration` flag skips Rediacc platform provisioning, giving you bare VMs with SSH access only.

### ステップ3: クラスターステータスの確認

```bash
rdc ops status
```

Shows the state of each VM in the cluster — IP addresses, resource allocation, and running status.

### ステップ4: VM上でコマンドを実行

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

ブリッジVM（ID `1`）上でSSH経由でコマンドを実行します。VM IDの後に任意のコマンドを渡せます。対話的なシェルの場合は、コマンドを省略します：`rdc ops ssh 1`。

### ステップ5: クラスターの破棄

```bash
rdc ops down
```

Destroys all VMs and cleans up resources. The cluster can be reprovisioned at any time with `rdc ops up`.

## 次のステップ

- [Experimental VMs](/ja/docs/experimental-vms) — full reference for `rdc ops` commands, VM configuration, and platform support
- [Machine Setup](/ja/docs/setup) — add remote machines to your config and provision them
- [Quick Start](/ja/docs/quick-start) — deploy a containerized service end-to-end
