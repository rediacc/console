---
title: "Rediaccのルール"
description: "Rediaccプラットフォームでアプリケーションを構築するための基本ルールと規則。Rediaccfile、compose、ネットワーク、ストレージ、CRIU、デプロイについて説明します。"
category: "Guides"
order: 5
language: ja
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
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
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | マウントされたリポジトリのルートパス |
| `REDIACC_NETWORK_ID` | `6336` | ネットワーク分離識別子 |
| `REDIACC_REPOSITORY` | `abc123-...` | リポジトリGUID |
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
- **再起動ポリシー（`restart: always`、`on-failure`など）は安全に使用できます** — renetはCRIU互換性のために自動的にこれらを削除します。ルーターウォッチドッグは`.rediacc.json`に保存された元のポリシーに基づいて停止したコンテナを自動回復します。
- **危険な設定はデフォルトでブロックされます** — `privileged: true`、`pid: host`、`ipc: host`、およびシステムパスへのバインドマウントは拒否されます。自己責任でオーバーライドするには `renet compose --unsafe` を使用してください。

### コンテナ内の環境変数

Renetはすべてのコンテナに以下を自動注入します:

| 変数 | 説明 |
|------|------|
| `SERVICE_IP` | このコンテナの専用ループバックIP |
| `REDIACC_NETWORK_ID` | ネットワーク分離ID |

### サービスの命名とルーティング

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}`（例: `https://myapp.marketing.server-1.example.com`）。
- **Fork repos**: `https://{service}-{tag}.{machine}.{baseDomain}` — uses the machine wildcard cert to avoid Let's Encrypt rate limits.
- カスタムドメインには Traefik ラベルを使用してください（注意: カスタムドメインは fork との互換性がありません — ドメインは grand repo に属します）。

## ネットワーク

- **各リポジトリは独自のDockerデーモンを持ちます**（`/var/run/rediacc/docker-<networkId>.sock`）。
- **各サービスは/26サブネット内でユニークなループバックIPを取得します**（例: `127.0.24.192/26`）。
- **`SERVICE_IP`にバインドしてください** — 各サービスはユニークなループバックIPを取得します。
- **ヘルスチェックは`${SERVICE_IP}`を使用する必要があります**。`localhost`ではありません。例: `healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **サービス間通信**: ループバックIPまたは`SERVICE_IP`環境変数を使用してください。DockerのDNS名はホストモードでは動作しません。
- **リポジトリ間のポート競合は不可能です** — 各リポジトリは独自のDockerデーモンとIP範囲を持っています。
- **TCP/UDPポートフォワーディング**: 非HTTPポートを公開するためにラベルを追加します:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## ストレージ

- **すべてのDockerデータは暗号化されたリポジトリ内に保存されます** — Dockerの`data-root`はLUKSボリューム内の`{mount}/.rediacc/docker/data`にあります。名前付きボリューム、イメージ、コンテナレイヤーはすべて暗号化され、バックアップされ、自動的にフォークされます。
- **`${REDIACC_WORKING_DIR}/...`へのバインドマウントは明確さのために推奨されます**が、名前付きボリュームも安全に使用できます。
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # バインドマウント（推奨）
    - pgdata:/var/lib/postgresql/data      # 名前付きボリューム（こちらも安全）
  ```
- LUKSボリュームは`/mnt/rediacc/mounts/<guid>/`にマウントされます。
- BTRFSスナップショットは、すべてのバインドマウントデータを含むLUKSバッキングファイル全体をキャプチャします。
- データストアはシステムディスク上の固定サイズのBTRFSプールファイルです。`rdc machine query <name> --system`で実際の空き容量を確認できます。`rdc datastore resize`で拡張できます。

## CRIU（ライブマイグレーション）

- **`backup push --checkpoint`** は実行中のプロセスメモリ + ディスク状態をキャプチャします。
- **`repo up --mount --checkpoint`** はチェックポイントからコンテナを復元します（クリーンスタートなし）。
- **TCP接続は復元後に失効します** — アプリケーションは`ECONNRESET`を処理して再接続する必要があります。
- **Docker実験モード**はリポジトリごとのデーモンで自動的に有効化されます。
- **CRIU**は`rdc config machine setup`中にインストールされます。
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
- 再起動ポリシーはrenetによって自動管理されます（CRIUのために削除され、ウォッチドッグが回復を処理します）。
- Docker DNSに依存しないでください — サービス間通信にはループバックIPを使用してください。

## セキュリティ

- **LUKS暗号化**は標準リポジトリに必須です。各リポジトリは独自の暗号化キーを持っています。
- **認証情報はCLI設定に保存されます**（`~/.config/rediacc/rediacc.json`）。設定を失うと暗号化ボリュームへのアクセスを失います。
- **認証情報を絶対にバージョン管理にコミットしないでください**。`env_file`を使用し、`up()`でシークレットを生成してください。
- **リポジトリの分離**: 各リポジトリのDockerデーモン、ネットワーク、ストレージは同じマシン上の他のリポジトリから完全に分離されています。
- **エージェント分離**: AIエージェントはデフォルトでfork-onlyモードで動作します。各リポジトリはサーバーサイドのサンドボックス強制（`sandbox-gateway` ForceCommand）付きの独自のSSHキーを持ちます。すべての接続はLandlock LSM、OverlayFS homeオーバーレイ、リポジトリごとのTMPDIRでサンドボックス化されます。リポジトリ間のファイルシステムアクセスはカーネルによってブロックされます。

## デプロイ

- **`rdc repo up`** はすべてのRediaccfileで`up()`を実行します。
- **`rdc repo up --mount`** はまずLUKSボリュームを開き、次にライフサイクルを実行します。新しいマシンへの`backup push`後に必要です。
- **`rdc repo down`** は`down()`を実行してDockerデーモンを停止します。
- **`rdc repo down --unmount`** はLUKSボリュームも閉じます（暗号化ストレージをロックします）。
- **フォーク**（`rdc repo fork`）は新しいGUIDとnetworkIdを持つCoW（コピーオンライト）クローンを作成します。フォークは親の暗号化キーを共有します。
- **テイクオーバー**（`rdc repo takeover <fork> -m <machine>`）はgrandリポジトリのデータをフォークのデータで置き換えます。grandはその識別情報（GUID、networkId、ドメイン、自動起動、バックアップチェーン）を保持します。古い本番データはバックアップフォークとして保存されます。使用例: フォークでアップグレードをテストし、確認後に本番にテイクオーバー。`rdc repo takeover <backup-fork> -m <machine>`で元に戻せます。
- **プロキシルート**はデプロイ後約3秒で有効になります。`repo up`中の「Proxy is not running」警告はops/dev環境では情報提供目的です。

## よくある間違い

- `renet compose`の代わりに`docker compose`を使用する — コンテナがネットワーク分離を取得できません。
- 再起動ポリシーは安全です — renetが自動的に削除し、ウォッチドッグが回復を処理します。
- `privileged: true` を使用する — 不要です。renetが代わりに特定のCRIUケーパビリティを注入します。
- `SERVICE_IP`にバインドしない — リポジトリ間のポート競合を引き起こします。
- IPをハードコードする — `SERVICE_IP`環境変数を使用してください。IPはnetworkIdごとに動的に割り当てられます。
- `backup push`後の初回デプロイで`--mount`を忘れる — LUKSボリュームは明示的に開く必要があります。
- 失敗したコマンドの回避策として`rdc term -c`を使用する — 代わりにバグを報告してください。
- `repo delete`はループバックIPとsystemdユニットを含む完全なクリーンアップを実行します。古い削除の残骸をクリーンアップするには`rdc machine prune <name>`を実行してください。
