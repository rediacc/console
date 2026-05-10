---
title: "最初のアプリをデプロイする"
description: "renet dev up を使い、組み込みテンプレートからコンテナ化されたアプリをデプロイします。"
category: "Tutorials"
subcategory: essentials
order: 5
language: ja
sourceHash: "f75b5b6a716e94bf"
---

# 最初のアプリをデプロイする

空のリポジトリが用意できました。`rdc` には組み込みテンプレートが用意されているので、`docker-compose` をゼロから書かずに本格的なアプリを立ち上げることができます。3ステップで完了します。テンプレートを選び、適用して、実行するだけです。

## チュートリアル動画

![チュートリアル: 最初のアプリをデプロイする](/assets/tutorials/tutorial-deploy-app.cast)

## 選択・適用・実行

![テンプレートを選び、適用して、実行する](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## ステップ1: 選択する

利用可能なテンプレートを確認します。

```bash
time rdc repo template list
```

Postgres、Redis、Webサーバーなど、よく使われるアプリのための既成セットアップが表示されます。

## ステップ2: 適用する

テンプレートをリポジトリに追加します。ここでは `app-postgres` を使います。

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

リポジトリに2つのファイルが追加されます。`docker-compose.yml` はコンテナを記述するファイルで、`Rediaccfile` はアプリの起動・停止時の処理（`up` と `down` のライフサイクルフック）を定義します。

## ステップ3: 実行する

前のチュートリアルの VS Code 接続を通じてリポジトリのサンドボックス内にいるので、`renet` を直接使います。

```bash
time renet dev up
```

以上です。アプリが起動しています。確認しましょう。

```bash
time docker ps
```

ここで表示される `docker ps` は、このリポジトリのコンテナのみを表示します。同じサーバー上の他のリポジトリは専用の Docker デーモンを持っており、このビューからは完全に見えません。

---

次: [リポジトリで作業する](/en/docs/tutorial-work-with-repo)
