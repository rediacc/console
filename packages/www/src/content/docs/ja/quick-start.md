---
title: クイックスタート
description: 数分でサーバー上にコンテナ化されたサービスを稼働させましょう。
category: Guides
order: -1
language: ja
sourceHash: "2047fd1ce3a47944"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# クイックスタート

自分のサーバーに Rediacc をインストールします。暗号化された隔離コンテナ環境で、クラウドアカウントやSaaS依存は不要です。あなたのハードウェア、あなたの管理。

---

## はじめに

### 主要な概念

リポジトリはディスク上の単一の暗号化ファイルです。移動、バックアップ、フォークが可能です。ただのファイルです。マウントすると、専用の Docker デーモンとアプリデータを含むフォルダになります。

リポジトリは USB ドライブのようなものだと考えてください。任意のマシンに差し込むとアプリとデータがマウントされ、すぐに実行できます。何も再構築せずにマシンやクラウドプロバイダーをまたいで移動できます。

**2つのツール、2つの役割:**

- **rdc** = ラップトップ上の CLI（TypeScript、グローバルインストール）
- **renet** = サーバー上のオーケストレーター（Go バイナリ、デーモン/ネットワーク/隔離を管理）
- RDC は `config machine setup` 時に renet を自動的にプロビジョニングします。サーバー上での手動セットアップは不要です。

> [アーキテクチャ](/en/docs/architecture)でセキュリティモデルを説明しています。[rdc vs renet](/en/docs/rdc-vs-renet)でどちらのツールをいつ使うか説明しています。

### 1. CLI のインストール

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # 確認: Node、SSH キー、renet、Docker
```

> Windows、Alpine、Arch: [インストール](/en/docs/installation)を参照してください。完全なシステム要件: [要件](/en/docs/requirements)。

### 2. SSH キーの設定

rdc は SSH 経由で接続します。rdc がサーバーに到達するには、事前にサーバーがあなたの公開鍵を信頼している必要があります。

```bash
# キーを生成（既にお持ちの場合はスキップ）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 公開鍵をサーバーにコピー（パスワードの入力を求められます）
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# rdc が使用するキーを設定
rdc config ssh set --key ~/.ssh/id_ed25519
```

以降のすべての rdc コマンドはこのキーで認証されます。パスワードは不要です。

### 3. サーバーの追加

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # renet のプロビジョニング + データストアの作成
```

**実行される処理:** SSH ホストキーのスキャン、renet バイナリのアップロード、サーバー上で暗号化データストアの初期化。リポジトリの準備が完了します。

> データストアのサイズ設定、Ceph RBD、クラウドプロバイダー: [マシンセットアップ](/en/docs/setup)。SSH 接続の問題: [トラブルシューティング](/en/docs/troubleshooting)。

### 4. 設定ファイル

```bash
rdc config show                            # 人間が読みやすい形式の概要
cat ~/.config/rediacc/rediacc.json         # 生の JSON: マシン、リポジトリ、ストレージ、SSH キー
```

**1つのファイル = 1つの環境。** 別のラップトップにコピーすればすぐに使えます。

---

## リポジトリの操作

### 1. リポジトリの作成

```bash
rdc repo create --name my-app -m my-server --size 2G  # 2 GB の暗号化リポジトリを作成
```

暗号化ボリュームの作成、マウント、Docker デーモンの起動が行われます。リポジトリは設定に登録され、使用可能になります。

> リサイズ、削除、バリデーション: [リポジトリ](/en/docs/repositories)。

### 2. テンプレートの適用

```bash
rdc repo template list                                        # 組み込みテンプレートを表示
rdc repo template apply --name app-postgres -m my-server -r my-app  # docker-compose.yml + Rediaccfile をデプロイ
```

テンプレートは `docker-compose.yml`、`Rediaccfile`、およびサポートファイルを提供します。テンプレート（または独自の compose ファイル）がなければ、起動するものがありません。最初のリポジトリには組み込みテンプレートを使用してください。これが全体のワークフローをエンドツーエンドで学習する最速の方法です。

### 3. リポジトリの起動

```bash
rdc repo up --name my-app -m my-server  # Rediaccfile の up() を実行
rdc repo list -m my-server                           # マシン上のすべてのリポジトリを表示
rdc repo status --name my-app -m my-server  # マウント状態、Docker、サイズ、暗号化
```

`repo up` は必要に応じて自動マウントします。フラグは不要です。

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # VS Code SSH を開き、リポジトリサンドボックス内に移動
```

暗号化ボリューム*内部*でファイルを編集できます。`docker ps` はこのリポジトリのコンテナのみ表示します。保存、compose up、反復開発ができます。

### 5. `rdc repo up` と `renet dev up` の比較

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **実行場所** | ラップトップ（CLI） | VS Code サンドボックス内 |
| **動作内容** | SSH → 自動マウント → Rediaccfile の `up()` を実行 | Rediaccfile の `up()` を直接実行 |
| **ユースケース** | CI/CD、自動化、リモート操作 | 開発者のインナーループ |
| **隔離** | 外部からオーケストレーション | 既にサンドボックス内 |

**デモフロー:** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → `docker-compose.yml` を編集 → `renet dev up` → アプリの動作確認 → 反復開発。

> Rediaccfile の構造: [サービス](/en/docs/services)。どちらのツールを使うか: [rdc vs renet](/en/docs/rdc-vs-renet)。

### 6. 隔離モデル

- **ユニバーサルユーザー** (`rediacc`): すべてのマシンで同じ UID。リポジトリを別のサーバーに移動してもファイル所有権がそのまま機能します。`chown` の問題はありません。
- **リポジトリごとの Docker デーモン**: 各リポジトリは独自の隔離された Docker デーモンを持ちます。`docker ps` はこのリポジトリのコンテナのみ表示します。
- **Landlock + OverlayFS サンドボックス**: VS Code シェルはファイルシステムが制限されています。他のリポジトリは読み取れません。`$HOME` への書き込みはリポジトリごとのオーバーレイです。

> 隔離の仕組み: [アーキテクチャ](/en/docs/architecture)。Rediaccfile のライフサイクル: [サービス](/en/docs/services)。

### 7. ターミナル、同期、トンネル

**ターミナル:**
```bash
rdc term connect -m my-server -r my-app                            # リポジトリサンドボックスに SSH 接続
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # コマンドを実行して終了
rdc term connect -m my-server                                   # マシンに SSH 接続（サンドボックスなし）
```

**ファイル同期（SSH 経由の rsync）:**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # ディレクトリをアップロード
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # 単一ファイルをアップロード
rdc repo sync download -m my-server -r my-app --local ./backup                              # ディレクトリをダウンロード
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # 単一ファイルをダウンロード
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # まずプレビュー
```

**トンネル（コンテナへの SSH ポートフォワーディング）:**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # app コンテナのポートを自動検出
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # Postgres をトンネル
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # カスタムローカルポート
```

トンネルを実行 → ブラウザで `localhost:3000` を開く → リモートサーバーのライブアプリが表示されます。

> 同期、ターミナル、VS Code の詳細: [ツール](/en/docs/tools)。

---

## フォークとバックアップ

### 1. グランドとリポジトリのフォーク

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # 即座に CoW クローン + 起動
rdc repo list -m my-server                                  # 表示: my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # フォークを削除、グランドは影響なし
```

**即座のゼロコピークローン。** CoW（コピーオンライト）。マイクロ秒で完了、データのコピーは不要。一方が書き込むまでブロックは共有されます。

**ユースケース:**
- **AI / ML:** 本番データセットをフォーク、実験を実行、破棄または昇格
- **DevOps:** フォーク → マイグレーションをテスト → 問題があれば削除、成功すれば昇格
- **バックアップ:** フォーク = 即座のスナップショット、オフサイトにプッシュ

> フォークのライフサイクル、クロスマシンフォーク: [リポジトリ](/en/docs/repositories)。

### 2. 別のマシンへのプッシュ

```bash
# リポジトリを別のマシンにプッシュ
rdc repo push --name my-app -m my-server --to backup-server

# プッシュしてターゲットで自動デプロイ
rdc repo push --name my-app -m my-server --to backup-server --up

# CRIU チェックポイント付きプッシュ（ライブマイグレーション、メモリ状態を保持）
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# 新しいマシンにプッシュ（クラウドプロバイダー経由で自動プロビジョニング）
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. クラウドストレージへのプッシュ（OneDrive、Google Drive、S3）

```bash
# rclone 設定をストレージバックエンドとしてインポート
rdc config storage import --file ~/rclone.conf

# 利用可能なストレージを一覧表示
rdc storage list

# リポジトリをクラウドストレージにプッシュ
rdc repo push --name my-app -m my-server --to my-s3-backup

# ストレージ上のバックアップを一覧表示
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` はターゲットがマシンかストレージバックエンドかを自動検出します。rclone がサポートするすべてのプロバイダーで動作します: S3、R2、B2、OneDrive、Google Drive、SFTP など。

### 4. リモートからのプル

```bash
# クラウドマシンからローカルサーバーにリポジトリをプル
rdc repo pull --name my-app -m my-local-server --from cloud-server

# クラウドストレージからプル
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# プルして即座に起動
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**なぜプルするのか?** ローカルマシンは NAT の背後にあります。クラウドからプッシュすることはできません。しかし、クラウドには到達できます。プルでリポジトリを手元に持ってきます。

**フルサイクル:** 開発環境で作成 → クラウドにプッシュ → 本番環境でプル → `--up`。1つのリポジトリ、どのマシンでも、どのクラウドでも。

> スケジュール設定、自動バックアップ、リストア: [バックアップとリストア](/en/docs/backup-restore)。

---

## プロキシと SSL

### 1. インフラ設定

```bash
rdc config infra set -m my-server  # 設定: ベースドメイン、パブリック IP、ポート範囲
rdc config infra show -m my-server  # 設定を確認
rdc config infra push -m my-server  # プロキシ設定をリモートにプッシュ
```

**ルーティングの仕組み:**
- Traefik は `rediacc.service_name` と `rediacc.service_port` ラベルを通じてコンテナを自動検出します
- ルート: `{service}-{networkId}.{baseDomain}` → コンテナ IP:ポート
- SSL: Cloudflare DNS-01 チャレンジ経由の Let's Encrypt（自動更新、ワイルドカード証明書）

### 2. プロキシテンプレート

```bash
rdc repo template apply --name proxy -m my-server -r infra  # リポジトリにプロキシをデプロイ
rdc repo up --name infra -m my-server  # Traefik を起動
```

Traefik がこのマシン上のすべてのリポジトリに外部トラフィックをルーティングします。すべてのコンテナが自動的に HTTPS エンドポイントを取得します。

```bash
# https://my-app.example.com にアクセス → コンテナにルーティング
# データベース用の TCP/UDP フォワーディング:
#   rediacc.tcp_ports=3306,5432 → 自動割り当ての外部ポート
```

> ルーティングルール、DNS、TLS 設定: [ネットワーキング](/en/docs/networking)。

---

## 次のステップ

- **[移行ガイド](/en/docs/migration)** - 既存のプロジェクトを Rediacc リポジトリに移行
- **[モニタリング](/en/docs/monitoring)** - マシンの健全性、コンテナ、サービス、診断
- **[CLI リファレンス](/en/docs/cli-application)** - 完全なコマンドリファレンス
- **[チートシート](/en/docs/rdc-cheat-sheet)** - コマンドのクイックリファレンス
- **[トラブルシューティング](/en/docs/troubleshooting)** - よくある問題の解決策
- **[Rediacc のルール](/en/docs/rules-of-rediacc)** - Rediaccfile のベストプラクティスとデプロイメントチェックリスト
