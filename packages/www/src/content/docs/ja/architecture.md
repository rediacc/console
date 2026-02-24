---
title: アーキテクチャ
description: Rediaccの仕組み：2ツールアーキテクチャ、アダプター検出、セキュリティモデル、設定構造。
category: Concepts
order: 0
language: ja
sourceHash: 5a717ddac450cb81
---

# アーキテクチャ

このページでは、Rediaccの内部の仕組みについて説明します：2ツールアーキテクチャ、アダプター検出、セキュリティモデル、設定構造。

## Full Stack Overview

Traffic flows from the internet through a reverse proxy, into isolated Docker daemons, each backed by encrypted storage:

![Full Stack Architecture](/img/arch-full-stack.svg)

Each repository gets its own Docker daemon, loopback IP subnet (/26 = 64 IPs), and LUKS-encrypted BTRFS volume. The route server discovers running containers across all daemons and feeds routing configuration to Traefik.

## 2ツールアーキテクチャ

RediaccはSSH経由で連携する2つのバイナリを使用します：

![2ツールアーキテクチャ](/img/arch-two-tool.svg)

- **rdc** はワークステーション（macOS、Linux、またはWindows）上で動作します。ローカル設定を読み取り、SSH経由でリモートマシンに接続し、renetコマンドを呼び出します。
- **renet** はリモートサーバー上でroot権限で動作します。LUKS暗号化ディスクイメージ、隔離されたDockerデーモン、サービスオーケストレーション、リバースプロキシ設定を管理します。

ローカルで入力するすべてのコマンドは、リモートマシン上でrenetを実行するSSH呼び出しに変換されます。手動でサーバーにSSHする必要はありません。

オペレーター向けの実用的なルールについては、[rdc vs renet](/ja/docs/rdc-vs-renet) を参照してください。また、`rdc ops` を使用してテスト用のローカルVMクラスターを実行することもできます — [実験的VM](/ja/docs/experimental-vms) を参照してください。

## Config & Stores

すべてのCLI状態は `~/.config/rediacc/` 配下のフラットなJSON設定ファイルに保存されます。Storeを使用することで、バックアップ、共有、マルチデバイスアクセスのために外部バックエンドにこれらの設定を同期できます。Storeの認証情報は `~/.config/rediacc/.credentials.json` に別途保管されます。

![Config & Stores](/img/arch-operating-modes.svg)

### ローカルアダプター（デフォルト）

セルフホスト利用のデフォルトです。すべての状態はワークステーションの設定ファイル（例：`~/.config/rediacc/rediacc.json`）に保存されます。

- マシンへの直接SSH接続
- 外部サービス不要
- シングルユーザー、シングルワークステーション
- デフォルト設定はCLI初回使用時に自動作成。名前付き設定は `rdc config init <name>` で作成

### クラウドアダプター（実験的）

設定に `apiUrl` と `token` フィールドが含まれている場合に自動的に有効になります。状態管理とチームコラボレーションにRediacc APIを使用します。

- 状態はクラウドAPIに保存
- ロールベースアクセス制御によるマルチユーザーチーム
- ビジュアル管理用Webコンソール
- `rdc auth login` でセットアップ

> **注意：** クラウドアダプターのコマンドは実験的です。`rdc --experimental <command>`または`REDIACC_EXPERIMENTAL=1`を設定して有効にしてください。

### S3リソース状態（オプション）

設定にS3設定（エンドポイント、バケット、アクセスキー）が含まれている場合、リソース状態はS3互換バケットに保存されます。ローカルアダプターと組み合わせて使用することで、セルフホストの運用とワークステーション間の移植性を兼ね備えます。

- リソース状態はS3/R2バケットに`state.json`として保存
- マスターパスワードによるAES-256-GCM暗号化
- ポータブル：バケット資格情報を持つ任意のワークステーションからインフラストラクチャを管理可能
- `rdc config init <name> --s3-endpoint <url> --s3-bucket <bucket> --s3-access-key-id <key>` で設定

すべてのアダプターで同じCLIコマンドを使用します。アダプターは状態の保存場所と認証方法にのみ影響します。

## rediaccユーザー

`rdc config setup-machine`を実行すると、renetはリモートサーバー上に`rediacc`というシステムユーザーを作成します：

- **UID**: 7111
- **シェル**: `/sbin/nologin`（SSH経由でログイン不可）
- **目的**: リポジトリファイルを所有し、Rediaccfile関数を実行

`rediacc`ユーザーはSSH経由で直接アクセスできません。代わりに、rdcは設定したSSHユーザー（例：`deploy`）として接続し、renetは`sudo -u rediacc /bin/sh -c '...'`経由でリポジトリ操作を実行します。これは以下を意味します：

1. SSHユーザーに`sudo`権限が必要
2. すべてのリポジトリデータは、SSHユーザーではなく`rediacc`が所有
3. Rediaccfile関数（`prep()`、`up()`、`down()`）は`rediacc`として実行

この分離により、どのSSHユーザーが管理しても、リポジトリデータの所有権が一貫して維持されます。

## Dockerの隔離

各リポジトリは独自の隔離されたDockerデーモンを取得します。リポジトリがマウントされると、renetは固有のソケットを持つ専用の`dockerd`プロセスを起動します：

![Dockerの隔離](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

例えば、ネットワークID `2816`のリポジトリは以下を使用します：
```
/var/run/rediacc/docker-2816.sock
```

これは以下を意味します：
- 異なるリポジトリのコンテナは互いに見えない
- 各リポジトリは独自のイメージキャッシュ、ネットワーク、ボリュームを持つ
- ホストのDockerデーモン（存在する場合）は完全に分離されている

Rediaccfile関数では、`DOCKER_HOST`が自動的に正しいソケットに設定されます。

## LUKS暗号化

リポジトリは、サーバーのデータストア（デフォルト：`/mnt/rediacc`）に保存されるLUKS暗号化ディスクイメージです。各リポジトリは：

1. ランダムに生成された暗号化パスフレーズ（「クレデンシャル」）を持つ
2. ファイルとして保存される：`{datastore}/repos/{guid}.img`
3. アクセス時に`cryptsetup`経由でマウントされる

クレデンシャルは設定ファイルに保存されますが、サーバーには**保存されません**。クレデンシャルがなければ、リポジトリデータを読み取ることはできません。自動開始が有効な場合、起動時の自動マウントを可能にするために、サーバー上にセカンダリLUKSキーファイルが保存されます。

## 設定構造

各設定は `~/.config/rediacc/` に保存されるフラットなJSONファイルです。デフォルト設定は `rediacc.json`; 名前付き設定はファイル名として名前を使用します（例：`production.json`）。以下は注釈付きの例です：

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 1,
  "ssh": {
    "privateKeyPath": "/home/you/.ssh/id_ed25519"
  },
  "machines": {
    "prod-1": {
      "ip": "203.0.113.50",
      "user": "deploy",
      "port": 22,
      "datastore": "/mnt/rediacc",
      "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
    }
  },
  "storages": {
    "backblaze": {
      "provider": "b2",
      "vaultContent": { "...": "..." }
    }
  },
  "repositories": {
    "webapp": {
      "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "credential": "base64-encoded-random-passphrase",
      "networkId": 2816
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**主要なフィールド：**

| フィールド | 説明 |
|-------|-------------|
| `id` | この設定ファイルの一意識別子 |
| `version` | 設定ファイルのスキーマバージョン |
| `ssh.privateKeyPath` | すべてのマシン接続に使用されるSSH秘密鍵のパス |
| `machines.<name>.user` | マシンへの接続に使用されるSSHユーザー名 |
| `machines.<name>.knownHosts` | `ssh-keyscan`からのSSHホスト鍵 |
| `repositories.<name>.repositoryGuid` | 暗号化ディスクイメージを識別するUUID |
| `repositories.<name>.credential` | LUKS暗号化パスフレーズ（**サーバーには保存されません**） |
| `repositories.<name>.networkId` | IPサブネットを決定するネットワークID（2816 + n*64）。自動割り当て |
| `nextNetworkId` | ネットワークID割り当て用のグローバルカウンター |
| `universalUser` | デフォルトのシステムユーザー（`rediacc`）のオーバーライド |

> このファイルには機密データ（SSH鍵パス、LUKSクレデンシャル）が含まれています。`0600`パーミッション（所有者のみ読み書き可能）で保存されます。共有したり、バージョン管理にコミットしないでください。
