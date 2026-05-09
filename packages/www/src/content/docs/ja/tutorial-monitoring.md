---
title: "モニタリング"
description: "rdc machine コマンドでラップトップからサーバーとリポジトリのヘルスを確認します。"
category: "Tutorials"
subcategory: advanced
order: 12
language: ja
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# モニタリング

アプリがデプロイされ、稼働中で、バックアップも取れています。次はすべてが健全に動き続けているか確認しましょう。`rdc` はラップトップから任意のサーバーの全体像（ヘルス、コンテナ、リポジトリ）を把握できます。

## チュートリアル動画

![チュートリアル: モニタリング](/assets/tutorials/tutorial-monitoring.cast)

## 確認できる3つのこと

![ヘルス、コンテナ、リポジトリ](/img/tutorials/tutorial-monitoring/slide-1.svg)

## ヘルス: システム情報

まずシステムビューを確認します。

```bash
time rdc machine query --name my-server --system
```

システムの稼働時間、ディスク使用量、ストレージの状態が表示されます。問題があれば教えてくれます。

## コンテナ

マシン上のすべてのリポジトリで動いているすべてのコンテナを確認するには次のコマンドを使います。

```bash
time rdc machine query --name my-server --containers
```

各コンテナの名前、状態、ヘルス、CPU、メモリ、さらにどのリポジトリが所有しているかが表示されます。

## リポジトリ

リポジトリを確認するには次のコマンドを使います。

```bash
time rdc machine query --name my-server --repositories
```

各リポジトリのサイズ、マウント状態、Docker の状態、ディスク使用量が表示されます。

## すべてを一度に確認する

```bash
time rdc machine query --name my-server
```

システム情報、リポジトリ、コンテナ、すべてを1つのコマンドで確認できます。同じ `query` コマンドにフィルターなしで使うと全体像が表示され、`--system`、`--containers`、`--repositories`、`--services`、`--network`、`--block-devices` で該当セクションに絞り込めます。

## ローカルの動作確認

`rdc doctor` は特定のサーバーとは無関係に、ローカルのセットアップ（Node、SSH キー、`renet`、Docker）を確認します。

```bash
time rdc doctor
```

## 完了です

以上でシリーズ全体が完了です。インストール、設定、デプロイ、フォーク、本番公開、オートスタート、バックアップ、モニタリングをすべてマスターしました。すべてターミナルから、すべて自分のサーバーで行えます。
