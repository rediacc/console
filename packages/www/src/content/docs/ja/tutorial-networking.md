---
title: "ネットワーキングとドメイン"
description: "ドメイン、自動 TLS、Traefik リバースプロキシを使ってアプリをインターネットに公開します。"
category: "Tutorials"
subcategory: advanced
order: 9
language: ja
sourceHash: "9f72a61ed1ff4cb9"
---

# ネットワーキングとドメイン

アプリは動いていますが、まだ外部からアクセスできません。このチュートリアルでは、本物のドメイン、Let's Encrypt による自動 TLS、コンテナを自動検出する Traefik プロキシをセットアップします。Cloudflare 上のドメインと API トークンが必要です。

## チュートリアル動画

![チュートリアル: ネットワーキングとドメイン](/assets/tutorials/tutorial-networking.cast)

## 4つのステップ

![トークン、設定、プッシュ、デプロイ](/img/tutorials/tutorial-networking/slide-1.svg)

1. **取得**: Cloudflare API トークンを取得します。
2. **設定**: `rdc` にインフラ情報を設定します。
3. **プッシュ**: サーバーに反映します。
4. **デプロイ**: プロキシをデプロイします。

## ステップ1: Cloudflare API トークン

Cloudflare ダッシュボードで **マイプロファイル（My Profile）→ API トークン（API Tokens）** に移動し、**Zone DNS Edit** 権限のトークンを作成します。トークンの値をコピーします。表示されるのは一度だけです。

## ステップ2: インフラを設定する

`rdc` にパブリック IP、ベースドメイン、証明書のメールアドレス、トークンを設定します。

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

IP アドレス、ドメイン、メールアドレス、トークンはご自身のものに置き換えてください。

`--cert-email` と `--cf-dns-token` はすべてのマシンで共有されるため、一度だけ設定すれば十分です。

## ステップ3: サーバーにプッシュする

```bash
time rdc config infra push -m my-server
```

これにより Cloudflare に DNS レコードが自動的に作成され、サーバー上のプロキシ設定が準備されます。

## ステップ4: プロキシをデプロイする

プロキシ自体はまだ動いていません。`infra` という名前の小さなリポジトリ内に、組み込みの `proxy` テンプレートからデプロイします。

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

以上です。Traefik が起動しています。アプリには次の URL でアクセスできます。

```
myapp.my-app.my-server.yourdomain.com
```

Traefik は5秒ごとにコンテナを自動検出します。TLS 証明書は Let's Encrypt から自動的に取得されます。プロキシの手動設定は不要です。

---

次: [本番モード](/en/docs/tutorial-production-mode)
