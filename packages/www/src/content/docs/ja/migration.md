---
title: "移行ガイド"
description: "既存のプロジェクトを暗号化されたRediaccリポジトリに移行します。"
category: "Guides"
order: 11
language: ja
sourceHash: "5064d721c8cf32ff"
---

# 移行ガイド

既存のプロジェクト（ファイル、Dockerサービス、データベース）を従来のサーバーやローカル開発環境から暗号化されたRediaccリポジトリに移行します。

## 前提条件

- `rdc` CLIがインストール済み（[インストール](/ja/docs/installation)）
- マシンが追加・プロビジョニング済み（[セットアップ](/ja/docs/setup)）
- プロジェクトに十分なディスク容量がサーバーにあること（`rdc machine status`で確認）

## ステップ1：リポジトリを作成する

プロジェクトに合ったサイズの暗号化リポジトリを作成します。DockerイメージとコンテナデータのためにBに余裕を持たせてください。

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **ヒント：** 必要に応じて後から`rdc repo resize`でサイズ変更できますが、リポジトリは先にアンマウントする必要があります。最初から十分な容量で始めるほうが簡単です。

## ステップ2：ファイルをアップロードする

`rdc sync upload`を使用して、プロジェクトファイルをリポジトリに転送します。

```bash
# 転送内容のプレビュー（変更なし）
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# ファイルをアップロード
rdc sync upload -m server-1 -r my-project --local ./my-project
```

アップロード前にリポジトリがマウントされている必要があります。まだマウントされていない場合：

```bash
rdc repo mount my-project -m server-1
```

リモートをローカルディレクトリと完全に一致させたい後続の同期の場合：

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> `--mirror`フラグは、ローカルに存在しないリモートのファイルを削除します。まず`--dry-run`で確認してください。

## ステップ3：ファイル所有権を修正する

アップロードされたファイルはローカルユーザーのUID（例：1000）で到着します。Rediaccはユニバーサルユーザー（UID 7111）を使用し、VS Code、ターミナルセッション、ツールがすべて一貫したアクセスを持てるようにします。所有権コマンドを実行して変換します：

```bash
rdc repo ownership my-project -m server-1
```

### Docker対応の除外

Dockerコンテナが実行中（または実行されたことがある）の場合、所有権コマンドはコンテナの書き込み可能なデータディレクトリを自動的に検出し、**スキップします**。これにより、異なるUIDで独自のファイルを管理するコンテナ（例：MariaDBはUID 999、NextcloudはUID 33を使用）の破損を防ぎます。

コマンドは処理内容を報告します：

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### 実行タイミング

- **ファイルアップロード後** — ローカルUIDを7111に変換するため
- **コンテナ起動後** — DockerボリュームディレクトリBを自動除外したい場合。コンテナがまだ起動されていなければ、除外するボリュームがないため、すべてのディレクトリが変更されます（問題ありません — コンテナは初回起動時にデータを再作成します）

### 強制モード

Dockerボリューム検出をスキップして、コンテナデータディレクトリを含むすべてを変更するには：

```bash
rdc repo ownership my-project -m server-1 --force
```

> **警告：** 実行中のコンテナが破損する可能性があります。必要に応じて、先に`rdc repo down`で停止してください。

### カスタムUID

デフォルトの7111以外のUIDを設定するには：

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## ステップ4：Rediaccfileを設定する

プロジェクトのルートに`Rediaccfile`を作成します。このBashスクリプトは、サービスの準備、起動、停止方法を定義します。

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

3つのライフサイクル関数：

| 関数 | 目的 | エラー時の動作 |
|------|------|----------------|
| `prep()` | イメージの取得、マイグレーション実行、依存関係のインストール | 即時失敗：エラーが発生するとすべて停止 |
| `up()` | サービスの起動 | ルートの失敗は致命的；サブディレクトリの失敗はログに記録して続行 |
| `down()` | サービスの停止 | ベストエフォート：常にすべてを試行 |

> **重要：** Rediaccfileでは`docker`を直接使用してください — `sudo docker`は使わないでください。`sudo`コマンドは環境変数をリセットするため、`DOCKER_HOST`が失われ、コンテナがリポジトリの分離されたデーモンではなくシステムのDockerデーモン上に作成されてしまいます。Rediaccfile関数はすでに十分な権限で実行されています。詳細は[サービス](/ja/docs/services#environment-variables)を参照してください。

Rediaccfile、マルチサービスレイアウト、実行順序の詳細については、[サービス](/ja/docs/services)を参照してください。

## ステップ5：サービスネットワークを構成する

Rediaccはリポジトリごとに分離されたDockerデーモンを実行します。サービスは`network_mode: host`を使用し、一意のループバックIPにバインドすることで、リポジトリ間の競合なく標準ポートを使用できます。

### docker-compose.ymlを適応させる

**変更前（従来型）：**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**変更後（Rediacc）：**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

主な変更点：

1. **すべてのサービスに`network_mode: host`を追加**
2. **`ports:`マッピングを削除**（ホストネットワークでは不要）
3. **サービスを`${SERVICE_IP}`環境変数にバインド**（Rediaccが自動注入）
4. **Docker DNSの名前の代わりにIPで他のサービスを参照**（例：`postgres`の代わりに`${POSTGRES_IP}`）

`{SERVICE}_IP`変数はcomposeファイルのサービス名から自動生成されます。命名規則：大文字、ハイフンをアンダースコアに置換、`_IP`サフィックス。例えば、`listmonk-app`は`LISTMONK_APP_IP`になります。

IP割り当てと`.rediacc.json`の詳細については、[サービスネットワーク](/ja/docs/services#service-networking-rediaccjson)を参照してください。

## ステップ6：サービスを起動する

リポジトリをマウントし（まだマウントされていない場合）、すべてのサービスを起動します：

```bash
rdc repo up my-project -m server-1 --mount
```

これにより以下が実行されます：
1. 暗号化リポジトリのマウント
2. 分離されたDockerデーモンの起動
3. サービスIP割り当てを含む`.rediacc.json`の自動生成
4. すべてのRediaccfileから`prep()`を実行
5. すべてのRediaccfileから`up()`を実行

コンテナが稼働していることを確認します：

```bash
rdc machine containers server-1
```

## ステップ7：自動起動を有効にする（オプション）

デフォルトでは、サーバー再起動後にリポジトリを手動でマウントして起動する必要があります。自動起動を有効にして、サービスが自動的に起動するようにします：

```bash
rdc repo autostart enable my-project -m server-1
```

リポジトリのパスフレーズの入力を求められます。

> **セキュリティに関する注意：** 自動起動はサーバーにLUKSキーファイルを保存します。root権限を持つ誰でもパスフレーズなしでリポジトリをマウントできます。詳細は[自動起動](/ja/docs/services#autostart-on-boot)を参照してください。

## 一般的な移行シナリオ

### WordPress / PHPとデータベース

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPressファイル（実行時UID 33）
├── database/data/          # MariaDBデータ（実行時UID 999）
└── wp-content/uploads/     # ユーザーアップロード
```

1. プロジェクトファイルをアップロード
2. 最初にサービスを起動（`rdc repo up`）して、コンテナがデータディレクトリを作成するようにする
3. 所有権修正を実行 — MariaDBとアプリのデータディレクトリは自動的に除外されます

### Node.js / PythonとRedis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # アプリケーションソースコード
├── node_modules/           # 依存関係
└── redis-data/             # Redis永続化（実行時UID 999）
```

1. プロジェクトをアップロード（`node_modules`を除外して`prep()`で取得することを検討）
2. コンテナ起動後に所有権修正を実行

### カスタムDockerプロジェクト

Dockerサービスを使用する任意のプロジェクト：

1. プロジェクトファイルをアップロード
2. `docker-compose.yml`を適応（ステップ5参照）
3. ライフサイクル関数を含む`Rediaccfile`を作成
4. 所有権修正を実行
5. サービスを起動

## トラブルシューティング

### アップロード後の権限エラー

ファイルにはまだローカルのUIDが設定されています。所有権コマンドを実行してください：

```bash
rdc repo ownership my-project -m server-1
```

### コンテナが起動しない

サービスが`0.0.0.0`や`localhost`ではなく、割り当てられたIPにバインドされていることを確認してください：

```bash
# 割り当てられたIPを確認
rdc term server-1 my-project -c "cat .rediacc.json"

# コンテナログを確認
rdc term server-1 my-project -c "docker logs <container-name>"
```

### リポジトリ間のポート競合

各リポジトリは一意のループバックIPを取得します。ポート競合が発生する場合は、`docker-compose.yml`がバインドに`0.0.0.0`ではなく`${SERVICE_IP}`を使用していることを確認してください。`0.0.0.0`にバインドされたサービスはすべてのインターフェースでリッスンし、他のリポジトリと競合します。

### 所有権修正がコンテナを破損する

`rdc repo ownership --force`を実行してコンテナが動作しなくなった場合、コンテナのデータファイルが変更されています。コンテナを停止し、データディレクトリを削除してから再起動してください — コンテナがデータを再作成します：

```bash
rdc repo down my-project -m server-1
# コンテナのデータディレクトリを削除（例：database/data）
rdc repo up my-project -m server-1
```
