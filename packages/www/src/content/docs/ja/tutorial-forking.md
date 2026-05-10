---
title: "リポジトリをフォークする"
description: "リポジトリ全体（アプリ、データベース、ファイル）を数秒でクローンします。サイズ無制限、追加ディスク不要。"
category: "Tutorials"
subcategory: advanced
order: 7
language: ja
sourceHash: "9237f00dce2ee5ec"
---

# リポジトリをフォークする

これが目玉機能です。本番環境全体（アプリ、データベース、設定ファイル）を数秒でクローンできます。サイズ制限なし、追加ディスク不要、何度でもフォークできます。

キャッチフレーズ: **本番をクローンして、何も壊さない。**

## チュートリアル動画

![チュートリアル: リポジトリをフォークする](/assets/tutorials/tutorial-forking.cast)

## 失うものを用意する

まず、フォークの分離を証明するためにファイルを追加します。VS Code でリポジトリを開きます。

```bash
rdc vscode connect -m my-server -r my-app
```

リポジトリ内でマーカーファイルを作成します。

```bash
time echo "Hello from production" > index.html
```

では、フォークしましょう。

## フォーク

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![親から独立したクローンへ展開](/img/tutorials/tutorial-forking/slide-1.svg)

コマンド1つです。すべて（アプリ、データベース、設定ファイル）を数秒でクローンしました。もう一度実行すれば、また別の独立したクローンが作成されます。

## なぜこんなに速いのか

![フォルダサイズに関係なく、リンクの共有速度は同じ](/img/tutorials/tutorial-forking/slide-2.svg)

フォルダのリンクを共有することを想像してください。フォルダが小さくても大きくても、リンクは同じです。フォルダは重くても、リンクは軽いのです。

![1 GB、100 GB、1 TB。常に同じ時間。](/img/tutorials/tutorial-forking/slide-3.svg)

フォークも同じ仕組みです。1 GB、100 GB、1 TB。常に同じ時間がかかります。

## 共有されるものと、自分のもの

![多くの鏡と1つの太陽: 共有ベース、変更は自分のもの](/img/tutorials/tutorial-forking/slide-4.svg)

親リポジトリを太陽だと考えてください。太陽を手で持つことはできませんが、太陽を映す鏡を持つことはできます。その鏡があなたのフォークです。鏡に絵を描けば、その絵はあなたのものです。何枚鏡を向けても、太陽は変わりません。

> 太陽は持てないけれど、鏡の中に持てる。

## 親がその後変わったら？

![フォークは凍った写真、親は流れ続ける川](/img/tutorials/tutorial-forking/slide-5.svg)

今度は川を想像してください。水は流れ続けます。毎瞬間、姿が変わります。フォークするとき、あなたはその瞬間の川の写真を撮ります。川は流れ続けますが、写真は変わりません。

親リポジトリがその後変わっても、あなたのフォークはフォークした時点のまま残ります。

> 川は持てないけれど、写真の中に持てる。

## ディスク使用量は増えない

![100 GB リポジトリの5つのフォーク、合計はまだ約 100 GB](/img/tutorials/tutorial-forking/slide-6.svg)

だからディスクが溢れないのです。100 GB のリポジトリを5つフォークしても、合計はまだ約 100 GB です。各フォークで変更した分だけディスクが使われます。

> 何度でもフォークしてください。ディスクは気づきもしません。

## フォークが*引き継がない*もの: シークレット

フォークが意図的に引き継がないものが1つあります。シークレットです。フォークは API キー、データベースパスワード、Stripe トークンを持たない状態で起動します。だからこそ「本番をクローンして、何も壊さない」が実際に機能するのです。サンドボックスは本物の顧客に課金できません。なぜなら、あなたのふりをすることができないからです。この仕組みは [シークレットの管理](/en/docs/tutorial-managing-secrets) チュートリアルで適切にセットアップします。

## 分離を確認する

両方のリポジトリを並べて確認します。

```bash
time rdc repo list -m my-server
```

`my-app` と `my-app:experiment` が同時に動いているのが確認できます。

元のリポジトリで動いているものを確認します。

```bash
time docker ps
```

稼働時間に注目してください。これらが元のコンテナです。では、フォークに切り替えましょう。

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

同じイメージですが、稼働時間が新しいです。フォークしたときに起動したコンテナです。

違いをさらにわかりやすくしましょう。フォーク内だけにコンテナを追加します。

```bash
time docker run --rm -it -d nginx
time docker ps
```

nginx が動いていますが、このフォーク内だけです。

何か破壊的なことを試してみましょう。

```bash
time rm index.html
```

ここでは消えました。元のリポジトリに戻りましょう。

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

nginx はありません。フォークのコンテナはフォーク内に留まりました。そして `index.html` はここにあり、手つかずのままです。元のリポジトリは何も起きたことを知りません。同じイメージ、別の Docker デーモン、別のファイルシステムです。

## クリーンアップ

作業が終わったら、フォークを削除するだけです。

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

元のリポジトリはまったく変わりません。**フォークして、実験して、壊して、削除する。** リスクゼロです。

---

次: [シークレットの管理](/en/docs/tutorial-managing-secrets)
