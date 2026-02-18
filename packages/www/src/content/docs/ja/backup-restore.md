---
title: "バックアップと復元"
description: "暗号化されたリポジトリを外部ストレージにバックアップし、バックアップから復元し、自動バックアップをスケジュールします。"
category: "Guides"
order: 7
language: ja
---

# バックアップと復元

Rediaccは暗号化されたリポジトリを外部ストレージプロバイダにバックアップし、同じマシンまたは別のマシンで復元できます。バックアップは暗号化されており、復元にはリポジトリのLUKS認証情報が必要です。

## ストレージの設定

バックアップを送信する前に、ストレージプロバイダを登録します。Rediaccはrclone互換のストレージをすべてサポートしています：S3、B2、Google Driveなど。

### rcloneからのインポート

既にrcloneリモートが設定されている場合：

```bash
rdc context import-storage my-storage
```

これにより、rclone設定からストレージ構成が現在のコンテキストにインポートされます。

### ストレージの表示

```bash
rdc context storages
```

## バックアップの送信

リポジトリのバックアップを外部ストレージに送信します：

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| オプション | 説明 |
|-----------|------|
| `--to <storage>` | ターゲットストレージの場所 |
| `--to-machine <machine>` | マシン間バックアップのターゲットマシン |
| `--dest <filename>` | カスタム宛先ファイル名 |
| `--checkpoint` | 送信前にチェックポイントを作成 |
| `--force` | 既存のバックアップを上書き |
| `--tag <tag>` | バックアップにタグを付ける |
| `-w, --watch` | 操作の進捗を監視 |
| `--debug` | 詳細出力を有効化 |

## バックアップの取得 / 復元

外部ストレージからリポジトリのバックアップを取得します：

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| オプション | 説明 |
|-----------|------|
| `--from <storage>` | ソースストレージの場所 |
| `--from-machine <machine>` | マシン間復元のソースマシン |
| `--force` | 既存のローカルバックアップを上書き |
| `-w, --watch` | 操作の進捗を監視 |
| `--debug` | 詳細出力を有効化 |

## バックアップの一覧表示

ストレージの場所にある利用可能なバックアップを表示します：

```bash
rdc backup list --from my-storage -m server-1
```

## 一括同期

すべてのリポジトリを一度に送信または取得します：

### すべてをストレージに送信

```bash
rdc backup sync --to my-storage -m server-1
```

### すべてをストレージから取得

```bash
rdc backup sync --from my-storage -m server-1
```

| オプション | 説明 |
|-----------|------|
| `--to <storage>` | ターゲットストレージ（送信方向） |
| `--from <storage>` | ソースストレージ（取得方向） |
| `--repo <name>` | 特定のリポジトリを同期（繰り返し指定可能） |
| `--override` | 既存のバックアップを上書き |
| `--debug` | 詳細出力を有効化 |

## スケジュールバックアップ

リモートマシン上でsystemdタイマーとして実行されるcronスケジュールでバックアップを自動化します。

### スケジュールの設定

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| オプション | 説明 |
|-----------|------|
| `--destination <storage>` | デフォルトのバックアップ先 |
| `--cron <expression>` | cron式（例：`"0 2 * * *"` で毎日午前2時） |
| `--enable` | スケジュールを有効化 |
| `--disable` | スケジュールを無効化 |

### スケジュールをマシンに送信

スケジュール構成をsystemdタイマーとしてマシンにデプロイします：

```bash
rdc backup schedule push server-1
```

### スケジュールの表示

```bash
rdc backup schedule show
```

## ストレージの参照

ストレージの場所の内容を参照します：

```bash
rdc storage browse my-storage -m server-1
```

## ベストプラクティス

- **毎日のバックアップをスケジュール**し、少なくとも1つのストレージプロバイダに保存する
- **復元テスト**を定期的に行い、バックアップの整合性を検証する
- **複数のストレージプロバイダを使用**し、重要なデータを保護する（例：S3 + B2）
- **認証情報を安全に保管** -- バックアップは暗号化されていますが、復元にはLUKS認証情報が必要です
