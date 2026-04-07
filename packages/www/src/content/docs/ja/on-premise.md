---
title: "オンプレミスインストール"
description: "独自インフラ上でアカウントサーバーとCLIディストリビューションを運用する方法。"
category: "Guides"
order: 5
language: ja
sourceHash: "bd53b8bc522532de"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Rediaccは完全に独自インフラ上で運用できます。スタンドアロンDockerイメージには、アカウントサーバー、ウェブポータル、マーケティングサイト、およびCLIディストリビューションエンドポイントが含まれます。Rediaccのホスト型サービスへの外部依存は不要です。

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
3. サーバーURL、更新チャネル、暗号化キーを含む`server.json`を書き込みます
4. `rdc update`が今後の更新をサーバーから確認するよう設定します

`REDIACC_CHANNEL`変数は不要です。インストールスクリプトはサーバーの設定からチャネルを自動的に読み取ります。

## 名前付きConfigを使ったCLI設定

複数のサーバー（オンプレミス、本番、エッジ）に接続するユーザーには、名前付きconfigで各環境を分離できます：

```bash
# オンプレミスサーバー用のconfigを作成する
rdc config init --name myserver --server https://account.example.com

# そのconfigでログインする
rdc --config myserver subscription login

# --configを指定した全コマンドがオンプレミスサーバーを使用する
rdc --config myserver machine query --name prod-1
```

各名前付きconfigは専用のアカウントサーバーURLとサブスクリプショントークンを保持します。configを切り替えることでサーバーコンテキスト全体が切り替わります。

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
| `RDC_UPDATE_CHANNEL` | CLIランタイム | `rdc update`の更新チャネルを上書きします。 |

## サーバー設定

オンプレミスDockerイメージはホスト型サービスと同じ`ENVIRONMENT`変数を使用します。DockerまたはオーケストレーションのConfig内に設定してください：

- `ENVIRONMENT=production`（デフォルト）：標準制限、クライアントへstableチャネルを推奨
- `ENVIRONMENT=edge`：Communityの2倍制限、クライアントへedgeチャネルを推奨

各環境の詳細については[リリースチャネル](/en/docs/release-channels)を参照してください。

## サーバーがCLIに伝えること

CLIがサーバーに接続すると、`/.well-known/server-info`をクエリして以下を検出します：

- **E2E暗号化公開鍵**：ゼロ知識Config保存のため
- **最低CLIバージョン**：古いCLIの接続をブロック
- **更新チャネル**：CLIが更新に使用するリリースチャネルを通知
- **環境**：本番かエッジデプロイメントかを示す

この自動設定により、ユーザーはサーバーURLを知るだけで済みます。その他は自動的に検出されます。

## エアギャップデプロイメントのライセンス

エアギャップおよびセルフホスト型オンプレミスサーバーは、上流マスターキーで署名された**委任証明書**を使用してライセンスをローカルで発行します。証明書はオンプレミスサーバーをそのプランの制限内に制約し、改ざん検知可能なチェーンを形成します。暗号設計（チェーン整合性、フォーク検出、監査証明）については[ライセンスチェーンと委任](/en/docs/license-chain)を参照してください。

このセクションでは、運用上のセットアップ（キー生成、証明書の取得、自動更新の設定、オフライン（エアギャップ）更新フロー）を説明します。

### 1サブスクリプション、1オンプレミスインストール

1つのサブスクリプションは**同時に最大1つのアクティブな委任証明書**を持てます。各オンプレミスインストールは、独自のローカル発行台帳に対して月次制限とマシン制限を適用します。そのため、複数のアクティブな証明書が存在すると、調整が不可能なまま有効クォータが倍増してしまいます。

別々の環境（本番、ステージング、DR、マルチリージョン）が必要な場合は、インストールごとに1つのサブスクリプションを購入してください。シングルアクティブ強制はこの契約を明文化したものです。2つ目のアクティブな証明書を作成しようとすると、`409 DELEGATION_CERT_ALREADY_ACTIVE`が返され、既存の証明書IDと更新（推奨 - チェーンを保持）または取り消して再作成（チェーンをリセット）の手順が示されます。

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

**オプションA - Customerセルフサービス（推奨）。** Orgのオーナーまたはアドミンとして上流ポータルにログインし、**/account/delegation-certs**に移動します。**Create New**をクリックし、オンプレミス公開鍵（base64 SPKI）を貼り付け、有効期間を選択（またはプランごとのデフォルトを受け入れ）して、生成された`.json`ファイルをダウンロードします。

**オプションB - Admin（クロスカスタマー）。** Rediaccサポートまたは上流システムアドミンが同じパラメーターで`POST /admin/delegation-certs`を使用できます。

**オプションC - `rdc` CLI（計画中）。** 将来のCLIコマンドがポータルのフローをラップする予定です。

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

ダウンロードした`.json`を既知のパスに保存し、オンプレミスから参照します：

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

または、一時的なコンテナ/Dockerシークレットのワークフローでは、証明書をbase64で環境変数に埋め込みます：

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

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

| コード | 原因 | 修正方法 |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | 新しい証明書の`genesisSequence`がローカルチェーンヘッドより進んでいる | 上流がフォークしたチェーンにある - 調査が必要 |
| `CHAIN_FORK_ON_UPLOAD` | 証明書の`genesisSequence`でのローカル台帳エントリがローカル台帳と一致しない | ローカルチェーンが上流から分岐している - 調査が必要 |
| `Signature verification failed` | 証明書が設定済みの`UPSTREAM_PUBLIC_KEY`で署名されていない | `UPSTREAM_PUBLIC_KEY`が上流マスター公開鍵と一致しているか確認する |

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
| `DELEGATION_CERT_PATH` | いずれか一方 | 署名済み証明書JSONのファイルシステムパス |
| `DELEGATION_CERT_BASE64` | いずれか一方 | Base64エンコードされた証明書JSON（ファイルパスの代替） |
| `UPSTREAM_PUBLIC_KEY` | `UPSTREAM_API_KEY`が設定されている場合、または`/onprem/cert-upload`が機能するために必須 | 上流マスター公開鍵のBase64 SPKI。欠如している場合は起動時にfail-fast。 |
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
