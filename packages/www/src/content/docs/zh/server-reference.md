---
title: "服务器参考"
description: "远程服务器的目录布局、renet 命令、systemd 服务和工作流。"
category: "Concepts"
tags:
  - operations
  - cli
subcategory: architecture
order: 3
language: zh
sourceHash: "334e3ab3d1d1cce9"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
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
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
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
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
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

### 文件系统沙箱

```bash
# 检查 Landlock 支持
renet sandbox-exec --detect

# 在 Landlock 沙箱中运行命令（内部使用）
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` 会应用 Landlock LSM 文件系统限制，然后执行指定的命令。它由 `sandbox-gateway`（SSH ForceCommand 处理程序）自动调用，用于所有仓库级别的连接。

### 每用户 Hub（开发环境）

Hub 为每个用户提供其独立的 Docker 守护进程用于开发环境，与每个仓库的 `FlavorRediacc` 守护进程相互独立。

```bash
# 安装 / 卸载每用户 Hub systemd 单元
sudo renet hub install
sudo renet hub uninstall

# 回收空闲的每用户 Hub 守护进程
sudo renet hub gc
```

守护进程以两种 flavor 之一运行，通过 `--flavor` 选择：

```bash
# 每仓库隔离守护进程（bridge=none，iptables=false）— 默认
sudo renet daemon start-foreground --flavor=rediacc ...

# 每用户 Hub 守护进程（bridge=docker0，iptables=true，live-restore=true）
sudo renet daemon start-foreground --flavor=hub ...
```

`hub` flavor 启用普通桥接网络，使用户运行的容器具有出站连接能力；`rediacc` flavor 强制执行仓库间的 loopback 隔离。Hub 审计日志写入 `/var/log/rediacc/hub/<user>.log`。

**标志：**
- `--allow-rw`、`--allow-ro`、`--allow-exec`：Landlock 路径规则
- `--home-overlay`：在主目录上挂载 OverlayFS，实现每个仓库的写入隔离
- `--sandbox-dir`：每个仓库的工作区（`<datastore>/.interim/sandbox/<name>/`）
- `--work-dir`：设置工作目录并加载仓库环境的 `.envrc`
- `--run-as`：设置完成后将权限降至目标用户
- `--reset-home`：清除每个仓库的主目录覆盖层以全新启动

**`sandbox-gateway`** 是通过 `authorized_keys` 中的 `command=` 设置的 SSH ForceCommand 处理程序。每个仓库的 SSH 密钥会以内置的仓库名称触发网关，客户端无法伪造。网关构建 sandbox-exec 参数并通过 sudo 执行。

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

> 大多数用户应改用 `rdc repo push/pull`。`rdc` 命令会自动处理凭据和机器解析。

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

### 数据存储后端（Ceph RBD）

数据存储要么是本地的（机器磁盘上基于 loop 设备的 BTRFS，默认），要么通过 RBD 镜像由外部 Ceph 集群支持。后端在初始化时选择：

```bash
# 本地后端（默认）
renet datastore init --size 50G

# Ceph RBD 后端：BTRFS 建立在从外部 Ceph 集群映射的 RBD 镜像之上
renet datastore init --backend ceph --pool rbd --image {name} --cluster ceph
```

在 Ceph 后端上，fork 和 unfork 使用 RBD 自身的写时复制原语，而不是 BTRFS reflink：

```bash
renet datastore fork   --source {image} --target {new-image}   # RBD snapshot -> protect -> clone
renet datastore unfork --image {image}                         # 按依赖顺序拆解克隆
```

Ceph 节点从不打开 LUKS（此后端没有按镜像的 LUKS 层），因此它们的内存占用取决于 Ceph 守护进程的调优（`osd_memory_target`），而非 KDF 的计算。第二个客户端可以以只读方式映射同一个 RBD 镜像，并叠加一个本地写时复制覆盖层，这就是以读为主的横向扩展路径。

### Kubernetes（renet kube）

在集群节点上，renet 以包装 Docker 的方式包装 k3s。`renet kube` 是 compose 的类比：它注入 `KUBECONFIG`，并从 Rediaccfile 的 `up()` 中应用清单或 Helm chart。

```bash
sudo renet kube apply -f manifests/     # 应用到仓库的命名空间
sudo renet kube -- get pods             # 透传到固定命名空间中的 kubectl
```

集群状态存储在由数据存储支持的写时复制镜像中（k3s 的 `--data-dir` 绑定在镜像挂载点内部），这正是整个集群能够 fork 和迁移的原因。持久卷是独立的写时复制单元：Ceph 上的 RBD 镜像（每个集群实例和每次 fork 各有一个 RADOS 命名空间），或在本地后端通过本地 PV 供应器提供的小型数据存储镜像文件。面向用户的工作流在 [Kubernetes](/en/docs/kubernetes) 指南中；CLI 通过 `rdc cluster` 和支持集群的 `rdc repo` 命令驱动这些路径。

## Systemd 服务

每个仓库会创建以下 systemd 单元：

| 单元 | 用途 |
|------|------|
| `rediacc-docker-{id}.service` | 隔离的 Docker 守护进程 |
| `rediacc-docker-{id}.socket` | Docker API 套接字激活 |
| `rediacc-loopback-{id}.service` | 回环 IP 别名设置 |
| `rediacc-k3s-{id}.service` | 每集群 k3s 节点（仅限集群主机） |

所有仓库共享的全局服务：

| 单元 | 用途 |
|------|------|
| `rediacc-router.service` | 路由发现（端口 7111） |
| `rediacc-autostart.service` | 启动时自动挂载仓库 |
| `rediacc-autostart-reconcile.service` | 周期性自动启动协调器（由下方定时器运行） |
| `rediacc-autostart-reconcile.timer` | 大约每 3 分钟运行一次 `renet repository reconcile`，以恢复启动后停止的自动启动仓库 |

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
sudo renet compose -- up -d
```

在包含 `docker-compose.yml` 的目录中运行此命令。已更改的容器会自动重新创建。

### 检查所有守护进程中的全部容器

```bash
renet list containers
```

## 提示

- `renet compose`、`renet repository` 和 `renet docker` 命令始终需要使用 `sudo`，它们需要 root 权限来执行 LUKS 和 Docker 操作
- 向 `renet compose` 和 `renet docker` 传递参数前必须使用 `--` 分隔符
- 在包含 `docker-compose.yml` 的目录中运行 compose
- `.rediacc.json` 的槽位分配是稳定的，部署后请勿更改
- 使用 `/run/rediacc/docker-{id}.sock` 路径（systemd 可能会更改旧的 `/var/run/` 路径）
- 定期运行 `renet prune --dry-run` 以查找孤立资源
- BTRFS 快照（`renet backup`）快速且开销低，在进行有风险的更改前使用它们
- 仓库使用 LUKS 加密，丢失密码意味着丢失数据
