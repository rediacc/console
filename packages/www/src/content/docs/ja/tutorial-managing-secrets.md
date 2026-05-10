---
title: "シークレットの管理"
description: "デプロイ時の認証情報をフォークが届かない場所に保管します。設計上、書き込み専用です。"
category: "Tutorials"
subcategory: advanced
order: 8
language: ja
sourceHash: "0b4d72c80b489e12"
---

# シークレットの管理

本番アプリには本物の認証情報が必要です。Stripe のライブキー、データベースパスワード、API トークンなどです。これらをリポジトリに置くのは間違いです。フォークは暗号化イメージの内容をそのまま引き継ぐため、突然サンドボックスが本物の顧客カードに課金してしまいます。

正しい置き場所は `rdc repo secret` です。2つの配信モード、設計上の書き込み専用、そしてフォークは何も持たない状態で起動します。

## チュートリアル動画

![チュートリアル: シークレットの管理](/assets/tutorials/tutorial-managing-secrets.cast)

## 落とし穴: リポジトリ内の `.env`

![リポジトリイメージ内の .env ファイルはすべてのフォークにクローンされる](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

ほとんどのチームは `.env` をリポジトリに置きます。当然の選択です。

そしてフォークします。

フォークは親イメージのバイト単位のコピーです。`.env` の内容はフォークの `.env` にも入ります。フォークのコンテナが起動します。同じ Stripe キーを読み込みます。本番の認証情報で同じ Stripe API を呼び出します。Stripe 側から見ると、その呼び出しは *あなた自身* のものです。

これは大変なことになります。

## シークレットを設定する

解決策は `rdc repo secret` です。`env` モードで設定します。値はコンテナ内の環境変数として渡されます。

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

2つのポイントがあります。

- `--mode env`: 値が環境変数として渡されます。
- `--current ""`: 空文字列です。これは以前の値がない新しいシークレットであることを宣言します。

機密性の高いものは `file` モードで設定します。

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file` モードは値をコンテナの環境変数に入れません。代わりに Docker の標準メカニズムを使って `/run/secrets/stripe_key` に書き込みます。

一覧を確認します。

```bash
time rdc repo secret list --name my-app
```

名前とモードだけが表示されます。**値は表示されません。** リストは決して値を表示しません。

## compose に組み込む

`docker-compose.yml` を開きます。両方のモードを参照します。

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}` は `env` モードです。`renet` の compose ラッパーがデプロイ時にシークレットストアから展開します。

`secrets:` ブロックは `file` モードで、Docker の標準メカニズムを使います。ホストパスは `${REDIACC_NETWORK_ID}` を使っているため、同じ compose が親リポジトリとフォークで使えます。各フォークは独自のネットワーク ID を持ちます。

デプロイします。

```bash
time rdc repo up --name my-app -m my-server
```

## コンテナ内で確認する

両方のモードがコンテナ内に届いているはずです。env モードのシークレットを確認します。

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal` と表示されます。env モードのシークレットがコンテナの環境変数に届きました。

次に file モードを確認します。

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx` と表示されます。Docker の標準シークレットメカニズムでファイルがマウントされています。

## 値は読み返せない

![書き込み専用モデル: get はダイジェストを返し、値は返さない](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

次は多くの人を驚かせる部分です。

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

ダイジェストが表示されます。**値ではありません。** 値を返すフラグはありません。平文を返すコマンドはどこにも存在しません。

これは GitHub Actions モデルです。書き込み専用です。`--current <値>` を渡して前提条件が通ることで、シークレットを知っていることを証明できます。Rediacc にシークレットの内容を教えてもらうことはできません。

値を忘れた場合は、**覗こうとしないでください。ローテーションしてください。**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` は前提条件チェックをスキップします。監査ログはこれをローテーションとして記録します。明示的で意図的な操作です。

以前の値を覚えている場合は、代わりにそれを使って証明できます。

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

こちらがより安全な方法です。「間違ったターミナルにいる」というミスを防げます。

## フォークの結末

![フォーク後、シークレットリストは空](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

落とし穴を覚えていますか？リポジトリをフォークして確認してみましょう。

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**空です。**

フォークには Stripe キーがありません。データベースパスワードもありません。API トークンもありません。フォーク内のコンテナは `${REDIACC_SECRET_STRIPE_KEY}` を展開できません。`/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` というファイルは存在しません。

フォークはあなたのふりをすることができません。

テスト用にフォークにシークレットが必要な場合は、サンドボックスの値で明示的に設定します。

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

これでフォークは Stripe サンドボックスと通信します。本番の認証情報は本番から出ません。

## まとめ

- `rdc repo secret` は認証情報をリポジトリイメージの外に置きます。
- フォークはそこに届きません。
- `get` はダイジェストを返し、値は返しません。
- 忘れたらローテーション。覗こうとしないでください。

シークレットはフォークが追えません。

---

次: [ネットワーキングとドメイン](/en/docs/tutorial-networking)
