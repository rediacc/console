---
title: "ツール"
description: "ターミナル、ファイル同期、VS Code統合、CLIアップデートコマンドの使用方法を一緒に見ていきましょう。"
category: "Tutorials"
order: 5
language: ja
sourceHash: "6cf8e14712148f7f"
---

# チュートリアル: ツール

This tutorial demonstrates the productivity tools built into `rdc`: SSH terminal access, file synchronization, VS Code integration, and CLI updates.

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine with a running repository (see [Tutorial: Repository Lifecycle](/ja/docs/tutorial-repos))

## インタラクティブ録画

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

## 内容の説明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### ステップ1: マシンに接続

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Run inline commands on a remote machine via SSH. The `-c` flag executes a single command and returns the output without opening an interactive session.

### ステップ2: リポジトリに接続

```bash
rdc term server-1 my-app -c "docker ps"
```

When connecting to a repository, `DOCKER_HOST` is automatically set to the repository's isolated Docker socket. Any Docker command runs against that repository's containers only.

### ステップ3: ファイル同期のプレビュー（ドライラン）

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

The `--dry-run` flag previews what would be transferred without actually uploading files. Shows new files, changed files, and total transfer size.

### ステップ4: ファイルをアップロード

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Transfers files from your local machine to the remote repository mount via rsync over SSH.

### ステップ5: アップロードしたファイルを確認

```bash
rdc term server-1 my-app -c "ls -la"
```

Confirm the files arrived by listing the repository's mount directory.

### ステップ6: VS Code統合の確認

```bash
rdc vscode check
```

Verifies your VS Code installation, Remote SSH extension, and SSH configuration for remote development. Shows which settings need to be configured.

### ステップ7: CLIアップデートを確認

```bash
rdc update --check-only
```

Checks if a newer version of the `rdc` CLI is available without applying it. Use `rdc update` (without `--check-only`) to install the update.

## 次のステップ

- [Tools](/ja/docs/tools) — full reference for terminal, sync, VS Code, and update commands
- [Tutorial: Backup & Restore](/ja/docs/tutorial-backup) — backup, restore, and scheduled sync
- [Services](/ja/docs/services) — Rediaccfile reference and service networking
