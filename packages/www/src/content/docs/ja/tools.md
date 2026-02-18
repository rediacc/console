---
title: "ツール"
description: "ファイル同期、ターミナルアクセス、VS Code統合、アップデート、診断。"
category: "Guides"
order: 8
language: ja
---

# ツール

Rediaccには、リモートリポジトリで作業するための複数の生産性ツールが含まれています。これらのツールは、コンテキスト設定によって確立されたSSH接続の上に構築されています。

## ファイル同期（sync）

rsyncをSSH経由で使用して、ワークステーションとリモートリポジトリ間でファイルを転送します。

### ファイルのアップロード

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### ファイルのダウンロード

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### オプション

| オプション | 説明 |
|--------|-------------|
| `-m, --machine <name>` | ターゲットマシン |
| `--local <path>` | ローカルディレクトリパス |
| `--remote <path>` | リモートパス（リポジトリのマウントポイントからの相対パス） |
| `--dry-run` | 転送せずに変更をプレビュー |
| `--delete` | ソースに存在しない宛先のファイルを削除 |

`--dry-run`フラグは、同期を実行する前に転送される内容をプレビューするのに便利です。

## SSHターミナル（term）

マシンまたはリポジトリのマウントパスに直接、対話型SSHセッションを開きます。

### マシンへの接続

```bash
rdc term connect server-1
```

### リポジトリへの接続

```bash
rdc term connect my-app -m server-1
```

リポジトリに接続すると、ターミナルセッションはリポジトリのマウントディレクトリで開始され、リポジトリのDockerソケットが設定されます。

## VS Code統合（vscode）

正しいSSH設定とRemote SSH拡張機能で事前設定された、VS CodeでのリモートSSHセッションを開きます。

### リポジトリへの接続

```bash
rdc vscode connect my-app -m server-1
```

このコマンドは以下を実行します：
1. VS Codeのインストールを検出
2. `~/.ssh/config`にSSH接続を設定
3. セッション用のSSH鍵を永続化
4. リポジトリパスへのRemote SSH接続でVS Codeを起動

### 設定済み接続の一覧表示

```bash
rdc vscode list
```

VS Code用に設定されたすべてのSSH接続を表示します。

### 接続のクリーンアップ

```bash
rdc vscode clean
```

不要になったVS CodeのSSH設定を削除します。

> **前提条件：** VS Codeに[Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)拡張機能をインストールしてください。

## CLIアップデート（update）

`rdc` CLIを最新の機能とバグ修正で最新の状態に保ちます。

### アップデートの確認

```bash
rdc update --check-only
```

### アップデートの適用

```bash
rdc update
```

アップデートはダウンロードされ、その場で適用されます。新しいバージョンは次回実行時に有効になります。

### ロールバック

```bash
rdc update rollback
```

以前にインストールされたバージョンに戻します。アップデートが適用された後にのみ使用可能です。

### 自動アップデートステータス

```bash
rdc update status
```

現在のバージョン、アップデートチャンネル、自動アップデート設定を表示します。

## システム診断（doctor）

Rediacc環境の包括的な診断チェックを実行します。

```bash
rdc doctor
```

doctorコマンドは以下を確認します：

| カテゴリ | チェック項目 |
|----------|--------|
| **環境** | Node.jsバージョン、CLIバージョン、SEAモード |
| **Renet** | バイナリの存在、バージョン、組み込みCRIUとrsync |
| **設定** | アクティブなコンテキスト、モード、マシン、SSH鍵 |
| **認証** | ログインステータス |

各チェックは**OK**、**警告**、または**エラー**を簡単な説明とともに報告します。問題のトラブルシューティングの最初のステップとしてこのコマンドを使用してください。
