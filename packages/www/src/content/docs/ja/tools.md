---
title: "ツール"
description: "ファイル同期、ターミナルアクセス、VS Code統合、CLIアップデート。"
category: Guides
order: 9
language: ja
sourceHash: "4b3aebff5e82416f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# ツール

Rediaccは、マシンとリポジトリの日々の作業向けに4つのツールを備えています：SSH経由のファイル同期、SSHターミナル、VS Code統合、CLIの自己更新。これら4つはすべてSSH経由で動作し、リモート側にエージェントやデーモンは必要ありません。これらの操作用GUIが必要な場合は、このページは対象外です。

## ファイル同期 (sync)

SSH経由のrsyncを使用して、ワークステーションとリモートリポジトリ間でファイルを転送します。

### ファイルのアップロード

`--local`は1つまたは複数のパスを受け入れます。各パスはファイルまたはディレクトリです。ファイルは`<remote>/<basename>`に配置され、ディレクトリの内容は`<remote>/`にマージされます。単一のファイルの場合、`--remote-file`を使用してファイルの宛先パスを明示的に指定することをお勧めします。

```bash
# ディレクトリ（内容がリモートにマージされます）
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# 単一ファイルをリモートディレクトリに配置（ベース名は保持される）
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# 単一ファイル、明示的な宛先パス
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# 1つのコマンドで複数のソース
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote`と`--remote-file`は相互排他的です。`--remote-file`は、ファイルを指すちょうど1つの`--local`パスが必要です。

`--mirror`はファイルソースと組み合わせることはできません。リモートディレクトリ内の関連ファイルが削除されてしまいます。

### ファイルのダウンロード

ディレクトリの場合は`--remote`（デフォルト）を、単一ファイルの場合は`--remote-file`を使用します。この2つのフラグは相互排他的です。

```bash
# ディレクトリ
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# 単一ファイル：--localは既存のディレクトリである必要があります
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### 同期ステータスの確認

```bash
rdc repo sync status -m server-1 -r my-app
```

### オプション

| オプション | 説明 |
|--------|-------------|
| `-m, --machine <name>` | 対象マシン |
| `-r, --repository <name>` | 対象リポジトリ |
| `--local <paths...>` | 1つ以上のローカルファイル/ディレクトリパス（アップロード）またはローカル出力ディレクトリ（ダウンロード） |
| `--remote <path>` | リモートディレクトリ（リポジトリマウントからの相対パス） |
| `--remote-file <path>` | 単一ファイルアップロード/ダウンロード用リモートファイルパス（`--remote`の代替） |
| `--dry-run` | 転送せずに変更をプレビュー |
| `--mirror` | ソースをデスティネーションにミラーリング、余分なファイルを削除（ディレクトリソースのみ） |
| `--verify` | 転送後にチェックサムを検証 |
| `--confirm` | 詳細ビューによるインタラクティブな確認 |
| `--exclude <patterns...>` | ファイルパターンを除外 |
| `--skip-router-restart` | 操作後のルートサーバーの再起動をスキップ |

## SSHターミナル (term)

マシンまたはリポジトリ環境へのインタラクティブなSSHセッションを開きます。

### 省略構文

最も手軽な接続方法：

```bash
rdc term connect -m server-1                    # マシンに接続
rdc term connect -m server-1 -r my-app             # リポジトリに接続
```

### コマンドの実行

インタラクティブセッションを開かずにコマンドを実行します：

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

リポジトリに接続する際、`DOCKER_HOST`はリポジトリの分離されたDockerソケットに自動的に設定されるため、`docker ps`はそのリポジトリのコンテナのみを表示します。

### connect サブコマンド

`connect`サブコマンドは、明示的なフラグを使用して同じ操作を行います：

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### コンテナ操作

実行中のコンテナと直接やり取りします：

```bash
# コンテナ内でシェルを開く
rdc term connect -m server-1 -r my-app --container <container-id>

# コンテナログを表示
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# リアルタイムでログを追跡
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# コンテナの統計情報を表示
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# コンテナ内でコマンドを実行
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| オプション | 説明 |
|--------|-------------|
| `--container <id>` | 対象のDockerコンテナID |
| `--container-action <action>` | アクション：`terminal`（デフォルト）、`logs`、`stats`、`exec` |
| `--log-lines <n>` | 表示するログの行数（デフォルト：50） |
| `--follow` | ログを継続的に追跡 |
| `--external` | インラインSSHの代わりに外部ターミナルを使用 |

## VS Code統合 (vscode)

正しいSSH設定が事前構成された状態で、VS CodeでリモートSSHセッションを開きます。

### リポジトリへの接続

```bash
rdc vscode connect -r my-app -m server-1
```

このコマンドは以下を実行します：
1. VS Codeのインストールを検出
2. `~/.ssh/config`でSSH接続を設定
3. セッション用にSSHキーを保持
4. リポジトリパスへのRemote SSH接続でVS Codeを起動

### 設定済み接続の一覧表示

```bash
rdc vscode list
```

### 接続のクリーンアップ

```bash
rdc vscode cleanup
```

不要になったVS CodeのSSH設定を削除します。

### 設定の確認

```bash
rdc vscode check
```

VS Codeのインストール状況、Remote SSH拡張機能、およびアクティブな接続を検証します。

> **前提条件：** VS Codeに[Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)拡張機能をインストールしてください。

## CLIアップデート (update)

`rdc` CLIを最新の状態に保ちます。

### アップデートの確認

```bash
rdc update --check-only
```

### アップデートの適用

```bash
rdc update
```

アップデートはダウンロードされ、その場で適用されます。CLIはお使いのプラットフォーム（Linux、macOS、またはWindows）に適したバイナリを自動的に選択します。新しいバージョンは次回の実行時に有効になります。

### ロールバック

```bash
rdc update --rollback
```

以前にインストールされたバージョンに戻します。アップデートが適用された後にのみ利用可能です。

### アップデートステータス

```bash
rdc update --status
```

現在のバージョン、アップデートチャンネル、および自動アップデートの設定を表示します。

#### リリースチャンネル

```bash
rdc update --channel edge      # 継続的にデプロイされる本番環境アップデート
rdc update --channel stable    # エッジから7日間のテスト後にプロモート（デフォルト）
rdc update --status            # 現在のチャンネルとバージョン情報を表示
```
