---
title: サービス
description: Rediaccfile、サービスネットワーキング、自動開始を使用してコンテナ化されたサービスをデプロイ・管理。
category: Guides
order: 5
language: ja
sourceHash: 8add6342eea14e41
---

# サービス

どのツールを使うべきか迷う場合は、[rdc vs renet](/ja/docs/rdc-vs-renet) を参照してください。

このページでは、コンテナ化されたサービスのデプロイと管理方法について説明します：Rediaccfile、サービスネットワーキング、開始/停止、一括操作、自動開始。

## Rediaccfile

**Rediaccfile**は、サービスの準備、開始、停止の方法を定義するBashスクリプトです。ファイル名は`Rediaccfile`または`rediaccfile`（大文字小文字を区別しない）で、リポジトリのマウントされたファイルシステム内に配置する必要があります。

Rediaccfileは2つの場所で検出されます：
1. リポジトリマウントパスの**ルート**
2. マウントパスの**第1レベルサブディレクトリ**（再帰的ではありません）

隠しディレクトリ（`.`で始まる名前）はスキップされます。

### ライフサイクル関数

Rediaccfileは最大3つの関数を含みます：

| 関数 | 実行タイミング | 目的 | エラー動作 |
|----------|-------------|---------|----------------|
| `prep()` | `up()`の前 | 依存関係のインストール、イメージのプル、マイグレーションの実行 | **即時失敗** -- いずれかの`prep()`が失敗すると、プロセス全体が即座に停止 |
| `up()` | すべての`prep()`完了後 | サービスの開始（例：`docker compose up -d`） | ルートの失敗は**クリティカル**（すべて停止）。サブディレクトリの失敗は**非クリティカル**（ログに記録し、次に進む） |
| `down()` | 停止時 | サービスの停止（例：`docker compose down`） | **ベストエフォート** -- 失敗はログに記録されますが、すべてのRediaccfileが常に試行 |

3つの関数はすべてオプションです。関数が定義されていない場合、サイレントにスキップされます。

### 実行順序

- **開始（`up`）：** ルートRediaccfileが最初、次にサブディレクトリが**アルファベット順**（AからZ）。
- **停止（`down`）：** サブディレクトリが**逆アルファベット順**（ZからA）、最後にルート。

### 環境変数

Rediaccfile関数の実行時、以下の環境変数が利用可能です：

| 変数 | 説明 | 例 |
|----------|-------------|---------|
| `REPOSITORY_PATH` | リポジトリのマウントパス | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | リポジトリGUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ネットワークID（整数） | `2816` |
| `DOCKER_HOST` | このリポジトリの隔離デーモン用Dockerソケット | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json`で定義された各サービスのループバックIP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP`変数は`.rediacc.json`から自動生成されます。命名規則では、サービス名を大文字に変換し、ハイフンをアンダースコアに置き換え、`_IP`を付加します。例えば、`listmonk-app`は`LISTMONK_APP_IP`になります。

> **警告：Rediaccfile内で`sudo docker`を使用しないでください。** `sudo`コマンドは環境変数をリセットするため、`DOCKER_HOST`が失われ、Dockerコマンドがリポジトリの隔離デーモンではなくシステムデーモンを対象にします。これによりコンテナの隔離が壊れ、ポート競合が発生する可能性があります。Rediaccは`-E`なしの`sudo docker`を検出すると実行をブロックします。
>
> Rediaccfile内では`renet compose`を使用してください。`DOCKER_HOST`を自動的に処理し、ルート検出用のネットワーキングラベルを注入し、サービスネットワーキングを設定します。リバースプロキシ経由でサービスを公開する方法の詳細については、[ネットワーキング](/ja/docs/networking)を参照してください。Dockerを直接呼び出す場合は、`sudo`なしで`docker`を使用してください。Rediaccfile関数は既に十分な権限で実行されます。sudoを使用する必要がある場合は、環境変数を保持するために`sudo -E docker`を使用してください。

### 例

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `DOCKER_HOST`が自動的に設定されるため`docker compose`も動作しますが、リバースプロキシのルート検出に必要な`rediacc.*`ラベルを追加で注入するため`renet compose`が推奨されます。詳細については[ネットワーキング](/ja/docs/networking)を参照してください。

### マルチサービスレイアウト

複数の独立したサービスグループを持つプロジェクトでは、サブディレクトリを使用します：

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # ルート：共有セットアップ
├── docker-compose.yml
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

`up`の実行順序：ルート、次に`backend`、`database`、`monitoring`（A-Z）。
`down`の実行順序：`monitoring`、`database`、`backend`、最後にルート（Z-A）。

## サービスネットワーキング（.rediacc.json）

各リポジトリは`127.x.x.x`ループバック範囲内の/26サブネット（64個のIP）を取得します。サービスは一意のループバックIPにバインドされるため、競合なく同じポートで実行できます。

### .rediacc.jsonファイル

サービス名を**スロット**番号にマッピングします。各スロットは、リポジトリのサブネット内の一意のIPアドレスに対応します。

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Docker Composeからの自動生成

`.rediacc.json`を手動で作成する必要はありません。`rdc repo up`を実行すると、Rediaccは自動的に以下を行います：

1. Rediaccfileを含むすべてのディレクトリでcomposeファイル（`docker-compose.yml`、`docker-compose.yaml`、`compose.yml`、または`compose.yaml`）をスキャン
2. `services:`セクションからサービス名を抽出
3. 新しいサービスに次の利用可能なスロットを割り当て
4. 結果を`{repository}/.rediacc.json`に保存

### IP計算

サービスのIPは、リポジトリのネットワークIDとサービスのスロットから計算されます。ネットワークIDは`127.x.y.z`ループバックアドレスの第2、第3、第4オクテットに分割されます。各サービスにはネットワークIDに`slot + 2`のオフセットが加算されます（オフセット0と1はネットワークアドレスとゲートウェイ用に予約）。

**例**：ネットワークID `2816`（`0x0B00`）の場合、ベースアドレスは`127.0.11.0`：

| サービス | スロット | IPアドレス |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

各リポジトリは最大**61個のサービス**（スロット0から60）をサポートします。

### Docker ComposeでのサービスIPの使用

各リポジトリは隔離されたDockerデーモンを実行するため、サービスは`network_mode: host`を使用し、割り当てられたループバックIPにバインドします：

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

## サービスの開始

リポジトリをマウントし、すべてのサービスを開始します：

```bash
rdc repo up my-app -m server-1 --mount
```

| オプション | 説明 |
|--------|-------------|
| `--mount` | まだマウントされていない場合、先にリポジトリをマウント |
| `--prep-only` | `prep()`関数のみを実行し、`up()`をスキップ |

実行シーケンスは以下の通りです：
1. LUKS暗号化リポジトリをマウント（`--mount`の場合）
2. 隔離Dockerデーモンを起動
3. composeファイルから`.rediacc.json`を自動生成
4. すべてのRediaccfileで`prep()`を実行（A-Z順、即時失敗）
5. すべてのRediaccfileで`up()`を実行（A-Z順）

## サービスの停止

```bash
rdc repo down my-app -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--unmount` | 停止後に暗号化リポジトリをアンマウント |

実行シーケンスは以下の通りです：
1. すべてのRediaccfileで`down()`を実行（Z-A逆順、ベストエフォート）
2. 隔離Dockerデーモンを停止（`--unmount`の場合）
3. LUKS暗号化ボリュームをアンマウントおよびクローズ（`--unmount`の場合）

## 一括操作

マシン上のすべてのリポジトリを一度に開始または停止します：

```bash
rdc repo up-all -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--include-forks` | フォークされたリポジトリを含める |
| `--mount-only` | マウントのみ行い、コンテナは起動しない |
| `--dry-run` | 実行される操作を表示 |
| `--parallel` | 操作を並列実行 |
| `--concurrency <n>` | 最大同時操作数（デフォルト：3） |

## 起動時の自動開始

デフォルトでは、サーバー再起動後にリポジトリを手動でマウントして開始する必要があります。**自動開始**を設定すると、サーバー起動時にリポジトリを自動的にマウントし、Dockerを起動し、Rediaccfileの`up()`を実行するように構成できます。

### 仕組み

リポジトリの自動開始を有効にすると：

1. 256バイトのランダムなLUKSキーファイルが生成され、リポジトリのLUKSスロット1に追加されます（スロット0はユーザーパスフレーズのまま）
2. キーファイルは`{datastore}/.credentials/keys/{guid}.key`に`0600`パーミッション（root専用）で保存されます
3. systemdサービス（`rediacc-autostart`）が起動時にすべての有効なリポジトリをマウントしてサービスを開始します

システムのシャットダウン時、サービスはすべてのサービスを正常に停止し（Rediaccfileの`down()`）、Dockerデーモンを停止し、LUKSボリュームをクローズします。

> **セキュリティに関する注意：** 自動開始を有効にすると、サーバーのディスクにLUKSキーファイルが保存されます。サーバーへのrootアクセスを持つ者は、パスフレーズなしでリポジトリをマウントできます。脅威モデルに基づいて評価してください。

### 有効化

```bash
rdc repo autostart enable my-app -m server-1
```

リポジトリのパスフレーズの入力を求められます。

### すべてを有効化

```bash
rdc repo autostart enable-all -m server-1
```

### 無効化

```bash
rdc repo autostart disable my-app -m server-1
```

これによりキーファイルが削除され、LUKSスロット1が無効化されます。

### ステータスの一覧表示

```bash
rdc repo autostart list -m server-1
```

## 完全な例

この例では、PostgreSQL、Redis、APIサーバーを含むWebアプリケーションをデプロイします。

### 1. セットアップ

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. マウントと準備

```bash
rdc repo mount webapp -m prod-1
```

### 3. アプリケーションファイルの作成

リポジトリ内に以下のファイルを作成します：

**docker-compose.yml：**

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

**Rediaccfile：**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
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
    renet compose -- down
}
```

### 4. 開始

```bash
rdc repo up webapp -m prod-1
```

### 5. 自動開始の有効化

```bash
rdc repo autostart enable webapp -m prod-1
```
