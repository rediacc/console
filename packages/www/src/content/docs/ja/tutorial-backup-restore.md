---
title: "バックアップとリストア"
description: "リポジトリを外部ストレージにプッシュし、必要なときに新しいサーバーで復元します。"
category: "Tutorials"
subcategory: advanced
order: 11
language: ja
sourceHash: "8b48f3b19352aebe"
---

# バックアップとリストア

アプリが本番で稼働しています。次は絶対に失わないようにしましょう。`rdc` はリポジトリ全体（アプリ、データベース、ファイル、設定）を外部ストレージにプッシュし、いつでも引き戻すことができます。ランサムウェア、ハードウェア障害、どんな事態にも対応できます。

## チュートリアル動画

![チュートリアル: バックアップとリストア](/assets/tutorials/tutorial-backup-restore.cast)

## 3つのステップ

![設定、プッシュ、リストア](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **設定**: ストレージプロバイダーを設定します。
2. **プッシュ**: バックアップを取ります。
3. **リストア**: 必要なときに復元します。

## ステップ1: ストレージを設定する

`rclone` の設定ファイルが必要です。すでに rclone を使っている場合は直接インポートできます。

```bash
time rdc config storage import --file rclone.conf
```

S3、B2、Google Drive、Dropbox など多くのサービスに対応しています。設定されているストレージを確認します。

```bash
time rdc config storage list
```

## ステップ2: バックアップをプッシュする

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

リポジトリ全体（アプリ、データベース、ファイル、すべて）がバックアップされました。リポジトリ自体が暗号化されているため、バックアップも暗号化されます。追加の鍵管理は不要です。

バックアップはいつでも確認できます。

```bash
time rdc repo backup list --from my-storage -m my-server
```

## なぜダウンタイムがないのか

バックアップのアップロード中もアプリは動き続けます。一貫性はどのように保たれるのでしょうか。

[フォーク](/en/docs/tutorial-forking) と同じ仕組みです。`rdc` はまずフォークを作成し、そのフォークをアップロードします。フォークがその瞬間をキャプチャし、本番アプリは動き続けます。ダウンタイムなし、不整合なしです。

## ステップ3: 新しいサーバーにリストアする

サーバーが壊れたとしましょう。新しいサーバーをセットアップして `rdc` に追加し、プルします。

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

次に起動します。

```bash
time rdc repo up --name my-app -m new-server
```

アプリが戻りました。同じデータ、同じコンテナ、別のマシンです。

## 高速バックアップ: マシン間の直接転送

クラウドストレージを経由せずに、マシン間で直接プッシュすることもできます。

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **ヒント。** ストレージへのアップロードは常にすべてのデータを送信します。マシン間の転送は差分のみを送信します。初回のマシン間プッシュは通常の時間がかかりますが、それ以降のプッシュははるかに高速です。頻繁なバックアップに最適です。

---

次: [モニタリング](/en/docs/tutorial-monitoring)
