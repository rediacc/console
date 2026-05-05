---
title: "シークレットの管理"
description: "リポジトリごとのシークレットを設定し、composeに配線し、コンテナに到達することを確認し、ローテーションし、フォークが何も継承しないことを確認します。"
category: "Tutorials"
order: 7
language: ja
sourceHash: "fb8bc967ed22fc10"
---

# Rediacc でリポジトリごとのシークレットを管理する方法

実際のアプリケーションには認証情報が必要です：Stripe ライブキー、データベースパスワード、API トークンなど。それらをリポジトリ内に置くのは間違った場所です。フォークは暗号化されたイメージ内にあるものをすべて継承し、そのコンテナは外部サービスに対して親として識別されて起動します。正しい場所は `rdc repo secret` です。値は暗号化されたイメージの外に置かれるため、フォークは空のシークレットマップで開始します。

このチュートリアルでは、シークレットの両方のモードを設定し、compose ファイルに配線し、コンテナに到達することを確認し、1 つをローテーションし、フォークが何も継承しないことを確認します。

## 前提条件

- 設定が初期化された `rdc` CLI がインストールされていること
- プロビジョニングされたマシンと作成されたリポジトリ（[チュートリアル：リポジトリのライフサイクル](/ja/docs/tutorial-repos)を参照）
- 編集できる `Rediaccfile` と `docker-compose.yml`

## ステップ 1：シークレットを設定する

2 つの配信モードが利用できます。`env` は値を `REDIACC_SECRET_<KEY>` として compose の `${...}` 補間用にエクスポートします。`file` は値をホスト側の tmpfs ファイル `/var/run/rediacc/secrets/<networkID>/<KEY>` に書き込み、Docker compose の `secrets:` ブロックで使用します。機密性の高いものには `file` を使用してください。env モードの値は `docker inspect` と `/proc/<pid>/environ` に表示されます。

全く新しいキーの初回書き込みでは、`--current ""`（空）を渡して、以前の値がないことを確認します。

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## ステップ 2：何があるかを一覧表示する

```bash
rdc repo secret list --name my-app
```

出力は各シークレットの名前とモードを含む JSON です。値は決して一覧に表示されません。ディスクから取得さえされません。

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## ステップ 3：compose に配線する

両方のモードは同じ `docker-compose.yml` から参照されます：

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

サービス上の小文字の `stripe_key` は、コンテナ内の `/run/secrets/<name>` ファイル名です。ホストパスの大文字の `STRIPE_KEY` は、設定した `--key` と一致します。`${REDIACC_NETWORK_ID}` は `renet compose` によって自動的に補間されます。これは重要です。なぜならネットワーク ID はフォークごとなので、同じ compose ファイルが親と任意のフォーク（ステップ 6 で見るように、ファイルが単に存在しない場所）で動作するからです。

> **リポジトリ間の分離が強制されます。** renet の compose バリデーターは、別のリポジトリのネットワーク ID をターゲットとする `secrets: file:`（または `configs: file:`、`env_file:`）パスを拒否します。リテラル `${REDIACC_NETWORK_ID}` トークン（または自分のネットワークの整数）が唯一受け入れられる形式であり、`--unsafe` でこれを上書きできません。Rediaccfile bash サブプロセスを囲む Landlock サンドボックスは、ファイルシステム読み取りを自分のネットワークのシークレットディレクトリにスコープします。そのため、Rediaccfile からの悪意のある `cat /var/run/rediacc/secrets/<other>/X` でさえカーネル層で EACCES で失敗します。オプトインのために何もする必要はありません。保護はデフォルトで有効です。

## ステップ 4：デプロイして検証する

```bash
rdc repo up --name my-app -m server-1
```

デプロイ後、コンテナに exec して両方のモードが到達したことを確認します：

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

ホスト側の tmpfs ファイルを直接検査したい場合：

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## ステップ 5：以前の値を知らずにローテーションする

`rdc repo secret get` でダイジェストを読むことができますが、平文の値は決して読めません。これがライトオンリーモデルです。保存された値が持っているものと一致することを確認する必要がある場合は、`--current` 経由で渡し、前提条件が通過するか失敗するかを観察します：

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

以前の値を完全に忘れてしまった場合（パスワードマネージャーが失った、またはリポジトリを継承した）、`--rotate-secret` を使用して前提条件をスキップします。監査ログはこれをローテーションとして大きく記録します：

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` と `--rotate-secret` は相互排他的です。1 つを選んでください。

## ステップ 6：フォークが何も継承しないことを確認する

全体の要点：リポジトリをフォークし、フォークのシークレットリストを確認します：

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

空です。フォークのコンテナは `${REDIACC_SECRET_DB_HOST}` を補間できず（変数は未設定なので空文字列）、`/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` のファイルは単に存在しません。フォークの `repo up` が compose `secrets:` ブロック経由でマウントしようとすると、デプロイは明確なエラーで失敗します。これはまさに望ましい失敗モードです。なぜならサンドボックスは外部サービスに対して本番のフリをできないことを意味するからです。

フォークでシークレットを使用するには、サンドボックススコープの値でフォークに明示的に設定します：

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

これでフォークはテストデータベースと Stripe サンドボックスアカウントと通信します。親の本番認証情報が親を離れることはありません。

## クリーンアップ

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## 関連項目

- [リポジトリ § シークレット](/ja/docs/repositories#secrets)。完全なリファレンス
- [RDC CLI チートシート § リポジトリごとのシークレット](/ja/docs/rdc-cheat-sheet#per-repo-secrets)。コマンドのクイックリファレンス
- [AI エージェントの安全性](/ja/docs/ai-agents-safety)。対称ミューテーションゲートとエラーエンベロープ内の構造化された `next` アクションヒント
- [サービス § compose でリポジトリごとのシークレットを使用する](/ja/docs/services#using-per-repo-secrets-in-compose)。compose パターンリファレンス
