---
title: "Rediaccのルール"
description: "Rediaccプラットフォームでアプリケーションを構築するための基本ルールと規則。Rediaccfile、compose、ネットワーク、ストレージ、CRIU、デプロイについて説明します。"
category: "Guides"
order: 5
language: ja
sourceHash: "c276f24c681da0ef"
---

# Rediaccのルール

すべてのRediaccリポジトリは、独自のDockerデーモン、暗号化されたLUKSボリューム、専用のIP範囲を持つ分離された環境内で動作します。これらのルールにより、このアーキテクチャ内でアプリケーションが正しく動作することが保証されます。

## Rediaccfile

- **すべてのリポジトリにはRediaccfileが必要です** — ライフサイクル関数を持つbashスクリプトです。
- **ライフサイクル関数**: `up()`、`down()`。オプション: `info()`。
- `up()` はサービスを開始します。`down()` はサービスを停止します。
- `info()` はステータス情報を提供します（コンテナの状態、最近のログ、ヘルス）。
- Rediaccfileはrenetによってsourceされます — 環境変数だけでなく、シェル変数にもアクセスできます。

### Rediaccfileで利用可能な環境変数

| 変数 | 例 | 説明 |
|------|----|----|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | マウントされたリポジトリのルートパス |
| `REPOSITORY_NETWORK_ID` | `6336` | ネットワーク分離識別子 |
| `REPOSITORY_NAME` | `abc123-...` | リポジトリGUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | サービスごとのループバックIP（サービス名は大文字） |

### 最小限のRediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **`renet compose`を使用し、`docker compose`は絶対に使わないでください** — renetはネットワーク分離、ホストネットワーキング、ループバックIP、サービスラベルを注入します。
- **composeファイルで`network_mode`を設定しないでください** — renetはすべてのサービスに`network_mode: host`を強制します。設定した値は上書きされます。
- **`rediacc.*`ラベルを設定しないでください** — renetは`rediacc.network_id`、`rediacc.service_ip`、`rediacc.service_name`を自動注入します。
- **`ports:`マッピングは無視されます**（ホストネットワーキングモード）。80以外のポートへのプロキシルーティングには`rediacc.service_port`ラベルを使用してください。
- **`restart: always`や`restart: unless-stopped`は使用しないでください** — CRIUのチェックポイント/リストアと競合します。`restart: on-failure`を使用するか、省略してください。
- **Docker名前付きボリュームは使用しないでください** — 暗号化されたリポジトリの外に存在し、バックアップやフォークに含まれません。

### コンテナ内の環境変数

Renetはすべてのコンテナに以下を自動注入します:

| 変数 | 説明 |
|------|------|
| `SERVICE_IP` | このコンテナの専用ループバックIP |
| `REPOSITORY_NETWORK_ID` | ネットワーク分離ID |

### サービスの命名とルーティング

- composeの**サービス名**が自動ルートのURLプレフィックスになります。
- 例: ベースドメインが`example.com`でnetworkId 6336のサービス`myapp`は`https://myapp-6336.example.com`になります。
- カスタムドメインにはTraefikラベルを使用してください（注意: カスタムドメインはフォークに対応していません）。

## ネットワーク

- **各リポジトリは独自のDockerデーモンを持ちます**（`/var/run/rediacc/docker-<networkId>.sock`）。
- **各サービスは/26サブネット内でユニークなループバックIPを取得します**（例: `127.0.24.192/26`）。
- **`SERVICE_IP`にバインドしてください**。`0.0.0.0`ではありません — ホストネットワーキングでは`0.0.0.0`は他のリポジトリと競合します。
- **サービス間通信**: ループバックIPまたは`SERVICE_IP`環境変数を使用してください。DockerのDNS名はホストモードでは動作しません。
- **リポジトリ間のポート競合は不可能です** — 各リポジトリは独自のDockerデーモンとIP範囲を持っています。
- **TCP/UDPポートフォワーディング**: 非HTTPポートを公開するためにラベルを追加します:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## ストレージ

- **すべての永続データは`${REPOSITORY_PATH}/...`バインドマウントを使用する必要があります。**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Docker名前付きボリュームはLUKSリポジトリの外に存在します — **暗号化されず**、**バックアップされず**、**フォークに含まれません**。
- LUKSボリュームは`/mnt/rediacc/mounts/<guid>/`にマウントされます。
- BTRFSスナップショットは、すべてのバインドマウントデータを含むLUKSバッキングファイル全体をキャプチャします。

## CRIU（ライブマイグレーション）

- **`backup push --checkpoint`** は実行中のプロセスメモリ + ディスク状態をキャプチャします。
- **`repo up --mount --checkpoint`** はチェックポイントからコンテナを復元します（クリーンスタートなし）。
- **TCP接続は復元後に失効します** — アプリケーションは`ECONNRESET`を処理して再接続する必要があります。
- **Docker実験モード**はリポジトリごとのデーモンで自動的に有効化されます。
- **CRIU**は`rdc config setup-machine`中にインストールされます。
- **`/etc/criu/runc.conf`**はTCP接続保持のために`tcp-established`で設定されます。
- **コンテナのセキュリティ設定はrenetによって自動注入されます** — `renet compose`はCRIU互換性のために以下をすべてのコンテナに自動的に追加します:
  - `cap_add`: `CHECKPOINT_RESTORE`、`SYS_PTRACE`、`NET_ADMIN`（カーネル5.9+でのCRIUの最小セット）
  - `security_opt`: `apparmor=unconfined`（CRIUのAppArmorサポートはまだアップストリームで安定していません）
  - `userns_mode: host`（CRIUは`/proc/pid/map_files`のためにinitネームスペースアクセスが必要です）
- Dockerのデフォルトseccompプロファイルは保持されます — CRIUは`PTRACE_O_SUSPEND_SECCOMP`（カーネル4.3+）を使用して、チェックポイント/リストア中にフィルターを一時的に中断します。
- **composeファイルでこれらを手動で設定しないでください** — renetが処理します。手動で設定すると重複や競合のリスクがあります。
- CRIU互換のリファレンス実装については[heartbeatテンプレート](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat)を参照してください。

### CRIU互換のアプリケーションパターン

- すべての永続接続（データベースプール、WebSocket、メッセージキュー）で`ECONNRESET`を処理してください。
- 自動再接続をサポートするコネクションプールライブラリを使用してください。
- 内部ライブラリオブジェクトからの失効ソケットエラーに対するセーフティネットとして`process.on("uncaughtException")`を追加してください。
- `restart: always`を避けてください — CRIUリストアを妨げます。
- Docker DNSに依存しないでください — サービス間通信にはループバックIPを使用してください。

## セキュリティ

- **LUKS暗号化**は標準リポジトリに必須です。各リポジトリは独自の暗号化キーを持っています。
- **認証情報はCLI設定に保存されます**（`~/.config/rediacc/rediacc.json`）。設定を失うと暗号化ボリュームへのアクセスを失います。
- **認証情報を絶対にバージョン管理にコミットしないでください**。`env_file`を使用し、`up()`でシークレットを生成してください。
- **リポジトリの分離**: 各リポジトリのDockerデーモン、ネットワーク、ストレージは同じマシン上の他のリポジトリから完全に分離されています。
- **エージェント分離**: AIエージェントはデフォルトでfork-onlyモードで動作し、変更できるのはforkリポジトリのみで、grand（元の）リポジトリは変更できません。`term_exec` またはリポジトリコンテキスト付きの `rdc term` で実行されるコマンドは、Landlock LSM によりカーネルレベルでサンドボックス化され、リポジトリ間のファイルシステムアクセスを防ぎます。

## デプロイ

- **`rdc repo up`** はすべてのRediaccfileで`up()`を実行します。
- **`rdc repo up --mount`** はまずLUKSボリュームを開き、次にライフサイクルを実行します。新しいマシンへの`backup push`後に必要です。
- **`rdc repo down`** は`down()`を実行してDockerデーモンを停止します。
- **`rdc repo down --unmount`** はLUKSボリュームも閉じます（暗号化ストレージをロックします）。
- **フォーク**（`rdc repo fork`）は新しいGUIDとnetworkIdを持つCoW（コピーオンライト）クローンを作成します。フォークは親の暗号化キーを共有します。
- **プロキシルート**はデプロイ後約3秒で有効になります。`repo up`中の「Proxy is not running」警告はops/dev環境では情報提供目的です。

## よくある間違い

- `renet compose`の代わりに`docker compose`を使用する — コンテナがネットワーク分離を取得できません。
- `restart: always`を使用する — CRIUリストアを妨げ、`repo down`と干渉します。
- Docker名前付きボリュームを使用する — データは暗号化されず、バックアップされず、フォークされません。
- `0.0.0.0`にバインドする — ホストネットワーキングモードでリポジトリ間のポート競合を引き起こします。
- IPをハードコードする — `SERVICE_IP`環境変数を使用してください。IPはnetworkIdごとに動的に割り当てられます。
- `backup push`後の初回デプロイで`--mount`を忘れる — LUKSボリュームは明示的に開く必要があります。
- 失敗したコマンドの回避策として`rdc term -c`を使用する — 代わりにバグを報告してください。
