---
title: "プルーニング"
description: "孤立したバックアップ、古いスナップショット、リポジトリイメージ、ローカル設定の残存物を削除して、ディスク容量を回復し、状態の整合性を保ちます。"
category: "Guides"
order: 12
language: ja
sourceHash: "d2700c2ac4473962"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# プルーニング

プルーニングは、ライブリソースに対応しなくなった状態を一掃します。3 つのコマンドが 3 つの異なるスコープをカバーします。

| コマンド | クリーンアップ対象 | 信頼できる情報源の場所 |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | クラウドストレージ内の孤立したバックアップ | ローカル CLI 設定（マウント安全性のためにエグゼキュータマシンでクロスチェック） |
| `rdc machine prune --name <machine>` | マシン上のデータストアアーティファクト（常に）；孤立または unknown のリポジトリイメージ（オプトイン） | ローカル CLI 設定 + マシンの `.interim/state` ミラー |
| `rdc config prune` | ローカル設定の残存物（証明書キャッシュ、期限切れアーカイブ、宙吊りの相互参照） | ローカル CLI 設定のみ |

3 つは独立しています。任意の 1 つを他のものなしで実行できます。共通の安全モデルは下記の [安全モデル](#safety-model) で説明されています。

プルーニングは削除済みリソースが残した状態を取り除きます。*ライブ*リポジトリが占有している容量（ファイルシステムが解放したがプールがまだ保持しているブロック）を回収するには、代わりに [`rdc repo trim`](/ja/docs/repositories#領域の回収-trim) を使用してください。2 つは補完的な関係にあります。

## マウント安全プリフライト

`storage prune` と `machine prune --prune-unknown` はどちらも、何かを削除する前に **マウント安全プリフライト** を実行します。エグゼキュータマシンに対して現在マウントまたは実行中のリポジトリを問い合わせ、削除候補と交差させ、**マシン上でまだライブな候補の削除を拒否します**。マウントされたリポジトリのオフマシンバックアップを削除したり、ライブのリポジトリイメージを削除したりすることは、現実のデータ損失の落とし穴です。プリフライトはこれを誤って実行することを不可能にします。

オーバーライドするには（まれ。ライブ状態が間違っていることが本当に分かっている場合のみ）、`--force-delete-mounted` を渡します。これは（アーカイブの猶予期間を制御する）`--force` とは別のフラグであり、2 つのエスケープハッチを区別しています。

## Storage Prune

ストレージプロバイダーをスキャンし、GUID がローカル設定ファイルのいずれにも出現しなくなったバックアップを削除します。

```bash
# プレビューのみ — 削除されるものを表示
rdc storage prune --name my-s3 -m server-1 --dry-run

# 実際に孤立したバックアップを削除（デフォルト動作）
rdc storage prune --name my-s3 -m server-1

# 猶予期間をオーバーライド（デフォルト 7 日）
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# マウント安全チェックをオーバーライド（注意して使用）
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` は必須です。rclone 呼び出しはあなたのラップトップではなくエグゼキュータマシン上で実行されるためです。クライアントがローカルに rclone をインストールしていることは想定されていません。ストレージ認証情報は依然としてローカル設定から取得され、マシンは単に rclone のランナーです。

### チェック内容

1. 名前付きストレージ内のすべてのバックアップ GUID をリストします（`hot/` と `cold/` の両サブディレクトリに横断的に。[バックアップとリストア](/ja/docs/backup-restore#scheduled-backups) を参照）。
2. ディスク上のすべての設定ファイル（`~/.config/rediacc/*.json`）をスキャンします。
3. バックアップは、その GUID がどの設定の `repositories` セクションからも参照されていない場合 **孤立** しています。
4. 猶予期間内に最近アーカイブされたリポジトリは、アクティブな設定から削除されていても **保護** されます。
5. マウント安全プリフライト：`--machine` で現在マウントされている GUID はスキップされて報告され、決して削除されません。

### パフォーマンス

削除はストレージのサブパスごとにバッチ化されます。削除される GUID の数に関わらず、`hot/` または `cold/` ディレクトリごとに 1 回の rclone 呼び出しが行われます。11 件の孤立バックログでも、SSH オーバーヘッド約 50 秒からサブパスごとの単一ラウンドトリップに圧縮されます。

## Machine Prune

マシン上のリソースを 3 つのフェーズでクリーンアップします。フェーズ 1 は常に実行されます。フェーズ 2 と 3 はオプトインで、組み合わせることができます。

### フェーズ 1：データストアのクリーンアップ（常に実行）

リポジトリが削除されたときや、マシンレベルのリファクタリングで命名規則が廃止されたときに残りうる、あらゆる種類のリソースを削除します。各カテゴリは独立してスキャンされ、クリーンアップは 1 回の冪等なパスで行われるため、prune を繰り返し実行しても安全で、クリーンなデータストアへ収束します。

| カテゴリ | 削除対象 |
|---------|-----------------|
| 空のマウントディレクトリ | 裏付けとなるリポジトリイメージがない `mounts/<guid>/` ディレクトリ |
| 孤立した immovable ディレクトリ | 裏付けとなるリポジトリイメージがない `immovable/<guid>/` ディレクトリ |
| 古いロックファイル | 削除済みリポジトリの `repositories/.lock-<guid>` |
| 古いバックアップスナップショット | 強制終了されたバックアップ実行によって残された `.snapshot-*` と `.backup-*` |
| 孤立した VS Code サンドボックスディレクトリ | マシン上でもはやアクティブではないリポジトリの `.interim/sandbox/<name>` |
| 孤立した iptables チェーン | 削除済みネットワークの `REDIACC_WILDCARD_<N>` および `DOCKER_ISOLATED_NET_<N>` チェーン |
| 孤立した authorized_keys エントリ | `--guid` がもはやアクティブなマウントディレクトリに一致しない `sandbox-gateway <repo> --guid <uuid>` 行 |

authorized_keys のスキャンは `/home/*/.ssh/authorized_keys` と `/root/.ssh/authorized_keys` を対象とします。エントリは、その `--guid` タグがライブのマウントディレクトリ GUID に一致する場合にのみ保持されます。したがって、マシン上に現在デプロイされているリポジトリは、その名前がディスク上のどこに現れていようとも常に保持されます。renet が `--guid` タグを付加し始める前に書かれた古いエントリは検証できないため、常に孤立として報告されます。

```bash
# Dry-run、削除されるものを表示（変更は適用されない）
rdc machine prune --name server-1 --dry-run

# クリーンアップを実行
rdc machine prune --name server-1
```

> **連鎖的なクリーンアップ。** 一部のカテゴリは、より前のカテゴリに依存しています。例えば、空のマウントディレクトリを削除すると、その裏付けとなるマウントがなくなったために新たに孤立したサンドボックスが現れることがあります。`rdc machine prune` をもう一度実行すると、その連鎖を捕捉してクリーンアップを完了できます。最後の dry-run は、やるべきことが何も残っていないときに `No orphaned resources found. Datastore is clean.` で終わります。

### フェーズ 2：`--orphaned-repos`（粗い）

`--orphaned-repos` を指定すると、CLI はマシン上の **どの** ローカル設定ファイルにも出現しないリポジトリイメージも削除します。

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

これは **粗い** 動作です。ローカル設定にないものすべてを削除します。これには他のツールや別のオペレータの CLI チェックアウトが管理する正当なフォークも含まれます。renet `.interim/state` ミラーがリポジトリをフォークとして正しく識別していても、ローカル設定がそれを一度も見たことがない場合、このフェーズはやはり削除します。保守的に行いたい場合はフェーズ 3（`--prune-unknown`）を優先してください。

### フェーズ 3：`--prune-unknown`（外科的）

`--prune-unknown` を指定すると、CLI は **両方** のシグナルが分類できないリポジトリのみを削除します。すなわち、どのローカル設定にも存在せず、**かつ** マシンの `.interim/state` ミラーにフォーク印付きエントリがないものです（[リポジトリ. `Type` カラム](/ja/docs/repositories#type-column-and-the-state-mirror) を参照）。

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

実際には、定常的なクリーンアップに必要なのは `--prune-unknown` です。`--orphaned-repos` が正しいのは、ローカル設定がマシン上のすべてのリポジトリの完全かつ信頼できる目録であると確信できる場合のみです。ミラー以前のレガシー孤立物と、設定エントリが誤って削除されたリポジトリは、どちらも「unknown」バケットに該当します。これらは本当に不確実であり、外科的フラグはオペレータにそれを明示的に認識するよう求めます。

このフェーズでもマウント安全プリフライトが実行されます。`--machine` で現在マウントされているリポジトリは報告されてスキップされ、`--force-delete-mounted` が渡されない限り削除されません。

```bash
# 組み合わせ：外科的でフォーク対応のパスでのフルマシンクリーンアップ
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

`~/.config/rediacc/<config>.json` の **ローカル設定ファイル内** の古い残存物を一掃します。純粋にローカル動作で、SSH も renet 呼び出しもありません。3 つのバケットがクリーンアップされます。

1. **ACME 証明書キャッシュエントリ**：そのアンカー（GUID、リポジトリ名、またはマシン名）がアクティブな設定にもはや存在しないもの。証明書ワイルドカードはどこにもルーティングできないため、デッドウェイトです。
2. **期限切れのアーカイブ済みリポジトリ**：`resources.deletedRepositories[]` 内で、`deletedAt` が `defaults.pruneGraceDays`（デフォルト 7 日）より古いエントリ。猶予期間内のエントリは（残り日数とともに）報告され、保持されます。
3. **設定バケット間の宙吊りの相互参照**：
   - もはや存在しない戦略を名指しする `resources.machines.<m>.backupStrategies[]` エントリ。
   - もはや存在しないリポジトリを名指しする `resources.backupStrategies.<s>.exclude[]` および `include[]` エントリ。
   - ターゲットストレージが見つからないストレージ宛先. 警告としてフラグされ、自動削除されません（自動削除は戦略のセマンティクスを変えてしまうため）。

```bash
# プレビューのみ
rdc config prune --dry-run

# 適用（デフォルト動作）
rdc config prune

# 1 つのバケットに限定
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# 猶予期間に関わらずすべてのアーカイブ済みリポジトリを削除
rdc config prune --purge-archived

# この呼び出しのアーカイブ猶予ウィンドウをオーバーライド
rdc config prune --grace-days 30
```

### 触らないもの

- アクティブなリソース（マシン、ストレージ、リポジトリ、バックアップ戦略、クラウドプロバイダ）。
- 認証情報、アカウントブロック、暗号化ブロック、`defaults`。
- ストレージの `vaultContent`（期限切れの OneDrive `access_token` を含む. Refresh_token がまだ新しいものを発行できるため、プルーニングは再認証を強制してしまいます）。
- `knownHosts` エントリ（自動更新パスは `rdc config machine scan-keys`）。
- 圧縮された証明書 blob 配列（`infra.acmeCertCache.<base>.data[]`）はクリーンアップ後の証明書リストから自動的に再構築されます。保持された名前をまだカバーするチェーンを失うことはありません。

### 動作例

4 つの孤立 GUID ワイルドカードと 2 つの古いマシン名ワイルドカードを持つマシンでの実際の実行からの出力：

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

アンカーがライブのマシン、リポジトリ、または GUID である証明書名はそのまま残されます。単一ラベル `<service>.<base>` またはルート `*.<base>` ワイルドカードも同様です。

## 移行：状態ミラーバックフィル

`--prune-unknown` と `rdc repo list -m` の `Type` カラムを支える `.interim/state/<guid>/.rediacc.json` ミラーは、以下のタイミングで書き込まれます。

- **フォーク時**（`rdc repo fork`）. フォークが一度もマウントされる前であっても即座に。
- **すべての状態保存時**（`rdc repo mount` および任意のリポジトリ状態を更新する操作）. ミラーコードが導入される前に作成されたリポジトリ向け。

**ミラーが存在する前に作成され、アップグレード後一度も再マウントされていない** リポジトリにはミラーファイルがありません。それらは、いくつかが正当にフォークであっても、`rdc repo list -m` で `unknown` として表示されます。レガシー孤立物に対してこれを修正するには、マシン上でワンショットのバックフィルを実行します。

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

バックフィルは、現在マウントされているリポジトリについてはライブのボリューム内状態をミラーにコピーし、`--mark-as-fork` で列挙した GUID には合成のフォーク印付きミラーを書き込みます。バックフィル後、スケジュールされたバックアップは列挙されたフォークのアップロードを停止します（アップロードパイプラインはミラーで `is_fork: true` をチェックします）。

## 安全モデル

プルーニングは、複数設定のセットアップ全体でデフォルトで安全であるように設計されています。

### マルチコンフィグ対応

`storage prune` と `machine prune --orphaned-repos` は、アクティブな設定だけでなく、`~/.config/rediacc/` 内の **すべての** 設定ファイルをスキャンします。`production.json` で参照されているリポジトリは、`staging.json` に存在しなくても削除されません。これにより、設定が異なる環境に割り当てられている場合の誤削除を防ぎます。

### 猶予期間

リポジトリが `--archive-config` で設定から削除されると、その認証情報エントリは `deletedAt` タイムスタンプとともに `resources.deletedRepositories[]` に移動されます。プルーニングコマンドは猶予期間（デフォルト 7 日間）を尊重し、その間、最近アーカイブされたリポジトリは削除から保護されます。これにより、誤って削除された場合にリポジトリを復元する時間（`rdc config repository restore-archived --name <guid>`）が確保されます。猶予期間が切れると、`storage prune`、`machine prune`、`config prune` のすべてがエントリを自動的に削除します。

### マウント安全プリフライト

上記でカバーされています. `storage prune` と `machine prune --prune-unknown` は、エグゼキュータマシンで現在マウントされている、または実行中のリポジトリの削除を拒否します。`--force-delete-mounted` でのみオーバーライドしてください。

### デフォルトで適用；プレビューには `--dry-run`

3 つのプルーニングコマンドはすべて、デフォルトで変更を **適用** します。書き込みなしでプレビューするには `--dry-run` を渡します。これは動詞に対応しています：「prune」自体は破壊的であり、dry-run フラグは明示的なオプトアウトです。

## 設定

### `pruneGraceDays`

毎回 `--grace-days` を渡す必要がないように、設定ファイルにカスタムのデフォルト猶予期間を設定します。

```bash
# アクティブな設定で猶予期間を 14 日に設定
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

CLI フラグ `--grace-days` が指定された場合、この値をオーバーライドします。

### 優先順位

1. `--grace-days <N>` フラグ（最高優先度）
2. 設定ファイル内の `pruneGraceDays`
3. 組み込みのデフォルト値：7 日間

## ベストプラクティス

- **本番環境ではまず dry-run を実行してください。** 特に本番ストレージでは、破壊的なプルーニングを実行する前に必ずプレビューしてください。
- **複数の設定を最新に保ってください。** ストレージとマシンのプルーニングは設定ディレクトリ内のすべての設定をチェックします。設定ファイルが古くなったり削除されたりすると、そのリポジトリは保護を失います。設定ファイルを正確に保ってください。
- **`--orphaned-repos` よりも `--prune-unknown` を優先してください。** 外科的フラグは renet ミラーを尊重します。粗いフラグは他のツールが作成したフォークを平気で削除します。
- **本番環境には余裕のある猶予期間を使用してください。** デフォルトの 7 日間の猶予期間はほとんどのワークフローに適しています。メンテナンスウィンドウが少ない本番環境では、14 日または 30 日を検討してください。
- **バックアップ実行後に storage prune をスケジュールしてください。** `storage prune` をバックアップスケジュールと組み合わせて、手動介入なしでストレージコストを管理してください。
- **machine prune を backup schedule と組み合わせてください。** バックアップスケジュールのデプロイ（`rdc machine backup schedule`）後に、定期的なマシンプルーニングを追加して、古いスナップショットと孤立したデータストアアーティファクトをクリーンアップしてください。
- **`config prune` を定期的に実行してください。** ローカル設定の肥大化（特に証明書キャッシュ）は静かに蓄積されます。四半期ごとの `config prune --dry-run` で十分捕捉できます。
- **`--force` または `--force-delete-mounted` を使用する前に監査してください。** どちらのフラグも安全チェックをバイパスします。`--force` は、該当するリポジトリを他の設定が参照していないことが確実な場合にのみ使用してください。`--force-delete-mounted` は、マシン上のライブ状態が間違っていることが確実な場合にのみ使用してください。
