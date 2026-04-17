---
title: "Hub"
description: "認証済みのユーザー別コンテナ環境を提供し、ユーザーごとの Docker daemon、マルチテンプレート選択、CRIU チェックポイント/リストア、監査ログ、data-root ガベージコレクションに対応します。"
category: "Guides"
order: 14
language: ja
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Hub は、OAuth 認証の背後にユーザーごとのコンテナ環境を提供します。ユーザーは単一の URL にアクセスし、任意の OAuth2 プロバイダーで認証を行うと、自分の専用コンテナに透過的にルーティングされます。コンテナはオンデマンドで作成され、各ユーザーが独自の隔離された Docker daemon を持ち、アイドル状態のセッションは即座に再開できるよう CRIU チェックポイントで保存されます。

すべての設定は `docker-compose.yml` のラベルで行います。Hub 自体は、リポジトリの Compose ファイルから `renet hub install` コマンドによって生成されるホスト systemd サービスとして動作します。リポジトリが動作を定義し、Hub が認証・ルーティング・ライフサイクル・ユーザー別の隔離を処理します。

## 仕組み

1. ユーザーが `code.example.com`（または `term.`、`desktop.`、その他設定済みのプレフィックス）にアクセスします。
2. Hub がセッション Cookie を確認します。存在しない場合、ユーザーは設定された OAuth2 プロバイダー（Nextcloud、Keycloak、GitHub など）にリダイレクトされます。
3. 認証後、Hub はユーザーを識別し、そのコンテナを検索します。
4. コンテナが存在しない場合、Hub はホスト上でそのユーザー専用の Docker daemon をプロビジョニングし、コンテナを起動します。
5. リクエストは loopback ネットワークを通じてユーザーのコンテナにリバースプロキシされます。
6. アイドル状態のコンテナは CRIU チェックポイントで保存され、ユーザーごとの daemon はメモリ解放のために停止されます。次回ログイン時に daemon が再起動し、CRIU が数秒でコンテナの状態を復元します。

## クイックスタート

リポジトリの `docker-compose.yml` に Hub をサービスとして追加します。サービスは `install_as=systemd` とマークされており、Docker コンテナではなくホストサービスとして実行されます（systemd を使用するユーザーごとの daemon 管理に必要です）。

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # ルートマッピング：サブドメインプレフィックス -> ユーザーコンテナのポート
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # コンテナテンプレート
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik ルート（ファイルプロバイダー；rediacc-router もこれらのラベルを読み取ります）
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

OAuth2 プロバイダーの認証情報を含む `hub/.env` を作成します。

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

ホスト systemd ユニットをインストールします（一回限り、root が必要）。

```bash
sudo renet hub install /path/to/docker-compose.yml
```

これにより `install_as=systemd` サービスが読み込まれ、以下が書き込まれます。

- `/etc/systemd/system/rediacc-hub.service`（ユニットファイル）
- `/etc/rediacc/hub/hub.labels.yaml`（テンプレートラベル）
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml`（Traefik ファイルプロバイダーのルート）

次に `systemctl daemon-reload && systemctl enable --now rediacc-hub` を実行します。削除する場合は `sudo renet hub uninstall /path/to/docker-compose.yml` を使用します。

## install コマンドリファレンス

| コマンド | 目的 |
|---------|---------|
| `sudo renet hub install <compose-file>` | Compose ファイルの `install_as=systemd` サービスをホストの成果物に変換してユニットを起動します。 |
| `sudo renet hub uninstall <compose-file>` | サービスのすべての成果物を停止・無効化・削除します。`<workspace>/<user>-docker/` 以下の data-root は保持されます。 |
| `sudo renet hub gc <workspace-dir>` | 放棄されたユーザーごとの data-root を整理します（デフォルト：アクティブな daemon なしで 30 日以上経過）。フラグ：`--max-age=30d`、`--dry-run`。 |
| `renet hub status` | 実行中の Hub API を通じてすべてのコンテナの JSON ステータスを表示します。 |
| `renet hub stop <username>` | 特定ユーザーのコンテナを停止します。 |

## 設定

Hub のすべての設定は Hub サービスの Compose ラベルに記述します。シークレット（OAuth client_secret、session_secret）はラベルではなく `hub/.env` に記述します。

### ルートマッピング

サブドメインプレフィックスをユーザーコンテナのポートにマッピングします。Hub はこれらのラベルを読み取り、各リクエストのプロキシ先を判断します。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | `{prefix}.{domain}` をユーザーコンテナのこのポートにマッピングします | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

各ルートには Hub のポート（7112）を指す対応する Traefik ルーターも必要です。Hub はホスト名に基づいてユーザーごとのルーティングを内部で処理します。

### コンテナテンプレート

ユーザーコンテナの仕様を定義します。Hub はこれらのラベルを読み取り、新しいコンテナを作成する際に使用します。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.image` | コンテナイメージ | `--container-image` フラグの値 |
| `rediacc.hub.command` | 起動コマンド（bash -c 互換） | なし |
| `rediacc.hub.user` | コンテナユーザー（非 root を推奨） | `vscode` |
| `rediacc.hub.workspace` | コンテナ内のワークスペースマウントポイント | `/workspace` |
| `rediacc.hub.shm_size` | 共有メモリサイズ（バイト） | `1073741824`（1 GB） |
| `rediacc.hub.docker` | ユーザーごとに専用の dockerd をプロビジョニングする場合は `per-user`（強く推奨） | `""` |

`command` ラベルはコンテナに割り当てられた loopback IP への `${SERVICE_IP}` および `__SERVICE_IP__` 展開をサポートします（後者は Compose の事前展開を回避します）。

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### ユーザーごとの Docker Daemon

`rediacc.hub.docker=per-user` が設定されると、各ユーザーはホスト上に専用の `dockerd` インスタンスを持ち、コンテナ内に `/var/run/docker.sock` としてバインドマウントされます。これにより以下が実現されます。

- 特権コンテナや Docker-in-Docker なしで、ユーザー環境内で `docker ps`、`docker run`、`docker build` をフルに利用可能。
- ユーザー間の完全な隔離（ユーザー A はユーザー B のコンテナやイメージを参照できません）。
- `<workspace-dir>/<user>-docker/.rediacc/docker/data` にユーザーごとの BTRFS data-root があり、セッションを越えて保持されるためキャッシュされたイメージがアイドルチェックポイントサイクルを生き延びます。

Daemon は 32768 から始まる専用のネットワーク ID 範囲に割り当てられます。各ユーザーの data-root にある `.networkid` マーカーファイルに割り当てられた ID が記録され、再訪ユーザーが同じ daemon を利用できるようになります。

### リソース制限

特定のユーザーがすべてのホストリソースを消費しないよう、ユーザーごとのリソース制限を設定します。制限はユーザーのコンテナとユーザーごとの dockerd インスタンスの両方に適用されます（systemd `CPUQuota=` / `MemoryMax=` を使用）。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota 値 | `200%`（2 コア） |
| `rediacc.hub.limits.memory` | systemd MemoryMax 値 | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemon は `rediacc.slice` systemd スライスに配置されるため、スライスレベルの制限が継承されます。

### マルチテンプレートサポート

複数の環境タイプを提供します。ユーザーは `https://code.example.com/_hub/login?template=python` にアクセスしてログイン時にテンプレートを選択します（選択は OAuth ステートを経由して伝達されます）。次回以降のログインでテンプレートを変更するとコンテナが再構築されます。

テンプレートは `rediacc.hub.templates.<name>.<field>` ラベルで定義します。フラットな `rediacc.hub.image` / `rediacc.hub.command` などのラベルは、テンプレートを選択しないユーザー向けの暗黙の「デフォルト」テンプレートとして引き続き機能します。

```yaml
labels:
  # ?template=... が省略された場合のデフォルトテンプレート。
  - "rediacc.hub.template=fulldev"

  # VS Code + デスクトップ + ターミナルのフル環境。
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # VS Code のみ、軽量版。
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python 専用環境。
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### ライフサイクルフック

ライフサイクルの節目にユーザーコンテナ内でコマンドを実行します。フックはコンテナユーザーとして実行されます（root ではありません）。

| ラベル | 実行タイミング | 例 |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | コンテナ作成後（初回ログイン） | リポジトリのクローン、依存関係のインストール |
| `rediacc.hub.hook.checkpoint.pre_dump` | アイドルセッションの CRIU チェックポイント前 | チェックポイントできない daemon を停止（X server、dbus） |
| `rediacc.hub.hook.checkpoint.post_restore` | CRIU リストア後 | pre_dump で停止した daemon を再起動 |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### チェックポイント / リストア

`--checkpoint` が設定されると、アイドル状態のユーザーコンテナが CRIU チェックポイントで保存され、メモリを解放するためにユーザーごとの daemon が停止されます。次回ログイン時に daemon が再起動し、CRIU がディスクからコンテナの状態を復元します。この際、開いているファイル、実行中のプロセス、ターミナルセッションが保持されます。典型的な再開時間はワークロードに関わらず数秒です。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | ユーザーコンテナの CRIU チェックポイントを有効にする | `false` |

Hub コマンドに `--checkpoint` と 0 以外の `--idle-timeout`（例：`30m`）を指定します。チェックポイントのディレクトリは `<workspace-dir>/<user>/.checkpoint/` に保存されます。

あるユーザーで CRIU が連続して 3 回失敗した場合、そのユーザーのチェックポイントが無効化され、フォールバックとして停止後に再作成が行われます。

### エフェメラルモード

デフォルトでは、ユーザーのワークスペースは永続的です（再起動後も保持されます）。エフェメラルモードは毎回のログインでクリーンな環境を提供し、デモ、トレーニング、CI に適しています。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` または `ephemeral` | `persistent` |

エフェメラルモードではワークスペースは tmpfs（RAM バック）を使用し、コンテナは停止時に自動的に削除されます。

### アイドルタイムアウト

| フラグ | 説明 | デフォルト |
|------|-------------|---------|
| `--idle-timeout=<dur>` | この時間より長くアイドル状態のコンテナを停止またはチェックポイント保存します | `0`（無効） |

`0` はコンテナを永久に実行し続けます。実用的な値は `30m` です。アイドルユーザーは 30 分後にメモリを解放し、戻ってきたユーザーは CRIU によって数秒で再開できます。

### アクセス制御

| 変数 | 説明 |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Hub の使用を許可するカンマ区切りのグループ（プロバイダーがグループクレームを提供する場合） |
| `HUB_ADMIN_USERS` | カンマ区切りの管理者ユーザー名。管理者はダッシュボードで他のユーザーのコンテナを確認・制御できます。 |

## 監査ログ

ユーザーごとの daemon 上でユーザーが開始した各コンテナ/イメージイベント（create、start、stop、destroy、kill、pull、push）は、行区切りの JSON レコードとして `/var/log/rediacc/hub/<user>.log` に追記されます。

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

エントリは CRIU チェックポイント/リストアを経ても保持されます（監査ストリームはリストア時に再アーム）。`logrotate` を使用してディスク使用量を制限できます。設定例：

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## ダッシュボード

Hub は `/_hub/dashboard` にセルフサービスのダッシュボードを提供します。表示内容：

- すべての実行中の環境とそのステータス
- 選択されたテンプレート
- サービスリンク（コード、ターミナル、デスクトップ、その他のルートをワンクリックで開けます）
- アイドルタイマー
- ユーザーごとのディスク使用量、実行中のコンテナ数、イメージ数
- 管理者はすべてのコンテナを表示できます。一般ユーザーは自分のコンテナのみ表示されます。

統計は 30 秒ごとにサンプリングされます。

## Data-Root ガベージコレクション

長期稼働のホストではユーザーごとの data-root が蓄積されます。`renet hub gc` をスケジュールして放棄されたものを整理します。systemd タイマーが適しています。

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` は削除せずに候補をログに記録します。`.networkid` マーカーファイルが `--max-age` より古く、かつ記録された daemon がホスト上でもはや設定されていない場合に、data-root は対象となります。

## OAuth セットアップ

Hub は任意の標準 OAuth2 プロバイダーで動作します。設定は環境変数で行います。

| 変数 | 説明 | 必須 |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 クライアント ID | はい |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 クライアントシークレット | はい |
| `HUB_OAUTH_AUTHORIZE_URL` | プロバイダーの認可エンドポイント | はい |
| `HUB_OAUTH_TOKEN_URL` | プロバイダーのトークンエンドポイント | はい |
| `HUB_OAUTH_USERINFO_URL` | プロバイダーのユーザー情報エンドポイント | はい |
| `HUB_OAUTH_USERINFO_PATH` | JSON レスポンスからユーザー名を抽出するドットパス | はい |
| `HUB_OAUTH_REDIRECT_URI` | コールバック URL の上書き（空の場合は自動計算） | いいえ |
| `HUB_OAUTH_SCOPES` | 追加スコープ（スペース区切り） | いいえ |
| `HUB_SESSION_SECRET` | Cookie 署名用の 32 バイト以上の 16 進数文字列 | 推奨 |

### プロバイダーの例

**Nextcloud：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` は JSON レスポンスへのドット区切りパスです。Nextcloud の `{"ocs":{"data":{"id":"alice"}}}` のようなネストされたオブジェクトには `ocs.data.id` を使用します。

## 例

### 開発環境（VS Code + ターミナル + デスクトップ）

OpenVSCode Server、Web ターミナル（ttyd）、noVNC デスクトップを備えたフル開発環境。ユーザーは内部に自分専用の Docker daemon を持ちます。

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... 各プレフィックス用の Traefik ルーター ...
```

### Jupyter Notebook 環境

JupyterLab を使用したデータサイエンス環境：

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### シンプルな Web アプリケーション（エフェメラル）

毎回のログインでゼロから始まる単一サービス環境：

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## 関連ガイド

- [**サービス**](/ja/docs/services) -- Rediaccfile ライフサイクル、Compose パターン
- [**ネットワーク**](/ja/docs/networking) -- Docker ラベル、Traefik ルーティング、TLS 証明書
- [**バックアップとリストア**](/ja/docs/backup-restore) -- ワークスペースの永続性と復元
- [**開発環境**](/ja/docs/development-environments) -- 開発環境のための本番クローン
