---
title: "トラブルシューティング"
description: "SSH、セットアップ、リポジトリ、サービス、Dockerに関する一般的な問題の解決策。"
category: "Guides"
order: 10
language: ja
---

# トラブルシューティング

一般的な問題とその解決策です。迷った場合は、まず `rdc doctor` を実行して包括的な診断チェックを行ってください。

## SSH接続の失敗

- 手動で接続できるか確認してください: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- `rdc context scan-keys server-1` を実行してホストキーを更新してください
- SSHポートが一致しているか確認してください: `--port 22`
- 接続をテストしてください: `rdc machine test-connection --ip 203.0.113.50 --user deploy`

## ホストキーの不一致

サーバーが再インストールされた場合やSSHキーが変更された場合、「host key verification failed」というエラーが表示されます:

```bash
rdc context scan-keys server-1
```

このコマンドは新しいホストキーを取得し、設定を更新します。

## マシンセットアップの失敗

- SSHユーザーがパスワードなしのsudoアクセスを持っているか確認するか、必要なコマンドに `NOPASSWD` を設定してください
- サーバーの空きディスク容量を確認してください
- `--debug` を付けて詳細な出力を取得してください: `rdc context setup-machine server-1 --debug`

## リポジトリの作成失敗

- セットアップが完了しているか確認してください: データストアディレクトリが存在する必要があります
- サーバーのディスク容量を確認してください
- renetバイナリがインストールされているか確認してください（必要に応じてセットアップを再実行してください）

## サービスが起動しない

- Rediaccfileの構文を確認してください: 有効なBashである必要があります
- `docker compose` ファイルが `network_mode: host` を使用しているか確認してください
- Dockerイメージにアクセスできるか確認してください（`prep()` 内で `docker compose pull` の実行を検討してください）
- リポジトリのDockerソケットを使用してコンテナログを確認してください:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
```

または全てのコンテナを表示:

```bash
rdc machine containers server-1
```

## 権限拒否エラー

- リポジトリ操作にはサーバーでのroot権限が必要です（renetは `sudo` で実行されます）
- SSHユーザーが `sudo` グループに所属しているか確認してください
- データストアディレクトリに正しいパーミッションが設定されているか確認してください

## Dockerソケットの問題

各リポジトリには独自のDocker daemonがあります。Dockerコマンドを手動で実行する場合、正しいソケットを指定する必要があります:

```bash
# rdc termを使用（自動設定済み）:
rdc term server-1 my-app -c "docker ps"

# またはソケットを手動で指定:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816` をリポジトリのネットワークIDに置き換えてください（`config.json` または `rdc repo status` で確認できます）。

## 間違ったDocker daemonにコンテナが作成される

コンテナがリポジトリの分離されたdaemonではなくホストシステムのDocker daemonに表示される場合、最も一般的な原因はRediaccfile内での `sudo docker` の使用です。

`sudo` は環境変数をリセットするため、`DOCKER_HOST` が失われ、Dockerはシステムソケット（`/var/run/docker.sock`）をデフォルトで使用します。Rediaccはこれを自動的にブロックしますが、発生した場合:

- **`docker` を直接使用してください** — Rediaccfileの関数は既に十分な権限で実行されています
- sudoを使用する必要がある場合は、`sudo -E docker` を使用して環境変数を保持してください
- Rediaccfileで `sudo docker` コマンドがないか確認し、`sudo` を削除してください

## ターミナルが動作しない

`rdc term` がターミナルウィンドウを開けない場合:

- `-c` を使用してインラインモードでコマンドを直接実行してください:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- インラインモードに問題がある場合は `--external` で外部ターミナルを強制してください
- Linuxでは、`gnome-terminal`、`xterm`、またはその他のターミナルエミュレータがインストールされていることを確認してください

## 診断の実行

```bash
rdc doctor
```

このコマンドは環境、renetのインストール状況、コンテキスト設定、認証ステータスをチェックします。各チェックはOK、Warning、またはErrorを簡単な説明付きで報告します。
