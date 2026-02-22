---
title: "サーバーリファレンス"
description: "リモートサーバーのディレクトリ構成、renetコマンド、systemdサービス、ワークフロー。"
category: "Concepts"
order: 3
language: ja
sourceHash: "fdfadf580c39b1fe"
---

# サーバーリファレンス

このページでは、RediaccサーバーにSSH接続した際に見つかるものについて説明します：ディレクトリ構成、`renet`コマンド、systemdサービス、および一般的なワークフロー。

ほとんどのユーザーはワークステーションから`rdc`を通じてサーバーを管理するため、このページを参照する必要はありません。高度なデバッグやサーバー上で直接作業する必要がある場合のためのリファレンスです。

上位レベルのアーキテクチャについては、[アーキテクチャ](/ja/docs/architecture)を参照してください。`rdc`と`renet`の違いについては、[rdc vs renet](/ja/docs/rdc-vs-renet)を参照してください。

## ディレクトリ構成

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── interim/                           # Docker overlay2 data (per-repo)
│   └── {uuid}/docker/data/
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # BASE_DOMAIN, CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/docker-{id}/          # Per-network daemon data
/var/lib/rediacc/router/               # Router state (port allocations)
```

## renetコマンド

`renet`はサーバーサイドのバイナリです。すべてのコマンドにroot権限（`sudo`）が必要です。

### リポジトリのライフサイクル

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

特定のリポジトリのDockerデーモンに対してcomposeコマンドを実行します：

```bash
sudo renet compose --network-id {id} -- up -d
sudo renet compose --network-id {id} -- down
sudo renet compose --network-id {id} -- logs -f
sudo renet compose --network-id {id} -- config
```

dockerコマンドを直接実行します：

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

Dockerソケットを直接使用することもできます：

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> `docker-compose.yml`が含まれるディレクトリからcomposeを実行してください。そうしないとDockerがファイルを見つけられません。

### プロキシとルーティング

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

ルートはコンテナラベルから自動的に検出されます。Traefikラベルの設定方法については、[ネットワーキング](/ja/docs/networking)を参照してください。

### システムステータス

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### デーモン管理

各リポジトリは独自のDockerデーモンを実行します。個別に管理できます：

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### バックアップとリストア

別のマシンまたはクラウドストレージにバックアップをプッシュします：

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> ほとんどのユーザーは代わりに`rdc backup push/pull`を使用すべきです。`rdc`コマンドは資格情報とマシンの解決を自動的に処理します。

### チェックポイント (CRIU)

チェックポイントは実行中のコンテナの状態を保存し、後でリストアできるようにします：

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### メンテナンス

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## systemdサービス

各リポジトリは以下のsystemdユニットを作成します：

| ユニット | 目的 |
|------|---------|
| `rediacc-docker-{id}.service` | 分離されたDockerデーモン |
| `rediacc-docker-{id}.socket` | Docker APIソケットアクティベーション |
| `rediacc-loopback-{id}.service` | ループバックIPエイリアスの設定 |

すべてのリポジトリで共有されるグローバルサービス：

| ユニット | 目的 |
|------|---------|
| `rediacc-router.service` | ルート検出（ポート7111） |
| `rediacc-autostart.service` | 起動時のリポジトリマウント |

## 一般的なワークフロー

### 新しいサービスのデプロイ

1. 暗号化されたリポジトリを作成：
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. マウントして`docker-compose.yml`、`Rediaccfile`、`.rediacc.json`ファイルを追加します。
3. 起動：
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### 実行中のコンテナにアクセス

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### コンテナを実行しているDockerソケットの特定

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### 設定変更後のサービス再作成

```bash
sudo renet compose --network-id {id} -- up -d
```

`docker-compose.yml`が含まれるディレクトリから実行してください。変更されたコンテナは自動的に再作成されます。

### すべてのデーモンにわたるコンテナの確認

```bash
renet list containers
```

## ヒント

- `renet compose`、`renet repository`、`renet docker`コマンドには常に`sudo`を使用してください。LUKSおよびDockerの操作にroot権限が必要です
- `renet compose`および`renet docker`に引数を渡す前に`--`セパレーターが必要です
- `docker-compose.yml`が含まれるディレクトリからcomposeを実行してください
- `.rediacc.json`のスロット割り当ては固定です。デプロイ後に変更しないでください
- `/run/rediacc/docker-{id}.sock`パスを使用してください（systemdがレガシーの`/var/run/`パスを変更する場合があります）
- 孤立したリソースを見つけるために、定期的に`renet prune --dry-run`を実行してください
- BTRFSスナップショット（`renet backup`）は高速で低コストです。リスクのある変更の前に使用してください
- リポジトリはLUKS暗号化されています。パスワードを紛失するとデータも失われます
