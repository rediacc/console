---
title: Rediaccのルール
description: >-
  Rediaccプラットフォームでアプリケーションを構築するための基本ルールと規則。Rediaccfile、compose、ネットワーク、ストレージ、CRIU、デプロイについて説明します。
category: Guides
order: 5
language: ja
sourceHash: 9365e0cabf7e8f03
sourceCommit: d5c06171af0ef58b551a9682905d98af81e496cd
---

# Rediaccのルール

すべてのRediaccリポジトリは、独自のDockerデーモン、暗号化されたLUKSボリューム、専用のIP範囲を持つ分離された環境内で動作します。これらのルールにより、このアーキテクチャ内でアプリケーションが正しく動作することが保証されます。

## Rediaccfile

- **すべてのリポジトリにはRediaccfileが必要です**, ライフサイクル関数を持つbashスクリプトです。
- **ライフサイクル関数**: `up()`、`down()`。オプション: `info()`。
- `up()` はサービスを開始します。`down()` はサービスを停止します。
- `info()` はステータス情報を提供します（コンテナの状態、最近のログ、ヘルス）。
- Rediaccfileはrenetによってsourceされます, 環境変数だけでなく、シェル変数にもアクセスできます。

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

- **`renet compose`を使用し、`docker compose`は絶対に使わないでください**, renetはネットワーク分離、ホストネットワーキング、ループバックIP、サービスラベルを注入します。
- **composeファイルで`network_mode`を設定しないでください**, renetはすべてのサービスに`network_mode: host`を強制します。設定した値は上書きされます。
- **`rediacc.*`ラベルを設定しないでください**, renetは`rediacc.network_id`、`rediacc.service_ip`、`rediacc.service_name`を自動注入します。
- **`ports:`マッピングは無視されます**（ホストネットワーキングモード）。HTTP ルーティングには `rediacc.service_port` ラベルを追加してください（このラベルがないサービスは HTTP ルートを取得しません）。TCP/UDP 転送には `rediacc.tcp_ports`/`rediacc.udp_ports` ラベルを使用してください。
- **再起動ポリシー（`restart: always`、`on-failure`など）は安全に使用できます**, renetはCRIU互換性のために自動的にこれらを削除します。ルーターウォッチドッグは`.rediacc.json`に保存された元のポリシーに基づいて停止したコンテナを自動回復します。
- **危険な設定はデフォルトでブロックされます**, `privileged: true`、`pid: host`、`ipc: host`、およびシステムパスへのバインドマウントは拒否されます。自己責任でオーバーライドするには `renet compose --unsafe` を使用してください。

### コンテナ内の環境変数

Renetはすべてのコンテナに以下を自動注入します:

| 変数 | 説明 |
|------|------|
| `SERVICE_IP` | このコンテナの専用ループバックIP |
| `REDIACC_NETWORK_ID` | ネットワーク分離ID |

### サービスの命名とルーティング

- compose の **サービス名** が自動ルートの URL プレフィックスになります。
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}`（例: `https://myapp.marketing.server-1.example.com`）。
- **Fork repos**: `https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`（例: `https://myapp-fork-staging.marketing.server-1.example.com`）。`-fork-` セパレータにより grand repo のサービス名との URL 衝突を防ぎます。fork URL は常に親リポジトリの既存のワイルドカード証明書を使用するため、新しい証明書は必要ありません。
- カスタムドメインには Traefik ラベルを使用してください（注意: カスタムドメインは fork との互換性がありません, ドメインは grand repo に属します）。

## ネットワーク

- **各リポジトリは独自のDockerデーモンを持ちます**（`/var/run/rediacc/docker-<networkId>.sock`）。
- **各サービスは/26サブネット内でユニークなループバックIPを取得します**（例: `127.0.24.192/26`）。
- **バインドは自動です**: サービスは `0.0.0.0` または `localhost` にバインドでき、カーネルが透過的にアドレスをサービスに割り当てられたループバック IP に書き換えます。`${SERVICE_IP}` への明示的なバインドも引き続き機能しますが、もはや必須ではありません。
- **ヘルスチェックには `localhost`** または `${SERVICE_IP}` を使用できます。例: `healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **リポジトリ間接続はカーネルでブロックされます**: カーネルはリポジトリの `/26` サブネット外のループバック IP への接続を自動的にブロックします。あるリポジトリのサービスは、別のリポジトリのサービスに到達できません。
- **サービス間通信**: **サービス名**（例 `db`、`redis`）を使用してください。renet は各サービス名を自動的に正しい IP に解決するホスト名として注入します。Docker DNS 名はホストモードでは動作しませんが、`/etc/hosts` 経由のサービス名は動作します。`${DB_IP}` などを永続的な設定ファイル（例: データベースに格納された接続文字列）に埋め込むことは避けてください。fork された場合、生の IP が引き継がれて誤ったリポジトリを指します。サービス名は常にリポジトリごとに正しく解決されます。
- **リポジトリ間のポート競合は不可能です**, 各リポジトリは独自のDockerデーモンとIP範囲を持っています。
- **TCP/UDPポートフォワーディング**: 非HTTPポートを公開するためにラベルを追加します:
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## ストレージ

- **すべてのDockerデータは暗号化されたリポジトリ内に保存されます**, Dockerの`data-root`はLUKSボリューム内の`{mount}/.rediacc/docker/data`にあります。名前付きボリューム、イメージ、コンテナレイヤーはすべて暗号化され、バックアップされ、自動的にフォークされます。
- **`${REDIACC_WORKING_DIR}/...`へのバインドマウントは明確さのために推奨されます**が、名前付きボリュームも安全に使用できます。
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # バインドマウント（推奨）
    - pgdata:/var/lib/postgresql/data      # 名前付きボリューム（こちらも安全）
  ```
- LUKSボリュームは`/mnt/rediacc/mounts/<guid>/`にマウントされます。
- BTRFSスナップショットは、すべてのバインドマウントデータを含むLUKSバッキングファイル全体をキャプチャします。
- データストアはシステムディスク上の固定サイズのBTRFSプールファイルです。`rdc machine query --name <name> --system`で実際の空き容量を確認できます。`rdc datastore resize`で拡張できます。

## CRIU（ライブマイグレーション）

- **ラベルによるオプトイン**: チェックポイントしたいコンテナに`rediacc.checkpoint=true`を追加します。このラベルのないコンテナ（データベース、キャッシュ）はフレッシュスタートし、独自のメカニズム（WAL、LDF、AOF）で回復します。
- **`repo down --checkpoint`** は停止前にプロセス状態を保存し、次の `repo up` で自動復元します。**これが同一マシン上の主要なフローであり**、動作検証済みです。
- **`backup push --checkpoint`** はラベル付きコンテナの実行中プロセスメモリ + ディスク状態をキャプチャし、ボリュームを別のマシンに転送します。ターゲットマシンでは `repo up` で復元します。
- **`repo fork --checkpoint`** は fork 前にプロセス状態をキャプチャし、チェックポイントを fork と一緒に CoW クローンします。⚠️ 同一マシン上では、親がまだ実行中の場合、fork に対する後続の `repo up` は現在 `criu failed: type RESTORE errno 0` で**失敗します**。これは upstream CRIU のバグ [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514) によるものです。インプレースな保存/復元には `repo down --checkpoint` を、マシン間マイグレーションには `backup push --checkpoint` を使用してください。
- **`repo up`** はチェックポイントデータを自動検出し、見つかった場合は復元します。フレッシュスタートには`--skip-checkpoint`を使用してください。
- **依存関係を考慮した復元**: composeの`depends_on`を使用してデータベースを先に起動（healthyを待機）し、その後アプリコンテナをCRIU復元します。
- **TCP 接続は復元後に無効になります**。アプリケーションは `ECONNRESET` を処理して再接続する必要があります。CRIU は、サポートされているどのフローでも、復元時にアクティブな TCP 接続状態を保持しません。
- **Docker実験モード**はリポジトリごとのデーモンで自動的に有効になります。
- **CRIUはインストールされます** `rdc config machine setup`の実行時に。
- **`/etc/criu/runc.conf`** はデフォルトで `tcp-established` が設定されています。
- **コンテナのセキュリティ設定はラベル付きコンテナに自動注入されます**, `renet compose`は`rediacc.checkpoint=true`を持つコンテナに以下を追加します:
  - `cap_add`: `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN`（カーネル5.9+でのCRIU最小セット）
  - `security_opt`: `apparmor=unconfined`（CRIUのAppArmorサポートはまだ上流で安定していません）
  - `userns_mode: host`（CRIUは`/proc/pid/map_files`のためにinitネームスペースアクセスが必要）
- ラベルのないコンテナはよりクリーンなセキュリティ姿勢で実行されます（追加のcapabilitiesなし）。
- Dockerのデフォルトseccompプロファイルは保持されます, CRIUは`PTRACE_O_SUSPEND_SECCOMP`（カーネル4.3+）を使用してcheckpoint/restore中にフィルターを一時的に停止します。
- **CRIU capabilitiesをcomposeファイルに手動で設定しないでください**, renetがラベルに基づいて処理します。
- CRIU互換のリファレンス実装については[heartbeatテンプレート](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat)を参照してください。

### CRIU互換のアプリケーションパターン

- すべての永続接続（データベースプール、WebSocket、メッセージキュー）で`ECONNRESET`を処理してください。
- 自動再接続をサポートするコネクションプールライブラリを使用してください。
- 内部ライブラリオブジェクトからの失効ソケットエラーに対するセーフティネットとして`process.on("uncaughtException")`を追加してください。
- 再起動ポリシーはrenetによって自動管理されます（CRIUのために削除され、ウォッチドッグが回復を処理します）。
- Docker DNSに依存しないでください, サービス間通信にはループバックIPを使用してください。

### OSごとのホストセキュリティポリシー

公式にサポートされている5つのサーバーOS（[要件](/en/docs/requirements)を参照）において、各リポジトリのDockerデーモンとその上で動作するコンテナは**デフォルトのコンテナラベル**を使用します。`rdc config machine setup`はカスタムSELinuxポリシーやAppArmorプロファイルをインストールしません。

- **Ubuntu 24.04 / openSUSE Leap 16.0**: AppArmorはデフォルトで有効です。コンテナはデフォルトのdocker-containerプロファイルで動作します。唯一の例外はCRIUです（上記の注意書きのとおり、`rediacc.checkpoint=true`を持つコンテナには`apparmor=unconfined`が適用されます）。
- **Fedora 43 / Oracle Linux 10**: SELinuxはデフォルトでenforcing（強制）モードで動作します。コンテナは標準の`container_t`コンテキストを取得します。追加のポリシーインストールは不要です。AVCの拒否によってセットアップステップが失敗した場合は、[トラブルシューティング: SELinuxの拒否](/en/docs/troubleshooting)を参照してください。
- **Debian 13**: AppArmorは利用可能ですが、すべてのドメインでデフォルトで強制適用されるわけではありません。コンテナは引き続きdocker-containerプロファイルを使用します。

OS固有のセキュリティ姿勢フラグは必要ありません。`rdc`と`renet`は実行中の環境を検出し、5つのディストリビューションすべてで同じリポジトリごとの分離を実現します。

## セキュリティ

- **LUKS暗号化**は標準リポジトリに必須です。各リポジトリは独自の暗号化キーを持っています。
- **認証情報はCLI設定に保存されます**（`~/.config/rediacc/rediacc.json`）。設定を失うと暗号化ボリュームへのアクセスを失います。
- **認証情報を絶対にバージョン管理にコミットしないでください**。`env_file`を使用し、`up()`でシークレットを生成してください。
- **リポジトリの分離**: 各リポジトリのDockerデーモン、ネットワーク、ストレージは同じマシン上の他のリポジトリから完全に分離されています。
- **エージェント分離**: AIエージェントはデフォルトでfork-onlyモードで動作します。各リポジトリはサーバーサイドのサンドボックス強制（`sandbox-gateway` ForceCommand）付きの独自のSSHキーを持ちます。すべての接続はLandlock LSM、OverlayFS homeオーバーレイ、リポジトリごとのTMPDIRでサンドボックス化されます。リポジトリ間のファイルシステムアクセスはカーネルによってブロックされます。
- **リポジトリサンドボックス内では `sudo` は設計上無効化されています。** Landlock によるファイルシステム分離は `NoNewPrivs` を必要とし、これによりあらゆる権限昇格が阻止されるため、`sudo` は `no new privileges flag is set` で失敗します。リポジトリのオーナーユーザーは、リポジトリのマウントと Docker ソケット配下のすべての操作に必要な権限をすでに持っています。ホストパッケージのインストールやカーネルチューニングなど、本当に特権を必要とする操作は、サンドボックスの外で実行するか、インフラ経路で実行される Rediaccfile の `up()` 関数から実行してください。
- **Docker のブリッジネットワーキングは、すべてのリポジトリごとのデーモンで無効化されています。** 各リポジトリの `daemon.json` には `"bridge": "none"` と `"iptables": false` が設定されているため、単純な `docker run <image>` で作成されるコンテナはループバックインターフェースのみを持ち、外向きの接続性を持ちません。これはバグではなく、リポジトリ間の分離を強制するためのものです。あるリポジトリが別のリポジトリのループバック IP に到達することを防ぐカーネルレベルの eBPF フックは、ホストのネットワーク名前空間に属するコンテナにのみ適用されるからです。本番サービスでは `renet compose` を使用してください。これは自動的に `network_mode: host` を注入します。シェル内でアドホックに単発のコンテナを実行する場合は、明示的に `--network host` を指定してください。

## デプロイ

- **`rdc repo up`** はLUKSボリュームが未マウントの場合は自動マウントし、すべてのRediaccfileで`up()`を実行します。
- **`rdc repo down`** は`down()`を実行してDockerデーモンを停止します。
- **`rdc repo down --unmount`** はLUKSボリュームも閉じます（暗号化ストレージをロックします）。
- **フォーク**（`rdc repo fork`）は新しいGUIDとnetworkIdを持つCoW（コピーオンライト）クローンを、**リポジトリのサイズに関係なく一定時間で**作成します。BTRFS reflink はイメージのメタデータを複製するだけでデータは複製しないため、100 GB のリポジトリも 1 GB のリポジトリも同じ数秒でフォークされます。フォークは親の暗号化キーを共有します。
- **テイクオーバー**（`rdc repo takeover --name <fork> -m <machine>`）はgrandリポジトリのデータをフォークのデータで置き換えます。grandはその識別情報（GUID、networkId、ドメイン、自動起動、バックアップチェーン）を保持します。古い本番データはバックアップフォークとして保存されます。使用例: フォークでアップグレードをテストし、確認後に本番にテイクオーバー。`rdc repo takeover --name <backup-fork> -m <machine>`で元に戻せます。
- **プロキシルート**はデプロイ後約3秒で有効になります。`repo up`中の「Proxy is not running」警告はops/dev環境では情報提供目的です。
- **`rdc repo up` と `rdc repo fork --up` は、デプロイ終了時に** `rediacc.service_port` でラベル付けされたサービスの URL パターンを出力します。`{service}` を公開されたサービス名に置き換えて正確な URL を取得してください。`rediacc.service_port` のないサービス（データベース、ワーカー）はルートを取得せず、表示されません。

## よくある間違い

- `renet compose`の代わりに`docker compose`を使用する, コンテナがネットワーク分離を取得できません。
- 再起動ポリシーは安全です, renetが自動的に削除し、ウォッチドッグが回復を処理します。
- `privileged: true` を使用する, 不要です。renetが代わりに特定のCRIUケーパビリティを注入します。
- 生の IP を永続的な設定ファイルにハードコードする - 接続にはサービス名を使用して fork の分離性を保ってください。
- 失敗したコマンドの回避策として`rdc term connect -c`を使用する, 代わりにバグを報告してください。
- `repo delete`はループバックIPとsystemdユニットを含む完全なクリーンアップを実行します。古い削除の残骸をクリーンアップするには`rdc machine prune --name <name>`を実行してください。
