---
title: ネットワーキング
description: リバースプロキシ、Dockerラベル、TLS証明書、DNS、TCP/UDPポートフォワーディングによるサービスの公開。
category: Guides
order: 6
language: ja
sourceHash: "536db0c93646cad6"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# ネットワーキング

このページでは、隔離されたDockerデーモン内で実行されているサービスをインターネットからアクセス可能にする方法を説明します。リバースプロキシシステム、ルーティング用Dockerラベル、TLS証明書、DNS、TCP/UDPポートフォワーディングについて説明します。

サービスがループバックIPを取得する仕組みと`.rediacc.json`スロットシステムについては、[サービス](/ja/docs/services#サービスネットワーキングrediaccjson)を参照してください。

## ネットワーク分離

各リポジトリは、ネットワークフックを使用してカーネルレベルで自動的に分離されます。Linux kernel 6.1以降が必要です。設定は不要です。

- **自動バインド書き換え**: サービスは通常通り`0.0.0.0`または`127.0.0.1`にバインドできます。カーネルはアドレスをサービスに割り当てられたループバックIPに透過的に書き換えます。`${SERVICE_IP}`への明示的なバインドは不要です。
- **クロスリポジトリ接続ブロック**: サービスがリポジトリの`/26`サブネット外のループバックIPに接続しようとすると、カーネルがブロックします。リポジトリAのプロセスはリポジトリBのサービスに到達できません。
- **アプリケーション変更不要**: サービスはバインドに`0.0.0.0`または`localhost`を使用し、カーネルが正しいループバックIPでのみリッスンすることを保証します。分離は完全に透過的です。

## 仕組み

Rediaccは、外部トラフィックをコンテナにルーティングするために2コンポーネントのプロキシシステムを使用します：

1. **ルートサーバー**、すべてのリポジトリDockerデーモンにわたって実行中のコンテナを検出するsystemdサービス。コンテナラベルを検査し、YAMLエンドポイントとして提供されるルーティング設定を生成します。
2. **Traefik**、5秒ごとにルートサーバーをポーリングし、検出されたルートを適用するリバースプロキシ。HTTP/HTTPSルーティング、TLS終端、TCP/UDPフォワーディングを処理します。

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

> ルートサーバーのバイナリはCLIバージョンと同期して維持されます。CLIがマシン上のrenetバイナリを更新すると、ルートサーバーは自動的に再起動されます（約1-2秒）。これによるダウンタイムはなく、Traefikは再起動中も最後に知られた設定でトラフィックを提供し続け、次のポーリングで新しい設定を取得します。既存のクライアント接続は影響を受けません。アプリケーションコンテナは変更されません。

## Dockerラベル

ルーティングはDockerコンテナラベルで制御されます。2つのティアがあります：

### ティア1：`rediacc.*`ラベル（自動）

これらのラベルは、サービス起動時に`renet compose`によって**自動的に注入**されます。手動で追加する必要はありません。

| ラベル | 説明 | 例 |
|-------|-------------|---------|
| `rediacc.service_name` | サービスID | `myapp` |
| `rediacc.service_ip` | 割り当てられたループバックIP | `127.0.11.2` |
| `rediacc.network_id` | リポジトリのデーモンID | `2816` |
| `rediacc.repo_name` | リポジトリ名 | `marketing` |
| `rediacc.tcp_ports` | サービスがリッスンするTCPポート | `8080,8443` |
| `rediacc.udp_ports` | サービスがリッスンするUDPポート | `53` |

コンテナが`rediacc.*`ラベルのみを持つ場合（`traefik.enable=true`なし）、ルートサーバーはリポジトリ名とマシンのサブドメインを使用して**自動ルート**を生成します：

```
{service}.{repoName}.{machineName}.{baseDomain}
```

例えば、マシン`server-1`上の`marketing`というリポジトリ内でベースドメイン`example.com`の`myapp`というサービスは以下を取得します：

```
myapp.marketing.server-1.example.com
```

フォークの場合、サービス名は予約語`fork`とタグと組み合わされます：

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

例えば、`staging`とタグ付けされた`marketing`のフォークは以下を取得します：

```
myapp-fork-staging.marketing.server-1.example.com
```

各フォークURLは親リポジトリのサブドメイン下に位置し、既存のワイルドカード証明書でカバーされるため、新しい証明書は不要です。`-fork-`セパレータは本番リポジトリの実際のサービス名との衝突を防ぎます。カスタムドメインを使用するサービスには、ティア2ラベルまたは`rediacc.domain`ラベルを使用してください。

#### `rediacc.domain`によるカスタムドメイン

`docker-compose.yml`の`rediacc.domain`ラベルを使用して、サービスにカスタムドメインを設定できます。短縮名と完全なドメインの両方がサポートされています：

```yaml
labels:
  # 短縮名, マシンのbaseDomainを使用してcloud.example.comに解決
  - "rediacc.domain=cloud"

  # 完全なドメイン, そのまま使用
  - "rediacc.domain=cloud.example.com"
```

ドットを含まない値は短縮名として扱われ、マシンの`baseDomain`が自動的に追加されます。ドットを含む値は完全なドメインとして使用されます。

`machineName`が設定されている場合、カスタムドメインサービスは**2つのルート**を取得します：ベースドメイン上のルート（`cloud.example.com`）とマシンサブドメイン上のルート（`cloud.server-1.example.com`）。

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

1. マシンにインフラストラクチャが設定されていること（[マシンセットアップ, インフラストラクチャ設定](/ja/docs/setup#インフラストラクチャ設定)）：

   ```bash
   # 共有資格情報（configごとに一度、すべてのマシンに適用）
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # マシン固有の設定
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. ドメインのDNSレコードがサーバーのパブリックIPを指していること（下記の[DNS設定](#dns設定)を参照）。

### ラベルの追加

公開したいサービスの`docker-compose.yml`に`traefik.*`ラベルを追加します：

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # traefikラベルなし, データベースは内部専用
```

| ラベル | 目的 |
|-------|---------|
| `traefik.enable=true` | このコンテナのカスタムTraefikルーティングを有効化 |
| `traefik.http.routers.{name}.rule` | ルーティングルール, 通常は`Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | リッスンするポート：`websecure`（HTTPS IPv4）、`websecure-v6`（HTTPS IPv6） |
| `traefik.http.routers.{name}.tls.certresolver` | 証明書リゾルバ, 自動Let's Encryptには`letsencrypt`を使用 |
| `traefik.http.services.{name}.loadbalancer.server.port` | コンテナ内でアプリケーションがリッスンするポート |

ラベル内の`{name}`は任意の識別子です。関連するルーター/サービス/ミドルウェアラベル間で一貫している必要があります。

> **注意：** `rediacc.*`ラベル（`rediacc.service_name`、`rediacc.service_ip`、`rediacc.network_id`）は`renet compose`によって自動的に注入されます。composeファイルに追加する必要はありません。

## TLS証明書

TLS証明書はCloudflare DNS-01チャレンジを使用してLet's Encrypt経由で自動的に取得されます。資格情報はconfigごとに一度設定します（すべてのマシンで共有）：

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

自動ルートはサービスごとの証明書の代わりにリポジトリサブドメインレベルの**ワイルドカード証明書**（`*.marketing.server-1.example.com`）を使用します。証明書は最初の`repo up`時にTraefikによって自動的にプロビジョニングされます。手動の手順は不要です。フォークは親リポジトリの既存のワイルドカードを再利用するため、新しい証明書リクエストが発生することはありません。カスタムドメインルートはマシンレベルのワイルドカード（`*.server-1.example.com`）を使用します。

> **Cloudflare資格情報が必要です。** ワイルドカード証明書はDNS-01チャレンジを使用します。`--cf-dns-token`（およびオプションの`--cert-email`）なしでは、TraefikはチャレンジをDNS完了できず、HTTPSは機能しません。HTTPは機能し続けます。最初のデプロイ前に`rdc config infra set`で資格情報を設定してください。

`traefik.http.routers.{name}.tls.certresolver=letsencrypt`を持つティア2ルートでは、ルートのホスト名に基づいてワイルドカードドメインSANが自動的に注入されます。

Cloudflare DNS APIトークンには、保護したいドメインに対する`Zone:DNS:Edit`権限が必要です。

### TLS証明書のライフサイクル

Let's Encrypt証明書が発行されてから各リポジトリのコンテナに届くまでの完全な経路：

1. **ホストでの発行。** マシンレベルのTraefikコンテナ（`rediacc-proxy`、`/opt/rediacc/proxy/`にデプロイ）がACME更新を所有します。ホスト上の`/opt/rediacc/proxy/letsencrypt/acme.json`にすべての状態を保存します。更新は有効期限の約30日前に自動的にトリガーされます。`--cf-dns-token`が設定されていれば、オペレーターのアクションは不要です。

2. **リポジトリごとのダンピング（オプション）。** 独自のコンテナ内に証明書ファイルが必要なサービス（例：`.pem`を直接読み込むメールサーバー）は、小さな`traefik-certs-dumper`コンテナを自分自身の隣にデプロイします。ダンパーは`/opt/rediacc/proxy/letsencrypt`を読み取り専用でバインドマウントし、抽出された証明書とキーをリポジトリのデータボリュームに`cert.pem` / `key.pem`として書き込みます。これが機能するには、リポジトリごとのDockerデーモンがマウント名前空間のアローリストに`/opt/rediacc/proxy`を持つ必要があります。これはデフォルトで既に含まれています。

3. **クライアントサイドキャッシュ（`rediacc.json`）。** CLIは`acme.json`の圧縮コピーを設定ファイルの`acmeCertCache`に`baseDomain`をキーとして保存します。これにより複数のマシンが証明書を共有でき（`rdc config cert-cache push <machine>`経由）、オフラインインベントリとして機能します。

**クライアントキャッシュの同期トリガー：**

- `rdc repo up`後に自動的に、ただしマシンの`baseDomain`のローカルキャッシュが6時間以上古い場合のみ。新鮮なキャッシュはそのまま残され、連続したデプロイがSSHを酷使しないようにします。
- オンデマンド：`rdc config cert-cache pull -m <machine>`（強制プル）または`rdc machine query --name <machine> --sync-certs`（ステータスクエリの副作用としてのプル）。
- `rdc config infra push`時、キャッシュはマシンにプッシュされます（より長い有効期限のローカル証明書がリモートより優先されます）。

**キャッシュメンテナンス：**

- 古い自動ルートエントリ（`service-3200.rediacc.io`のような古いネットワークIDタグ付きドメイン）は、各プル時に削除されます。
- `notAfter`が7日以上過去の証明書は完全に削除されます。不活性でキャッシュを膨張させるだけです。
- `rdc config cert-cache clear`はすべてを消去します。`rdc config cert-cache status`はインベントリを表示します。

**トラブルシューティング：** `traefik-certs-dumper`が`/traefik/acme.json: no such file or directory`でクラッシュする場合、リポジトリごとのデーモンがホストのletsencryptストアを見ることができません。（a）ホスト上に`/opt/rediacc/proxy/letsencrypt/acme.json`が存在することを確認してください（これはホストレベルの`rediacc-proxy`の責任です）、および（b）リポジトリごとのデーモンが`/opt/rediacc/proxy`をアローリストに含む十分に新しいrenetで起動されたことを確認してください。renetをアップグレードした後、`rdc repo up`でリポジトリを再デプロイして適用してください。

> **実験的：** 自動同期ケイデンスと有効期限ベースの削除はrenet 0.9+で導入されました。古いCLI/renetバージョンは`rdc config cert-cache pull`経由の純粋な手動同期を使用します。

## TCP/UDPポートフォワーディング

非HTTPプロトコル（メールサーバー、DNS、外部公開するデータベース）には、TCP/UDPポートフォワーディングを使用します。

### ステップ1：ポートの登録

インフラストラクチャ設定時に必要なポートを追加します：

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

これにより`tcp-{port}`と`udp-{port}`という名前のTraefikエントリポイントが作成されます。

> ポートの追加または削除後は、プロキシ設定を更新するために常に`rdc config infra push`を再実行してください。

### ステップ2：TCP/UDPラベルの追加

composeファイルで`traefik.tcp.*`または`traefik.udp.*`ラベルを使用します：

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (ポート 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (ポート 993), TLSパススルー
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

### プレーンTCPの例（データベース）

TLSパススルーなしでデータベースを外部に公開する場合（TraefikがrawTCPを転送）：

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

ポート5432は事前設定済みです（下記参照）。`--tcp-ports`の設定は不要です。

> **セキュリティノート：** データベースをインターネットに公開することはリスクです。リモートクライアントが直接アクセスを必要とする場合にのみ使用してください。ほとんどの設定では、データベースを内部に保ち、アプリケーション経由で接続してください。

### 事前設定済みポート

以下のTCP/UDPポートにはデフォルトでエントリポイントがあります（`--tcp-ports`で追加する必要なし）。エントリポイントは設定されたアドレスファミリーに対してのみ生成されます。IPv4エントリポイントには`--public-ipv4`が、IPv6エントリポイントには`--public-ipv6`が必要です：

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

### 自動DNS（Cloudflare）

`--cf-dns-token`が設定されている場合、`rdc config infra push`はCloudflareに必要なDNSレコードを自動的に作成します：

| レコード | タイプ | 内容 | 作成元 |
|----------|--------|------|--------|
| `server-1.example.com` | A / AAAA | マシンのパブリックIP | `push-infra` |
| `*.server-1.example.com` | A / AAAA | マシンのパブリックIP | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | マシンのパブリックIP | `repo up` |

マシンレベルのレコードは`push-infra`によって作成され、カスタムドメインルート（`rediacc.domain`）をカバーします。リポジトリごとのワイルドカードレコードは`repo up`によって自動的に作成され、そのリポジトリの自動ルートをカバーします。

これは冪等です。IPが変更された場合は既存のレコードが更新され、既に正しい場合はそのまま維持されます。

ベースドメインのワイルドカード（`*.example.com`）は、`rediacc.domain=erp`のようなカスタムドメインラベルを使用する場合、手動で作成する必要があります。

### 手動DNS

Cloudflareを使用しない場合やDNSを手動で管理する場合は、A（IPv4）および/またはAAAA（IPv6）レコードを作成します：

```
# マシンサブドメイン（rediacc.domain=erpのようなカスタムドメインルート用）
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# リポジトリごとのワイルドカード（myapp.marketing.server-1.example.comのような自動ルート用）
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# ベースドメインワイルドカード（rediacc.domain=erpのようなカスタムドメインサービス用）
*.example.com                  A     203.0.113.50
```

Cloudflare DNSが設定されている場合、リポジトリごとのワイルドカードレコードは`repo up`によって自動的に作成されます。複数のマシンがある場合、各マシンはそれぞれのIPを指す独自のDNSレコードを取得します。

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
| 502 Bad Gateway | アプリケーションが宣言されたポートでリッスンしていない | アプリが実行中でポートが`loadbalancer.server.port`と一致していることを確認 |
| TCPポートに到達できない | インフラストラクチャにポートが登録されていない | `rdc config infra set --tcp-ports ...`と`push-infra`を実行 |
| ルートサーバーが古いバージョン | バイナリは更新されたがサービスが再起動されていない | プロビジョニング時に自動的に発生します。手動の場合：`sudo systemctl restart rediacc-router` |
| STUN/TURNリレーに到達できない | リレーアドレスが起動時にキャッシュされた | DNSまたはIP変更後、新しいネットワーク設定を取得するためにサービスを再作成 |

## 完全な例

この例では、PostgreSQLデータベースを持つWebアプリケーションをデプロイします。アプリは`app.example.com`でTLS付きで公開されます。データベースは内部専用です。

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
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
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # traefikラベルなし, 内部専用
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
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
rdc repo up --name my-app -m server-1
```

数秒以内にルートサーバーがコンテナを検出し、Traefikがルートを取得してTLS証明書をリクエストし、`https://app.example.com`が公開されます。
