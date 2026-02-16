---
title: "クイックスタートガイド"
description: "Rediaccをローカルモードで使用して、自分のサーバーに暗号化された隔離インフラストラクチャをデプロイするためのステップバイステップガイド。"
category: "Core Concepts"
order: 0
language: ja
---

# クイックスタートガイド

このガイドでは、Rediaccを**ローカルモード**で使用して、自分のサーバーに暗号化された隔離インフラストラクチャをデプロイする方法を説明します。このガイドを完了すると、ワークステーションから管理される、リモートマシン上でコンテナ化されたサービスを実行する完全に動作するリポジトリが構築されます。

ローカルモードとは、すべてが自分で管理するインフラストラクチャ上で実行されることを意味します。クラウドアカウントもSaaS依存関係も不要です。ワークステーションがSSH経由でリモートサーバーをオーケストレーションし、すべての状態はローカルマシンとサーバー自体に保存されます。

## アーキテクチャ概要

Rediaccは2つのツールで構成されるアーキテクチャを使用します:

```
ワークステーション                       リモートサーバー
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Goバイナリ)       │
│  rdc (CLI)   │                   │    ├── LUKS暗号化        │
│              │ ◀──────────────   │    ├── Dockerデーモン     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile実行   │
└──────────────┘                   │    └── Traefikプロキシ    │
                                   └──────────────────────────┘
```

- **rdc** はワークステーション（macOSまたはLinux）上で動作します。ローカル設定を読み取り、SSH経由でリモートマシンに接続し、renetコマンドを呼び出します。
- **renet** はリモートサーバー上でroot権限で動作します。LUKS暗号化ディスクイメージ、隔離されたDockerデーモン、サービスオーケストレーション、リバースプロキシ設定を管理します。

ローカルで入力するすべてのコマンドは、リモートマシン上でrenetを実行するSSH呼び出しに変換されます。手動でサーバーにSSHする必要はありません。

## 必要なもの

開始前に、以下のものを用意してください:

**ワークステーション側:**
- SSHクライアントがインストールされたmacOSまたはLinux
- SSHキーペア（例: `~/.ssh/id_ed25519` または `~/.ssh/id_rsa`）

**リモートサーバー側:**
- Ubuntu 20.04以降またはDebian 11以降（他のLinuxディストリビューションでも動作する可能性がありますが、テスト済みではありません）
- `sudo`権限を持つユーザーアカウント
- `~/.ssh/authorized_keys` にSSH公開鍵が追加済みであること
- 最低20 GBの空きディスク容量（ワークロードに応じてさらに必要）

## ステップ1: rdcのインストール

ワークステーションにRediacc CLIをインストールします:

```bash
curl -fsSL https://get.rediacc.com | sh
```

これにより`rdc`バイナリが`$HOME/.local/bin/`にダウンロードされます。このディレクトリがPATHに含まれていることを確認してください。インストールを確認します:

```bash
rdc --help
```

> 後でアップデートする場合は、`rdc update` を実行してください。

## ステップ2: ローカルコンテキストの作成

**コンテキスト**は、SSH資格情報、マシン定義、リポジトリマッピングを保存する名前付きの設定です。プロジェクトワークスペースと考えてください。

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `--ssh-key <path>` | はい | SSH秘密鍵へのパス。チルダ（`~`）は自動的に展開されます。 |
| `--renet-path <path>` | いいえ | リモートマシン上のrenetバイナリへのカスタムパス。デフォルトは標準インストール場所です。 |

これにより`my-infra`という名前のローカルコンテキストが作成され、`~/.rediacc/config.json`に保存されます。

> 複数のコンテキストを持つことができます（例: `production`、`staging`、`dev`）。任意のコマンドで`--context`フラグを使用して切り替えることができます。

## ステップ3: マシンの追加

リモートサーバーをコンテキスト内のマシンとして登録します:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `--ip <address>` | はい | - | リモートサーバーのIPアドレスまたはホスト名。 |
| `--user <username>` | はい | - | リモートサーバーのSSHユーザー名。 |
| `--port <port>` | いいえ | `22` | SSHポート。 |
| `--datastore <path>` | いいえ | `/mnt/rediacc` | Rediaccが暗号化リポジトリを保存するサーバー上のパス。 |

マシンを追加すると、rdcは自動的に`ssh-keyscan`を実行してサーバーのホスト鍵を取得します。手動で実行することもできます:

```bash
rdc context scan-keys server-1
```

登録済みのすべてのマシンを表示するには:

```bash
rdc context machines
```

## ステップ4: マシンのセットアップ

リモートサーバーに必要なすべての依存関係をプロビジョニングします:

```bash
rdc context setup-machine server-1
```

このコマンドは以下を実行します:
1. SFTP経由でrenetバイナリをサーバーにアップロード
2. Docker、containerd、cryptsetup をインストール（未インストールの場合）
3. データストアディレクトリを作成し、暗号化リポジトリ用に準備

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `--datastore <path>` | いいえ | `/mnt/rediacc` | サーバー上のデータストアディレクトリ。 |
| `--datastore-size <size>` | いいえ | `95%` | データストアに割り当てる利用可能ディスクの割合。 |
| `--debug` | いいえ | `false` | トラブルシューティング用の詳細出力を有効にします。 |

> セットアップはマシンごとに一度だけ実行する必要があります。必要に応じて再実行しても安全です。

## ステップ5: リポジトリの作成

**リポジトリ**は、リモートサーバー上のLUKS暗号化ディスクイメージです。マウントすると以下が提供されます:
- アプリケーションデータ用の隔離されたファイルシステム
- 専用のDockerデーモン（ホストのDockerとは別）
- /26サブネット内の各サービスに対する一意のループバックIP

リポジトリを作成します:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `-m, --machine <name>` | はい | リポジトリが作成されるターゲットマシン。 |
| `--size <size>` | はい | 暗号化ディスクイメージのサイズ（例: `5G`、`10G`、`50G`）。 |

出力には3つの自動生成された値が表示されます:

- **リポジトリGUID** -- サーバー上の暗号化ディスクイメージを識別するUUID。
- **クレデンシャル** -- LUKSボリュームの暗号化/復号化に使用されるランダムなパスフレーズ。
- **ネットワークID** -- このリポジトリのサービスのIPサブネットを決定する整数（2816から始まり、64ずつ増加）。

> **クレデンシャルは安全に保管してください。** これはリポジトリの暗号化鍵です。紛失した場合、データは復元できません。クレデンシャルはローカルの`config.json`に保存されますが、サーバーには保存されません。

## ステップ6: Rediaccfile

**Rediaccfile**は、サービスの準備、開始、停止の方法を定義するBashスクリプトです。サービスライフサイクル管理のコアメカニズムです。

### Rediaccfileとは？

Rediaccfileは、最大3つの関数を含むプレーンなBashスクリプトです: `prep()`、`up()`、`down()`。ファイル名は`Rediaccfile`または`rediaccfile`（大文字小文字を区別しない）で、リポジトリのマウントされたファイルシステム内に配置する必要があります。

Rediaccfileは2つの場所で検出されます:
1. リポジトリマウントパスの**ルート**
2. マウントパスの**第1レベルサブディレクトリ**（再帰的ではありません）

隠しディレクトリ（`.`で始まる名前）はスキップされます。

### ライフサイクル関数

| 関数 | 実行タイミング | 目的 | エラー動作 |
|----------|-------------|---------|----------------|
| `prep()` | `up()`の前 | 依存関係のインストール、イメージのプル、マイグレーションの実行 | **即時失敗** -- いずれかの`prep()`が失敗すると、プロセス全体が即座に停止します。 |
| `up()` | すべての`prep()`完了後 | サービスの開始（例: `docker compose up -d`） | ルートRediaccfileの失敗は**クリティカル**（すべて停止）。サブディレクトリの失敗は**非クリティカル**（ログに記録し、次に進む）。 |
| `down()` | 停止時 | サービスの停止（例: `docker compose down`） | **ベストエフォート** -- 失敗はログに記録されますが、すべてのRediaccfileが常に試行されます。 |

3つの関数はすべてオプションです。Rediaccfileで関数が定義されていない場合、サイレントにスキップされます。

### 実行順序

- **開始（`up`）:** ルートRediaccfileが最初、次にサブディレクトリが**アルファベット順**（AからZ）。
- **停止（`down`）:** サブディレクトリが**逆アルファベット順**（ZからA）、最後にルート。

### 環境変数

Rediaccfile関数の実行時、以下の環境変数が利用可能です:

| 変数 | 説明 | 例 |
|----------|-------------|---------|
| `REPOSITORY_PATH` | リポジトリのマウントパス | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | リポジトリGUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ネットワークID（整数） | `2816` |
| `DOCKER_HOST` | このリポジトリの隔離デーモン用Dockerソケット | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json`で定義された各サービスのループバックIP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP`変数は`.rediacc.json`から自動生成されます（ステップ7を参照）。命名規則では、サービス名を大文字に変換し、ハイフンをアンダースコアに置き換え、`_IP`を付加します。例えば、`listmonk-app`は`LISTMONK_APP_IP`になります。

### Rediaccfileの例

Webアプリケーション用のシンプルなRediaccfile:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### マルチサービスの例

複数の独立したサービスグループを持つプロジェクトでは、サブディレクトリを使用します:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # ルート: 共有セットアップ（例: Dockerネットワークの作成）
├── docker-compose.yml       # ルートcomposeファイル
├── database/
│   ├── Rediaccfile          # データベースサービス
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # APIサーバー
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus、Grafanaなど
    └── docker-compose.yml
```

`up`の実行順序: ルート、次に`backend`、`database`、`monitoring`（A-Z）。
`down`の実行順序: `monitoring`、`database`、`backend`、最後にルート（Z-A）。

## ステップ7: サービスネットワーキング（.rediacc.json）

各リポジトリは`127.x.x.x`ループバック範囲内の/26サブネット（64個のIP）を取得します。サービスは一意のループバックIPにバインドされるため、競合なく同じポートで実行できます。例えば、2つのPostgreSQLインスタンスがそれぞれ異なるIPでポート5432をリッスンできます。

### .rediacc.jsonファイル

`.rediacc.json`ファイルは、サービス名を**スロット**番号にマッピングします。各スロットは、リポジトリのサブネット内の一意のIPアドレスに対応します。

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

サービスはアルファベット順に記述されます。

### Docker Composeからの自動生成

`.rediacc.json`を手動で作成する必要はありません。`rdc repo up`を実行すると、Rediaccは自動的に以下を行います:

1. Rediaccfileを含むすべてのディレクトリでcomposeファイル（`docker-compose.yml`、`docker-compose.yaml`、`compose.yml`、または`compose.yaml`）をスキャン。
2. 各composeファイルの`services:`セクションからサービス名を抽出。
3. 新しいサービスに次の利用可能なスロットを割り当て。
4. 結果を`{repository}/.rediacc.json`に保存。

### IP計算

サービスのIPは、リポジトリのネットワークIDとサービスのスロットから計算されます。ネットワークIDは`127.x.y.z`ループバックアドレスの第2、第3、第4オクテットに分割されます。各サービスにはネットワークIDに`slot + 2`のオフセットが加算されます（オフセット0と1はネットワークアドレスとゲートウェイ用に予約されています）。

例えば、ネットワークID `2816`（`0x0B00`）の場合、ベースアドレスは`127.0.11.0`で、サービスは`127.0.11.2`から始まります。

**例**: ネットワークID `2816`の場合:

| サービス | スロット | IPアドレス |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

各リポジトリは最大**61個のサービス**（スロット0から60）をサポートします。

### Docker ComposeでのサービスIPの使用

各リポジトリは隔離されたDockerデーモンを実行するため、サービスは`network_mode: host`を使用し、割り当てられたループバックIPにバインドします:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

`${POSTGRES_IP}`と`${API_IP}`変数は、Rediaccfileの実行時に`.rediacc.json`から自動的にエクスポートされます。

## ステップ8: サービスの開始

リポジトリをマウントし、すべてのサービスを開始します:

```bash
rdc repo up my-app -m server-1 --mount
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `-m, --machine <name>` | はい | ターゲットマシン。 |
| `--mount` | いいえ | まだマウントされていない場合、先にリポジトリをマウントします。このフラグがない場合、リポジトリは既にマウントされている必要があります。 |
| `--prep-only` | いいえ | `prep()`関数のみを実行し、`up()`をスキップします。イメージの事前プルやマイグレーションの実行に便利です。 |

実行シーケンスは以下の通りです:

1. LUKS暗号化リポジトリをマウント（`--mount`が指定されている場合）
2. このリポジトリ用の隔離Dockerデーモンを起動
3. composeファイルから`.rediacc.json`を自動生成
4. すべてのRediaccfileで`prep()`を実行（A-Z順、即時失敗）
5. すべてのRediaccfileで`up()`を実行（A-Z順）

## ステップ9: サービスの停止

リポジトリ内のすべてのサービスを停止します:

```bash
rdc repo down my-app -m server-1
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `-m, --machine <name>` | はい | ターゲットマシン。 |
| `--unmount` | いいえ | サービス停止後に暗号化リポジトリをアンマウントします。これにより、隔離Dockerデーモンも停止し、LUKSボリュームもクローズされます。 |

実行シーケンスは以下の通りです:

1. すべてのRediaccfileで`down()`を実行（Z-A逆順、ベストエフォート）
2. 隔離Dockerデーモンを停止（`--unmount`の場合）
3. LUKS暗号化ボリュームをアンマウントおよびクローズ（`--unmount`の場合）

## その他の一般的な操作

### マウントとアンマウント（サービスを開始せずに）

```bash
rdc repo mount my-app -m server-1     # 復号化してマウント
rdc repo unmount my-app -m server-1   # アンマウントして再暗号化
```

### リポジトリステータスの確認

```bash
rdc repo status my-app -m server-1
```

### すべてのリポジトリの一覧表示

```bash
rdc repo list -m server-1
```

### リポジトリのリサイズ

```bash
rdc repo resize my-app -m server-1 --size 20G    # 正確なサイズに設定
rdc repo expand my-app -m server-1 --size 5G      # 現在のサイズに5Gを追加
```

### リポジトリの削除

```bash
rdc repo delete my-app -m server-1
```

> これにより、暗号化ディスクイメージとその中のすべてのデータが永久に破壊されます。

### リポジトリのフォーク

既存のリポジトリの現在の状態のコピーを作成します:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

これにより、独自のGUIDとネットワークIDを持つ新しい暗号化コピーが作成されます。フォークは親と同じLUKSクレデンシャルを共有します。

### リポジトリの検証

リポジトリのファイルシステム整合性を確認します:

```bash
rdc repo validate my-app -m server-1
```

## 起動時の自動開始

デフォルトでは、サーバー再起動後にリポジトリを手動でマウントして開始する必要があります。**自動開始**を設定すると、サーバー起動時にリポジトリを自動的にマウントし、Dockerを起動し、Rediaccfileの`up()`を実行するように構成できます。

### 仕組み

リポジトリの自動開始を有効にすると:

1. 256バイトのランダムなLUKSキーファイルが生成され、リポジトリのLUKSスロット1に追加されます（スロット0はユーザーパスフレーズのまま）。
2. キーファイルは`{datastore}/.credentials/keys/{guid}.key`に`0600`パーミッション（root専用）で保存されます。
3. systemdサービス（`rediacc-autostart`）がインストールされ、起動時にすべての有効なリポジトリをマウントしてサービスを開始します。

システムのシャットダウンまたは再起動時、サービスはすべてのサービスを正常に停止し（Rediaccfileの`down()`）、Dockerデーモンを停止し、LUKSボリュームをクローズします。

> **セキュリティに関する注意:** 自動開始を有効にすると、サーバーのディスクにLUKSキーファイルが保存されます。サーバーへのroot アクセスを持つ者は、パスフレーズなしでリポジトリをマウントできます。これは利便性（自動起動）とセキュリティ（手動パスフレーズ入力の要求）のトレードオフです。脅威モデルに基づいて評価してください。

### 自動開始の有効化

```bash
rdc repo autostart enable my-app -m server-1
```

リポジトリのパスフレーズの入力を求められます。これは、LUKSボリュームへのキーファイルの追加を承認するために必要です。

### すべてのリポジトリの自動開始を有効化

```bash
rdc repo autostart enable-all -m server-1
```

### 自動開始の無効化

```bash
rdc repo autostart disable my-app -m server-1
```

これによりキーファイルが削除され、LUKSスロット1が無効化されます。リポジトリは起動時に自動マウントされなくなります。

### 自動開始ステータスの一覧表示

```bash
rdc repo autostart list -m server-1
```

どのリポジトリで自動開始が有効になっているか、systemdサービスがインストールされているかどうかを表示します。

## 完全な例: Webアプリケーションのデプロイ

このエンドツーエンドの例では、PostgreSQL、Redis、APIサーバーを含むWebアプリケーションをデプロイします。

### 1. 環境のセットアップ

```bash
# rdcのインストール
curl -fsSL https://get.rediacc.com | sh

# ローカルコンテキストの作成
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# サーバーの登録
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# サーバーのプロビジョニング
rdc context setup-machine prod-1

# 暗号化リポジトリの作成（10 GB）
rdc repo create webapp -m prod-1 --size 10G
```

### 2. リポジトリのマウントと準備

```bash
rdc repo mount webapp -m prod-1
```

サーバーにSSHし、マウントされたリポジトリ内にアプリケーションファイルを作成します。マウントパスは出力に表示されます（通常は`/mnt/rediacc/repos/{guid}`）。

### 3. アプリケーションファイルの作成

リポジトリ内に以下のファイルを作成します:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. すべてを開始

```bash
rdc repo up webapp -m prod-1
```

これにより以下が実行されます:
1. `api`、`postgres`、`redis`のスロットを含む`.rediacc.json`を自動生成
2. `prep()`を実行してディレクトリの作成とイメージのプル
3. `up()`を実行してすべてのコンテナを起動

### 5. 自動開始の有効化

```bash
rdc repo autostart enable webapp -m prod-1
```

サーバーの再起動後、リポジトリは自動的にマウントされ、すべてのサービスが開始されます。

## コンテキスト設定の理解

すべてのコンテキスト設定は`~/.rediacc/config.json`に保存されます。上記の手順を完了した後のこのファイルの注釈付きの例を以下に示します:

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
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**主要なフィールド:**

| フィールド | 説明 |
|-------|-------------|
| `mode` | ローカルモードは`"local"`、S3バックドコンテキストは`"s3"`。 |
| `apiUrl` | `"local://"`はローカルモード（リモートAPIなし）を示します。 |
| `ssh.privateKeyPath` | すべてのマシン接続に使用されるSSH秘密鍵のパス。 |
| `machines.<name>.knownHosts` | `ssh-keyscan`からのSSHホスト鍵。サーバーIDの検証に使用されます。 |
| `repositories.<name>.repositoryGuid` | サーバー上の暗号化ディスクイメージを識別するUUID。 |
| `repositories.<name>.credential` | LUKS暗号化パスフレーズ。**サーバーには保存されません。** |
| `repositories.<name>.networkId` | IPサブネットを決定するネットワークID（2816 + n*64）。自動割り当て。 |

> このファイルには機密データ（SSH鍵パス、LUKSクレデンシャル）が含まれています。`0600`パーミッション（所有者のみ読み書き可能）で保存されます。共有したり、バージョン管理にコミットしないでください。

## トラブルシューティング

### SSH接続の失敗

- 手動で接続できることを確認: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- `rdc context scan-keys server-1`を実行してホスト鍵を更新
- SSHポートが一致していることを確認: `--port 22`

### マシンセットアップの失敗

- ユーザーがパスワードなしでsudoアクセスできることを確認するか、必要なコマンドに対して`NOPASSWD`を設定
- サーバーの空きディスク容量を確認
- `--debug`で詳細出力を有効にして実行: `rdc context setup-machine server-1 --debug`

### リポジトリ作成の失敗

- セットアップが完了していることを確認: データストアディレクトリが存在する必要があります
- サーバーのディスク容量を確認
- renetバイナリがインストールされていることを確認（必要に応じてセットアップを再実行）

### サービスの起動失敗

- Rediaccfileの構文を確認: 有効なBashである必要があります
- `docker compose`ファイルで`network_mode: host`が使用されていることを確認
- Dockerイメージにアクセスできることを確認（`prep()`で`docker compose pull`の使用を検討）
- コンテナログを確認: サーバーにSSHし、`docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`を使用

### 権限拒否エラー

- リポジトリ操作にはサーバー上のrootが必要です（renetは`sudo`経由で実行されます）
- ユーザーが`sudo`グループに所属していることを確認
- データストアディレクトリのパーミッションが正しいことを確認

## 次のステップ

- **CLIリファレンス** -- コマンドリファレンスの完全版は[CLIアプリケーション](/ja/docs/cli-application)ページをご覧ください。
- **バックアップとリカバリ** -- 災害復旧のためにS3互換ストレージへのオフサイトバックアップを設定します。
- **リバースプロキシ** -- 自動Let's Encrypt証明書を使用したHTTPS用のTraefik設定を行います。
- **CRIUチェックポイント/リストア** -- 実行中のコンテナをチェックポイントし、即座のマイグレーションまたはロールバックを実現します。
