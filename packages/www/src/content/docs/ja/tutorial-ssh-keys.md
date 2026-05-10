---
title: "SSH キーの設定"
description: "rdc がパスワードなしでサーバーに接続できるよう、SSH キーを設定します。"
category: "Tutorials"
subcategory: essentials
order: 2
language: ja
sourceHash: "009a1bd345e93413"
---

# SSH キーの設定

`rdc` は SSH 経由でサーバーに接続するため、各サーバーがあなたの SSH キーを信頼している必要があります。合計3ステップです。そのうち2つは一度だけ行う初期設定で、1つは新しいサーバーを追加するたびに繰り返します。

## チュートリアル動画

![チュートリアル: SSH キーの設定](/assets/tutorials/tutorial-ssh-keys.cast)

## 3つのステップ

![生成、コピー、登録](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **生成**: ラップトップで SSH キーを生成します。一度だけ行います。
2. **コピー**: サーバーにコピーします。新しいサーバーを追加するたびに繰り返します。
3. **登録**: `rdc` にキーを登録します。一度だけ行います。

## ステップ1: キーを生成する

使いたいキーがすでにある場合は、この手順をスキップしてください。ない場合は次のコマンドを実行します。

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` は現代の標準形式で、小さく、高速で、広くサポートされています。

## ステップ2: サーバーにコピーする

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

`user` と `your-server-ip` は、お使いのサーバーの SSH ユーザーと IP アドレスに置き換えてください。この最後の一度だけサーバーのパスワードを求められます。これ以降、パスワード認証は不要になります。

## ステップ3: `rdc` にキーを登録する

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

以上です。これ以降、すべての `rdc` コマンドはこのキーで認証します。パスワードも対話型プロンプトも不要です。

---

次: [最初のサーバーを追加する](/en/docs/tutorial-add-server)
