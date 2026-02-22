---
title: ネットワーキング
description: リバースプロキシ、Dockerラベル、TLS証明書、DNS、TCP/UDPポートフォワーディングによるサービスの公開。
category: Guides
order: 6
language: ja
sourceHash: 47ee41d44be935a8
---

# ネットワーキング

このページでは、隔離されたDockerデーモン内で実行されているサービスをインターネットからアクセス可能にする方法を説明します。リバースプロキシシステム、ルーティング用Dockerラベル、TLS証明書、DNS、TCP/UDPポートフォワーディングについて説明します。
| Route server running old version | Binary was updated but service not restarted | Happens automatically on provisioning; manual: `sudo systemctl restart rediacc-router` |
| STUN/TURN relay not reachable | Relay addresses cached at startup | Recreate the service after DNS or IP changes so it picks up the new network config |

サービスがループバックIPを取得する仕組みと`.rediacc.json`スロットシステムについては、[サービス](/ja/docs/services#サービスネットワーキングrediaccjson)を参照してください。

## 仕組み

Rediaccは、外部トラフィックをコンテナにルーティングするために2コンポーネントのプロキシシステムを使用します：

1. **ルートサーバー** -- すべてのリポジトリDockerデーモンにわたって実行中のコンテナを検出するsystemdサービス。コンテナラベルを検査し、YAMLエンドポイントとして提供されるルーティング設定を生成します。
2. **Traefik** -- 5秒ごとにルートサーバーをポーリングし、検出されたルートを適用するリバースプロキシ。HTTP/HTTPSルーティング、TLS終端、TCP/UDPフォワーディングを処理します。

フローは以下の通りです：

```
インターネット → Traefik (ポート 80/443/TCP/UDP)
                   ↓ 5秒ごとにポーリング
               ルートサーバー (コンテナを検出)
                   ↓ ラベルを検査
               Dockerデーモン (/var/run/rediacc/docker-*.sock)
                   ↓
               コンテナ (127.x.x.x ループバックIPにバインド)
```

適切なラベルをコンテナに追加して`renet compose`で起動すると、自動的にルーティング可能になります。手動のプロキシ設定は不要です。

> The route server binary is kept in sync with your CLI version. When the CLI updates the renet binary on a machine, the route server is automatically restarted (~1–2 seconds). This causes no downtime — Traefik continues serving traffic with its last known configuration during the restart and picks up the new config on the next poll. Existing client connections are not affected. Your application containers are not touched.

## Dockerラベル

ルーティングはDockerコンテナラベルで制御されます。2つのティアがあります：

### ティア1：`rediacc.*`ラベル（自動）

これらのラベルは、サービス起動時に`renet compose`によって**自動的に注入**されます。手動で追加する必要はありません。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.service_name` | サービスID | `myapp` |
| `rediacc.service_ip` | 割り当てられたループバックIP | `127.0.11.2` |
| `rediacc.network_id` | リポジトリのデーモンID | `2816` |
| `rediacc.tcp_ports` | TCP ports the service listens on | `8080,8443` |
| `rediacc.udp_ports` | UDP ports the service listens on | `53` |

コンテナが`rediacc.*`ラベルのみを持つ場合（`traefik.enable=true`なし）、ルートサーバーは**自動ルート**を生成します：

```
{service}-{networkID}.{baseDomain}
```

例えば、ネットワークID `2816`とベースドメイン`example.com`のリポジトリ内の`myapp`というサービスは以下を取得します：

```
myapp-2816.example.com
```

自動ルートは開発や内部アクセスに便利です。カスタムドメインを使用する本番サービスには、ティア2ラベルを使用してください。

### ティア2：`traefik.*`ラベル（ユーザー定義）

カスタムドメインルーティング、TLS、特定のエントリポイントが必要な場合は、`docker-compose.yml`にこれらのラベルを追加します。`traefik.enable=true`を設定すると、ルートサーバーに自動ルートの代わりにカスタムルールを使用するよう指示します。

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

これらは標準の[Traefik v3ラベル構文](https://doc.traefik.io/traefik/routing/providers/docker/)を使用します。

> **ヒント：** 内部専用サービス（データベース、キャッシュ、メッセージキュー）には`traefik.enable=true`を設定**しないで**ください。自動的に注入される`rediacc.*`ラベルのみが必要です。

## HTTP/HTTPSサービスの公開

### 前提条件

1. マシンにインフラストラクチャが設定されていること（[マシンセットアップ — インフラストラクチャ設定](/ja/docs/setup#インフラストラクチャ設定)）：

   ```bash
   rdc context set-infra server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   rdc context push-infra server-1
   ```

2. ドメインのDNSレコードがサーバーのパブリックIPを指していること（下記の[DNS設定](#dns設定)を参照）。

### ラベルの追加

公開したいサービスの`docker-compose.yml`に`traefik.*`ラベルを追加します：

```yaml
services:
  myapp:
    image: myapp:latest
    network_mode: host
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    network_mode: host
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # traefikラベルなし — データベースは内部専用
```

| ラベル | 目的 |
|-------|---------|
| `traefik.enable=true` | このコンテナのカスタムTraefikルーティングを有効化 |
| `traefik.http.routers.{name}.rule` | ルーティングルール — 通常は`Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | リッスンするポート：`websecure`（HTTPS IPv4）、`websecure-v6`（HTTPS IPv6） |
| `traefik.http.routers.{name}.tls.certresolver` | 証明書リゾルバ — 自動Let's Encryptには`letsencrypt`を使用 |
| `traefik.http.services.{name}.loadbalancer.server.port` | コンテナ内でアプリケーションがリッスンするポート |

ラベル内の`{name}`は任意の識別子です。関連するルーター/サービス/ミドルウェアラベル間で一貫している必要があります。

> **注意：** `rediacc.*`ラベル（`rediacc.service_name`、`rediacc.service_ip`、`rediacc.network_id`）は`renet compose`によって自動的に注入されます。composeファイルに追加する必要はありません。

## TLS証明書

TLS証明書はCloudflare DNS-01チャレンジを使用してLet's Encrypt経由で自動的に取得されます。インフラストラクチャ設定時に一度だけ設定します：

```bash
rdc context set-infra server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

サービスに`traefik.http.routers.{name}.tls.certresolver=letsencrypt`が設定されている場合、Traefikは自動的に以下を行います：
1. Let's Encryptから証明書をリクエスト
2. Cloudflare DNS経由でドメイン所有権を検証
3. 証明書をローカルに保存
4. 有効期限前に更新

Cloudflare DNS APIトークンには、保護したいドメインに対する`Zone:DNS:Edit`権限が必要です。このアプローチはCloudflareで管理されるすべてのドメイン（ワイルドカード証明書を含む）に対応しています。

## TCP/UDPポートフォワーディング

非HTTPプロトコル（メールサーバー、DNS、外部公開するデータベース）には、TCP/UDPポートフォワーディングを使用します。

### ステップ1：ポートの登録

インフラストラクチャ設定時に必要なポートを追加します：

```bash
rdc context set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc context push-infra server-1
```

これにより`tcp-{port}`と`udp-{port}`という名前のTraefikエントリポイントが作成されます。

### Plain TCP Example (Database)

To expose a database externally without TLS passthrough (Traefik forwards raw TCP):

```yaml
services:
  postgres:
    image: postgres:17
    network_mode: host
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 is pre-configured (see below), so no `--tcp-ports` setup is needed.

> **Security note:** Exposing a database to the internet is a risk. Use this only when remote clients need direct access. For most setups, keep the database internal and connect through your application.

> ポートの追加または削除後は、プロキシ設定を更新するために常に`rdc context push-infra`を再実行してください。

### ステップ2：TCP/UDPラベルの追加

composeファイルで`traefik.tcp.*`または`traefik.udp.*`ラベルを使用します：

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    network_mode: host
    labels:
      - "traefik.enable=true"

      # SMTP (ポート 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (ポート 993) — TLSパススルー
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

主要な概念：
- **`HostSNI(\`*\`)`** は任意のホスト名にマッチ（プレーンSMTPなどSNIを送信しないプロトコル用）
- **`tls.passthrough=true`** はTraefikが復号化せずに生のTLS接続を転送することを意味し、アプリケーション自体がTLSを処理
- エントリポイント名は`tcp-{port}`または`udp-{port}`の規則に従う

### 事前設定済みポート

以下のTCP/UDPポートにはデフォルトでエントリポイントがあります（`--tcp-ports`で追加する必要なし）：

| ポート | プロトコル | 一般的な用途 |
|------|----------|------------|
| 80 | HTTP | Web（HTTPSへ自動リダイレクト） |
| 443 | HTTPS | Web（TLS） |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000-10010 | TCP | 動的範囲（自動割り当て） |

## DNS設定

`set-infra`で設定したサーバーのパブリックIPアドレスにドメインを向けます：

### 個別サービスドメイン

各サービスにA（IPv4）およびAAAA（IPv6）レコードを作成します：

```
app.example.com      A     203.0.113.50
app.example.com      AAAA  2001:db8::1
gitlab.example.com   A     203.0.113.50
mail.example.com     A     203.0.113.50
```

### 自動ルート用ワイルドカード

自動ルート（ティア1）を使用する場合、ワイルドカードDNSレコードを作成します：

```
*.example.com   A     203.0.113.50
*.example.com   AAAA  2001:db8::1
```

これによりすべてのサブドメインがサーバーにルーティングされ、Traefikが`Host()`ルールまたは自動ルートホスト名に基づいて正しいサービスにマッチングします。

## ミドルウェア

Traefikミドルウェアはリクエストとレスポンスを変更します。ラベル経由で適用します。

### HSTS（HTTP Strict Transport Security）

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### 大容量ファイルアップロードバッファリング

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### 複数のミドルウェア

カンマ区切りでミドルウェアをチェーンします：

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

利用可能なミドルウェアの完全なリストについては、[Traefikミドルウェアドキュメント](https://doc.traefik.io/traefik/middlewares/overview/)を参照してください。

## 診断

サービスにアクセスできない場合、サーバーにSSHしてルートサーバーのエンドポイントを確認します：

### ヘルスチェック

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

全体的なステータス、検出されたルーターとサービスの数、自動ルートが有効かどうかを表示します。

### 検出されたルート

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

すべてのHTTP、TCP、UDPルーターとそのルール、エントリポイント、バックエンドサービスを一覧表示します。

### ポート割り当て

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

動的に割り当てられたポートのTCPおよびUDPポートマッピングを表示します。

### よくある問題

| 問題 | 原因 | 解決方法 |
|---------|-------|----------|
| サービスがルートに表示されない | コンテナが実行されていない、またはラベルが不足 | リポジトリのデーモンで`docker ps`を確認、ラベルを確認 |
| 証明書が発行されない | DNSがサーバーを指していない、または無効なCloudflareトークン | DNS解決を確認、Cloudflare APIトークンの権限を確認 |
| 502 Bad Gateway | アプリケーションが宣言されたポートでリッスンしていない | アプリが`{SERVICE}_IP`にバインドし、ポートが`loadbalancer.server.port`と一致していることを確認 |
| TCPポートに到達できない | インフラストラクチャにポートが登録されていない | `rdc context set-infra --tcp-ports ...`と`push-infra`を実行 |

## 完全な例

この例では、PostgreSQLデータベースを持つWebアプリケーションをデプロイします。アプリは`app.example.com`でTLS付きで公開されます。データベースは内部専用です。

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    network_mode: host
    restart: unless-stopped
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # traefikラベルなし — 内部専用
```

### Rediaccfile

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

`app.example.com`をサーバーのパブリックIPに向けるAレコードを作成します：

```
app.example.com   A   203.0.113.50
```

### デプロイ

```bash
rdc repo up my-app -m server-1 --mount
```

数秒以内にルートサーバーがコンテナを検出し、Traefikがルートを取得してTLS証明書をリクエストし、`https://app.example.com`が公開されます。
