---
title: リポジトリ
description: リモートマシン上のLUKS暗号化リポジトリの作成、管理、操作。
category: Guides
order: 4
language: ja
sourceHash: "65fd6e7f9e6a83c1"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# リポジトリ

**リポジトリ**とは、リモートサーバー上のLUKS暗号化ディスクイメージです。マウントすると以下が提供されます。
- アプリケーションデータ用の隔離されたファイルシステム
- 専用のDockerデーモン（ホストのDockerとは別個）
- /26サブネット内の各サービスに対するユニークなループバックIP

## リポジトリの作成

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| オプション | 必須 | 説明 |
|--------|----------|-------------|
| `-m, --machine <name>` | はい | リポジトリを作成するターゲットマシン |
| `--size <size>` | はい | 暗号化ディスクイメージのサイズ（例: `5G`, `10G`, `50G`） |
| `--skip-router-restart` | いいえ | 操作後にルートサーバーの再起動をスキップする |

出力には自動生成された3つの値が表示されます。

- **リポジトリGUID** -- サーバー上の暗号化ディスクイメージを識別するUUID。
- **クレデンシャル** -- LUKSボリュームの暗号化と復号に使用するランダムなパスフレーズ。
- **ネットワークID** -- このリポジトリのサービスに対するIPサブネットを決定する整数（2816から始まり64ずつ増加）。

> **クレデンシャルは安全な場所に保管してください。** これはリポジトリの暗号化キーです。紛失した場合、データは復元できません。クレデンシャルはローカルの `config.json` に保存されますが、サーバーには保存されません。

## マウントとアンマウント

マウントはリポジトリのファイルシステムを復号してアクセス可能にします。アンマウントは暗号化ボリュームを閉じます。

```bash
rdc repo mount --name my-app -m server-1  # 復号してマウント
rdc repo unmount --name my-app -m server-1  # アンマウントして再暗号化
```

| オプション | 説明 |
|--------|-------------|
| `--checkpoint` | マウント/アンマウント前にCRIUチェックポイントを作成する（`rediacc.checkpoint=true` ラベルを持つコンテナ用） |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップする |

## ステータスの確認

```bash
rdc repo status --name my-app -m server-1
```

## リポジトリ一覧

```bash
rdc repo list -m server-1
```

### Typeカラムとステートミラー

出力テーブルには3つの値を持つ `Type` カラムが含まれます。

- **`grand`**: ローカルCLI設定に親なしで登録されたトップレベルリポジトリ。基本ケース。
- **`fork`**: 別リポジトリのコピーオンライトフォーク。ローカル設定の `grandGuid` またはマシン上のrenet `.interim/state` ミラーのいずれかで識別されます。どちらのソースも信頼できますが、ミラーが生成されれば両者は一致するはずです。
- **`unknown`**: どちらのシグナルでもリポジトリを分類できない状態。多くの場合、ミラーコードがリリースされる前に作成され、その後一度もマウントされていないレガシーフォーク、またはローカル設定エントリが誤って削除されたままの `grand` です。CLIは推測を拒否します。オペレーターは[ミラーのバックフィル](/en/docs/pruning#migration-state-mirror-backfill)を実行するか、本当に孤立している場合はディレクトリを削除してください。

`.interim/state/<guid>/.rediacc.json` ミラーは、LUKS暗号化ボリューム**外部**に書き込まれる小さなサイドカーファイルです。これにより、バックアップツールや `repo list` は各イメージをアンロックせずにフォークの系統を読み取ることができます。このファイルはインボリュームの `.rediacc.json`（`is_fork`, `grand_guid`, `name` など）と同じ構造を持ち、`Repository.SaveState` のたびに更新されます。つまり、マウントのたびとステート変更のたびに更新されます。これはスケジュールされたバックアップにおけるフォーク検出の信頼できるソースです。ミラーが `is_fork: true` を示すアンマウントされたフォークは、`cold` および `hot` アップロードから正しくスキップされます。

不明なエントリの定期的なクリーンアップについては、[`rdc machine prune --prune-unknown`](/en/docs/pruning#phase-3---prune-unknown-surgical) を参照してください。

## サイズ変更

リポジトリを正確なサイズに設定するか、指定した量だけ拡張します。

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # 正確なサイズに設定
rdc repo expand --name my-app -m server-1 --size 5G  # 現在のサイズに5G追加
```

> サイズ変更の前にリポジトリをアンマウントする必要があります。`repo expand` はオンラインで動作します。サイズ変更はリポジトリの最大サイズを変更します。最大サイズを変えずに解放済みブロックをプールに返すには、代わりに [`repo trim`](#領域の回収-trim) を使用してください。

## 領域の回収 (trim)

リポジトリ内のファイルを削除するとそのリポジトリの空き容量が増えますが、`repo trim` はその解放されたブロックを共有データストアプールに返却します。ゼロダウンタイムでオンライン実行できます。

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

仕組み: リポジトリイメージはスパースファイルであり、暗号化ボリュームはディスカードを透過的に通過させます。trim はリポジトリ内部のファイルシステムに未使用ブロックをすべて解放するよう指示し、これにより裏付けイメージにホールが穿たれてプール使用量が即座に削減されます。

注意事項:

- アクティブなバックアップ中のリポジトリはスキップされて報告されます。バックアップ中のトリムは空き容量を解放しません。バックアップスナップショットがまだそのブロックを参照しているためです。
- trim を連続して2回実行すると、2回目は0バイトと報告されます。ファイルシステムはすでにトリム済みのブロックグループを記憶しており、これは想定された動作であり失敗ではありません。
- `--docker` はタグ付きイメージを削除せず、ダングリングイメージ、停止済みコンテナ、ビルドキャッシュのみを対象とします。未使用ボリュームも削除するには `--docker-volumes` を追加してください（データが削除されます。CLIのみ）。

## 自動サイズポリシー

手動でサイズ変更する代わりに、マシンがリポジトリのサイズを管理できます。ポリシーはオンラインでの自動拡張（リポジトリが満杯になると最大サイズが増加）とスケジュールされたトリムを有効にします。マシンは `rediacc-storage-maintain` systemd タイマーを通じて数分ごとにポリシーを適用します。

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

ポリシーフィールド:

| フィールド | 意味 | デフォルト |
|---|---|---|
| `--auto-grow` | ファイルシステムがしきい値を超えたときにリポジトリをオンラインで拡張する | オフ |
| `--max-quota` | 自動拡張のハード上限。必須: 設定することはプールをオーバープロビジョニングする明示的な同意を意味する | なし |
| `--grow-threshold` | 拡張をトリガーするファイルシステム使用率 % | 85 |
| `--grow-step` | 1回の拡張で追加する容量: 絶対値（`10G`）または現在サイズのパーセント（`20%`） | 20% |
| `--auto-trim` | スケジュールされたトリムを実行する | オフ |
| `--trim-interval` | 自動トリム間の最小時間（時間） | 24 |

ガードレール: プールの空き容量が予約容量（10 GB またはプールの5%のいずれか大きい方）を下回る場合、自動拡張は拒否されます。同じリポジトリの拡張間は少なくとも30分待機し、`--max-quota` を超えることはありません。自動縮小はありません。リポジトリの最大サイズの削減は手動かつオフラインの [`repo resize`](#サイズ変更) のままです。

リポジトリごとの設定はマシン全体のデフォルトを上書きします。`policy set` の繰り返し呼び出しでは、渡したフラグのみが変更されます。

## フォーク

既存のリポジトリを現在の状態でコピーします。

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

フォークはname:tagモデルを使用します。作成されたフォークは `my-app:staging` という名前になります。これにより、親の名前を共有しながら、独自のGUIDとネットワークIDを持つ新しい暗号化コピーが作成されます。フォークは親と同じLUKSクレデンシャルを共有します。

> フォークはBTRFS reflinkを通じて親のデータを共有します。ディスク上に保存されたクレデンシャルも含まれます。それらのクレデンシャルがStripe、AWS、Railwayなどの外部サービスを認証する場合の影響については、[Rediaccが隔離しないもの](/en/docs/ai-agents-safety#what-rediacc-does-not-isolate)を参照してください。デプロイ時のクレデンシャルをフォークからアクセスできないようにするには、リポジトリ内の `.env` ファイルに値を埋め込む代わりに[リポジトリシークレット](#secrets)を使用してください。

フォーク作成時に、`repo fork` はボリュームをアンロックせずに即座に `<datastore>/.interim/state/<fork-guid>/.rediacc.json` に[ステートミラーサイドカー](#typeカラムとステートミラー)を書き込みます。これにより、新しいフォークは作成された瞬間から `is_fork: true` として正しく識別されます。一度もマウントされていなくても、スケジュールされたバックアップはフォークをスキップできます（フォークはデフォルトでアップロードパイプラインから除外されます）。フォークのフォークを作成する場合、`grand_guid` は正しくチェーンされます。新しいフォークのミラーは、中間フォークのGUIDではなく、元のグランド親のGUIDを指します。

### 1ステップでフォークして起動

`--up` はフォーク、マウント、サービス起動をリモートで一括実行します。`--detach` を追加すると、コンテナが起動した時点でターミナルに制御が戻ります。ヘルスチェックはバックグラウンドで完了し、プロキシは各サービスがバインドするまで再試行を続けます。

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

実測値として、128 GB のリポジトリをフォークしてサービスが稼働状態に達するまで約 57 秒、`--detach` では約 31 秒でした。デタッチ実行は進捗確認のヒントを出力します：`rdc machine query --containers --name <machine>`。

### 時間の内訳

数秒を超える実行が完了すると、タイミングサマリーが表示されます。ステップごとの所要時間、並列実行の様子を示すウォーターフォール、そして Rediacc パイプライン部分とサービス自体の起動時間を分けた帰属行です。

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

サービス起動はコンテナのブート、イメージ取得、init、ヘルスチェックを含み、Rediaccfile の定義に従ってアプリごとに変わります。チャートはインタラクティブなターミナルで描画されます。パイプ出力でも強制表示するには `RDC_TIMING_CHART=1` を設定してください。

## Gitのようなバージョニング

フォークはgitのコミットのように機能できます。`rdc repo commit` は作業中のフォークを不変のバイト安定コミットにフリーズし、`rdc repo branch` は履歴の系列に名前を付け、`rdc repo checkout` はコミットを書き込み可能なフォークにリフリンク複製し、`rdc repo log` は親チェーンをたどり、`rdc repo merge` はライブリポジトリをその場で変更することなく2つの系列を結合します。`rdc repo fork --immutable` は1ステップでコミット相当のベースを作成します。

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

完全なコマンドセット、オプション、および実践例については [Gitのようなブランチングリファレンス](/en/docs/repo-branching) を参照してください。

## シークレット

リポジトリシークレットは、暗号化リポジトリイメージに書き込まれることなくコンテナに注入されるデプロイ時のクレデンシャルです。リポジトリのデータとは別の層に保持されるため、`rdc repo fork` では伝播されません。フォークは空のシークレットマップから始まり、そのコンテナは親とは異なる外部プリンシパルとして起動します。

> ステップバイステップのガイドをご希望の場合は、set/list/deploy/verify/rotateの全サイクルについて[シークレット管理チュートリアル](/en/docs/tutorial-managing-secrets)を参照してください。

**書き込み専用モデル（GitHubスタイル）:** `get` はSHA-256ダイジェストのみを返します。平文の値は人間にもエージェントにも返されません。値を忘れた場合は、パスワードマネージャーで確認してローテーションしてください。設計上、Rediaccから値を読み戻すことはできません。これにより、ターミナル記録、シェル履歴、誤ったリダイレクト、ショルダーサーフィンなど、漏洩の一類型全体が排除されます。

2つの配信モード:

- `env`: シークレットはターゲットマシンのrenetシェルで `REDIACC_SECRET_<KEY>` としてエクスポートされます。`docker-compose.yml` から `${REDIACC_SECRET_<KEY>}` 補間で参照します。コンテナの環境内で可視なので、アプリケーションがすでにenvで期待している接続文字列形式の値に使用してください。
- `file`: シークレットはホスト上の `/var/run/rediacc/secrets/<networkID>/<KEY>` に書き込まれます（tmpfs、永続化されません）。composeファイルからは、`file:` ソースを持つトップレベルの `secrets:` 宣言とサービスごとの `secrets:` リストで参照します。コンテナは `/run/secrets/<key>` から読み取ります。機密性の高いものにはこのモードを使用してください。`docker inspect` や `/proc/<pid>/environ` には表示されません。

```bash
# Set, list, get（ダイジェストのみ）, unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — 値なし
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**対称変更ゲート。** 人間もエージェントも、シークレットを上書きまたは削除するには `--current <前回の値>` が必要です（passwd形式の前提条件）。新しいキーの初回書き込みには `--current ""`（空）を渡します。前回の値を検証せずにローテーションするには `--rotate-secret` を使用します。これはローテーションとして大々的に監査されます。`--current` と `--rotate-secret` は相互排他的です。

シェル履歴への露出を避けるため、argvの代わりにstdinから読み取るには `--value -` を渡します。

`docker-compose.yml` での使用例:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

サービス側の小文字の参照（`stripe_live_key`）はコンテナ内の `/run/secrets/<name>` ファイル名です。ホストパスの大文字の末尾部分（`STRIPE_LIVE_KEY`）は `--key` で設定した値と一致します。`${REDIACC_NETWORK_ID}` は `renet compose` によって自動的に補間されます。

> **クロスリポジトリ隔離の強制**: renetのcomposeバリデーターは、他のリポジトリのネットワークIDを参照する `secrets: file:`（および `configs: file:`、`env_file:`）パスを拒否します。`/var/run/rediacc/secrets/...` 参照として受け入れられる形式はリテラルの `${REDIACC_NETWORK_ID}` トークン（または自分のネットワークの整数）のみです。`--unsafe` はこのチェックを上書きしません。RediaccfileのBashサブプロセスを囲むLandlockサンドボックスも、自分のネットワークのシークレットディレクトリのみにファイルシステムアクセスをスコープするため、Rediaccfileからの悪意ある `cat /var/run/rediacc/secrets/<other>/X` はカーネル層でEACCESで失敗します。

> **フォーク**: `rdc repo fork` はシークレットをコピー**しません**。フォークでシークレットを使用するには、フォークに対して `rdc repo secret set --name <fork>` を明示的に実行します。これは重要な安全特性です。フォークのコンテナは、外部サービスに対して本番プリンシパルとして動作できるべきではありません。

> **エージェント**（Claude Code、Cursorなど）: `repo secret list` と `repo secret get` はMCPツールとして公開されています（読み取り安全。名前とダイジェストのみ、値は含まれません）。`set` と `unset` はCLI専用です。`--current`/`--rotate-secret` の確認手順は人間の目視が必要なためです。シェル経由でこれらを呼び出すエージェントも人間と同じゲートを受けます。前提条件が失敗した場合、JSONエンベロープには構造化された `errors[].next.options[].run` フィールドが含まれます。エージェントはそれらのコマンドをそのままユーザーに伝えてください。完全なモデルについては[AIエージェントの安全性](/en/docs/ai-agents-safety)を参照してください。

## 検証

リポジトリのファイルシステムの整合性を確認します。

```bash
rdc repo validate --name my-app -m server-1
```

## 所有権

リポジトリ内のファイル所有権をユニバーサルユーザー（UID 7111）に設定します。これは通常、ワークステーションからファイルをアップロードした後に必要です。アップロードされたファイルはローカルのUIDで到着するためです。

```bash
rdc repo ownership --name my-app -m server-1
```

このコマンドはDockerコンテナのデータディレクトリ（書き込み可能なバインドマウント）を自動的に検出し、除外します。これにより、独自のUIDでファイルを管理するコンテナ（例: MariaDB=999、www-data=33）が壊れることを防ぎます。

| オプション | 説明 |
|--------|-------------|
| `--uid <uid>` | 7111の代わりにカスタムUIDを設定する |
| `--skip-router-restart` | 操作後にルートサーバーの再起動をスキップする |

コンテナデータを含む全ファイルに所有権を強制するには:

```bash
rdc repo ownership --name my-app -m server-1
```


プロジェクト移行時に所有権をいつどのように使用するかの完全なガイドは、[移行ガイド](/en/docs/migration)を参照してください。

## テンプレート

テンプレートを適用してリポジトリをファイルで初期化します。

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## 削除

リポジトリとその中のすべてのデータを永久に破棄します。

```bash
rdc repo delete --name my-app -m server-1
```

> これにより暗号化ディスクイメージが永久に破棄されます。この操作は元に戻せません。

## リポジトリの移行

あるマシンから別のマシンにリポジトリをライブ移行します。唯一のダウンタイムは最終デルタシンク段階であり、カットオーバー時の書き込みレートに応じて通常は数秒から数分です。

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| オプション | 説明 |
|--------|-------------|
| `--provision` | 移行前にターゲットマシンにリポジトリをプロビジョニングする（LUKSイメージを作成し設定を登録する） |
| `--checkpoint` | カットオーバー前に実行中コンテナのCRIUチェックポイントを作成する |
| `--bwlimit <kbps>` | rsyncの帯域幅をキロバイト毎秒で制限する |
| `--skip-dns` | カットオーバー後にDNSレコードの更新をスキップする |

**3フェーズのフロー:**

1. **ホットプリコピー** - リポジトリがソースで稼働したままrsyncがデータを転送します。ダウンタイム前に大きなファイルを転送します。
2. **カットオーバー** - リポジトリがソースで停止し、最終rsyncパスで残りの変更を同期してから、リポジトリがターゲットで起動します。
3. **ターゲットでの起動** - renetがターゲットマシンでリポジトリをマウントして起動します。`--skip-dns` が指定されない限りDNSが更新されます。

![リポジトリライブ移行](/img/repo-migrate-flow.svg)

**pushと移行の比較:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| 操作 | コピー | 移動 |
| 操作後のソース | 変更なし | 停止 |
| ダウンタイム | なし（コピーのみ） | 短いカットオーバーウィンドウ |
| DNS更新 | なし | あり（`--skip-dns` を指定しない場合） |
| ユースケース | バックアップ、ステージングクローン | マシン交換、サーバー移動 |

## プルーニング

リポジトリを削除したり、失敗した操作から復旧したりした後、孤立したマウントディレクトリ、ロックファイル、移動不能なマーカーが残ることがあります。プルーニングはこれらを安全に削除します。

```bash
# 削除されるものをプレビュー
rdc machine prune --name server-1 --dry-run

# 孤立したリソースを削除
rdc machine prune --name server-1
```

対応するリポジトリイメージが存在しないリソースのみが対象となります。空でないマウントディレクトリは削除されません。
