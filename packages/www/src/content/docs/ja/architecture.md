---
title: アーキテクチャ
description: Rediaccの仕組み：2ツールアーキテクチャ、動作モード、セキュリティモデル、設定構造。
category: Guides
order: 2
language: ja
sourceHash: 8f910f7827c8e958
---

# アーキテクチャ

どのツールを使うべきか迷う場合は、[rdc vs renet](/ja/docs/rdc-vs-renet) を参照してください。

このページでは、Rediaccの内部の仕組みについて説明します：2ツールアーキテクチャ、動作モード、セキュリティモデル、設定構造。

## 2ツールアーキテクチャ

RediaccはSSH経由で連携する2つのバイナリを使用します：

![2ツールアーキテクチャ](/img/arch-two-tool.svg)

- **rdc** はワークステーション（macOS、Linux、またはWindows）上で動作します。ローカル設定を読み取り、SSH経由でリモートマシンに接続し、renetコマンドを呼び出します。
- **renet** はリモートサーバー上でroot権限で動作します。LUKS暗号化ディスクイメージ、隔離されたDockerデーモン、サービスオーケストレーション、リバースプロキシ設定を管理します。

ローカルで入力するすべてのコマンドは、リモートマシン上でrenetを実行するSSH呼び出しに変換されます。手動でサーバーにSSHする必要はありません。

## 動作モード

Rediaccは3つのモードをサポートしており、それぞれ状態の保存場所とコマンドの実行方法が異なります。

![動作モード](/img/arch-operating-modes.svg)

### ローカルモード

セルフホスト利用のデフォルトモードです。すべての状態はワークステーションの`~/.rediacc/config.json`に保存されます。

- マシンへの直接SSH接続
- 外部サービス不要
- シングルユーザー、シングルワークステーション
- コンテキストは`rdc context create-local`で作成

### クラウドモード（実験的）

Rediacc APIを使用して状態管理とチームコラボレーションを行います。

- 状態はクラウドAPIに保存
- ロールベースアクセス制御によるマルチユーザーチーム
- ビジュアル管理用Webコンソール
- コンテキストは`rdc context create`で作成

> **注意：** クラウドモードのコマンドは実験的です。`rdc --experimental <command>`または`REDIACC_EXPERIMENTAL=1`を設定して有効にしてください。

### S3モード

暗号化された状態をS3互換バケットに保存します。ローカルモードのセルフホストの性質と、ワークステーション間の移植性を兼ね備えています。

- 状態はS3/R2バケットに`state.json`として保存
- マスターパスワードによるAES-256-GCM暗号化
- ポータブル：バケット資格情報を持つ任意のワークステーションからインフラストラクチャを管理可能
- コンテキストは`rdc context create-s3`で作成

3つのモードすべてで同じCLIコマンドを使用します。モードは状態の保存場所と認証方法にのみ影響します。

## rediaccユーザー

`rdc context setup-machine`を実行すると、renetはリモートサーバー上に`rediacc`というシステムユーザーを作成します：

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

クレデンシャルはローカルの`config.json`に保存されますが、サーバーには**保存されません**。クレデンシャルがなければ、リポジトリデータを読み取ることはできません。自動開始が有効な場合、起動時の自動マウントを可能にするために、サーバー上にセカンダリLUKSキーファイルが保存されます。

## 設定構造

すべての設定は`~/.rediacc/config.json`に保存されます。以下は注釈付きの例です：

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
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
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**主要なフィールド：**

| フィールド | 説明 |
|-------|-------------|
| `mode` | ローカルモードは`"local"`、S3モードは`"s3"`、クラウドモードは省略 |
| `apiUrl` | ローカルモードは`"local://"`、クラウドモードはAPI URL |
| `ssh.privateKeyPath` | すべてのマシン接続に使用されるSSH秘密鍵のパス |
| `machines.<name>.user` | マシンへの接続に使用されるSSHユーザー名 |
| `machines.<name>.knownHosts` | `ssh-keyscan`からのSSHホスト鍵。サーバーIDの検証に使用 |
| `repositories.<name>.repositoryGuid` | サーバー上の暗号化ディスクイメージを識別するUUID |
| `repositories.<name>.credential` | LUKS暗号化パスフレーズ（**サーバーには保存されません**） |
| `repositories.<name>.networkId` | IPサブネットを決定するネットワークID（2816 + n*64）。自動割り当て |
| `nextNetworkId` | ネットワークID割り当て用のグローバルカウンター |
| `universalUser` | デフォルトのシステムユーザー（`rediacc`）のオーバーライド |

> このファイルには機密データ（SSH鍵パス、LUKSクレデンシャル）が含まれています。`0600`パーミッション（所有者のみ読み書き可能）で保存されます。共有したり、バージョン管理にコミットしないでください。
