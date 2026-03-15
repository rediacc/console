---
title: "マシンセットアップ"
description: "設定の作成、マシンの追加、サーバーのプロビジョニング、インフラストラクチャの設定。"
category: "Guides"
order: 3
language: ja
sourceHash: "ebf1c9967814ec86"
---

# マシンセットアップ

このページでは、最初のマシンのセットアップ手順を説明します：設定の作成、サーバーの登録、プロビジョニング、およびオプションでパブリックアクセス用のインフラストラクチャ設定。

## ステップ1：Configの作成

**Config**は、SSH資格情報、マシン定義、リポジトリマッピングを保存する名前付き設定ファイルです。プロジェクトワークスペースと考えてください。

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `--ssh-key <path>` | はい | SSH秘密鍵へのパス。チルダ（`~`）は自動的に展開されます。 |
| `--renet-path <path>` | いいえ | リモートマシン上のrenetバイナリへのカスタムパス。デフォルトは標準インストール場所です。 |

これにより`my-infra`という名前の設定が作成され、`~/.config/rediacc/my-infra.json`に保存されます。デフォルト設定（名前を指定しない場合）は`~/.config/rediacc/rediacc.json`として保存されます。

> 複数の設定を持つことができます（例：`production`、`staging`、`dev`）。任意のコマンドで`--config`フラグを使用して切り替えることができます。

## ステップ2：マシンの追加

リモートサーバーを設定内のマシンとして登録します：

```bash
rdc config machine add server-1 --ip 203.0.113.50 --user deploy
```

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `--ip <address>` | はい | - | リモートサーバーのIPアドレスまたはホスト名 |
| `--user <username>` | はい | - | リモートサーバーのSSHユーザー名 |
| `--port <port>` | いいえ | `22` | SSHポート |
| `--datastore <path>` | いいえ | `/mnt/rediacc` | Rediaccが暗号化リポジトリを保存するサーバー上のパス |

マシンを追加すると、rdcは自動的に`ssh-keyscan`を実行してサーバーのホスト鍵を取得します。手動で実行することもできます：

```bash
rdc config machine scan-keys server-1
```

登録済みのすべてのマシンを表示するには：

```bash
rdc config machine list
```

## ステップ3：マシンのセットアップ

リモートサーバーに必要なすべての依存関係をプロビジョニングします：

```bash
rdc config machine setup server-1
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
rdc config machine scan-keys server-1
```

これにより、そのマシンの設定内の`knownHosts`フィールドが更新されます。

## SSH接続のテスト

マシンを追加した後、到達可能であることを確認します：

```bash
rdc term server-1 -c "hostname"
```

このコマンドはマシンへのSSH接続を開き、コマンドを実行します。成功すれば、SSH設定が正しいことが確認できます。

より詳細な診断については、以下を実行してください：

```bash
rdc doctor
```

> **クラウドアダプターのみ**: `rdc machine test-connection` コマンドは詳細なSSH診断を提供しますが、クラウドアダプターが必要です。ローカルアダプターでは、`rdc term` または `ssh` を直接使用してください。

## インフラストラクチャ設定

パブリックにトラフィックを提供する必要があるマシンの場合、インフラストラクチャ設定を行います：

### インフラストラクチャの設定

```bash
rdc config infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| オプション | スコープ | 説明 |
|--------|-------|-------------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address — proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address — proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | アプリケーション用のベースドメイン（例：`example.com`） |
| `--cert-email <email>` | Config | Let's Encrypt TLS証明書用のメールアドレス（マシン間で共有） |
| `--cf-dns-token <token>` | Config | ACME DNS-01チャレンジ用のCloudflare DNS APIトークン（マシン間で共有） |
| `--tcp-ports <ports>` | Machine | 転送する追加TCPポートのカンマ区切りリスト（例：`25,143,465,587,993`） |
| `--udp-ports <ports>` | Machine | 転送する追加UDPポートのカンマ区切りリスト（例：`53`） |

Machineスコープのオプションはマシンごとに保存されます。Configスコープのオプション（`--cert-email`、`--cf-dns-token`）は設定内のすべてのマシンで共有されます。一度設定すればすべてに適用されます。

### インフラストラクチャの表示

```bash
rdc config infra show server-1
```

### サーバーへのプッシュ

Traefikリバースプロキシ設定を生成してサーバーにデプロイします：

```bash
rdc config infra push server-1
```

このコマンドは以下を実行します：
1. renetバイナリをリモートマシンにデプロイ
2. Traefikリバースプロキシ、ルーター、systemdサービスを設定
3. `--cf-dns-token` が設定されている場合、マシンサブドメイン（`server-1.example.com` および `*.server-1.example.com`）のCloudflare DNSレコードを作成

DNSステップは自動的かつ冪等です — 不足しているレコードを作成し、IPが変更されたレコードを更新し、既に正しいレコードはスキップします。Cloudflareトークンが設定されていない場合、DNSは警告付きでスキップされます。 Per-repo wildcard DNS records (for auto-routes) are created automatically when you run `rdc repo up`.

## クラウドプロビジョニング

VMを手動で作成する代わりに、クラウドプロバイダーを設定して、[OpenTofu](https://opentofu.org/) を使用して `rdc` にマシンを自動的にプロビジョニングさせることができます。

### 前提条件

OpenTofu をインストールしてください: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

SSH設定に公開鍵が含まれていることを確認してください：

```bash
rdc config set ssh.privateKeyPath ~/.ssh/id_ed25519
```

### クラウドプロバイダーの追加

```bash
rdc config provider add my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `--provider <source>` | はい* | 既知のプロバイダーソース（例：`linode/linode`、`hetznercloud/hcloud`） |
| `--source <source>` | はい* | カスタムOpenTofuプロバイダーソース（未知のプロバイダー用） |
| `--token <token>` | はい | クラウドプロバイダーのAPIトークン |
| `--region <region>` | いいえ | 新しいマシンのデフォルトリージョン |
| `--type <type>` | いいえ | デフォルトのインスタンスタイプ/サイズ |
| `--image <image>` | いいえ | デフォルトのOSイメージ |
| `--ssh-user <user>` | いいえ | SSHユーザー名（デフォルト: `root`） |

\* `--provider` または `--source` のいずれかが必要です。既知のプロバイダー（組み込みデフォルト）には `--provider` を使用します。カスタムプロバイダーには `--source` と追加の `--resource`、`--ipv4-output`、`--ssh-key-attr` フラグを使用します。

### マシンのプロビジョニング

```bash
rdc machine provision prod-2 --provider my-linode
```

この単一コマンドで以下を実行します：
1. OpenTofu経由でクラウドプロバイダーにVMを作成
2. SSH接続を待機
3. マシンを設定に登録
4. renetとすべての依存関係をインストール
5. Configures Traefik proxy and Cloudflare DNS (auto-detects base domain from sibling machines, or pass `--base-domain` explicitly)

| オプション | 説明 |
|--------|-------------|
| `--provider <name>` | クラウドプロバイダー名（`add-provider` から） |
| `--region <region>` | プロバイダーのデフォルトリージョンを上書き |
| `--type <type>` | デフォルトのインスタンスタイプを上書き |
| `--image <image>` | デフォルトのOSイメージを上書き |
| `--base-domain <domain>` | Base domain for infrastructure. Auto-detected from sibling machines if not specified |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | 詳細なプロビジョニング出力を表示 |

### マシンのデプロビジョニング

```bash
rdc machine deprovision prod-2
```

OpenTofu経由でVMを破棄し、設定から削除します。`--force` を使用しない限り確認が必要です。`machine provision` で作成されたマシンのみ動作します。

### プロバイダーの一覧表示

```bash
rdc config provider list
```

## デフォルトの設定

毎回のコマンドで指定する必要がないように、デフォルト値を設定します：

```bash
rdc config set machine server-1    # デフォルトマシン
rdc config set team my-team        # デフォルトチーム（クラウドアダプター、実験的）
```

デフォルトマシンを設定した後は、コマンドから`-m server-1`を省略できます：

```bash
rdc repo create my-app --size 10G   # デフォルトマシンを使用
```

## 複数の設定

名前付き設定で複数の環境を管理します：

```bash
# 別々の設定を作成
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# 特定の設定を使用
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

すべての設定を表示：

```bash
rdc config list
```

現在の設定の詳細を表示：

```bash
rdc config show
```
