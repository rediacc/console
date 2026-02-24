---
title: rdc vs renet
description: rdc を使う場面と renet を使う場面。
category: Concepts
order: 1
language: ja
sourceHash: e0ef5f051cefb407
---

# rdc vs renet

Rediaccには2つのバイナリがあります。それぞれの使い分けを説明します。

| | rdc | renet |
|---|-----|-------|
| **実行環境** | ワークステーション | リモートサーバー |
| **接続方法** | SSH | ローカルでroot権限で実行 |
| **対象ユーザー** | すべてのユーザー | 高度なデバッグのみ |
| **インストール** | ユーザーがインストール | `rdc`が自動的にプロビジョニング |

> 日常的な作業には`rdc`を使用してください。`renet`を直接使用する必要はほとんどありません。

## 連携の仕組み

`rdc`はSSH経由でサーバーに接続し、`renet`コマンドを代行実行します。ワークステーションで1つのコマンドを入力するだけで、`rdc`が残りの処理を行います：

1. ローカル設定（`~/.rediacc/rediacc.json`）を読み取る
2. SSH経由でサーバーに接続する
3. 必要に応じて`renet`バイナリを更新する
4. サーバー上で対応する`renet`操作を実行する
5. 結果をターミナルに返す

## 通常の作業には`rdc`を使用

すべての一般的なタスクはワークステーション上の`rdc`を通じて実行します：

```bash
# 新しいサーバーをセットアップ
rdc config setup-machine server-1

# リポジトリを作成して起動
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# リポジトリを停止
rdc repo down my-app -m server-1

# マシンの健全性を確認
rdc machine health server-1
```

完全なウォークスルーについては、[クイックスタート](/ja/docs/quick-start)を参照してください。

## サーバーサイドのデバッグには`renet`を使用

`renet`を直接使用する必要があるのは、以下の目的でサーバーにSSH接続する場合のみです：

- `rdc`が接続できない場合の緊急デバッグ
- `rdc`を通じて利用できないシステム内部の確認
- 低レベルの復旧操作

すべての`renet`コマンドにはroot権限（`sudo`）が必要です。`renet`コマンドの完全なリストについては、[サーバーリファレンス](/ja/docs/server-reference)を参照してください。

## 実験的機能：`rdc ops`（ローカルVM）

`rdc ops`は、ワークステーション上でローカルVMクラスターを管理するために`renet ops`をラップします：

```bash
rdc ops setup              # 前提条件をインストール（KVMまたはQEMU）
rdc ops up --basic         # 最小構成のクラスターを起動
rdc ops status             # VMステータスを確認
rdc ops ssh 1              # ブリッジVMにSSH接続
rdc ops ssh 1 hostname     # ブリッジVM上でコマンドを実行
rdc ops down               # クラスターを破棄
```

> ローカルアダプターが必要です。クラウドアダプターでは利用できません。

これらのコマンドは`renet`をローカルで実行します（SSH経由ではありません）。完全なドキュメントについては、[実験的VM](/ja/docs/experimental-vms)を参照してください。

## Rediaccfileに関する注意

`Rediaccfile`内で`renet compose -- ...`が使われているのを目にすることがあるかもしれません。これは正常です。Rediaccfileの関数は`renet`が利用可能なサーバー上で実行されます。

ワークステーションからは、`rdc repo up`と`rdc repo down`を使用してワークロードを起動・停止してください。
