---
title: "インストール後の設定"
description: "Rediaccの自動開始設定、コンテキスト構造、トラブルシューティング。"
category: "Getting Started"
order: 3
language: ja
---

# インストール後の設定

[ステップバイステップガイド](/ja/docs/guide)を完了した後、このページでは自動開始の設定、コンテキスト設定ファイルの理解、よくある問題のトラブルシューティングについて説明します。

## 起動時の自動開始

デフォルトでは、サーバー再起動後にリポジトリを手動でマウントして開始する必要があります。**自動開始**を設定すると、サーバー起動時にリポジトリを自動的にマウントし、Dockerを起動し、Rediaccfileの`up()`を実行するように構成できます。

### 仕組み

リポジトリの自動開始を有効にすると：

1. 256バイトのランダムなLUKSキーファイルが生成され、リポジトリのLUKSスロット1に追加されます（スロット0はユーザーパスフレーズのまま）。
2. キーファイルは`{datastore}/.credentials/keys/{guid}.key`に`0600`パーミッション（root専用）で保存されます。
3. systemdサービス（`rediacc-autostart`）がインストールされ、起動時にすべての有効なリポジトリをマウントしてサービスを開始します。

システムのシャットダウンまたは再起動時、サービスはすべてのサービスを正常に停止し（Rediaccfileの`down()`）、Dockerデーモンを停止し、LUKSボリュームをクローズします。

> **セキュリティに関する注意：** 自動開始を有効にすると、サーバーのディスクにLUKSキーファイルが保存されます。サーバーへのrootアクセスを持つ者は、パスフレーズなしでリポジトリをマウントできます。これは利便性（自動起動）とセキュリティ（手動パスフレーズ入力の要求）のトレードオフです。脅威モデルに基づいて評価してください。

### 自動開始の有効化

```bash
rdc repo autostart enable my-app -m server-1
```

リポジトリのパスフレーズの入力を求められます。これは、LUKSボリュームへのキーファイルの追加を承認するために必要です。

### すべてのリポジトリの自動開始を有効化

```bash
rdc repo autostart enable-all -m server-1
```

### 自動開始の無効化

```bash
rdc repo autostart disable my-app -m server-1
```

これによりキーファイルが削除され、LUKSスロット1が無効化されます。リポジトリは起動時に自動マウントされなくなります。

### 自動開始ステータスの一覧表示

```bash
rdc repo autostart list -m server-1
```

どのリポジトリで自動開始が有効になっているか、systemdサービスがインストールされているかどうかを表示します。

## コンテキスト設定の理解

すべてのコンテキスト設定は`~/.rediacc/config.json`に保存されます。ガイドを完了した後のこのファイルの注釈付きの例を以下に示します：

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**主要なフィールド：**

| フィールド | 説明 |
|-------|-------------|
| `mode` | ローカルモードは`"local"`、S3バックドコンテキストは`"s3"`。 |
| `apiUrl` | `"local://"`はローカルモード（リモートAPIなし）を示します。 |
| `ssh.privateKeyPath` | すべてのマシン接続に使用されるSSH秘密鍵のパス。 |
| `machines.<name>.knownHosts` | `ssh-keyscan`からのSSHホスト鍵。サーバーIDの検証に使用されます。 |
| `repositories.<name>.repositoryGuid` | サーバー上の暗号化ディスクイメージを識別するUUID。 |
| `repositories.<name>.credential` | LUKS暗号化パスフレーズ。**サーバーには保存されません。** |
| `repositories.<name>.networkId` | IPサブネットを決定するネットワークID（2816 + n*64）。自動割り当て。 |

> このファイルには機密データ（SSH鍵パス、LUKSクレデンシャル）が含まれています。`0600`パーミッション（所有者のみ読み書き可能）で保存されます。共有したり、バージョン管理にコミットしないでください。

## トラブルシューティング

### SSH接続の失敗

- 手動で接続できることを確認：`ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- `rdc context scan-keys server-1`を実行してホスト鍵を更新
- SSHポートが一致していることを確認：`--port 22`

### マシンセットアップの失敗

- ユーザーがパスワードなしでsudoアクセスできることを確認するか、必要なコマンドに対して`NOPASSWD`を設定
- サーバーの空きディスク容量を確認
- `--debug`で詳細出力を有効にして実行：`rdc context setup-machine server-1 --debug`

### リポジトリ作成の失敗

- セットアップが完了していることを確認：データストアディレクトリが存在する必要があります
- サーバーのディスク容量を確認
- renetバイナリがインストールされていることを確認（必要に応じてセットアップを再実行）

### サービスの起動失敗

- Rediaccfileの構文を確認：有効なBashである必要があります
- `docker compose`ファイルで`network_mode: host`が使用されていることを確認
- Dockerイメージにアクセスできることを確認（`prep()`で`docker compose pull`の使用を検討）
- コンテナログを確認：サーバーにSSHし、`docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`を使用

### 権限拒否エラー

- リポジトリ操作にはサーバー上のrootが必要です（renetは`sudo`経由で実行されます）
- ユーザーが`sudo`グループに所属していることを確認
- データストアディレクトリのパーミッションが正しいことを確認

### 診断の実行

組み込みのdoctorコマンドを使用して問題を診断します：

```bash
rdc doctor
```

これにより、環境、renetのインストール、コンテキスト設定、認証ステータスが確認されます。
