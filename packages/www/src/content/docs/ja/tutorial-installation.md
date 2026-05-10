---
title: "インストール"
description: "コマンド1つでラップトップに rdc CLI をインストールし、rdc doctor で動作確認します。"
category: "Tutorials"
subcategory: essentials
order: 1
language: ja
sourceHash: "99d4ca1a4f89278e"
---

# インストール

`rdc` のインストールは3ステップです。インストールページを開き、オペレーティングシステムを選択して、コマンドをターミナルに貼り付けるだけです。全体で1〜2分もあれば完了します。

## チュートリアル動画

![チュートリアル: インストール](/assets/tutorials/tutorial-installation.cast)

## 3つのステップ

![3ステップの概要](/img/tutorials/tutorial-installation/slide-1.svg)

1. [インストールページ](/en/install) を開きます。
2. お使いのオペレーティングシステムを選択します。
3. インストールコマンドをコピーして、ターミナルに貼り付けます。

## プラットフォームへのインストール

インストールページが適切なコマンドを自動生成しますが、代表的なワンライナーを以下に記載します。

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> `time` プレフィックスは、コマンドの実行時間を表示するシェルの機能です。このシリーズ全体で使用しており、各ステップの実際の速度を確認できます。省略しても問題ありません。

## インストールの確認

スクリプトが完了したら、`rdc` に必要なものがすべて揃っているか確認します。

```bash
time rdc doctor
```

`rdc doctor` は Node、SSH、その他の `rdc` の依存関係を順番にチェックし、不足しているものを報告します。

## `rdc` がラップトップに置かれる理由

![ラップトップの rdc、サーバーの renet](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` はラップトップ上の CLI です。サーバーは `renet` という別のコンポーネントを実行しており、`rdc` が SSH 経由でプロビジョニングして操作します。サーバーに手動で SSH 接続する必要はありません。`rdc` がすべて行います。

次の2つのチュートリアルで、この仕組みをきちんとセットアップします。

---

次: [SSH キーの設定](/en/docs/tutorial-ssh-keys)
