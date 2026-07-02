---
title: アーキテクチャ
description: >-
  Rediaccの仕組み: 2ツール設計、アダプタ検出、セキュリティモデル、設定構造
category: Concepts
order: 0
language: ja
sourceHash: "947fcefa63eac600"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# アーキテクチャ

要するに、ワークステーション上の rdc、サーバー上の renet、SSH経由での通信です。Rediaccのアーキテクチャ全体はこの分割を基礎としています。このページでは、2つのツールがどのように責務を分担するか、アダプタ検出がどのように状態をルーティングするか、セキュリティモデルはどのような構成か、設定がどのように構造化されているかについて説明します。

## フルスタック概要

トラフィックはインターネットからリバースプロキシを通過して分離されたDockerデーモンに流入し、それぞれが暗号化ストレージによって支援されています:

![フルスタックアーキテクチャ](/img/arch-full-stack.svg)

各リポジトリは専用のDockerデーモン、ループバックIPサブネット(/26 = 64個のIP)、LUKS暗号化BtrfsボリュームのセットアップBtrfsボリュームをそれぞれ取得します。ルートサーバーはすべてのデーモンで実行中のコンテナを検出し、ルーティング設定をTraefikに供給します。

## 2ツール設計

Rediaccは、SSH経由で連携する2つのバイナリを使用しています:

![2ツール設計](/img/arch-two-tool.svg)

- **rdc**はワークステーション(macOS、Linux、またはWindows)で実行されます。ローカル設定を読み込み、SSH経由でリモートマシンに接続し、renetコマンドを実行します。
- **renet**はリモートサーバーでroot権限で実行されます。LUKS暗号化ディスクイメージ、分離されたDockerデーモン、サービスオーケストレーション、リバースプロキシ設定を管理します。

ローカルで入力したすべてのコマンドは、リモートマシンでrenetを実行するSSH呼び出しに変換されます。サーバーに手動でSSHで接続する必要はありません。

オペレーター向けの簡潔なルール説明については、[rdc vs renet](/en/docs/rdc-vs-renet)をご覧ください。また`rdc ops`を使用してテスト用のローカルVMクラスターを実行することもできます。[実験的VM](/en/docs/experimental-vms)をご覧ください。

## 設定

すべてのCLI状態は`~/.config/rediacc/`以下のフラットなJSON設定ファイルに保存されています。

すべての状態はワークステーション上の設定ファイル(例:`~/.config/rediacc/rediacc.json`)に存在します。

- マシンへの直接SSH接続
- 外部サービスは不要
- デフォルト設定はCLI初回使用時に自動作成されます。名前付き設定は`rdc config init --name <name>`で作成されます
- オプションの暗号化設定同期により、同じファイルがチームごとにスコープされた設定ストアに保存されます

## rediaccユーザー

`rdc config machine setup`を実行すると、renetはリモートサーバー上に`rediacc`というシステムユーザーを作成します:

- **UID**: 7111
- **Shell**: `/sbin/nologin`(SSH経由のログインはできません)
- **目的**: リポジトリファイルの所有およびRediaccfile関数の実行

`rediacc`ユーザーはSSH経由で直接アクセスできません。代わりに、rdcは設定したSSHユーザー(例:`deploy`)として接続し、renetは`sudo -u rediacc /bin/sh -c '...'`経由でリポジトリ操作を実行します。これは以下を意味します:

1. SSHユーザーに`sudo`権限が必要
2. すべてのリポジトリデータはSSHユーザーではなく`rediacc`に所有される
3. Rediaccfile関数(`up()`、`down()`)は`rediacc`として実行

この分離により、どのSSHユーザーがリポジトリを管理しているかに関わらず、リポジトリデータの所有権が一貫性を保ちます。

## Docker分離

各リポジトリは分離されたDockerデーモンを取得します。リポジトリをマウントすると、renetは一意のソケットを持つ専用の`dockerd`プロセスを開始します:

![Docker分離](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

例えば、ネットワークID`2816`を持つリポジトリは以下を使用します:
```
/var/run/rediacc/docker-2816.sock
```

これは以下を意味します:
- 異なるリポジトリのコンテナは互いに見えない
- 各リポジトリは独自のイメージキャッシュ、ネットワーク、ボリュームを持つ
- ホストDockerデーモン(存在する場合)は完全に分離されている

Rediaccfile関数には、`DOCKER_HOST`が正しいソケットに自動的に設定されます。

AIエージェントが`rdc term connect -r <repo>`経由でリポジトリに入る場合、同じ分離が適用されます。セッションは非特権`rediacc`ユーザー(UID 7111)として実行され、別個のマウント名前空間内で、`DOCKER_HOST`はそのリポジトリのデーモンソケットに限定されます。フォークファースト最適化はこのランタイム分離をCoWクローンプリミティブと組み合わせます。エージェントはタスクごとのフォーク上で動作し、grand(本番環境)リポジトリ上では決して動作しません。完全なサンドボックスモデル、オーバーライド意味論、外部サービス認証情報の開発者責任境界については、[AIエージェント安全性とガードレール](/en/docs/ai-agents-safety)をご覧ください。

### デーモンパスレイアウト

Dockerデータと設定はリポジトリのマウント内に保存され、各デーモンをホストおよび他のリポジトリから完全に分離しておきます。

**リポジトリごとのレイアウト:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Dockerデータルート
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker設定
```

**スタンドアロンレイアウト**(リポジトリマウントに接続されていないデーモン):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**共有ランタイムパス**(変更なし):
```
/run/rediacc/docker-{N}.sock
```

この統合レイアウトにより、デーモンパスがホストファイルシステムと暗号化ボリュームに分割されていた場合に発生していた読み取り専用/読み書きマウント衝突が排除されます。この分割に複数回遭遇してから落ち着きました。リポジトリごともスタンドアロン両方のデーモンは同じディレクトリ構造に従うため、ツールと診断は両方のケースで同等に機能します。

## LUKS暗号化

リポジトリはサーバーのデータストア(デフォルト:`/mnt/rediacc`)に保存されたLUKS暗号化ディスクイメージです。各リポジトリ:

1. ランダムに生成された暗号化パスフレーズを持つ(「認証情報」)
2. ファイルとして保存:`{datastore}/repos/{guid}.img`
3. アクセス時に`cryptsetup`経由でマウント

認証情報は設定ファイルに保存されていますが、サーバー上には**決して**保存されていません。認証情報なしでは、リポジトリデータは読み込めません。自動起動が有効な場合、セカンダリLUKSキーファイルはサーバーに保存され、ブート時の自動マウントが可能になります。

## 設定構造

各設定は`~/.config/rediacc/`に保存されたJSONファイルです。デフォルト設定は`rediacc.json`です。名前付き設定は名前をファイル名として使用します(例:`production.json`)。フィールドは目的別にバケット化されます:`resources`はデプロイを保持し、`credentials`はシークレットを保持し、`account`はクラウドのデフォルトを保持し、`infra`はTLS/DNSを保持し、`encryption`はフィールド単位の保存時の状態を保持します。トップレベル`schemaVersion: 2`識別子は前方互換性を確保します。

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**キーバケット:**

| バケット | 内容 |
|---|---|
| `schemaVersion` | 識別子(現在`2`)。ローダーは不明なバージョンを拒否します。 |
| `id` / `version` | 不変UUID + 単調カウンター。リモート設定ストアでの楽観的ロック用。 |
| `defaults.*` | 非機密ランタイムのデフォルト(`machine`、`language`、`pruneGraceDays`、`universalUser`、`nextNetworkId`)。 |
| `credentials.ssh` | インラインSSH鍵ペア + `knownHosts`。レガシー`ssh.privateKeyPath`を置き換え(ファイルパス間接参照はなく、コンテンツはロード時に解決されインラインで保存)。 |
| `credentials.cfDnsApiToken` | Cloudflare DNS-01 ACMEトークン。 |
| `credentials.masterPasswordVerifier` | `encryption.mode === "master-password"`の場合にのみ存在。 |
| `resources.machines.*` | マシンごとのSSH接続詳細。 |
| `resources.storages.*` | rclone互換のオフサイトバックアップ認証情報。 |
| `resources.repositories.*` | リポジトリごとのGUID + LUKS認証情報 + サンドボックス分離エージェントアクセス用SSH鍵。 |
| `infra.acmeCertCache.*` | キャッシュTraefik acme.json、gzip+base64、ドメインでキー。 |
| `encryption.mode` | `"plaintext"`(デフォルト)または`"master-password"`。 |
| `encryption.encryptedFields` | 暗号化時、ポインター単位のAES-GCMボーダマップ(`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`)。セッション単位で1つのロック解除プロンプトでフィールドが読み込まれます。 |
| `remote` | 設定が暗号化設定ストアに同期されている場合にのみ存在。[暗号化設定ストア](/en/docs/config-storage)をご覧ください。 |

**CLIで安全に編集(vimではなく):**

```bash
# ポインターアドレッシング単一フィールド編集(機密パスの知識ゲート)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# 削除されたJSONプロジェクション付きフルエディター(人間用)
rdc config edit

# スクリプトとエージェント用の読み取り専用JSONCダンプ
rdc config edit --dump

# すべてのミューテーション + 拒否 + 公開を監査ログで検査
rdc config audit log --since 24h
rdc config audit verify
```

> このファイルには機密データ(SSH秘密鍵、LUKS認証情報、Cloudflareトークン)が含まれています。`0600`パーミッション(所有者読み書きのみ)で保存されます。共有したり、バージョン管理にコミットしないでください。いかなる`rdc`コマンドがこれを読み込むときも、機密フィールドは[デフォルトで削除されます](/en/docs/ai-agents-safety):平文は対話型の人間TTYで`--reveal`を使用する場合のみ出現します。

### Envelope v2とサーバー側の強制

設定が[暗号化設定ストア](/en/docs/config-storage)に同期される場合、CLIはフィールド単位のHMAC約束ですべての機密フィールドをラップし、これらの約束を平文エンベロープで保持します。サーバーは16進数ダイジェストのみを表示します。値は決して表示されません。しかしすべての書き込みで知識ゲートを強制できます:

- **前提条件チェック**: `PUT /configs/<id>`で、クライアントは変更を望むパスについて知っていることを主張するダイジェストを送信します。サーバーは保存されたエンベロープの約束と比較します。不一致 → `409 precondition_failed`で`mismatchedPaths`。ゼロ知識:サーバーは平文を見ません。
- **アンチダウングレード**: 新しいエンベロープは前のエンベロープが約束するすべての機密パスをコミットする必要があります。エージェントはパスを約束から削除して今後の前提条件をバイパスできません。
- **エンベロープバージョンピンニング**: サーバーは`envelopeVersion: 2`を欠くエンベロープを`400 unsupported_envelope_version`で拒否します。デュアルアクセプトウィンドウはありません。
- **フィールド単位の保存時暗号化**(CLI側): `encryption.mode === "master-password"`の場合、各シークレットはマスターパスワードでキー指定された個別のAES-GCMブロブになります。コマンドが実際にシークレットに接触しない限り、読み込みはプロンプトをトリガーしません(`rdc machine list`はプロンプト無しのままです)。

コミットメントキー(FCK)はCEKからクライアント側で`HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")`を使用してコンフィグ単位のソルトで導出されます。`fckSalt`を回転させるとすべての前のコミットメントが無効になり、完全な再計算を強制します:CEK回転時に有用です。
