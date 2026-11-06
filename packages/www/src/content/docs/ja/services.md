---
title: サービス
description: >-
  Rediaccfile、サービスネットワーキング、自動開始を使用してコンテナ化されたサービスをデプロイおよび管理します。
category: Guides
tags:
  - containers
  - operations
subcategory: workloads
order: 5
language: ja
sourceHash: "c0f1046e3af31219"
sourceCommit: "40b28261b0fa1018c0268405cbfdb899ab283c06"
---

# サービス

このページでは、以下の内容を説明します：コンテナ化されたサービスのデプロイと管理、Rediaccfile、サービスネットワーキング、開始/停止、一括操作、自動開始。

## Rediaccfile

**Rediaccfile**は、サービスの開始と停止方法を定義するBashスクリプトです。（別プロセスとして実行されるのではなく）**ソースされる**ため、関数は同じシェルコンテキストを共有し、エクスポートされたすべての環境変数にアクセスできます。ファイル名は`Rediaccfile`または`rediaccfile`（大文字小文字を区別しない）で、リポジトリのマウントされたファイルシステム内に配置する必要があります。

Rediaccfileは2つの場所で検出されます：
1. リポジトリマウントパスの**ルート**
2. マウントパスの**第1レベルサブディレクトリ**（再帰的ではありません）

隠しディレクトリ（`.`で始まる名前）はスキップされます。

### ライフサイクル関数

Rediaccfileは最大2つの関数を含みます：

| 関数 | 実行タイミング | 目的 | エラー動作 |
|----------|-------------|---------|----------------|
| `up()` | 開始時 | サービスの開始（例：`renet compose -- up -d`） | ルートの失敗は**クリティカル**（すべて停止）。サブディレクトリの失敗は**非クリティカル**（ログに記録し、続行） |
| `down()` | 停止時 | サービスの停止（例：`renet compose -- down`） | **ベストエフォート** - 失敗はログに記録されますが、すべてのRediaccfileが常に試行されます |

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
| `DOCKER_HOST` | このリポジトリの隔離デーモン用Dockerソケット | `unix:///var/run/rediacc/net-2816/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json`で定義された各サービスのループバックIP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP`変数は`.rediacc.json`のスロットマッピングから自動生成され、Rediaccfile関数が実行される前にエクスポートされます。命名規則では、サービス名を大文字に変換し、ハイフンをアンダースコアに置き換え、`_IP`を付加します。例えば、スロット`0`の`listmonk-app`というサービスは`LISTMONK_APP_IP=127.0.11.2`になります。

> **警告：Rediaccfile内で`sudo docker`を使用しないでください。** `sudo`コマンドは環境変数をリセットするため、`DOCKER_HOST`が失われ、Dockerコマンドがリポジトリの隔離デーモンではなくシステムデーモンを対象にします。これによりコンテナの隔離が壊れ、ポート競合が発生する可能性があります。Rediaccは`sudo docker`を検出すると実行をブロックします。
>
> Rediaccfile内では`renet compose`を使用してください。`DOCKER_HOST`を自動的に処理し、ルート検出用のネットワーキングラベルを注入し、サービスネットワーキングを設定します。リバースプロキシ経由でサービスを公開する方法の詳細については、[ネットワーキング](/ja/docs/networking)を参照してください。Dockerを直接呼び出す場合は、`sudo`なしで`docker`を使用してください。Rediaccfile関数は、rootではなくユニバーサルユーザーとしてリポジトリのDockerデーモンに接続します（[権限](/ja/docs/services#privileges)を参照）。
>
> `renet`はリモートロー・レベルツールです。ワークステーションから通常のユーザー作業フローを行う場合は、`rdc repo up`や`rdc repo down`などの`rdc`コマンドを優先してください。[rdc vs renet](/ja/docs/rdc-vs-renet)を参照してください。

### 権限

`up()`と`down()`は、読み書きできる場所を制限するサンドボックスの中で、rootではなくユニバーサルユーザー（`rediacc`）として実行されます。環境は継承ではなく関数ごとに組み立てられるため、上記の変数、リポジトリの`REDIACC_SECRET_*`の値、最小限の`PATH`だけを持ちます。`sudo`はどのティアでも使えません。サンドボックスが`no_new_privs`を設定するので、`sudo`を使うRediaccfileの行は失敗し、`sudo`を外す必要があります。Landlockのないマシンは、`up()`と`down()`を制限なしで実行せず、実行を拒否します。

デフォルトを超える権限が必要な行は、サンドボックスが返すエラーで失敗します。ジャーナルとCLIは、該当するRediaccfileの行をグラントのコマンドとともに表示します。

| Rediaccfileの処理 | 見えるもの | 対処 |
|---|---|---|
| `sudo x` | `sudo: The "no new privileges" flag is set` | `sudo`を外す。そのステップはrootが不要か、グラントが必要 |
| `chown 5050 ...`、またはコンテナが所有するディレクトリへの`rm -rf` | `Operation not permitted`または`Permission denied` | ステップを使い捨てコンテナで実行する（rootになるのはコンテナ内のみで、マシン上ではありません）：`renet compose -- run --rm --no-deps --user 0 --entrypoint chown <service> -R 5050:5050 /data` |
| マウント内の`.env`などのファイルへの書き込み | 動作する。ファイルの所有者はユニバーサルユーザー | 不要 |
| `/etc/rediacc/*`、`/proc/kcore`、ブロックデバイスの読み取り | `Permission denied` | パスのグラントを依頼する |
| ファイルシークレットを直接読み取る | `Permission denied` | composeの`secrets:`、またはenvモードのシークレットを使う |
| デバイスのグラントなしで`nvidia-smi` | デバイスが見つからない | デバイスをグラントする。[GPU](/ja/docs/gpu)を参照 |
| `sysctl -w` | `Permission denied` | 管理者としてマシンに一度だけ設定する |

#### グラントを依頼する

グラントは、`up()`と`down()`が到達できる範囲を広げます。グラントを与えられるのはオペレーターだけで、リポジトリの外から行います。

```bash
rdc repo permission grant <repo-ref> --path /srv/data:rw
rdc repo permission grant <repo-ref> --root
rdc repo permission show <repo-ref>
rdc repo permission revoke <repo-ref> --path /srv/data
```

`--path`はLandlockのルールを1つ追加します。`:rw`を付けない限り読み取り専用です。マシンは、別のリポジトリ、データストア、`/etc/rediacc`に届くパスを拒否します。`--root`は権限を落とさず、関数をrootとして実行し、コールドバックアップはそのようなリポジトリを拒否します。エージェントが起動する前にオペレーターが`REDIACC_ALLOW_GRAND_REPO`を設定していない限り、エージェントは`--root`を与えられません。フォークは新しいネットワークIDを持ち、グラントなしで始まります。再利用されたネットワークIDで見つかったグラントは破棄されます。

Rediaccfileは、必要なものをコメント行で宣言できます。これはあくまで依頼です。

```bash
# rediacc:needs root
# rediacc:needs path=/srv/data
# rediacc:needs device=nvidia.com/gpu=all
```

`up()`は宣言をグラントと照合します。グラントがない場合、`up()`はどの行も実行される前に拒否され、メッセージに正確なグラントのコマンドが表示されます。`down()`は宣言を確認しないため、リポジトリ内で編集したコメントによってオペレーターの`repo down`が止められることはありません。グラントが本当に必要な`down()`は、そのステップ自身で失敗します。`machine converge`は、拒否される状態に再起動する代わりに、そのようなリポジトリを`needs_lifecycle_grant`としてスキップします。

### タイムアウトとシャットダウンの順序

リポジトリのコンテナは、その `down()` が実行されて終了するまで停止しません。対象は、リポジトリの Docker ユニットに対する `systemctl stop` と `restart`、`machine converge`、`repo down --unmount`、ユニットの書き換え、ホストのシャットダウンです。例外は、Docker デーモンまたはホストのクラッシュ、停電、ホストのシャットダウン時でも `systemctl stop` や `restart` の際でも、タイムアウトを超えた `down()` です。その `down()` は終了され、停止は後述のとおり続行されます。

各 Docker ユニットは、デーモンにシグナルを送る前に停止フックを実行します。フックは、このデーモンの起動で renet がすでに実行済みでない限り、稼働中のデーモンに対して `down()` を実行し、デーモンが応答しない場合やリポジトリに Rediaccfile がない場合は実行しません。ホストのシャットダウンでは、まず Docker ユニットが停止して各々が `down()` を並列実行し、その後クリーンアップ用ユニットが、自動起動の有無にかかわらずマウント中のすべてのリポジトリをアンマウントします。ユニットの停止猶予は 17 分で、再起動ジョブの 30 分の上限に収まります。このフックの中で `down()` がタイムアウトすると、そのプロセスグループには SIGTERM が送られ、10 秒後に SIGKILL が送られ(`FunctionKillGrace`、`pkg/orchestration/procgroup.go`)、警告がログに記録され、フックは終了コード 0 で終わるため、systemd は停止を続けます。したがってタイムアウトした `down()` が `systemctl stop` や再起動を遅らせるのは最大でタイムアウト+10 秒(上限で 15 分 10 秒)で、停止はユニットの `TimeoutStopSec`(17 分)に収まります。停止を拒否するのは、`repo down --unmount` のような renet 自身の経路だけです。

`up()` と `down()` の既定値はそれぞれ 10 分で、`RENET_UP_TIMEOUT` と `RENET_DOWN_TIMEOUT`、または `--up-timeout` と `--down-timeout` で設定します。タイムアウトすると、プロセスグループに SIGTERM が送られ、10 秒後に SIGKILL が送られます。`repo down --unmount` や converge による再起動のように先に `down()` が必要な操作は、`down()` がタイムアウトした場合にコンテナを動かしたままにし、`--force` を付けると続行します。Rediaccfile はコメント行で上限を引き上げられます。

```bash
# rediacc:timeout up=20m down=15m backup=120s
```

| キー | 既定値 | 上限 |
|---|---|---|
| `up` | 10 分 | 60 分 |
| `down` | 10 分 | 15 分 |
| `backup` | 30 秒 | 300 秒 |

ディレクティブは制限を引き上げるだけで、上限を超える値は上限に切り詰められます。そのためリポジトリ側から `down()` を短くして強制終了させることはできません。未知のキーは警告を出して無視されます。

リポジトリのデーモンでは Docker の `live-restore` を無効のままにします。有効にすればデーモンの再起動後もコンテナは残りますが、コンテナの shim はユニットの cgroup を共有していて一緒に終了するため、復元後のデーモンは再接続できず、計画停止の間もコンテナがマウントを保持し続けてしまいます。

renet が管理するリポジトリごとの RAM ボリューム(`# rediacc:ram size=6G`、ホストの RAM はオペレーターが割り当てます)は設計段階で、まだ実装されていません。

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

> **重要：** `docker compose`の代わりに常に`renet compose --`を使用してください。`renet compose`ラッパーは、ホストネットワーキング、IPアロケーション、およびrenet-proxyに必要なサービスディスカバリラベルを強制適用します。CRIUチェックポイント/リストア機能は`rediacc.checkpoint=true`ラベル付きコンテナに追加されます。直接的な`docker compose`の使用はRediaccfileのバリデーションで拒否されます。詳細については[ネットワーキング](/ja/docs/networking)を参照してください。

### ケーパビリティラベル

コンテナはデフォルトで最小限のLinuxケーパビリティセットで動作します。サービスが追加のケーパビリティを必要とする場合は、`docker-compose.yml`にラベルを追加してオプトインします：

| ラベル | 付与されるもの | 用途 |
|-------|--------|---------|
| `rediacc.checkpoint=true` | `CHECKPOINT_RESTORE`、`SYS_PTRACE`、`NET_ADMIN` | CRIUチェックポイント/リストア（ライブマイグレーション、保存と再開） |
| `rediacc.wireguard=true` | `NET_ADMIN` と `/dev/net/tun` デバイス | コンテナ内でWireGuardクライアントを実行 |

```yaml
services:
  vpn:
    image: alpine
    labels:
      - "rediacc.wireguard=true"
```

`rediacc.wireguard` を使うと、サービスからWireGuardトンネルを確立できます。たとえば、特定のプロセスのトラフィックをリモートエンドポイント経由でルーティングする場合などに活用できます。すべてのサービスはホストネットワーキングで動作するため、ホストのルーティングに影響が出ないよう、トンネルはコンテナ内のネットワーク名前空間に閉じ込めてください。`privileged: true`、`pid: host`、`ipc: host` などの広範な特権オプションは、ラベルに関わらず、composeのバリデーションでもDocker API上でも拒否されます。Docker APIではリポジトリのデーモンが `403` を返します。

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

サービスのIPは、リポジトリのネットワークIDとサービスのスロットから計算されます。ネットワークIDは`127.x.y.z`ループバックアドレスの第2、第3、第4オクテットに分割されます。サービスはオフセット2から開始します：

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 - .62 | `127.0.11.2` - `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**例**：ネットワークID `2816`（`0x0B00`）の場合、ベースアドレスは`127.0.11.0`：

| サービス | スロット | IPアドレス |
|---------|------|------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

各リポジトリは最大**61個のサービス**（スロット0から60）をサポートします。

### Docker ComposeでのサービスIPの使用

各リポジトリは隔離されたDockerデーモンを実行するため、`renet compose`はすべてのサービスに対して自動的に`network_mode: host`を設定します。カーネルは`bind()`呼び出しをサービスに割り当てられたループバックIPに透過的に書き換えるため、サービスは競合なく`0.0.0.0`や`localhost`にバインドできます。**他のサービスへの接続**には**サービス名**を使用してください。renetはすべてのサービス名を常に正しいIPに解決するホスト名として注入します（フォークでも同様）：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # 明示的なlisten_addressesは不要 - カーネルがbindを正しいループバックIPに書き換えます

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # サービス名を使用
      LISTEN_ADDR: 0.0.0.0:8080                                      # カーネルがサービスIPに書き換え
```

> **接続へのサービス名の使用：** 他のサービスへ**接続する**際は**サービス名**（例：`postgres`、`redis`）を使用してください - renetは`/etc/hosts`経由で各サービス名をそのループバックIPに自動的にマッピングします。データベースや設定ファイルに保存された接続文字列に`${POSTGRES_IP}`を埋め込むと生のIPが固定され、フォークの隔離を壊す**バリデーションエラー**になります。`${SERVICE_IP}`変数は明示的な使用のために引き続き利用可能ですが、バインドはカーネルが自動的に処理します。

> **注意：** `network_mode: host`を手動で追加しないでください。`renet compose`が自動的に注入します。再起動ポリシー（例：`restart: always`）は安全に使用できます。renetはCRIU互換性のために自動的に削除し、ルーターウォッチドッグがコンテナの回復を処理します。

### コンテナの回復と再起動ポリシー

renetとDockerは、コンテナの再起動処理について意図的に見解が異なります。この分離を理解することは、コンテナが戻った（戻らなかった）理由をデバッグする際に重要です。

**再起動ポリシーの変換。** composeファイルに`restart: always`（または`unless-stopped`、`on-failure`）を書くと、renetは実際のcomposeデプロイメントを合成する際にそれを**削除**し、`restart: no`に置き換えます。元の値はリポジトリの`.rediacc.json`の`services.<name>.restart_policy`に保存されます。これにより、DockerデーモンレベルのAuto-RestartがCRIUチェックポイント/リストアを妨げるのを防ぎます（デーモン主導の再起動は古いチェックポイント前の状態から再開します）。

**ウォッチドッグの適用。** ルーターウォッチドッグは各マシンで定期的に実行されます。各ティックで：

1. 各リポジトリの`.rediacc.json`を読み込み、回復可能な`restart_policy`を持つサービスを見つけます。
2. そのリポジトリのデーモンのすべてのコンテナをリストし、停止しているものを特定し、保存されたポリシーに従って再起動します。30秒のグレース期間により、`docker stop`を実行したオペレーターとの競合を防ぎます。
3. 同じループは`/var/run/rediacc/cold-backup-<guid>.running.json`も処理します（[コールドバックアップのセマンティクス](backup-restore.md#cold-backup-semantics)を参照）。リストされたコンテナは保存されたポリシーに関わらず再起動されます。サイドカーは「renetがこれらを意図的に停止し、オペレーターへの再起動を約束している」ことを意味するからです。

**`on-failure`が壊れて見える理由。** Dockerの`on-failure`ポリシーは、コンテナが非ゼロコードで終了した場合にのみ再起動します。`docker stop`やデーモンのシャットダウンによる正常な停止（exit 0）は「失敗」ではなく、Dockerのネイティブロジックでもウォッチドッグのポリシーパスでも再起動を**トリガーしません**。コールドバックアップサイドカーがセーフティネットです：意図的に停止したコンテナはポリシーに関わらず再起動されます。

**ランタイム状態の解釈方法：**

- `docker inspect <container>` -> `RestartPolicy.Name`：renet管理コンテナでは常に`no`になります。セマンティックポリシーの判断には使用しないでください。
- リポジトリマウントルートの`.rediacc.json` -> `services.<name>.restart_policy`：真の意図。
- `docker ps --format '{{.Status}}'`：ランタイム状態。

**ドリフトの修正方法。** コンテナの`.rediacc.json`に保存されたポリシーが誤っている場合（例：composeを編集したがコンテナを再作成しなかった場合）、`rdc repo up <repo>`を再実行してください。コンテナは更新されたポリシーを記録した状態で再作成されます。

> **実験的：** コールドバックアップサイドカーベースの回復と`rdc machine status`の`--sync-certs`フラグはrenet 0.9+で導入されました。古いバージョンはウォッチドッグ回復のために保存された`restart_policy`のみに依存するため、コールドバックアップ後に`on-failure`コンテナが孤立する可能性があります。

> **Docker のブリッジネットワーキングはリポジトリごとのデーモンでは無効化されています。** リポジトリごとの各デーモン（`FlavorRediacc`）は `"bridge": "none"` と `"iptables": false` で構成されています。リポジトリシェル内で単純に `docker run <image>` を実行してもコンテナは起動しますが、ループバックインターフェースしか持たず、DNS も外向きの接続性もありません。これは仕様です。なぜなら、リポジトリ間のループバック分離は eBPF の cgroup フックによって強制されており、ブリッジ化されたコンテナはそれを迂回してしまうからです。本番サービスは `renet compose` を使用してください（ホストネットワーキングを自動で注入してくれます）。アドホックなデバッグでは、明示的に `--network host` を指定してください: `docker run --rm --network host -it ubuntu bash`。
>
> ユーザーごとの Hub デーモン（`FlavorHub`、開発環境で使用）は例外です。これらは `bridge="docker0"`、`iptables=true`、`live-restore=true` を設定することで、ユーザーが実行するコンテナが通常のブリッジネットワーキングと外向きの接続性を利用できるようにします。

> **注意：** Forkリポジトリは親のサブドメイン下に自動ルートを取得します：`{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`。カスタムドメインはforkでは省略されます。

## サービスの開始

リポジトリをマウントし、すべてのサービスを開始します：

```bash
rdc repo up my-app
```

| オプション | 説明 |
|--------|-------------|
| `--no-wait` | コンテナ起動後すぐに返す。ヘルスチェックはバックグラウンドで継続 |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップ |

実行シーケンスは以下の通りです：
1. LUKS暗号化リポジトリをマウント（未マウントの場合は自動マウント）
2. 隔離Dockerデーモンを起動
3. composeファイルから`.rediacc.json`を自動生成
4. すべてのRediaccfileで`up()`を実行（A-Z順）

デプロイ後、出力には各サービスの実際のURLを示す**PROXY ROUTES**セクションが表示されます。カスタムTraefikラベルを持つサービス（例：`traefik.http.routers.myapp.rule=Host(...)`）は、カスタムドメインをプライマリURLとして表示します：

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

カスタムTraefikラベルを持たないサービスは、自動生成されたルートのみを表示します。ブラウザアクセス、API呼び出し、サービス間設定にはこれらのURL（CLIで表示される汎用パターンではなく）を使用してください。

### デタッチ起動

`--no-wait` を指定すると、ヘルスチェックの完了を待たず、コンテナが起動した時点でコマンドが返ります。起動の残りはバックグラウンドで進行します。プロキシは各サービスがバインドするまでアップストリーム接続を自動的に再試行するため、ルートは自然に回復します。進捗は `rdc machine status <machine> --containers` で確認できます。次のステップでサービスが揃っている必要のないスクリプトや使い捨てフォークに最適です。

### 準備完了プローブ

`up()` の実行後、renet は各 HTTP サービスが TCP 接続を受け入れるまでプローブを続けます。これにより、ブラウザからの最初のリクエストがプロキシの 502 に当たるのを防ぎます。Docker ヘルスチェックを定義しているコンテナはそのシグナルが優先されます。healthy なコンテナはプローブをスキップし、`start_period` 中のコンテナは警告ではなく情報ログを出します。プローブは 15 秒でタイムアウトします（マシン上の環境変数 `REDIACC_READINESS_TIMEOUT` に秒数を設定することで変更できます）。デタッチ起動ではプローブ自体がスキップされます。

## サービスの停止

```bash
rdc repo down my-app
```

| オプション | 説明 |
|--------|-------------|
| `--unmount` | 停止後に暗号化リポジトリをアンマウント。 |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップ |

実行シーケンスは以下の通りです：
1. すべてのRediaccfileで`down()`を実行（Z-A逆順、ベストエフォート）
2. 隔離Dockerデーモンを停止（`--unmount`の場合）
3. LUKS暗号化ボリュームをアンマウントおよびクローズ（`--unmount`の場合）

## 一括操作

マシン上のすべてのリポジトリを一度に開始または停止します：

```bash
rdc repo up --all -m server-1
```

| オプション | 説明 |
|--------|-------------|
| `--include-forks` | フォークされたリポジトリを含める |
| `--no-start` | マウントと準備のみ実行し、リポジトリの`up()`は実行しない |
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
rdc repo admin autostart enable my-app
```

リポジトリのパスフレーズの入力を求められます。

### すべてを有効化

```bash
rdc repo admin autostart enable
```

### 無効化

```bash
rdc repo admin autostart disable my-app
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
rdc repo admin autostart list -m server-1
```

起動後に停止したリポジトリを定期リコンサイラーが回復する仕組みの詳細については、[自動開始と回復](/ja/docs/autostart-recovery)を参照してください。

## 完全な例

この例では、PostgreSQL、Redis、APIサーバーを含むWebアプリケーションをデプロイします。

### 1. セットアップ

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init production --ssh-key ~/.ssh/id_ed25519
rdc machine add prod-1 --ip 203.0.113.50 --user deploy
rdc machine setup prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. マウントと準備

```bash
rdc repo up webapp --no-start
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
rdc repo up webapp
```

### 5. 自動開始の有効化

```bash
rdc repo admin autostart enable webapp
```

## composeでリポジトリごとのシークレットを使用する

上記の`POSTGRES_PASSWORD: changeme`プレースホルダーはチュートリアル用ですが、実アプリケーションは実クレデンシャルが必要で、composeファイル（またはリポジトリ内の`.env`ファイル）にコミットするということは、フォークもそれを継承することを意味します。デプロイ時のクレデンシャルについては、`rdc repo secret`を使用してください。値は暗号化リポジトリイメージの外側にあるため、フォークは空のシークレットマップで開始します。

composeで機能する2つの配信モードがあります：

**`env`モード**。任意の`environment:`値内で`${REDIACC_SECRET_<KEY>}`を使用して補間します。renetラッパーはデプロイ時にコンテナの環境に値を渡します。

**`file`モード**。値はホスト側のtmpfsファイル（`/var/run/rediacc/net-<networkID>/secrets/<KEY>`）に配置され、Dockerのcomposeの標準`secrets:`ブロック経由でコンテナにマウントします。コンテナは`/run/secrets/<key>`を読みます。何か機密情報がある場合はこのモードを優先してください。値は`docker inspect`や`/proc/<pid>/environ`に表示されません。

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/net-${REDIACC_NETWORK_ID}/secrets/STRIPE_LIVE_KEY
```

`rdc repo secret set <repo> --key DATABASE_URL --value <val> --mode env --current ""`でファイルモード相当の値をシードします。詳細については[リポジトリ » シークレット](/ja/docs/repositories#secrets)を参照し、コマンドリファレンスについてはチートシートの[リポジトリごとのシークレット](/ja/docs/rdc-cheat-sheet#per-repo-secrets)を参照してください。

> **クロスリポパスはバリデーション時に拒否されます。** composeの`secrets: file:`（または`configs: file:`、または`env_file:`）が別のリポジトリの`/var/run/rediacc/net-<other-networkID>/secrets/`ディレクトリを指していると、renetラッパーによって`docker compose`実行前に厳密に拒否されます。`--unsafe`はオーバーライドしません。深層防御：Rediaccfileシェルの周囲のLandlockサンドボックスはリードを現在のネットワークのシークレットディレクトリにスコープするため、YAMLバリデーターをバイパスしても、Rediaccfileのbashから`cat /var/run/rediacc/net-<other>/secrets/X`を実行するとEACCESで失敗します。オプトインする必要はありません。これはすべての`repo up`でデフォルトで有効です。
