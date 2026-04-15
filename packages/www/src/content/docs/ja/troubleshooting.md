---
title: "トラブルシューティング"
description: "SSH、セットアップ、リポジトリ、サービス、Dockerに関する一般的な問題の解決策。"
category: "Guides"
order: 10
language: ja
sourceHash: "ee8fe3ee7166cfe4"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# トラブルシューティング

一般的な問題とその解決策です。迷った場合は、まず `rdc doctor` を実行して包括的な診断チェックを行ってください。

## SSH接続の失敗

- 手動で接続できるか確認してください: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- `rdc config machine scan-keys server-1` を実行してホストキーを更新してください
- SSHポートが一致しているか確認してください: `--port 22`
- 簡単なコマンドでテストしてください: `rdc term connect -m server-1 -c "hostname"`

## ホストキーの不一致

サーバーが再インストールされた場合やSSHキーが変更された場合、「host key verification failed」というエラーが表示されます:

```bash
rdc config machine scan-keys -m server-1
```

このコマンドは新しいホストキーを取得し、設定を更新します。

## マシンセットアップの失敗

- SSHユーザーがパスワードなしのsudoアクセスを持っているか確認するか、必要なコマンドに `NOPASSWD` を設定してください
- サーバーの空きディスク容量を確認してください
- `--debug` を付けて詳細な出力を取得してください: `rdc config machine setup server-1 --debug`

## ディストリビューション固有のセットアップ問題

公式サポートされている5つのサーバーOS（Ubuntu 24.04、Debian 13、Fedora 43、openSUSE Leap 16.0、Oracle Linux 10）はそれぞれ異なるセキュリティポリシーとパッケージマネージャーを持っています。ほとんどのセットアップは問題なく動作します。以下は動作しないケースを扱っています。

### SELinuxの拒否 (Fedora 43、Oracle Linux 10)

どちらもSELinuxをenforcing（強制）モードで実行します。rdc setupはカスタムSELinuxポリシーをインストールしません。リポジトリごとのdocker daemonは標準の `container_t` コンテキストで動作します。AVC拒否によりセットアップが失敗した場合は、auditログを確認してドメインを特定してください:

```bash
sudo ausearch -m AVC -ts recent | head -40
# または:
sudo tail -f /var/log/audit/audit.log | grep AVC
```

拒否がrenetバイナリや特定のファイルパスを指している場合、SELinuxを無効化するのではなく、ラベルの再設定（`restorecon -v /path`）で解決できることがほとんどです。調査中の一時的な回避策として、`sudo setenforce 0` でシステムをpermissive（許容）モードにできます。ラベルの再設定が定着したことを確認したら `sudo setenforce 1` で再度有効にしてください。

### AppArmorの拒否 (Ubuntu 24.04、openSUSE Leap 16.0)

どちらもデフォルトでAppArmorを使用しています。リポジトリごとのdocker daemonはデフォルトのコンテナプロファイルを使用します。リポジトリ内のコンテナがブロックされている場合:

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIUがAppArmorに引っかかる既知のケースです。Renetは `rediacc.checkpoint=true` とラベル付けされたコンテナに対して自動的に `security_opt: apparmor=unconfined` を設定します。それ以外についてはAppArmorプロファイルを手動で設定する必要はないはずです。CRIUに関する注意事項は [Rediaccのルール](/en/docs/rules-of-rediacc) を参照してください。

### パッケージマネージャーのエラーシグネチャ

| OS | パッケージマネージャー | 典型的なエラー | 解決策 |
|---|---|---|---|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | オリジンの後ろにあるCloudflareエッジキャッシュの問題です。~15秒後に `apt-get update` を再試行してください。次のポーリングで整合性チェックが通過します。 |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | ディスクにキャッシュされているRPMリポジトリのメタデータが古くなっています。`sudo dnf clean all && sudo dnf makecache` を実行してください。 |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | `sudo zypper refresh rediacc` を一度実行してください。それ以降のインストールは成功するはずです。 |

### btrfsモジュールが見つからない (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

`rdc config machine setup` または `renet system check-btrfs` が次のエラーで失敗する場合:

```
Module btrfs not found
```

...サーバーはRHEL 10の標準カーネルで動作しており、これにはツリー内のbtrfsモジュールが含まれていません。これはRediaccのバグではありません。RHEL 10はbtrfsを意図的に削除しました。解決策は **代わりにOracle Linux 10を使用すること** です。Oracle 10はデフォルトでUnbreakable Enterprise Kernel（UEK）を使用しており、btrfsが維持されています。詳細については [要件 - なぜUEKなのか?](/en/docs/requirements) を参照してください。

## リポジトリの作成失敗

- セットアップが完了しているか確認してください: データストアディレクトリが存在する必要があります
- サーバーのディスク容量を確認してください
- renetバイナリがインストールされているか確認してください（必要に応じてセットアップを再実行してください）

## サービスが起動しない

- Rediaccfileの構文を確認してください: 有効なBashである必要があります
- Rediaccfileが `renet compose --` を使用しているか確認してください（`docker compose` ではなく）
- Dockerイメージにアクセスできるか確認してください（`up()` 内で `renet compose -- pull` の実行を検討してください）
- リポジトリのDockerソケットを使用してコンテナログを確認してください:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
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
rdc term connect -m server-1 -r my-app -c "docker ps"

# またはソケットを手動で指定:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816` をリポジトリのネットワークIDに置き換えてください（`rediacc.json` または `rdc repo status` で確認できます）。

## `docker run` にネットワークがない、`apt update` が失敗する、`curl` がハングする

リポジトリシェル内で `--network host` を付けずにコンテナを実行すると、ループバックインターフェースしか持たず、DNS も外向きの接続性もない分離されたコンテナが得られます。`apt update`、`pip install`、`curl https://...` のようなコマンドや、ネットワーク取得を行うあらゆる処理は、DNS エラーで即座に失敗します。

これは意図的な仕様です。Rediacc のネットワーキングモデルは**すべてのサービスでホストネットワーキングを使用する**というものであり、`renet compose` によって強制されています。NAT 付きの標準的な Docker ブリッジは、あるリポジトリが別のリポジトリのサービスに到達することを防ぐカーネルレベルのループバック分離を迂回してしまうため、リポジトリごとの Docker デーモンは `"bridge": "none"` と `"iptables": false` で構成されており、単純な `docker run` コンテナが接続できるルーティング可能なブリッジは存在しません。

**アドホックなコンテナでネットワークアクセスを得るには、ホストネットワーキングを使用してください:**

```bash
# リポジトリシェル内で（rdc term connect -m <machine> -r <repo>）
docker run --rm --network host -it ubuntu bash
# これで apt update、curl、pip install はすべて動作します。
```

**本番サービスでは、生の `docker run` の代わりに Rediaccfile で `renet compose` を使用してください。** `renet compose` は `network_mode: host`、サービス IP ラベル、Traefik のルーティングラベルを自動的に注入します。詳細は [サービス](/ja/docs/services) を参照してください。

## VS Code でサンドボックスファイルに Permission Denied が出る

`rdc vscode connect -m <machine> -r <repo>` で接続した際、以前の VS Code セッションの後に `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` のようなエラーが出たことがあるかもしれません。これはサンドボックスディレクトリ内のファイル所有権が混在していたことが原因で、SSH ユーザーと内部の `rediacc` ユーザーの両方によって書かれたファイルが含まれていました。

最近のバージョンの renet は、以下の方法でこれを修正しています:

- リポジトリごとのサンドボックスワークスペース（`/mnt/rediacc/.interim/sandbox/<repo>/`）を、グループ `rediacc` と set-group-ID ビット（モード `2775`）付きで作成するため、配下に書かれるすべてのファイルは正しいグループを継承します。
- サンドボックスランタイム内で umask `002` を適用し、新しいファイルがグループ書き込み可能（`0664`/`0775`）で作成されるようにします。
- 起動時に既存の `.vscode-server/` サブツリーを正規化するため、修正前からある古いファイルが自動的に修復されます。

それでもパーミッションエラーが発生する場合は、マシン上のシェルから一度 `sudo systemctl restart rediacc-docker-<network-id>` でリポジトリの Docker デーモンを再起動して正規化パスを走らせてから、再度 `rdc vscode connect` を試してください。

## renet のアップグレード後にデーモンが起動しない

`renet daemon start-foreground` は起動のたびに、リポジトリの設定ディレクトリ内の `daemon.json` と `containerd.toml` を現在のテンプレートから書き換えるため、古いバージョンの renet で生成された設定を持つリポジトリも新しいフォーマットを自動的に取り込みます。マイグレーションコマンドを実行する必要はなく、systemd ユニットを手動で再生成する必要もありません。サービスを再起動するだけです:

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

それでもユニットが起動に失敗する場合は、ジャーナルで具体的なエラーを確認してください:

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## 間違ったDocker daemonにコンテナが作成される

コンテナがリポジトリの分離されたdaemonではなくホストシステムのDocker daemonに表示される場合、最も一般的な原因はRediaccfile内での `sudo docker` の使用です。

`sudo` は環境変数をリセットするため、`DOCKER_HOST` が失われ、Dockerはシステムソケット（`/var/run/docker.sock`）をデフォルトで使用します。Rediaccはこれを自動的にブロックしますが、発生した場合:

- **`docker` を直接使用してください**, Rediaccfileの関数は既に十分な権限で実行されています
- sudoを使用する必要がある場合は、`sudo -E docker` を使用して環境変数を保持してください
- Rediaccfileで `sudo docker` コマンドがないか確認し、`sudo` を削除してください

## ターミナルが動作しない

`rdc term` がターミナルウィンドウを開けない場合:

- `-c` を使用してインラインモードでコマンドを直接実行してください:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- インラインモードに問題がある場合は `--external` で外部ターミナルを強制してください
- Linuxでは、`gnome-terminal`、`xterm`、またはその他のターミナルエミュレータがインストールされていることを確認してください

## 診断の実行

```bash
rdc doctor
```

このコマンドは環境、renetのインストール状況、設定、認証ステータスをチェックします。各チェックはOK、Warning、またはErrorを簡単な説明付きで報告します。
