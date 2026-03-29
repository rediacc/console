---
title: "Hub"
description: "OAuth認証付きのユーザーごとのコンテナ環境を提供し、自動プロビジョニング、アイドル管理、チェックポイント/リストアに対応します。"
category: "Guides"
order: 14
language: ja
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Hubは、OAuth認証の背後にユーザーごとのコンテナ環境を提供します。ユーザーは単一のURLにアクセスし、任意のOAuth2プロバイダーで認証を行うと、自分の個人コンテナに透過的にルーティングされます。コンテナはオンデマンドで作成され、自動的に管理されます。

すべての設定は`docker-compose.yml`のラベルで行います。Hubはコンテナ内で何が実行されているかを知りませんし、気にしません -- 認証、ルーティング、ライフサイクルを処理します。リポジトリが動作を定義します。

## 仕組み

![Hubアーキテクチャ](/img/hub-architecture.svg)

1. ユーザーが`code.example.com`にアクセスします
2. Hubがセッションクッキーを確認します。存在しない場合、ユーザーは設定されたOAuth2プロバイダー（Nextcloud、Keycloak、GitHubなど）にリダイレクトされます
3. 認証後、Hubはユーザーを識別し、そのコンテナを検索します
4. コンテナが存在しない場合、設定されたテンプレートからオンデマンドで作成されます
5. リクエストはリバースプロキシを通じてユーザーのコンテナに転送されます
6. Hubはホスト名に基づいてプロキシ先のポートを決定します（例：`code.` -> ポート8080、`term.` -> ポート7681）

アイドル状態のコンテナは自動的に停止されるか、CRIU によるチェックポイントが作成され、次回ログイン時に即座に復元されます。

## クイックスタート

リポジトリの`docker-compose.yml`にHubをサービスとして追加します：

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # ルートマッピング：サブドメインプレフィックス -> ユーザーコンテナのポート
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # コンテナテンプレート
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Traefikルート（サブドメインごとに1つ）
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

OAuth2プロバイダーの認証情報を含む`hub.env`を作成します：

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

`rdc repo up`でデプロイします。

## 設定

Hubの設定はすべてHubサービス自体のComposeラベルに含まれています。Hubバイナリ内に設定ファイルはありません。

### ルートマッピング

サブドメインプレフィックスをユーザーコンテナのポートにマッピングします。Hubはこれらのラベルを読み取り、各リクエストのルーティング先を判断します。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | `{prefix}.{domain}`をユーザーコンテナのこのポートにマッピング | `rediacc.hub.route.code=8080` |

任意の数のルートを定義できます。プレフィックスはホスト名の最初のセグメントと照合されます：

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

各ルートにはHubのポート（7112）を指す対応するTraefikルーターも必要です。Hubはユーザーごとのルーティングを内部で処理します。

### コンテナテンプレート

ユーザーコンテナの外観を定義します。Hubはこれらのラベルを読み取り、ユーザーの新しいコンテナを作成する際に使用します。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.image` | コンテナイメージ | `--container-image`フラグの値 |
| `rediacc.hub.command` | 起動コマンド（bash -c互換） | なし |
| `rediacc.hub.user` | コンテナユーザー（非rootを推奨） | `vscode` |
| `rediacc.hub.workspace` | コンテナ内のワークスペースマウントポイント | `/workspace` |
| `rediacc.hub.shm_size` | 共有メモリサイズ（バイト） | `1073741824`（1 GB） |

`command`ラベルは`${SERVICE_IP}`展開をサポートしており、作成時にコンテナに割り当てられたループバックIPに置き換えられます。

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **ヒント：** Docker Composeによる環境変数の早期展開を防ぐため、Composeラベルではリテラルの`$`に`$$`を使用してください。

### リソース制限

単一ユーザーがすべてのホストリソースを消費するのを防ぐため、ユーザーごとのリソース制限を設定します。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | CPU制限（コア数） | `2` |
| `rediacc.hub.limits.memory` | メモリ制限 | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### ライフサイクルフック

ライフサイクルの特定のポイントでユーザーコンテナ内でコマンドを実行します。

| ラベル | 実行タイミング | 例 |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | コンテナ作成後（初回ログイン） | リポジトリのクローン、依存関係のインストール |
| `rediacc.hub.hook.on_start` | コンテナの起動または復元後 | シークレットのマウント、トークンの更新 |
| `rediacc.hub.hook.on_idle` | コンテナの停止またはチェックポイント前 | 状態の保存、変更のプッシュ |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### チェックポイント / リストア

有効にすると、アイドル状態のコンテナは停止される代わりにCRIUを使用してチェックポイントが作成されます。次回ログイン時にチェックポイントから数秒でコンテナが復元され、正確な状態が保持されます：開いているファイル、実行中のプロセス、ターミナルセッション。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | ユーザーコンテナのCRIUチェックポイントを有効にする | `false` |

Hub起動時に`--checkpoint`も指定します：

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...その他のフラグ...
```

> **注意：** チェックポイント/リストアにはホスト上でCRIUバイナリが利用可能であり、コンテナがホストネットワークモードで実行されている必要があります（Rediaccサービスのデフォルト）。

### アクセス制御

Hubを使用できるユーザーと管理者権限を持つユーザーを制限します。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Hubの使用を許可するカンマ区切りのグループ | `developers,ops` |
| `rediacc.hub.admin_users` | カンマ区切りの管理者ユーザー名 | `alice,bob` |

管理者ユーザーはダッシュボードですべてのコンテナを表示・管理できます。一般ユーザーは自分のコンテナのみ表示されます。

### エフェメラルモード

デフォルトでは、ユーザーワークスペースは永続的です（コンテナの再起動後も保持されます）。エフェメラルモードはログインのたびにクリーンな環境を提供し、デモ、トレーニング、CIに便利です。

| ラベル | 説明 | デフォルト |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent`または`ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

エフェメラルモードでは、ワークスペースはtmpfs（RAMバック）を使用し、コンテナは停止時に自動的に削除されます。

### マルチテンプレートサポート

複数の環境タイプを提供します。ユーザーは初回ログイン時にテンプレートを選択するか、ダッシュボードから切り替えることができます。

```yaml
labels:
  # デフォルトテンプレート
  - "rediacc.hub.template.default=fulldev"

  # フル開発環境
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # 軽量オプション
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## OAuthセットアップ

Hubは任意の標準OAuth2プロバイダーで動作します。設定はComposeラベルではなく環境変数で行います（シークレットはラベルに含めるべきではありません）。

| 変数 | 説明 | 必須 |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2クライアントID | はい |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2クライアントシークレット | はい |
| `HUB_OAUTH_AUTHORIZE_URL` | プロバイダーの認可エンドポイント | はい |
| `HUB_OAUTH_TOKEN_URL` | プロバイダーのトークンエンドポイント | はい |
| `HUB_OAUTH_USERINFO_URL` | プロバイダーのユーザー情報エンドポイント | はい |
| `HUB_OAUTH_USERINFO_PATH` | JSONレスポンスからユーザー名を抽出するドットパス | はい |
| `HUB_OAUTH_REDIRECT_URI` | コールバックURLの上書き（空の場合は自動計算） | いいえ |
| `HUB_OAUTH_SCOPES` | 追加スコープ（スペース区切り） | いいえ |
| `HUB_SESSION_SECRET` | クッキー署名用の32バイト以上の16進文字列 | 推奨 |

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

`HUB_OAUTH_USERINFO_PATH`はJSONレスポンスへのドット区切りパスです。Nextcloudの`{"ocs":{"data":{"id":"alice"}}}`のようなネストされたオブジェクトの場合は、`ocs.data.id`を使用します。

## ダッシュボード

Hubには`/_hub/dashboard`にセルフサービスダッシュボードが含まれています。表示内容：

- すべての実行中の環境とそのステータス
- サービスリンク（ワンクリックでコード、ターミナル、デスクトップを開く）
- アイドルタイマーとリソース使用量
- 起動/停止コントロール
- 管理者ユーザーはすべてのコンテナを表示・管理可能

認証後に`https://code.example.com/_hub/dashboard`にアクセスしてダッシュボードを表示します。

## 例

### 開発環境（VS Code + ターミナル + デスクトップ）

OpenVSCode Server、Webターミナル（ttyd）、noVNCデスクトップを備えたフル開発環境：

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Jupyterノートブック環境

JupyterLabを備えたデータサイエンス環境：

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### シンプルなWebアプリケーション

Webフレームワーク用の単一サービス環境：

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## 関連ガイド

- [**サービス**](/ja/docs/services) -- Rediaccfileライフサイクル、Composeパターン
- [**ネットワーク**](/ja/docs/networking) -- Dockerラベル、Traefikルーティング、TLS証明書
- [**バックアップとリストア**](/ja/docs/backup-restore) -- ワークスペースの永続性と復元
- [**開発環境**](/ja/docs/development-environments) -- 開発環境のための本番クローン
