---
title: "最初のサーバーを追加する"
description: "最初のサーバーを rdc に登録してプロビジョニングし、rdc と renet のアーキテクチャを理解します。"
category: "Tutorials"
subcategory: essentials
order: 3
language: ja
sourceHash: "2b5de59f61cfb88c"
---

# 最初のサーバーを追加する

サーバーを追加する前に、`rdc` の仕組みを理解しておくと役立ちます。Rediacc は2つのツールで構成されています。ラップトップ上の `rdc` と、サーバー上の `renet` です。

## チュートリアル動画

![チュートリアル: 最初のサーバーを追加する](/assets/tutorials/tutorial-add-server.cast)

## なぜ2つのツールが必要なのか

![ラップトップの rdc、サーバーの renet、SSH で接続](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** はラップトップ上の CLI です。ここでコマンドを入力します。
- **`renet`** はサーバー上のオーケストレーターです。暗号化、Docker、分離を管理します。

ローカルでコマンドを実行すると、`rdc` が SSH 経由で接続し、サーバー上の `renet` を実行します。サーバーに手動で SSH 接続する必要はありません。`rdc` がすべて行います。

## ステップ1: サーバーを登録する

`rdc` にサーバーを知らせます。名前、IP アドレス、ユーザー名はご自身のものに置き換えてください。

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## ステップ2: プロビジョニングする

セットアップにより `renet` がインストールされ、サーバーに暗号化データストアが作成されます。

```bash
time rdc config machine setup --name my-server
```

完了すると、サーバーはリポジトリをホストする準備が整います。

## 設定ファイルの場所

`rdc` がセットアップ内容を正しく把握しているか確認します。

```bash
time rdc config show
```

または、JSON ファイルを直接開くこともできます。

```bash
vim ~/.config/rediacc/rediacc.json
```

このファイル1つにすべてが格納されています。マシン、リポジトリ、SSH キー、暗号化の認証情報などです。別のラップトップにコピーすれば、そのマシンからも同じサーバーを操作できます。

---

次: [最初のリポジトリを作成する](/en/docs/tutorial-create-repo)
