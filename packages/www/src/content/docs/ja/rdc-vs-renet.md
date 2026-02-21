---
title: "rdc vs renet"
description: "rdc を使う場面と renet を使う場面。"
category: "Guides"
order: 1
language: ja
sourceHash: "cb2c174b8cf1a078"
---

# rdc vs renet

Rediacc には2つのバイナリがあります。

- `rdc` は、ワークステーションで実行するユーザー向けCLIです。
- `renet` は、サーバー側で動作する低レベルのリモートバイナリです。

日常的な運用のほとんどは `rdc` を使ってください。

## メンタルモデル

`rdc` は control plane、`renet` は data plane と考えると分かりやすいです。

`rdc`:
- ローカルコンテキストとマシンの対応情報を読む
- SSHでサーバーに接続する
- 必要に応じて `renet` を導入/更新する
- 適切なリモート操作を代わりに実行する

`renet`:
- サーバー上で高い権限で動作する
- datastore、LUKSボリューム、マウント、分離Docker daemonを管理する
- リポジトリとシステムに対する低レベル操作を実行する

## 実運用で何を使うか

### `rdc` を使う（デフォルト）

通常のワークフローは `rdc` を使います:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### `renet` を使う（上級 / サーバー側）

`renet` を直接使うのは、意図して低レベル制御が必要な場合だけです。例えば:

- サーバー上での緊急デバッグ
- ホストレベルの保守や復旧
- `rdc` では公開されていない内部状態の確認

ほとんどのユーザーは通常運用で `renet` を直接呼び出す必要はありません。

### 実験的機能: `rdc ops`（ローカルVM）

`rdc ops` は `renet ops` をラップし、ワークステーション上でローカルVMクラスターを管理します:

```bash
rdc ops setup    # 前提条件をインストール（KVM または QEMU）
rdc ops up --basic  # 最小クラスターを構築
rdc ops status   # VMのステータスを確認
rdc ops ssh 1    # ブリッジVMにSSH接続
rdc ops down     # クラスターを破棄
```

これらのコマンドは `renet` をローカルで実行します（SSH経由ではありません）。詳細は [実験的VM](/ja/docs/experimental-vms) を参照してください。

## Rediaccfile について

`Rediaccfile` に `renet compose -- ...` が出てくることがあります。これは想定どおりです。Rediaccfile の関数は `renet` があるサーバー側で実行されます。

ワークステーションからは、通常どおり `rdc repo up` と `rdc repo down` でワークロードを起動/停止します。
