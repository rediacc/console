---
title: "リポジトリのライフサイクル"
description: "暗号化されたリポジトリの作成、コンテナ化されたアプリのデプロイ、コンテナの検査、クリーンアップを一緒に見ていきましょう。"
category: "Tutorials"
order: 3
language: ja
sourceHash: "b692ef9f49ac4aa0"
---

# チュートリアル: リポジトリのライフサイクル

This tutorial walks through the full repository lifecycle: creating an encrypted repository, deploying a containerized application, inspecting running containers, stopping services, and cleaning up.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine (run `rdc config setup-machine` first — see [Machine Setup](/ja/docs/setup))
- A simple application with a `Rediaccfile` and `docker-compose.yml`

## インタラクティブ録画

![Tutorial: Repository lifecycle](/assets/tutorials/repos-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: 暗号化リポジトリを作成

```bash
rdc repo create test-app -m server-1 --size 2G
```

Creates a 2 GB LUKS-encrypted repository on the machine. The repository is automatically mounted and ready for file uploads.

### ステップ2: リポジトリを一覧表示

```bash
rdc repo list -m server-1
```

Shows all repositories on the machine with their size, mount status, and encryption state.

### ステップ3: アプリケーションファイルをアップロード

Upload your `Rediaccfile` and `docker-compose.yml` to the repository mount. The `rdc sync upload` command handles this via rsync:

```bash
rdc sync upload -m server-1 -r test-app --local ./my-app
```

### ステップ4: サービスを開始

```bash
rdc repo up test-app -m server-1 --mount
```

This mounts the repository (if not already mounted), starts an isolated Docker daemon, pulls images via `prep()`, and starts services via `up()`.

### ステップ5: 実行中のコンテナを表示

```bash
rdc machine containers server-1
```

マシン上のすべてのリポジトリにわたって実行中のすべてのコンテナを表示します。CPUとメモリの使用量も表示されます。

### ステップ6: ターミナル経由でリポジトリにアクセス

```bash
rdc term server-1 test-app -c "docker ps"
```

Opens an SSH session with `DOCKER_HOST` set to the repository's isolated Docker daemon. Any Docker command runs against that repo's containers.

### ステップ7: 停止してクリーンアップ

```bash
rdc repo down test-app -m server-1      # Stop services
rdc repo unmount test-app -m server-1   # Close encrypted volume
rdc repo delete test-app -m server-1    # Delete repository permanently
```

`down` stops containers and the Docker daemon. `unmount` closes the LUKS volume. `delete` permanently removes the repository and its encrypted storage.

## 次のステップ

- [Services](/ja/docs/services) — Rediaccfile reference, service networking, autostart, and multi-service layouts
- [Tutorial: Monitoring](/ja/docs/tutorial-monitoring) — health checks, container inspection, and diagnostics
- [Tools](/ja/docs/tools) — terminal, file sync, and VS Code integration
