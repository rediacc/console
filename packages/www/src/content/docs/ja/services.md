---
title: サービス
description: Rediaccfile、サービスネットワーキング、自動開始を使用してコンテナ化されたサービスをデプロイ・管理。
category: Guides
order: 5
language: ja
sourceHash: "1eddcf9de8bfac31"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

# サービス

どのツールを使うべきか迷う場合は、[rdc vs renet](/ja/docs/rdc-vs-renet) を参照してください。

このページでは、コンテナ化されたサービスのデプロイと管理方法について説明します：Rediaccfile、サービスネットワーキング、開始/停止、一括操作、自動開始。

## Rediaccfile

**Rediaccfile**は、サービスの開始と停止の方法を定義するBashスクリプトです。ファイル名は`Rediaccfile`または`rediaccfile`（大文字小文字を区別しない）で、リポジトリのマウントされたファイルシステム内に配置する必要があります。

Rediaccfileは2つの場所で検出されます：
1. リポジトリマウントパスの**ルート**
2. マウントパスの**第1レベルサブディレクトリ**（再帰的ではありません）

隠しディレクトリ（`.`で始まる名前）はスキップされます。

### ライフサイクル関数

Rediaccfileは最大2つの関数を含みます：

| 関数 | 実行タイミング | 目的 | エラー動作 |
|----------|-------------|---------|----------------|
| `up()` | 開始時 | サービスの開始（例：`renet compose -- up -d`） | ルートの失敗は**クリティカル**（すべて停止）。サブディレクトリの失敗は**非クリティカル**（ログに記録し、次に進む） |
| `down()` | 停止時 | サービスの停止（例：`renet compose -- down`） | **ベストエフォート** -- 失敗はログに記録されますが、すべてのRediaccfileが常に試行 |

両方の関数はオプションです。関数が定義されていない場合、サイレントにスキップされます。

### 実行順序

- **開始（`up`）：** ルートRediaccfileが最初、次にサブディレクトリが**アルファベット順**（AからZ）。
- **停止（`down`）：** サブディレクトリが**逆アルファベット順**（ZからA）、最後にルート。

### 環境変数

Rediaccfile関数の実行時、以下の環境変数が利用可能です：

| 変数 | 説明 | 例 |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | リポジトリのマウントパス | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | リポジトリGUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ネットワークID（整数） | `2816` |
| `DOCKER_HOST` | このリポジトリの隔離デーモン用Dockerソケット | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json`で定義された各サービスのループバックIP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP`変数は`.rediacc.json`から自動生成されます。命名規則では、サービス名を大文字に変換し、ハイフンをアンダースコアに置き換え、`_IP`を付加します。例えば、`listmonk-app`は`LISTMONK_APP_IP`になります。

> **警告：Rediaccfile内で`sudo docker`を使用しないでください。** `sudo`コマンドは環境変数をリセットするため、`DOCKER_HOST`が失われ、Dockerコマンドがリポジトリの隔離デーモンではなくシステムデーモンを対象にします。これによりコンテナの隔離が壊れ、ポート競合が発生する可能性があります。Rediaccは`-E`なしの`sudo docker`を検出すると実行をブロックします。
>
> Rediaccfile内では`renet compose`を使用してください。`DOCKER_HOST`を自動的に処理し、ルート検出用のネットワーキングラベルを注入し、サービスネットワーキングを設定します。リバースプロキシ経由でサービスを公開する方法の詳細については、[ネットワーキング](/ja/docs/networking)を参照してください。Dockerを直接呼び出す場合は、`sudo`なしで`docker`を使用してください。Rediaccfile関数は既に十分な権限で実行されます。sudoを使用する必要がある場合は、環境変数を保持するために`sudo -E docker`を使用してください。

### 例

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **重要:** `docker compose`の代わりに常に`renet compose --`を使用してください。`renet compose`ラッパーは、ホストネットワーキング、IPアロケーション、およびrenet-proxyに必要なサービスディスカバリラベルを強制適用します。CRIUチェックポイント/リストア機能は`rediacc.checkpoint=true`ラベル付きコンテナに追加されます。`docker compose`の直接使用はRediaccfileのバリデーションで拒否されます。詳細については[ネットワーキング](/ja/docs/networking)を参照してください。

### マルチサービスレイアウト

複数の独立したサービスグループを持つプロジェクトでは、サブディレクトリを使用します：

```
/mnt/rediacc/mounts/my-app/
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

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**例**：ネットワークID `2816`（`0x0B00`）の場合、ベースアドレスは`127.0.11.0`：

| サービス | スロット | IPアドレス |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

各リポジトリは最大**61個のサービス**（スロット0から60）をサポートします。

### Docker ComposeでのサービスIPの使用

各リポジトリは隔離されたDockerデーモンを実行するため、`renet compose`はすべてのサービスに対して自動的に`network_mode: host`を設定します。カーネルは`bind()`呼び出しをサービスに割り当てられたループバックIPに透過的に書き換えるため、サービスは競合なく`0.0.0.0`や`localhost`にバインドできます。**他のサービスへの接続**には**サービス名**を使用してください -- renetはすべてのサービス名を常に正しいIPに解決するホスト名として注入します（フォークでも同様）：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # 明示的なlisten_addressesは不要 -- カーネルがbindを正しいループバックIPに書き換えます

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # サービス名を使用
      LISTEN_ADDR: 0.0.0.0:8080                                      # カーネルがサービスIPに書き換え
```

> **接続へのサービス名の使用：** 他のサービスへ**接続する**際は**サービス名**（例：`postgres`、`redis`）を使用してください -- renetは`/etc/hosts`経由で各サービス名をそのループバックIPに自動的にマッピングします。データベースや設定ファイルに保存された接続文字列に`${POSTGRES_IP}`を埋め込むと生のIPが固定され、フォークの隔離を壊す**バリデーションエラー**になります。`${SERVICE_IP}`変数は明示的な使用のために引き続き利用可能ですが、バインドはカーネルが自動的に処理します。

> **注意：** `network_mode: host`を手動で追加しないでください, `renet compose`が自動的に注入します。再起動ポリシー（例：`restart: always`）は安全に使用できます, renetがCRIU互換性のために自動的に削除し、ルーターウォッチドッグがコンテナの回復を処理します。

### コンテナの回復と再起動ポリシー

renetとDockerは、コンテナの再起動処理について意図的に見解が異なります。この分離を理解することは、コンテナが戻った（戻らなかった）理由をデバッグする際に重要です。

**再起動ポリシーの変換。** composeファイルに`restart: always`（または`unless-stopped`、`on-failure`）を書くと、renetは実際のcomposeデプロイメントを合成する際にそれを**削除**し、`restart: no`に置き換えます。元の値はリポジトリの`.rediacc.json`の`services.<name>.restart_policy`に保存されます。これにより、DockerデーモンレベルのAuto-RestartがCRIUチェックポイント/リストアを妨げるのを防ぎます（デーモン主導の再起動は古いチェックポイント前の状態から再開します）。

**ウォッチドッグの適用。** ルーターウォッチドッグは各マシンで定期的に実行されます。各ティックで：

1. 各リポジトリの`.rediacc.json`を読み込み、回復可能な`restart_policy`を持つサービスを見つけます。
2. そのリポジトリのデーモンのすべてのコンテナをリストし、停止しているものを特定し、保存されたポリシーに従って再起動します。30秒のグレース期間により、`docker stop`を実行したオペレーターとの競合を防ぎます。
3. 同じループは`/var/run/rediacc/cold-backup-<guid>.running.json`も処理します（[コールドバックアップのセマンティクス](backup-restore.md#cold-backup-semantics)を参照）。リストされたコンテナは保存されたポリシーに関わらず再起動されます。サイドカーは「renetがこれらを意図的に停止し、オペレーターへの再起動を約束している」ことを意味するからです。

**`on-failure`が壊れて見える理由。** Dockerの`on-failure`ポリシーは、コンテナが非ゼロコードで終了した場合にのみ再起動します。`docker stop`やデーモンのシャットダウンによる正常な停止（exit 0）は「失敗」ではなく、Dockerのネイティブロジックでもウォッチドッグのポリシーパスでも再起動を**トリガーしません**。コールドバックアップサイドカーがセーフティネットです：意図的に停止したコンテナはポリシーに関わらず再起動されます。

**ランタイム状態の解釈方法：**

- `docker inspect <container>` → `RestartPolicy.Name`：renet管理コンテナでは常に`no`になります。セマンティックポリシーの判断には使用しないでください。
- リポジトリマウントルートの`.rediacc.json` → `services.<name>.restart_policy`：真の意図。
- `docker ps --format '{{.Status}}'`：ランタイム状態。

**ドリフトの修正方法。** コンテナの`.rediacc.json`に保存されたポリシーが誤っている場合（例：composeを編集したがコンテナを再作成しなかった場合）、`rdc repo up --name <repo> -m <machine>`を再実行してください。コンテナは更新されたポリシーを記録した状態で再作成されます。

> **実験的：** コールドバックアップサイドカーベースの回復と`rdc machine query`の`--sync-certs`フラグはrenet 0.9+で導入されました。古いバージョンはウォッチドッグ回復のために保存された`restart_policy`のみに依存するため、コールドバックアップ後に`on-failure`コンテナが孤立する可能性があります。

> **Docker のブリッジネットワーキングはリポジトリごとのデーモンでは無効化されています。** リポジトリごとの各デーモン（`FlavorRediacc`）は `"bridge": "none"` と `"iptables": false` で構成されています。リポジトリシェル内で単純に `docker run <image>` を実行してもコンテナは起動しますが、ループバックインターフェースしか持たず、DNS も外向きの接続性もありません。これは仕様です。なぜなら、リポジトリ間のループバック分離は eBPF の cgroup フックによって強制されており、ブリッジ化されたコンテナはそれを迂回してしまうからです。本番サービスは `renet compose` を使用してください（ホストネットワーキングを自動で注入してくれます）。アドホックなデバッグでは、明示的に `--network host` を指定してください: `docker run --rm --network host -it ubuntu bash`。
>
> ユーザーごとの Hub デーモン（`FlavorHub`、開発環境で使用）は例外です。これらは `bridge="docker0"`、`iptables=true`、`live-restore=true` を設定することで、ユーザーが実行するコンテナが通常のブリッジネットワーキングと外向きの接続性を利用できるようにします。

> **注意：** Forkリポジトリは親のサブドメイン下に自動ルートを取得します：`{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`。カスタムドメインはforkでは省略されます。

## サービスの開始

リポジトリをマウントし、すべてのサービスを開始します：

```bash
rdc repo up --name my-app -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップ |

実行シーケンスは以下の通りです：
1. LUKS暗号化リポジトリをマウント（未マウントの場合は自動マウント）
2. 隔離Dockerデーモンを起動
3. composeファイルから`.rediacc.json`を自動生成
4. すべてのRediaccfileで`up()`を実行（A-Z順）

デプロイ後、出力には各サービスの実際のURLを示す**PROXY ROUTES**セクションが表示されます。カスタムTraefikラベルを持つサービスはカスタムドメインをプライマリURLとして表示します：

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

## サービスの停止

```bash
rdc repo down --name my-app -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--unmount` | 停止後に暗号化リポジトリをアンマウント。効果が現れない場合は、`rdc repo unmount` を別途使用してください。 |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップ |

実行シーケンスは以下の通りです：
1. すべてのRediaccfileで`down()`を実行（Z-A逆順、ベストエフォート）
2. 隔離Dockerデーモンを停止（`--unmount`の場合）
3. LUKS暗号化ボリュームをアンマウントおよびクローズ（`--unmount`の場合）

## 一括操作

マシン上のすべてのリポジトリを一度に開始または停止します：

```bash
rdc repo up -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--include-forks` | フォークされたリポジトリを含める |
| `--mount-only` | マウントのみ行い、コンテナは起動しない |
| `--dry-run` | 実行される操作を表示 |
| `--parallel` | 操作を並列実行 |
| `--concurrency <n>` | 最大同時操作数（デフォルト：3） |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップ |

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
rdc repo autostart enable --name my-app -m server-1
```

リポジトリのパスフレーズの入力を求められます。

### すべてを有効化

```bash
rdc repo autostart enable -m server-1
```

### 無効化

```bash
rdc repo autostart disable --name my-app -m server-1
```

これによりキーファイルが削除され、LUKSスロット1が無効化されます。

### デプロイ時のキーファイル更新

自動開始が有効な場合、`rdc repo up`はLUKSスロット1のキーファイルを検証します。
ディスク上のキーファイルがまだLUKSスロットと一致する場合、変更は行われません。

`repo push` / `repo pull`でリポジトリをマシン間で転送した後、
新しいマシン上のキーファイルは一致しません。この場合、`repo up`は自動的に
キーファイルを再生成してLUKSスロット1を更新します。以下のログメッセージが表示されます：

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

これは安全です。スロット0（パスフレーズ）は変更されません。自動開始が
有効でない場合、チェックはサイレントにスキップされます。失敗は致命的でなく、デプロイをブロックしません。

### ステータスの一覧表示

```bash
rdc repo autostart list -m server-1
```

## 完全な例

この例では、PostgreSQL、Redis、APIサーバーを含むWebアプリケーションをデプロイします。

### 1. セットアップ

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. マウントと準備

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. アプリケーションファイルの作成

リポジトリ内に以下のファイルを作成します：

**docker-compose.yml：**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile：**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up --name webapp -m prod-1
```

### 5. 自動開始の有効化

```bash
rdc repo autostart enable --name webapp -m prod-1
```
