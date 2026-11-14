---
title: "オンプレミスインストール"
description: "独自インフラ上でアカウントサーバーとCLIディストリビューションを運用する方法。"
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: ja
sourceHash: "6b60637180f58cc2"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Rediaccは完全に独自インフラ上で運用できます。スタンドアロンDockerイメージには、アカウントサーバー、ウェブポータル、マーケティングサイト、およびCLIディストリビューションエンドポイントが含まれます。Rediaccのホスト型サービスへの外部依存は不要です。

## rdcでインストールする

`rdc server install`は、CLIがSSHで到達できるマシンに、アカウントサーバーをリポジトリとしてインストールします。1つのコマンドで、マシンの確認、renetのセットアップ、DNS、TLS、キー生成、ライセンス、起動、オーナーアカウントの作成までを行います。すべての値にフラグがあります。ターミナルでは不足している値を尋ね、`--yes`を付けると何も尋ねず、不足した値は拒否されます。各ステップは記録されるため、再実行では完了済みのステップが省略されます。

ステップは次の順です。`preflight`(パスワードなしのsudo、アーキテクチャ、80番と443番ポート、ディスク容量、時計のずれ)、`setup`(renetがない場合のみ`rdc machine setup`)、`dns`、`tls`、`repo`、`keys`、`licence`、`image`、`up`、`owner`。

### 既存のマシンを優先する

インストール先は、すでに存在するマシンです。データセンターのサーバーでも、LAN上の機器でも構いません。設定済みのマシンは引数で指定します。まだ登録されていないマシンは、アドレスで追加します。

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port`と`--name`で、SSHポートとマシンの登録名を指定します。クラウドVMは事前に`rdc machine provision`で作成します。インストール自体がVMを作成することはありません。

### DNS

インストールは、サーバーのドメインとバックアップストアのドメイン(`--store-domain`、既定値は`<名前>-store.<ドメインの残り>`)のAレコードとAAAAレコードを表示し、両方がマシンに解決されるまで待ちます。ゾーンにレコードが書き込まれることはありません。`--no-dns-wait`はレコードを表示してそのまま進むため、ローカルのリゾルバーが提供するLAN内の名前に向いています。

### TLS

`--tls`は3つの方式から1つを選びます。

| 方式 | 必要なもの | 備考 |
|---|---|---|
| `letsencrypt` | 80番と443番ポートにインターネットから到達できること | HTTP-01チャレンジ。`--cert-email`が有効期限の通知を受け取ります。既定値はオーナーです。 |
| `cloudflare` | `--cf-token` | CloudflareのAPIトークンによるDNS-01チャレンジ。 |
| `byo` | `--tls-cert`と`--tls-key` | 両方のドメインをカバーする既存のPEM証明書。`--tls-ca`は、ヘルスチェックが信頼するCAを指定します。 |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### イメージ

イメージのステップでは、既定でマシン上に`ghcr.io/rediacc/server:latest`をpullします。`--image`で別の参照を選べます。`--image-file`は`docker save`で作成したtarを送り、`--local-image`はローカルのDockerから`--image`を保存して送ります。どちらもマシンからレジストリへアクセスする必要がありません。

### ライセンスと無料プラン

`--licence auto`(既定)は、ログイン中のアカウントの委任証明書を使い、なければ無料プランで起動します。`--licence free`は常に無料プランで起動します。インストールコマンドが存在する前にログインしたアカウントは、適切なスコープを得るために`rdc subscription login`を再実行する必要があります。

アカウントサーバーへの経路がないマシンでは、`--cert <file>`で別の場所で取得した委任証明書を渡せます。証明書にはマシン上で生成されたキーが指定されている必要があるため、通常は先に無料プランでインストールし、その後に証明書を適用します。

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence`は、無料プランのサーバーを、ログイン中のアカウントまたは`--cert`の証明書に切り替えます。サーバーが何を検証するかは、後述のライセンスのセクションのステップ3に記載しています。

### リカバリーバンドル

すべてのキーはマシン上で生成され、リポジトリの`secrets.env`にのみ書き込まれます。ターミナルでは、インストールの最後に一度だけリカバリーバンドルを表示します。内容は、委任されたキーペア、アカウント設定サーバーのキー、オブジェクトストレージの認証情報です。バンドルはログに記録されず、`--output json`にも含まれません。ターミナルがない場合は表示されず、最後の行で`rdc server backup`が案内されます。

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out`はファイルをモード0600で書き込みます。指定しない場合、バンドルはstdoutに出力されます。インストール時の`--bws-project <id>`は、キーをBitwarden Secrets Managerのプロジェクトにもコピーし、`--rotate`は保存済みの異なる値を置き換えます。`--bws-project`がない場合、キーがサーバーの外へ出るのは、インストール時に表示されるリカバリーバンドルと、`rdc server backup --out`が書き込むファイルだけです。

### ステータス

```bash
rdc server status accounts.example.com
```

ステータスには、サーバーのヘルス、プラン、証明書、イメージが表示されます。このデバイスにドメインのインストール記録がない場合は、`--machine`と`--repo`で対象を指定します。

### アップデート

| コンポーネント | コマンド |
|---|---|
| CLI | `rdc update` |
| マシン上のrenet | `rdc machine setup <machine>` |
| サーバーイメージとテンプレート | `rdc server upgrade <domain>` |

`rdc server upgrade`は、リポジトリをロールバック用にforkし、新しいイメージを配置し、組み込みのテンプレートが新しければ再適用して、再起動します。インストールと同様に`--image`、`--image-file`、`--local-image`を受け付けるため、エアギャップのマシンは保存したイメージのtarからアップグレードできます。

## Dockerイメージ

スタンドアロンイメージをプルします：

```bash
docker pull ghcr.io/rediacc/server:stable
```

デフォルト設定で実行します：

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

イメージが提供するエンドポイント：
- アカウントAPI：`/account/api/v1/`
- ウェブポータル：`/account/`
- マーケティングサイト：`/`
- CLIアーティファクト：`/releases/`
- Renetバイナリ：`/bin/`

## サーバーからのCLIインストール

ユーザーはオンプレミスサーバーから直接CLIをインストールできます。インストールスクリプトは更新チャネルを自動検出し、CLIがサーバーから更新を確認するよう設定します。

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

このコマンド一つで以下を行います：
1. サーバーの`/releases/`エンドポイントからCLIバイナリをダウンロードします
2. `/account/api/v1/.well-known/server-info`をクエリして更新チャネルを検出します
3. サーバーURL、更新チャネル、暗号化キーを`account.*`フィールド以下に含めた、デフォルトconfig（`rediacc.json`）を書き込みます
4. `rdc update`が今後の更新をサーバーから確認するよう設定します

`REDIACC_CHANNEL`変数は不要です。インストールスクリプトはサーバーの設定からチャネルを自動的に読み取ります。

## 名前付きConfigを使ったCLI設定

複数のサーバー（オンプレミス、本番、エッジ）に接続するユーザーには、名前付きconfigで各環境を分離できます：

```bash
# オンプレミスサーバー用のconfigを作成する
rdc config init myserver --server https://account.example.com

# そのconfigでログインする
rdc --config myserver subscription login

# --configを指定した全コマンドがオンプレミスサーバーを使用する
rdc --config myserver machine status prod-1
```

各名前付きconfigは専用のアカウントサーバーURL（`account.*`以下）と専用のアカウントAPIトークンを保持し、トークンはconfigのそばに`api-token-<name>.json`として保存されます。configを切り替えることでサーバーコンテキスト全体が切り替わります。

## エアギャップ環境

インターネットアクセスのない環境では、サーバーURLとカスタムリリースURLの両方を設定します：

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

CLIは公開リリースCDNの代わりに`account.example.com/releases/cli/stable/manifest.json`から更新を確認します。

サーバーが完全にオフラインの場合、バンドルされたtarballからnpm経由でCLIをインストールします：

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## 環境変数リファレンス

| 変数 | 使用箇所 | 目的 |
|---|---|---|
| `REDIACC_SERVER_URL` | インストールスクリプト | アカウントサーバーURL。チャネルと暗号化キーを自動検出します。 |
| `REDIACC_RELEASES_URL` | インストールスクリプト、CLIアップデーター | CLIバイナリ用カスタムリリースエンドポイント。デフォルト：`https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | インストールスクリプト | 更新チャネルを上書きします。未設定の場合はサーバーから自動検出されます。 |
| `REDIACC_ACCOUNT_SERVER` | CLIランタイム | 全CLIコマンドのアカウントサーバーURLを上書きします。 |
| `REDIACC_UPDATE_CHANNEL` | CLIランタイム | `rdc update`の更新チャネルを上書きします。 |

## サーバー設定

オンプレミスDockerイメージはホスト型サービスと同じ`ENVIRONMENT`変数を使用します。DockerまたはオーケストレーションのConfigに設定してください：

- `ENVIRONMENT=production`（デフォルト）：標準のリソース制限。このサーバーに接続するCLIはデフォルトで**stable**アップデートチャネルを使用します。値名`production`はレガシーデプロイ識別子です。`production`と`edge`はどちらも本番環境品質です。
- `ENVIRONMENT=edge`：Communityの2倍制限。CLIはデフォルトで**edge**アップデートチャネルを使用します

各環境の詳細については[リリースチャネル](/en/docs/release-channels)を参照してください。

## サーバーがCLIに伝えること

CLIがサーバーに接続すると、`/.well-known/server-info`をクエリして以下を検出します：

- **E2E暗号化公開鍵**：ゼロ知識Config保存のため
- **最低CLIバージョン**：古いCLIの接続をブロック
- **更新チャネル**：CLIが更新に使用するリリースチャネルを通知
- **環境**：サーバーが実行するデプロイプロファイル(標準制限 vs. 2X制限のedge)

この自動設定により、ユーザーはサーバーURLを知るだけで済みます。その他は自動的に検出されます。

## エアギャップデプロイメントのライセンス

エアギャップおよびセルフホスト型オンプレミスサーバーは、上流マスターキーで署名された**委任証明書**を使用してライセンスをローカルで発行します。証明書はオンプレミスサーバーをそのプランの制限内に制約し、改ざん検知可能なチェーンを形成します。暗号設計（チェーン整合性、フォーク検出、監査証明）については[ライセンスチェーンと委任](/en/docs/license-chain)を参照してください。

このセクションでは、運用上のセットアップ（キー生成、証明書の取得、自動更新の設定、オフライン（エアギャップ）更新フロー）を説明します。

### 1サブスクリプション、1オンプレミスインストール

1つのサブスクリプションは**同時に最大1つのアクティブな委任証明書**を持てます。各オンプレミスインストールは、独自のローカル発行台帳に対して月次制限とマシン制限を適用します。そのため、複数のアクティブな証明書が存在すると、調整が不可能なまま有効クォータが倍増してしまいます。

別々の環境（本番、ステージング、DR、マルチリージョン）が必要な場合は、インストールごとに1つのサブスクリプションを購入してください。シングルアクティブ強制はこの契約を明文化したものです。2つ目のアクティブな証明書を作成しようとすると、`409 DELEGATION_CERT_ALREADY_ACTIVE`が返され、既存の証明書IDと更新（推奨、チェーンを保持）または取り消して再作成（チェーンをリセット）の手順が示されます。

### 1. オンプレミスEd25519キーペアの生成

オンプレミスサーバーはライセンス署名に専用のEd25519キーペアを使用します。上流の委任証明書がこの特定の公開鍵を認可します。

```bash
# 新しいキーペアを生成する
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# base64に変換する（オンプレミスが環境変数に期待するフォーマット）
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

秘密鍵は他のシークレットと一緒に保管してください（例：Dockerシークレット、Kubernetes Secret）。オンプレミス環境から外に出ることはありません。

### 2. 上流からの委任証明書のリクエスト

上流アカウントポータルから証明書を取得する方法は3つあります：

**オプションA：顧客セルフサービス（推奨）。** Orgのオーナーまたはアドミンとして上流ポータルにログインし、**/account/delegation-certs**に移動します。**Create New**をクリックし、オンプレミス公開鍵（base64 SPKI）を貼り付け、有効期間を選択（またはプランごとのデフォルトを受け入れ）して、生成された`.json`ファイルをダウンロードします。

**オプションB：Admin（クロスカスタマー）。** Rediaccサポートまたは上流システムアドミンが同じパラメーターで`POST /admin/delegation-certs`を呼び出せます。

**オプションC：`rdc` CLI（計画中）。** 将来のCLIコマンドがポータルのフローをラップする予定です。

返される`.json`の形式：

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

証明書の有効期間は有効ポリシーによって決まります（プランごとのデフォルトと上限、サブスクリプションごとの上書き、サブスクリプション終了+3日の猶予期間にキャップ）。レスポンスには`effectiveDays`と`reason`も含まれるため、その値が選択された理由を確認できます。完全なルールについては[ライセンスチェーン - 有効ポリシー](/en/docs/license-chain)を参照してください。

### 3. オンプレミスサーバーへの証明書のインストール

サーバーは委任証明書を、データボリューム上の1つのファイル`/data/delegation-cert.json`（パスは`DELEGATION_CERT_PATH`で指定）から読み込みます。証明書そのものを保持する環境変数はありません。`rdc server install`はダウンロードした証明書をそこに置き、`rdc server licence`は後からそれを差し替えます。

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

どちらのコマンドも、証明書を証明書インボックス（`data/web/cert-inbox/new.json`）経由で稼働中のサーバーに渡します。サーバーは証明書を検証し、`applied.json`または`rejected.json`で応答します。コマンドは新しい証明書IDを`rdc server status`で確認します（ステップ6の`cert-status`と同じデータです）。`rdc server upgrade`も同じインボックスを使います。サーバーは`DELEGATION_CERT_BASE64`を読み込まなくなりました。アップグレードの1ステップが、`secrets.env`に残っていた値をインボックスへ移すため、インボックス導入前にインストールしたボックスでも証明書は保持されます。

サーバーは起動時に証明書を読み込み、ライセンスの署名に使う鍵と照合します。署名鍵のフィンガープリントが証明書の`delegatedPublicKey`のフィンガープリントと一致している必要があります。証明書が認めていない鍵で署名したライセンスは、どのマシンでも検証できないためです。署名鍵ペアと証明書の`delegatedPublicKey`は常に一致させてください。

起動時にサーバーが拒否した証明書（署名不正、鍵の不一致、`UPSTREAM_PUBLIC_KEY`の欠如、ファイルの破損）があっても、サーバーは停止しません。サーバーは無料プランで起動し、問題のファイルを元のファイルの隣の`delegation-cert.rejected.json`に移します。有効な証明書が入るまで、リポジトリのライセンス署名は`503 DELEGATION_CERT_REFUSED`を返し、`rdc server status`には`cert REFUSED (reason)`と表示されます。有効な証明書を指定して`rdc server licence`を実行すると復旧できます。期限切れの証明書は引き続き読み込まれ、拒否されずに段階的に機能が縮退します。

### 4. 上流検証と自動更新の設定（オプション、推奨）

オンプレミスから上流へのアウトバウンドHTTPSアクセスがある場合、手動介入なしに有効期限前に証明書を更新する自動更新を設定します：

```bash
# /onprem/cert-uploadがアップロードされた証明書を上流マスターキーに対して検証するために必要。
# UPSTREAM_API_KEYが設定されているがこれが欠けている場合、起動時にfail-fastします。
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# 自動更新ループに必要。ポータルから取得します：
#   Orgオーナー/アドミン → /account/delegation-certs → "Get auto-renew token"
# これがdelegation:renew-scopedのAPIトークンを取得する唯一の方法です。
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# オプションのチューニング（デフォルト値を表示）。
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

オンプレミスの自動更新ループは起動時に1回実行され、その後設定された間隔で実行されます。**適応型しきい値**（`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`）を使用するため、15日間のCOMMUNITY証明書は初日に更新をトリガーするのではなく、残り5日で更新されます。90日間のBUSINESS証明書は残り14日で更新されます（環境設定の上限が適用）。

更新が失敗した場合、証明書は自然な有効期限まで使用され続けます。失敗は1時間のバックオフ後、`${DELEGATION_CERT_PATH}.status.json`に記録され、`GET /onprem/cert-status`で公開されます。

### 5. エアギャップ更新（アウトバウンドHTTPSなし）

オンプレミスから上流に到達できない場合、手動転送フローを使用します：

1. **オンプレミス管理ポータルから更新リクエストをダウンロードします。** オンプレミスのシステムルートとして`GET /onprem/renewal-request`にアクセスします。ローカルチェーンヘッド、委任公開鍵、およびオンプレミス秘密鍵からのEd25519署名を含むJSONマニフェストが返されます。
2. **マニフェストをUSB、暗号化メール、またはその他のアウトオブバンドチャネルで上流に転送します。** マニフェストは小さい（数KB）ので、シークレットは含まれません。
3. **上流でマニフェストを処理します。** Orgオーナー/アドミンが**/account/delegation-certs** → **Upload renewal request**を開き、マニフェストファイルを選択します。上流はマニフェストの署名をアクティブな証明書の`delegatedPublicKey`に対して検証し（オンプレミス秘密鍵の保持者から来たことを証明）、リプレイ対策を確認し（7日以上古いマニフェストは拒否）、新しい証明書を発行します。
4. **上流ポータルから新しい証明書を`.json`ファイルとしてダウンロードします。**
5. **証明書をオンプレミスに転送して戻します。**
6. **ローカル管理ポータルからオンプレミスにアップロードします（`POST /onprem/cert-upload`）。** オンプレミスは新しい証明書を`UPSTREAM_PUBLIC_KEY`に対して検証し、証明書の`genesisSequence`がローカル発行台帳のチェーンエントリにリンクしていることを確認します（転送中のシーケンス進行がサポートされており、チェーンは自然に拡張されます）。

このループ全体で、オンプレミスからのネットワークエグレスは不要です。

#### マニフェストの失敗モード

| コード | 原因 | 修正方法 |
|---|---|---|
| `NO_ACTIVE_CERT` | このサブスクリプションに対して上流にアクティブな証明書がない | 更新ではなく作成フローで新しい証明書を発行する |
| `DELEGATED_KEY_MISMATCH` | マニフェストの`delegatedPublicKey`がアクティブな証明書と異なる | 異なるオンプレミスインストールからのリプレイの可能性がある |
| `MANIFEST_SIGNATURE_INVALID` | 署名が委任公開鍵に対して検証できない | マニフェストが転送中に改ざんされたか、別のオンプレミスで生成した |
| `MANIFEST_EXPIRED` | マニフェストが7日以上古い | オンプレミスから新しい更新リクエストを生成する |

#### 証明書アップロードの失敗モード

`POST /onprem/cert-upload`は成功すると`{uploaded: true, bootstrap, certId}`を返します。拒否された証明書には`{error, code}`が返り、`error`に詳細、`code`に下表の理由のいずれかが入ります。適用または拒否された証明書はすべてログに記録され、ボックスの所有者にメールで通知されます。

`rdc server licence`は、SSHで証明書をボックスのインボックス（`data/web/cert-inbox`）に置き、`applied.json`または`rejected.json`を読み戻します。その後、`cert-status`で新しい証明書IDを確認します。拒否の理由は同じ表のものに加え、インボックス自身が返す`not-a-regular-file`と`too-large`があります。

| コード | HTTP | 原因 |
|---|---|---|
| `malformed` | 400 | アップロードされたものが有効な証明書ではない |
| `bad-signature` | 400 | 証明書が設定済みの`UPSTREAM_PUBLIC_KEY`で署名されていない |
| `wrong-key` | 400 | 証明書がこのオンプレミスとは別の鍵向けに発行されている |
| `expired` | 400 | 証明書がすでに`validUntil`を過ぎている |
| `not-newer` | 409 | 証明書が現在有効なものより新しくない |
| `other-subscription` | 409 | 証明書が別のサブスクリプションのものである |
| `chain-ahead` | 409 | 証明書の`genesisSequence`がローカルチェーンヘッドより進んでいる |
| `chain-fork` | 409 | 証明書の`genesisSequence`でのチェーンハッシュがローカル台帳と一致しない |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY`が設定されていない |
| `write-failed` | 500 | 証明書をディスクに書き込めなかった |
| `adoption-failed` | 500 | 書き込んだ証明書をサーバーが読み込めなかった |

`bad-signature`の場合は、`UPSTREAM_PUBLIC_KEY`が上流マスター公開鍵と一致しているか確認します。`no-upstream-key`の場合は、`UPSTREAM_PUBLIC_KEY`を設定します。

### 6. ステータスとモニタリング

オンプレミスのローカル証明書状態をいつでもクエリできます：

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

ロードされた証明書の`subscriptionId`、`planCode`、`validUntil`、`daysUntilExpiry`、および`autoRenew`ブロック（`enabled`、`lastSuccessAt`、`lastErrorAt`、`lastError`）が返されます。古い`lastSuccessAt`やnullでない`lastError`をアラートするためにモニタリングスタックに組み込んでください。

バックアップと監査のため、オンプレミス管理者は`GET /onprem/cert-current`（昇格セッション必要）からも現在ロードされている署名済み証明書をダウンロードできます。

### 委任証明書の環境変数リファレンス

| 変数 | 必須？ | 目的 |
|---|---|---|
| `ON_PREMISE_MODE` | はい | `true`に設定するとオンプレミスのルートサブセットが有効になる |
| `ON_PREMISE_PRIVATE_KEY` | はい | 委任署名用のBase64 PKCS8 Ed25519秘密鍵 |
| `ON_PREMISE_PUBLIC_KEY` | はい | Base64 SPKI Ed25519公開鍵（証明書の`delegatedPublicKey`と一致する必要がある） |
| `DELEGATION_CERT_PATH` | オプション | 署名済み証明書JSONのファイルシステムパス。デフォルトはデータボリューム上の`/data/delegation-cert.json`。証明書は手作業ではなく`rdc server licence`で差し替えます。 |
| `UPSTREAM_PUBLIC_KEY` | `UPSTREAM_API_KEY`が設定されている場合、または`/onprem/cert-upload`が機能するために必須 | 上流マスター公開鍵のBase64 SPKI。ない場合、サーバーは起動時にすべての証明書を拒否し（`no-upstream-key`）、ステップ3で説明するとおり無料プランで動作します。 |
| `UPSTREAM_URL` | 自動更新に必要 | 上流アカウントサーバーのベースURL（例：`https://www.rediacc.com`） |
| `UPSTREAM_API_KEY` | 自動更新に必要 | `delegation:renew`スコープのAPIトークン。ポータルから取得 - ステップ4を参照。 |
| `AUTO_RENEW_INTERVAL_HOURS` | オプション | デフォルト24。証明書の更新が必要かどうか確認する間隔。 |
| `RENEW_THRESHOLD_DAYS` | オプション | デフォルト14。適応型1/3-of-validityしきい値の上限として機能。 |

### 脅威モデルの概要

委任証明書モデルは以下を防御します：

- **偽造ライセンス**：オンプレミスはプランの制限内でのみ署名できます。renetは証明書の範囲外のものをすべて拒否します。
- **デプロイメント間での証明書共有**：チェーンの分岐は更新時に検出されます（`CHAIN_FORK_DETECTED`を返す）。
- **マルチインストールによるクォータのバイパス**：上流がシングルアクティブ（1サブスクリプションにつき1証明書）を強制します。
- **チェーンのロールバック**：renetはサブスクリプションごとに最高シーケンス番号を保存し、低いシーケンスのblobをすべて拒否します。
- **上流クレデンシャルの侵害**：ブートストラップ`delegation:renew`トークンは専用のポータルエンドポイントからのみ発行でき、アドミン権限が必要です。このトークンは更新のみを許可し、他のリソースの読み取りや変更はできません。
- **マニフェストへのリプレイ攻撃**：7日以上古いマニフェストは拒否されます。

防御**しない**こと：

- **オンプレミス秘密鍵の侵害**：漏洩した秘密鍵により、攻撃者は証明書の`validUntil`まで署名できます。緩和策：キーペアをローテーション（古い証明書を取り消し、新しいキーで新しい証明書を作成）し、古いキーで署名されたすべてのライセンスを疑わしいものとして扱います。
- **上流マスターキーの侵害**：これはトラストルートです。ローテーション手順はここでの範囲外です。
