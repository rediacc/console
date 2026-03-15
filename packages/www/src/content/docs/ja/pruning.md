---
title: "プルーニング"
description: "孤立したバックアップ、古いスナップショット、未使用のリポジトリイメージを削除してディスク容量を回復します。"
category: "Guides"
order: 12
language: ja
sourceHash: "39df2a50797597f6"
---

# プルーニング

プルーニングは、どの設定ファイルからも参照されなくなったリソースを削除します。異なるリソースタイプを対象とする2つのプルーニングコマンドがあります：

- **`rdc storage prune`** -- クラウド/外部ストレージから孤立したバックアップファイルを削除します
- **`rdc machine prune`** -- マシン上のデータストアアーティファクトと（オプションで）孤立したリポジトリイメージをクリーンアップします

## Storage Prune

ストレージプロバイダーをスキャンし、GUIDがどの設定ファイルにも存在しなくなったバックアップを削除します。

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### チェック内容

1. 指定されたストレージ内のすべてのバックアップGUIDをリストアップします。
2. ディスク上のすべての設定ファイル（`~/.config/rediacc/*.json`）をスキャンします。
3. バックアップは、そのGUIDがどの設定のリポジトリセクションからも参照されていない場合、**孤立**しています。
4. 猶予期間内に最近アーカイブされたリポジトリは、アクティブな設定から削除されていても**保護**されます。

## Machine Prune

マシン上のリソースを2つのフェーズでクリーンアップします。

### フェーズ1：データストアのクリーンアップ（常に実行）

空のマウントディレクトリ、古いロックファイル、古いBTRFSスナップショットを削除します。

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### フェーズ2：孤立したリポジトリイメージ（オプトイン）

`--orphaned-repos` を指定すると、CLIはマシン上のどの設定ファイルにも存在しないLUKSリポジトリイメージも特定し、削除します。

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
```

## セーフティモデル

プルーニングは、複数設定のセットアップ全体でデフォルトで安全であるように設計されています。

### マルチコンフィグ対応

両方のプルーニングコマンドは、アクティブな設定だけでなく、`~/.config/rediacc/` 内の**すべての**設定ファイルをスキャンします。`production.json` で参照されているリポジトリは、`staging.json` に存在しなくても削除されません。これにより、設定が異なる環境に割り当てられている場合の誤削除を防ぎます。

### 猶予期間

リポジトリが設定から削除されると、タイムスタンプ付きでアーカイブされることがあります。プルーニングコマンドは猶予期間（デフォルト7日間）を尊重し、その間、最近アーカイブされたリポジトリは削除から保護されます。これにより、誤って削除されたリポジトリを復元する時間が確保されます。

### デフォルトでDry-Run

`storage prune` と `machine prune` はデフォルトでdry-runモードで動作します。変更を加えずに何が削除されるかを表示します。実際の削除を実行するには `--no-dry-run` または `--force` を渡してください。

## 設定

### `pruneGraceDays`

毎回 `--grace-days` を渡す必要がないように、設定ファイルにカスタムのデフォルト猶予期間を設定します：

```bash
# Set grace period to 14 days in the active config
rdc config set pruneGraceDays 14
```

CLIフラグ `--grace-days` が指定された場合、この値をオーバーライドします。

### 優先順位

1. `--grace-days <N>` フラグ（最高優先度）
2. 設定ファイル内の `pruneGraceDays`
3. 組み込みのデフォルト値：7日間

## ベストプラクティス

- **まずdry-runを実行してください。** 特に本番ストレージでは、破壊的なプルーニングを実行する前に必ずプレビューしてください。
- **複数の設定を最新に保ってください。** プルーニングは設定ディレクトリ内のすべての設定をチェックします。設定ファイルが古くなったり削除されたりすると、そのリポジトリは保護を失います。設定ファイルを正確に保ってください。
- **本番環境には余裕のある猶予期間を使用してください。** デフォルトの7日間の猶予期間はほとんどのワークフローに適しています。メンテナンスウィンドウが少ない本番環境では、14日または30日を検討してください。
- **バックアップ実行後にstorage pruneをスケジュールしてください。** `storage prune` をバックアップスケジュールと組み合わせて、手動介入なしでストレージコストを管理してください。
- **machine pruneをdeploy-backupと組み合わせてください。** バックアップスケジュールのデプロイ（`rdc machine deploy-backup`）後に、定期的なマシンプルーニングを追加して、古いスナップショットと孤立したデータストアアーティファクトをクリーンアップしてください。
- **`--force` を使用する前に確認してください。** `--force` フラグは猶予期間をバイパスします。該当するリポジトリを他の設定が参照していないことが確実な場合にのみ使用してください。
