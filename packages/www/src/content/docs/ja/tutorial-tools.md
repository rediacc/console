---
title: "ツール"
description: "SSHターミナルアクセス、ファイル同期、VS Code統合、CLIアップデートコマンドを使用します。"
category: "Tutorials"
order: 5
language: ja
sourceHash: "f581499837e09360"
---

# Rediaccでターミナル、同期、VS Codeツールを使用する方法

CLIには日常業務のための生産性ツールが含まれています：SSHターミナルアクセス、rsyncによるファイル同期、VS Codeリモート開発、CLIアップデート。このチュートリアルでは、リモートコマンドの実行、リポジトリへのファイル同期、VS Code統合の確認、CLIバージョンの検証を行います。

## 前提条件

- 設定が初期化された`rdc` CLIがインストール済み
- 実行中のリポジトリを持つプロビジョニング済みマシン（[チュートリアル: リポジトリライフサイクル](/ja/docs/tutorial-repos)を参照）

## インタラクティブ録画

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### ステップ1: マシンに接続

インタラクティブセッションを開かずに、SSH経由でリモートマシンのインラインコマンドを実行します。

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

`-c`フラグは単一のコマンドを実行して出力を返します。`-c`を省略するとインタラクティブSSHセッションが開きます。

### ステップ2: リポジトリに接続

リポジトリの分離されたDocker環境内でコマンドを実行するには：

```bash
rdc term server-1 my-app -c "docker ps"
```

リポジトリに接続すると、`DOCKER_HOST`はリポジトリの分離されたDockerソケットに自動的に設定されます。すべてのDockerコマンドはそのリポジトリのコンテナに対してのみ実行されます。

### ステップ3: ファイル同期のプレビュー（ドライラン）

ファイルを転送する前に、何が変更されるかをプレビューします。

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

`--dry-run`フラグは、実際にアップロードせずに、新しいファイル、変更されたファイル、合計転送サイズを表示します。

### ステップ4: ファイルをアップロード

ローカルマシンからリモートリポジトリのマウントポイントにファイルを転送します。

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

ファイルはSSH経由のrsyncで転送されます。以降のアップロードでは変更されたファイルのみが送信されます。

### ステップ5: アップロードしたファイルを確認

リポジトリのマウントディレクトリを一覧表示してファイルが到着したことを確認します。

```bash
rdc term server-1 my-app -c "ls -la"
```

### ステップ6: VS Code統合の確認

VS Codeでリモート開発するために、必要なコンポーネントがインストールされているか確認します。

```bash
rdc vscode check
```

VS Codeのインストール、Remote SSH拡張機能、SSH設定を確認します。出力に従って不足している前提条件を解決し、`rdc vscode <machine> [repo]`で接続します。

### ステップ7: CLIアップデートを確認

```bash
rdc update --check-only
```

CLIの新しいバージョンが利用可能かどうかを報告します。アップデートをインストールするには、`--check-only`なしで`rdc update`を実行します。

## トラブルシューティング

**ファイル同期中の"rsync: command not found"**
ローカルマシンとリモートサーバーの両方にrsyncをインストールしてください。Debian/Ubuntuの場合：`sudo apt install rsync`。macOSの場合：rsyncはデフォルトで含まれています。

**同期アップロード中の"Permission denied"**
SSHユーザーがリポジトリのマウントディレクトリへの書き込みアクセス権を持っているか確認してください。リポジトリマウントはマシン登録時に指定されたユーザーが所有しています。

**"VS Code Remote SSH extension not found"**
VS Codeマーケットプレイスから拡張機能をインストールしてください：Microsoftの"Remote - SSH"を検索します。インストール後、VS Codeを再起動して`rdc vscode check`を再度実行してください。

## 次のステップ

リモートコマンドの実行、ファイルの同期、VS Code統合の確認、CLIアップデートの検証を行いました。データを保護するには：

- [Tools](/ja/docs/tools) — ターミナル、同期、VS Code、アップデートコマンドの完全なリファレンス
- [チュートリアル: バックアップとネットワーク](/ja/docs/tutorial-backup) — バックアップスケジュールとネットワーク設定
- [サービス](/ja/docs/services) — Rediaccfileリファレンスとサービスネットワーク
