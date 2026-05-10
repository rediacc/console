---
title: "リポジトリで作業する"
description: "ポートをブラウザにトンネリングし、サンドボックス内でコマンドを実行し、ラップトップとリポジトリの間でファイルを同期します。"
category: "Tutorials"
subcategory: essentials
order: 6
language: ja
sourceHash: "3d56eb69e72c1a5a"
---

# リポジトリで作業する

アプリが起動しましたが、これまでは `docker ps` でしか確認していません。日常的な作業をカバーする3つのコマンドを紹介します。**tunnel** でブラウザでアプリを確認し、**term** でサンドボックス内のコマンドを実行し、**sync** でラップトップとリポジトリの間でファイルを移動します。

## チュートリアル動画

![チュートリアル: リポジトリで作業する](/assets/tutorials/tutorial-work-with-repo.cast)

## 毎日の3つのコマンド

![トンネル、ターム、シンク](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: ブラウザでアプリを開く。
2. **Term**: サンドボックス内でコマンドを実行する。
3. **Sync**: ファイルを出し入れする。

## Tunnel: ブラウザでアプリを確認する

アプリはラップトップではなくサーバーで動いています。SSH 経由でコンテナのポートを転送します。

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

ブラウザで `localhost` を開きます。アプリがそこに表示されます。完了したら `Ctrl+C` を押します。

別のコンテナを使う場合は、`-c` を変えてポートを指定します。

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: リポジトリ内でコマンドを実行する

シェルだけが必要なときは VS Code を使わなくても大丈夫です。

```bash
rdc term connect -m my-server -r my-app
```

これでリポジトリのサンドボックス内に入ります。試してみましょう。

```bash
time docker ps
```

VS Code と同じビューで、`my-app` のコンテナだけが表示されます。

単発コマンドの場合は `-c` を使えば対話型シェルを省略できます。

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: ラップトップとリポジトリの間でファイルを移動する

ラップトップからリポジトリにフォルダをプッシュします。

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

ファイルを引き戻します。

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

不安な場合はまずプレビューしましょう。`--dry-run` は実際にコピーせずに変更内容を表示します。

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

トンネル、ターム、シンク。3つのコマンドで日常の作業サイクルをカバーできます。

---

次: [リポジトリをフォークする](/en/docs/tutorial-forking)
