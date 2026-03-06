---
title: "バックアップとネットワーク"
description: "自動バックアップスケジュールの設定、ストレージプロバイダーの管理、インフラストラクチャネットワークの構築、サービスポートの登録を行います。"
category: "Tutorials"
order: 6
language: ja
sourceHash: "e756fef6749b54c5"
---

# Rediaccでバックアップとネットワークを設定する方法

自動バックアップはリポジトリを保護し、インフラストラクチャネットワークはサービスを外部に公開します。このチュートリアルでは、ストレージプロバイダーを使ったバックアップスケジュールの設定、TLS証明書を使った公開ネットワークの構築、サービスポートの登録、設定の検証を行います。完了すると、マシンは本番トラフィックの受け入れ準備が整います。

## 前提条件

- 設定が初期化された`rdc` CLIがインストール済みであること
- プロビジョニング済みのマシン（[チュートリアル: マシンセットアップ](/ja/docs/tutorial-setup)を参照）

## インタラクティブ録画

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### ステップ1: 現在のストレージを表示

ストレージプロバイダー（S3、B2、Google Driveなど）はバックアップ先として機能します。設定済みのプロバイダーを確認します。

```bash
rdc config storages
```

rclone設定からインポートされた全ての設定済みストレージプロバイダーを一覧表示します。空の場合は、まずストレージプロバイダーを追加してください — [バックアップとリストア](/ja/docs/backup-restore)を参照。

### ステップ2: バックアップスケジュールを設定

cronスケジュールで実行される自動バックアップを設定します。

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

毎日午前2時にすべてのリポジトリを`my-s3`ストレージにプッシュする日次バックアップをスケジュールします。スケジュールは設定に保存され、systemdタイマーとしてマシンにデプロイできます。

### ステップ3: バックアップスケジュールを表示

スケジュールが適用されたことを確認します。

```bash
rdc backup schedule show
```

現在のバックアップ設定を表示します：宛先、cron式、有効化ステータス。

### ステップ4: インフラストラクチャを設定

公開サービスの場合、マシンには外部IP、ベースドメイン、Let's Encrypt TLS用の証明書メールアドレスが必要です。

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediaccはこれらの設定からTraefikリバースプロキシ設定を生成します。

### ステップ5: TCP/UDPポートを追加

サービスが非HTTPポート（例：SMTP、DNS）を必要とする場合、Traefikエントリポイントとして登録します。

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

Traefikエントリポイント（`tcp-25`、`udp-53`など）を作成し、Dockerサービスがラベルでリファレンスできるようにします。

### ステップ6: インフラストラクチャ設定を表示

インフラストラクチャ設定の全体を確認します。

```bash
rdc config show-infra server-1
```

パブリックIP、ドメイン、証明書メールアドレス、登録済みの全ポートを表示します。

### ステップ7: バックアップスケジュールを無効化

設定を削除せずに自動バックアップを停止するには：

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

設定は保持され、後で`--enable`で再度有効化できます。

## トラブルシューティング

**"Invalid cron expression"**
cronのフォーマットは`minute hour day month weekday`です。一般的なスケジュール：`0 2 * * *`（毎日午前2時）、`0 */6 * * *`（6時間ごと）、`0 0 * * 0`（毎週日曜深夜）。

**"Storage destination not found"**
宛先名は設定済みのストレージプロバイダーと一致する必要があります。`rdc config storages`を実行して利用可能な名前を確認してください。新しいプロバイダーはrclone設定で追加します。

**デプロイ時の"Infrastructure config incomplete"**
3つのフィールドすべてが必須です：`--public-ipv4`、`--base-domain`、`--cert-email`。`rdc config show-infra <machine>`を実行して不足しているフィールドを確認してください。

## 次のステップ

自動バックアップの設定、インフラストラクチャネットワークの構築、サービスポートの登録、設定の検証が完了しました。バックアップを管理するには：

- [バックアップとリストア](/ja/docs/backup-restore) — push、pull、list、syncコマンドの完全なリファレンス
- [ネットワーク](/ja/docs/networking) — Dockerラベル、TLS証明書、DNS、TCP/UDP転送
- [チュートリアル: マシンセットアップ](/ja/docs/tutorial-setup) — 初期設定とプロビジョニング
