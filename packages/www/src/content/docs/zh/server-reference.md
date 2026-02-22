---
title: "服务器参考"
description: "远程服务器的目录布局、renet 命令、systemd 服务和工作流。"
category: "Concepts"
order: 3
language: zh
sourceHash: "fdfadf580c39b1fe"
---

# 服务器参考

本页介绍您通过 SSH 登录到 Rediacc 服务器后所看到的内容：目录布局、`renet` 命令、systemd 服务和常见工作流。

大多数用户从工作站通过 `rdc` 管理服务器，无需参考此页面。本页面用于高级调试或需要直接在服务器上操作的场景。

关于高层架构，请参阅[架构](/zh/docs/architecture)。关于 `rdc` 和 `renet` 的区别，请参阅 [rdc vs renet](/zh/docs/rdc-vs-renet)。

## 目录布局

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

## renet 命令

`renet` 是服务器端的二进制文件。所有命令都需要 root 权限（`sudo`）。

### 仓库生命周期

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

针对特定仓库的 Docker 守护进程运行 compose 命令：

```bash
sudo renet compose --network-id {id} -- up -d
sudo renet compose --network-id {id} -- down
sudo renet compose --network-id {id} -- logs -f
sudo renet compose --network-id {id} -- config
```

直接运行 Docker 命令：

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

您也可以直接使用 Docker 套接字：

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> 请始终在包含 `docker-compose.yml` 的目录中运行 compose，否则 Docker 将找不到该文件。

### 代理和路由

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

路由会从容器标签中自动发现。有关如何配置 Traefik 标签，请参阅[网络](/zh/docs/networking)。

### 系统状态

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### 守护进程管理

每个仓库运行自己的 Docker 守护进程。您可以单独管理它们：

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### 备份与恢复

将备份推送到另一台机器或云存储：

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

> 大多数用户应改用 `rdc backup push/pull`。`rdc` 命令会自动处理凭据和机器解析。

### 检查点 (CRIU)

检查点会保存运行中容器的状态，以便稍后恢复：

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### 维护

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Systemd 服务

每个仓库会创建以下 systemd 单元：

| 单元 | 用途 |
|------|---------|
| `rediacc-docker-{id}.service` | 隔离的 Docker 守护进程 |
| `rediacc-docker-{id}.socket` | Docker API 套接字激活 |
| `rediacc-loopback-{id}.service` | 回环 IP 别名设置 |

所有仓库共享的全局服务：

| 单元 | 用途 |
|------|---------|
| `rediacc-router.service` | 路由发现（端口 7111） |
| `rediacc-autostart.service` | 启动时自动挂载仓库 |

## 常见工作流

### 部署新服务

1. 创建加密仓库：
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. 挂载它并添加 `docker-compose.yml`、`Rediaccfile` 和 `.rediacc.json` 文件。
3. 启动它：
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### 访问运行中的容器

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### 查找运行容器的 Docker 套接字

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### 配置更改后重新创建服务

```bash
sudo renet compose --network-id {id} -- up -d
```

在包含 `docker-compose.yml` 的目录中运行此命令。已更改的容器会自动重新创建。

### 检查所有守护进程中的全部容器

```bash
renet list containers
```

## 提示

- `renet compose`、`renet repository` 和 `renet docker` 命令始终需要使用 `sudo` — 它们需要 root 权限来执行 LUKS 和 Docker 操作
- 向 `renet compose` 和 `renet docker` 传递参数前必须使用 `--` 分隔符
- 在包含 `docker-compose.yml` 的目录中运行 compose
- `.rediacc.json` 的槽位分配是稳定的 — 部署后请勿更改
- 使用 `/run/rediacc/docker-{id}.sock` 路径（systemd 可能会更改旧的 `/var/run/` 路径）
- 定期运行 `renet prune --dry-run` 以查找孤立资源
- BTRFS 快照（`renet backup`）快速且开销低 — 在进行有风险的更改前使用它们
- 仓库使用 LUKS 加密 — 丢失密码意味着丢失数据
