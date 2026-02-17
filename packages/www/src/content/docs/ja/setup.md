---
title: "マシンセットアップ"
description: "コンテキストの作成、マシンの追加、サーバーのプロビジョニング、インフラストラクチャの設定。"
category: "Guides"
order: 3
language: ja
---

# マシンセットアップ

このページでは、最初のマシンのセットアップ手順を説明します：コンテキストの作成、サーバーの登録、プロビジョニング、およびオプションでパブリックアクセス用のインフラストラクチャ設定。

## ステップ1：ローカルコンテキストの作成

**コンテキスト**は、SSH資格情報、マシン定義、リポジトリマッピングを保存する名前付きの設定です。プロジェクトワークスペースと考えてください。

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `--ssh-key <path>` | はい | SSH秘密鍵へのパス。チルダ（`~`）は自動的に展開されます。 |
| `--renet-path <path>` | いいえ | リモートマシン上のrenetバイナリへのカスタムパス。デフォルトは標準インストール場所です。 |

これにより`my-infra`という名前のローカルコンテキストが作成され、`~/.rediacc/config.json`に保存されます。

> 複数のコンテキストを持つことができます（例：`production`、`staging`、`dev`）。任意のコマンドで`--context`フラグを使用して切り替えることができます。

## ステップ2：マシンの追加

リモートサーバーをコンテキスト内のマシンとして登録します：

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `--ip <address>` | はい | - | リモートサーバーのIPアドレスまたはホスト名 |
| `--user <username>` | はい | - | リモートサーバーのSSHユーザー名 |
| `--port <port>` | いいえ | `22` | SSHポート |
| `--datastore <path>` | いいえ | `/mnt/rediacc` | Rediaccが暗号化リポジトリを保存するサーバー上のパス |

マシンを追加すると、rdcは自動的に`ssh-keyscan`を実行してサーバーのホスト鍵を取得します。手動で実行することもできます：

```bash
rdc context scan-keys server-1
```

登録済みのすべてのマシンを表示するには：

```bash
rdc context machines
```

## ステップ3：マシンのセットアップ

リモートサーバーに必要なすべての依存関係をプロビジョニングします：

```bash
rdc context setup-machine server-1
```

このコマンドは以下を実行します：
1. SFTP経由でrenetバイナリをサーバーにアップロード
2. Docker、containerd、cryptsetupをインストール（未インストールの場合）
3. `rediacc`システムユーザー（UID 7111）を作成
4. データストアディレクトリを作成し、暗号化リポジトリ用に準備

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `--datastore <path>` | いいえ | `/mnt/rediacc` | サーバー上のデータストアディレクトリ |
| `--datastore-size <size>` | いいえ | `95%` | データストアに割り当てる利用可能ディスクの割合 |
| `--debug` | いいえ | `false` | トラブルシューティング用の詳細出力を有効にします |

> セットアップはマシンごとに一度だけ実行する必要があります。必要に応じて再実行しても安全です。

## ホスト鍵の管理

サーバーのSSHホスト鍵が変更された場合（例：再インストール後）、保存されている鍵を更新します：

```bash
rdc context scan-keys server-1
```

これにより、そのマシンの設定内の`knownHosts`フィールドが更新されます。

## SSH接続のテスト

続行する前に、マシンに到達可能であることを確認します：

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

このコマンドはSSH接続をテストし、以下を報告します：
- 接続ステータス
- 使用された認証方法
- SSH鍵の設定
- 既知のホストエントリ

検証されたホスト鍵をマシン設定に保存するには`--save -m server-1`を使用します。

## インフラストラクチャ設定

パブリックにトラフィックを提供する必要があるマシンの場合、インフラストラクチャ設定を行います：

### インフラストラクチャの設定

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| オプション | 説明 |
|--------|-------------|
| `--public-ipv4 <ip>` | 外部アクセス用のパブリックIPv4アドレス |
| `--public-ipv6 <ip>` | 外部アクセス用のパブリックIPv6アドレス |
| `--base-domain <domain>` | アプリケーション用のベースドメイン（例：`example.com`） |
| `--cert-email <email>` | Let's Encrypt TLS証明書用のメールアドレス |
| `--cf-dns-token <token>` | ACME DNS-01チャレンジ用のCloudflare DNS APIトークン |
| `--tcp-ports <ports>` | 転送する追加TCPポートのカンマ区切りリスト（例：`25,143,465,587,993`） |
| `--udp-ports <ports>` | 転送する追加UDPポートのカンマ区切りリスト（例：`53`） |

### インフラストラクチャの表示

```bash
rdc context show-infra server-1
```

### サーバーへのプッシュ

Traefikリバースプロキシ設定を生成してサーバーにデプロイします：

```bash
rdc context push-infra server-1
```

これにより、インフラストラクチャ設定に基づいてプロキシ設定がプッシュされます。TraefikはTLS終端、ルーティング、ポートフォワーディングを処理します。

## デフォルトの設定

毎回のコマンドで指定する必要がないように、デフォルト値を設定します：

```bash
rdc context set machine server-1    # デフォルトマシン
rdc context set team my-team        # デフォルトチーム（クラウドモード、実験的）
```

デフォルトマシンを設定した後は、コマンドから`-m server-1`を省略できます：

```bash
rdc repo create my-app --size 10G   # デフォルトマシンを使用
```

## 複数のコンテキスト

名前付きコンテキストで複数の環境を管理します：

```bash
# 別々のコンテキストを作成
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# 特定のコンテキストを使用
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

すべてのコンテキストを表示：

```bash
rdc context list
```

現在のコンテキストの詳細を表示：

```bash
rdc context show
```
