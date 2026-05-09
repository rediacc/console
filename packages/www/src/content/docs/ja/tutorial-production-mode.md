---
title: "本番モード"
description: "ラップトップから切断してもアプリを動かし続け、オートスタートでサーバー再起動に対応します。"
category: "Tutorials"
subcategory: advanced
order: 10
language: ja
sourceHash: "0e070fcd877900ab"
---

# 本番モード

これまではリポジトリ内から `renet dev up` でアプリを動かしてきました。開発には最適な方法です。本番では、`rdc` を使ってラップトップからすべてを管理します。ラップトップを閉じてもアプリは動き続けます。

## チュートリアル動画

![チュートリアル: 本番モード](/assets/tutorials/tutorial-production-mode.cast)

## 開発と本番の違い

違いはシンプルです。

- `renet dev up` は**リポジトリ内**で実行します。接続が必要です。
- `rdc repo up` は**ラップトップから**実行します。その後は接続不要です。

開発から本番への移行は3つのアクションで完了します。

![停止、起動、オートスタート](/img/tutorials/tutorial-production-mode/slide-1.svg)

## ステップ1: 開発セッションを停止する

リポジトリに接続してアプリを停止します。

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## ステップ2: 本番モードで起動する

ラップトップのターミナルから実行します。

```bash
time rdc repo up --name my-app -m my-server
```

以上です。アプリが動いており、ラップトップを閉じることができます。`Rediaccfile` がすべてを処理します。`rdc repo up` は `renet dev up` と同じ `up` 関数を呼び出します。同じ `Rediaccfile`、呼び出し方が違うだけです。

## ステップ3: サーバー再起動に対応する

サーバーが再起動したときにアプリが自動的に戻ってくるよう設定します。

```bash
time rdc repo autostart enable --name my-app -m my-server
```

オートスタートが有効なリポジトリを確認します。

```bash
time rdc repo autostart list -m my-server
```

## 本番での停止

アプリを停止する必要があるときは次のコマンドを使います。

```bash
time rdc repo down --name my-app -m my-server
```

起動は1コマンド、停止も1コマンド。すべてラップトップから操作できます。

---

次: [バックアップとリストア](/en/docs/tutorial-backup-restore)
