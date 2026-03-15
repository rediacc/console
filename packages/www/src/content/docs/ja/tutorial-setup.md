---
title: "マシンセットアップ"
description: "構成プロファイルの作成、リモートマシンの登録、SSH接続の検証、インフラストラクチャ設定の構成を行います。"
category: "Tutorials"
order: 2
language: ja
sourceHash: "04756cddd86e097c"
---

# Rediaccでマシンをセットアップする方法

すべてのRediaccデプロイは、構成プロファイルと登録済みマシンから始まります。このチュートリアルでは、構成の作成、リモートサーバーの登録、SSH接続の検証、環境診断の実行、インフラストラクチャネットワークの構成を行います。完了すると、マシンはリポジトリのデプロイに対応できる状態になります。

## 前提条件

- `rdc` CLIがインストール済み
- SSH経由でアクセス可能なリモートサーバー（またはローカルVM）
- サーバーに認証できるSSH秘密鍵

## インタラクティブ録画

![チュートリアル: マシンセットアップと構成](/assets/tutorials/setup-tutorial.cast)

### ステップ1: 新しい構成を作成

構成プロファイルは、マシン定義、SSH認証情報、インフラストラクチャ設定を保存します。この環境用に1つ作成します。

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

これにより、`~/.config/rediacc/tutorial-demo.json`に名前付き構成ファイルが作成されます。

### ステップ2: 構成を表示

新しいプロファイルが構成リストに表示されることを確認します。

```bash
rdc config list
```

利用可能なすべての構成を、アダプタータイプ（ローカルまたはクラウド）とマシン数とともに一覧表示します。

### ステップ3: マシンを追加

IPアドレスとSSHユーザーを指定してマシンを登録します。CLIは`ssh-keyscan`を介してサーバーのホストキーを自動的に取得・保存します。

```bash
rdc config machine add bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### ステップ4: マシンを表示

マシンが正しく登録されたことを確認します。

```bash
rdc config machine list --config tutorial-demo
```

現在の構成内のすべてのマシンを接続情報とともに表示します。

### ステップ5: デフォルトマシンを設定

デフォルトマシンを設定すると、すべてのコマンドで`-m bridge-vm`を繰り返す必要がなくなります。

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### ステップ6: 接続をテスト

何かをデプロイする前に、マシンがSSH経由でアクセス可能であることを確認します。

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

両方のコマンドはリモートマシンで実行され、すぐに結果を返します。どちらかが失敗した場合は、SSHキーが正しいこととサーバーにアクセスできることを確認してください。

### ステップ7: 診断を実行

```bash
rdc doctor
```

ローカル環境を確認します: CLIバージョン、Docker、renetバイナリ、構成ステータス、SSHキー、仮想化の前提条件。各チェックは**OK**、**Warning**、または**Error**を報告します。

### ステップ8: インフラストラクチャを構成

公開サービスの場合、マシンにはネットワーク構成が必要です — 外部IP、ベースドメイン、TLS用の証明書メールアドレス。

```bash
rdc config infra set bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

構成を確認します:

```bash
rdc config infra show bridge-vm
```

生成されたTraefikプロキシ構成を`rdc config infra push bridge-vm`でサーバーにデプロイします。

## トラブルシューティング

**"SSH key not found"または"Permission denied (publickey)"**
`config init`に渡したキーパスが存在し、サーバーの`authorized_keys`と一致することを確認してください。権限を確認: 秘密鍵ファイルは`600`である必要があります（`chmod 600 ~/.ssh/id_ed25519`）。

**SSHコマンドで"Connection refused"**
サーバーが実行中でIPが正しいことを確認してください。ポート22が開いているか確認: `nc -zv <ip> 22`。非標準ポートを使用している場合は、マシン追加時に`--port`を渡してください。

**"Host key verification failed"**
保存されたホストキーがサーバーの現在のキーと一致しません。これはサーバーの再構築やIPの再割り当て後に発生します。`rdc config machine scan-keys <machine>`を実行してキーを更新してください。

## 次のステップ

構成プロファイルの作成、マシンの登録、接続の検証、インフラストラクチャネットワークの構成が完了しました。アプリケーションをデプロイするには:

- [マシンセットアップ](/ja/docs/setup) — すべての構成およびセットアップコマンドの完全なリファレンス
- [チュートリアル: リポジトリライフサイクル](/ja/docs/tutorial-repos) — リポジトリの作成、デプロイ、管理
- [クイックスタート](/ja/docs/quick-start) — コンテナ化されたアプリケーションをエンドツーエンドでデプロイ
