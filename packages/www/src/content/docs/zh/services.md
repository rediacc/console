---
title: 服务
description: 使用 Rediaccfile、服务网络和开机自启来部署和管理容器化服务。
category: Guides
order: 5
language: zh
sourceHash: c4048b13799a7767
---

# 服务

如果你不确定该使用哪个工具，请参考 [rdc vs renet](/zh/docs/rdc-vs-renet)。

本页面介绍如何部署和管理容器化服务：Rediaccfile、服务网络、启动/停止、批量操作和开机自启。

## Rediaccfile

**Rediaccfile** 是一个 Bash 脚本，用于定义服务的准备、启动和停止方式。文件必须命名为 `Rediaccfile` 或 `rediaccfile`（不区分大小写），并放置在仓库的已挂载文件系统中。

Rediaccfile 在两个位置被发现：
1. 仓库挂载路径的**根目录**
2. 挂载路径的**第一级子目录**（不递归）

隐藏目录（名称以 `.` 开头）将被跳过。

### 生命周期函数

一个 Rediaccfile 最多包含三个函数：

| 函数 | 运行时机 | 用途 | 错误行为 |
|------|----------|------|----------|
| `prep()` | 在 `up()` 之前 | 安装依赖、拉取镜像、运行迁移 | **快速失败** -- 如果任何 `prep()` 失败，整个过程立即停止。 |
| `up()` | 所有 `prep()` 完成后 | 启动服务（例如 `docker compose up -d`） | 根 Rediaccfile 失败是**关键性的**（停止一切）。子目录失败是**非关键性的**（记录日志，继续下一个）。 |
| `down()` | 停止时 | 停止服务（例如 `docker compose down`） | **尽力而为** -- 失败会被记录，但所有 Rediaccfile 都会被尝试执行。 |

三个函数都是可选的。如果某个函数未在 Rediaccfile 中定义，它会被静默跳过。

### 执行顺序

- **启动（`up`）：** 先执行根 Rediaccfile，然后按**字母顺序**（A 到 Z）执行子目录。
- **停止（`down`）：** 先按**反向字母顺序**（Z 到 A）执行子目录，最后执行根 Rediaccfile。

### 环境变量

当 Rediaccfile 函数执行时，以下环境变量可用：

| 变量 | 描述 | 示例 |
|------|------|------|
| `REPOSITORY_PATH` | 仓库的挂载路径 | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | 仓库 GUID | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | 网络 ID（整数） | `2816` |
| `DOCKER_HOST` | 此仓库隔离守护进程的 Docker 套接字 | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json` 中定义的每个服务的回环 IP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP` 变量从 `.rediacc.json` 自动生成。命名规则是将服务名称转换为大写，连字符替换为下划线，然后追加 `_IP`。例如，`listmonk-app` 变为 `LISTMONK_APP_IP`。

> **警告：请勿在 Rediaccfile 中使用 `sudo docker`。** `sudo` 命令会重置环境变量，导致 `DOCKER_HOST` 丢失，Docker 命令将指向系统守护进程而非仓库的隔离守护进程。这会破坏容器隔离并可能导致端口冲突。如果 Rediacc 检测到未带 `-E` 的 `sudo docker`，将阻止执行。
>
> 在 Rediaccfile 中请使用 `renet compose` — 它会自动处理 `DOCKER_HOST`，注入路由发现所需的网络标签，并配置服务网络。有关服务如何通过反向代理暴露的详细信息，请参阅[网络](/zh/docs/networking)。如果直接调用 Docker，请使用不带 `sudo` 的 `docker` — Rediaccfile 函数已经拥有足够的权限。如果必须使用 sudo，请使用 `sudo -E docker` 来保留环境变量。

### 示例

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` 也可以使用，因为 `DOCKER_HOST` 会自动设置，但推荐使用 `renet compose`，因为它还会注入反向代理路由发现所需的 `rediacc.*` 标签。详情请参阅[网络](/zh/docs/networking)。

### 多服务布局

对于包含多个独立服务组的项目，使用子目录：

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # 根目录：共享设置
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # 数据库服务
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # API 服务器
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus、Grafana 等
    └── docker-compose.yml
```

`up` 执行顺序：根目录，然后 `backend`、`database`、`monitoring`（A-Z）。
`down` 执行顺序：`monitoring`、`database`、`backend`，然后根目录（Z-A）。

## 服务网络（.rediacc.json）

每个仓库获得一个 /26 子网（64 个 IP），位于 `127.x.x.x` 回环地址范围内。服务绑定到唯一的回环 IP，因此它们可以使用相同的端口而不会冲突。

### .rediacc.json 文件

将服务名称映射到**槽位**编号。每个槽位对应仓库子网内的一个唯一 IP 地址。

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### 从 Docker Compose 自动生成

您无需手动创建 `.rediacc.json`。当您运行 `rdc repo up` 时，Rediacc 会自动：

1. 扫描所有包含 Rediaccfile 的目录中的 compose 文件（`docker-compose.yml`、`docker-compose.yaml`、`compose.yml` 或 `compose.yaml`）。
2. 从每个 compose 文件的 `services:` 部分提取服务名称。
3. 为任何新服务分配下一个可用槽位。
4. 将结果保存到 `{repository}/.rediacc.json`。

### IP 计算

服务的 IP 根据仓库的网络 ID 和服务的槽位计算。网络 ID 分布在 `127.x.y.z` 回环地址的第二、第三和第四个八位组中。每个服务会在网络 ID 的基础上加上 `slot + 2` 的偏移量（偏移量 0 和 1 保留给网络地址和网关）。

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**示例**：网络 ID 为 `2816`（`0x0B00`）时，基础地址为 `127.0.11.0`：

| 服务 | 槽位 | IP 地址 |
|------|------|---------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

每个仓库最多支持 **61 个服务**（槽位 0 到 60）。

### 在 Docker Compose 中使用服务 IP

由于每个仓库运行隔离的 Docker 守护进程，服务使用 `network_mode: host` 并绑定到其分配的回环 IP：

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## 启动服务

挂载仓库并启动所有服务：

```bash
rdc repo up my-app -m server-1 --mount
```

| 选项 | 描述 |
|------|------|
| `--mount` | 如果尚未挂载，则先挂载仓库 |
| `--prep-only` | 仅运行 `prep()` 函数，跳过 `up()` |
| `--skip-router-restart` | Skip restarting the route server after the operation |

执行顺序为：
1. 挂载 LUKS 加密仓库（如果指定了 `--mount`）
2. 为此仓库启动隔离的 Docker 守护进程
3. 从 compose 文件自动生成 `.rediacc.json`
4. 按 A-Z 顺序在所有 Rediaccfile 中运行 `prep()`（快速失败）
5. 按 A-Z 顺序在所有 Rediaccfile 中运行 `up()`

## 停止服务

```bash
rdc repo down my-app -m server-1
```

| 选项 | 描述 |
|------|------|
| `--unmount` | 停止服务后卸载加密仓库 |
| `--skip-router-restart` | Skip restarting the route server after the operation |

执行顺序为：
1. 按 Z-A 反向顺序在所有 Rediaccfile 中运行 `down()`（尽力而为）
2. 停止隔离的 Docker 守护进程（如果指定了 `--unmount`）
3. 卸载并关闭 LUKS 加密卷（如果指定了 `--unmount`）

## 批量操作

一次启动或停止机器上的所有仓库：

```bash
rdc repo up-all -m server-1
```

| 选项 | 描述 |
|------|------|
| `--include-forks` | 包含复刻仓库 |
| `--mount-only` | 仅挂载，不启动容器 |
| `--dry-run` | 显示将要执行的操作 |
| `--parallel` | 并行运行操作 |
| `--concurrency <n>` | 最大并发操作数（默认：3） |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## 开机自启

默认情况下，服务器重启后需要手动挂载和启动仓库。**开机自启**功能可配置仓库在服务器启动时自动挂载、启动 Docker 并运行 Rediaccfile `up()`。

### 工作原理

当您为仓库启用开机自启时：

1. 生成一个 256 字节的随机 LUKS 密钥文件，并添加到仓库的 LUKS 槽位 1（槽位 0 仍为用户密码短语）。
2. 密钥文件存储在 `{datastore}/.credentials/keys/{guid}.key`，权限为 `0600`（仅 root 可读）。
3. 安装一个 systemd 服务（`rediacc-autostart`），在启动时挂载所有已启用的仓库并启动其服务。

在系统关机或重启时，该服务会优雅地停止所有服务（Rediaccfile `down()`）、停止 Docker 守护进程并关闭 LUKS 卷。

> **安全提示：**启用开机自启会将 LUKS 密钥文件存储在服务器磁盘上。任何拥有服务器 root 权限的人都可以在无需密码短语的情况下挂载仓库。请根据您的威胁模型进行评估。

### 启用

```bash
rdc repo autostart enable my-app -m server-1
```

系统将提示您输入仓库密码短语。

### 为所有仓库启用

```bash
rdc repo autostart enable-all -m server-1
```

### 禁用

```bash
rdc repo autostart disable my-app -m server-1
```

此操作将删除密钥文件并清除 LUKS 槽位 1。

### 查看状态

```bash
rdc repo autostart list -m server-1
```

## 完整示例

以下示例部署一个包含 PostgreSQL、Redis 和 API 服务器的 Web 应用。

### 1. 设置环境

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. 挂载并准备

```bash
rdc repo mount webapp -m prod-1
```

### 3. 创建应用文件

在仓库内创建以下文件：

**docker-compose.yml：**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile：**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. 启动

```bash
rdc repo up webapp -m prod-1
```

### 5. 启用开机自启

```bash
rdc repo autostart enable webapp -m prod-1
```
