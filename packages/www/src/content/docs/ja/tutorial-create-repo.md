---
title: "最初のリポジトリを作成する"
description: "サーバーに暗号化されたリポジトリを作成し、VS Code で開きます。"
category: "Tutorials"
subcategory: essentials
order: 4
language: ja
sourceHash: "1294b0494f20671b"
---

# 最初のリポジトリを作成する

Rediacc のリポジトリは、サーバー上の1つの暗号化ファイルです。マウントすると、専用の Docker デーモンとアプリケーションデータを持つフォルダになります。完全に分離されており、完全にポータブルです。

本番用の USB ドライブのようなものと考えてください。静止時はファイルであり、実行時はサーバーになります。

## チュートリアル動画

![チュートリアル: 最初のリポジトリを作成する](/assets/tutorials/tutorial-create-repo.cast)

## ディスク上のファイル、マウント時の環境

![暗号化ファイルが分離されたフォルダとしてマウントされる](/img/tutorials/tutorial-create-repo/slide-1.svg)

ディスク上の形態は1つの暗号化イメージです。マウントすると以下が利用できます。

- 専用の Docker デーモン（ホストとは別のもの）
- 暗号化ボリューム内のアプリケーションデータ
- 同じサーバー上の他のものと衝突しないループバック IP

リポジトリはポータブルです。マシン間で移動したり、バックアップを取ったり、即座にフォークすることができます。同じサーバー上のすべてのリポジトリは、互いに完全に分離されています。

## 作成する

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

`my-server` に 2 GB の暗号化リポジトリが作成されます。確認しましょう。

```bash
time rdc repo list -m my-server
```

## VS Code で開く

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code がリポジトリの内部に直接開きます。ワークスペースは空になっています。これがあなたの分離された環境です。ここで作成したものはすべて暗号化ボリューム内に格納され、同じサーバー上の他のリポジトリからは見えません。

---

次: [最初のアプリをデプロイする](/en/docs/tutorial-deploy-app)
