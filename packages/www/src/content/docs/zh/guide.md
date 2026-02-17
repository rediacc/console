---
title: "分步指南"
description: "使用 Rediacc 本地模式在您自己的服务器上部署加密隔离基础设施。"
category: "Guides"
order: 2
language: zh
---

# 分步指南

本指南将引导您使用 Rediacc 的**本地模式**在您自己的服务器上部署加密、隔离的基础设施。完成本指南后，您将拥有一个在远程机器上运行容器化服务的完整仓库，所有操作均从您的工作站进行管理。

本地模式意味着一切运行在您控制的基础设施上。无需云账户，无需 SaaS 依赖。您的工作站通过 SSH 编排远程服务器，所有状态存储在您的本地机器和服务器上。

## 架构概述

Rediacc 采用双工具架构：

```
您的工作站                          远程服务器
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** 运行在您的工作站上（macOS 或 Linux）。它读取您的本地配置，通过 SSH 连接到远程机器，并调用 renet 命令。
- **renet** 以 root 权限运行在远程服务器上。它管理 LUKS 加密磁盘映像、隔离的 Docker 守护进程、服务编排和反向代理配置。

您在本地输入的每条命令都会转化为一个 SSH 调用，在远程机器上执行 renet。您无需手动 SSH 登录服务器。

## 步骤 1：创建本地上下文

**上下文**是一个命名配置，用于存储您的 SSH 凭据、机器定义和仓库映射。可以将其理解为一个项目工作区。

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `--ssh-key <path>` | 是 | SSH 私钥路径。波浪号（`~`）会自动展开。 |
| `--renet-path <path>` | 否 | 远程机器上 renet 二进制文件的自定义路径。默认为标准安装位置。 |

此命令创建一个名为 `my-infra` 的本地上下文，并将其存储在 `~/.rediacc/config.json` 中。

> 您可以拥有多个上下文（例如 `production`、`staging`、`dev`）。在任何命令上使用 `--context` 标志在它们之间切换。

## 步骤 2：添加机器

将您的远程服务器注册为上下文中的机器：

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| 选项 | 必填 | 默认值 | 描述 |
|------|------|--------|------|
| `--ip <address>` | 是 | - | 远程服务器的 IP 地址或主机名。 |
| `--user <username>` | 是 | - | 远程服务器上的 SSH 用户名。 |
| `--port <port>` | 否 | `22` | SSH 端口。 |
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上 Rediacc 存储加密仓库的路径。 |

添加机器后，rdc 会自动运行 `ssh-keyscan` 获取服务器的主机密钥。您也可以手动运行：

```bash
rdc context scan-keys server-1
```

查看所有已注册的机器：

```bash
rdc context machines
```

## 步骤 3：设置机器

为远程服务器安装所有必需的依赖项：

```bash
rdc context setup-machine server-1
```

此命令将：
1. 通过 SFTP 将 renet 二进制文件上传到服务器
2. 安装 Docker、containerd 和 cryptsetup（如果尚未安装）
3. 创建数据存储目录并为加密仓库做准备

| 选项 | 必填 | 默认值 | 描述 |
|------|------|--------|------|
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上的数据存储目录。 |
| `--datastore-size <size>` | 否 | `95%` | 分配给数据存储的可用磁盘空间比例。 |
| `--debug` | 否 | `false` | 启用详细输出以进行故障排除。 |

> 每台机器只需运行一次设置。如果需要，可以安全地重新运行。

## 步骤 4：创建仓库

**仓库**是远程服务器上的一个 LUKS 加密磁盘映像。挂载后，它提供：
- 应用数据的隔离文件系统
- 专用的 Docker 守护进程（与主机的 Docker 分离）
- 在 /26 子网内为每个服务分配唯一的回环 IP

创建仓库：

```bash
rdc repo create my-app -m server-1 --size 10G
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `-m, --machine <name>` | 是 | 将要创建仓库的目标机器。 |
| `--size <size>` | 是 | 加密磁盘映像的大小（例如 `5G`、`10G`、`50G`）。 |

输出将显示三个自动生成的值：

- **仓库 GUID** -- 用于在服务器上标识加密磁盘映像的 UUID。
- **凭据** -- 用于加密/解密 LUKS 卷的随机密码短语。
- **网络 ID** -- 一个整数（从 2816 开始，每次递增 64），用于确定此仓库服务的 IP 子网。

> **请安全存储凭据。**它是您仓库的加密密钥。如果丢失，数据将无法恢复。凭据存储在您的本地 `config.json` 中，但不会存储在服务器上。

## 步骤 5：Rediaccfile

**Rediaccfile** 是一个 Bash 脚本，用于定义服务的准备、启动和停止方式。它是服务生命周期管理的核心机制。

### 什么是 Rediaccfile？

Rediaccfile 是一个纯 Bash 脚本，最多包含三个函数：`prep()`、`up()` 和 `down()`。文件必须命名为 `Rediaccfile` 或 `rediaccfile`（不区分大小写），并放置在仓库的已挂载文件系统中。

Rediaccfile 在两个位置被发现：
1. 仓库挂载路径的**根目录**
2. 挂载路径的**第一级子目录**（不递归）

隐藏目录（名称以 `.` 开头）将被跳过。

### 生命周期函数

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

`{SERVICE}_IP` 变量从 `.rediacc.json` 自动生成（见步骤 6）。命名规则是将服务名称转换为大写，连字符替换为下划线，然后追加 `_IP`。例如，`listmonk-app` 变为 `LISTMONK_APP_IP`。

### Rediaccfile 示例

一个简单的 Web 应用 Rediaccfile：

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### 多服务示例

对于包含多个独立服务组的项目，使用子目录：

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # 根目录：共享设置（例如创建 Docker 网络）
├── docker-compose.yml       # 根 compose 文件
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

## 步骤 6：服务网络（.rediacc.json）

每个仓库获得一个 /26 子网（64 个 IP），位于 `127.x.x.x` 回环地址范围内。服务绑定到唯一的回环 IP，因此它们可以使用相同的端口而不会冲突。例如，两个 PostgreSQL 实例可以都监听 5432 端口，各自使用不同的 IP。

### .rediacc.json 文件

`.rediacc.json` 文件将服务名称映射到**槽位**编号。每个槽位对应仓库子网内的一个唯一 IP 地址。

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

服务按字母顺序排列。

### 从 Docker Compose 自动生成

您无需手动创建 `.rediacc.json`。当您运行 `rdc repo up` 时，Rediacc 会自动：

1. 扫描所有包含 Rediaccfile 的目录中的 compose 文件（`docker-compose.yml`、`docker-compose.yaml`、`compose.yml` 或 `compose.yaml`）。
2. 从每个 compose 文件的 `services:` 部分提取服务名称。
3. 为任何新服务分配下一个可用槽位。
4. 将结果保存到 `{repository}/.rediacc.json`。

### IP 计算

服务的 IP 根据仓库的网络 ID 和服务的槽位计算。网络 ID 分布在 `127.x.y.z` 回环地址的第二、第三和第四个八位组中。每个服务会在网络 ID 的基础上加上 `slot + 2` 的偏移量（偏移量 0 和 1 保留给网络地址和网关）。

例如，当网络 ID 为 `2816`（`0x0B00`）时，基础地址为 `127.0.11.0`，服务从 `127.0.11.2` 开始。

**示例**：网络 ID 为 `2816` 时：

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

`${POSTGRES_IP}` 和 `${API_IP}` 变量在 Rediaccfile 运行时从 `.rediacc.json` 自动导出。

## 步骤 7：启动服务

挂载仓库并启动所有服务：

```bash
rdc repo up my-app -m server-1 --mount
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `-m, --machine <name>` | 是 | 目标机器。 |
| `--mount` | 否 | 如果尚未挂载，则先挂载仓库。不使用此标志时，仓库必须已经挂载。 |
| `--prep-only` | 否 | 仅运行 `prep()` 函数，跳过 `up()`。适用于预拉取镜像或运行迁移。 |

执行顺序为：

1. 挂载 LUKS 加密仓库（如果指定了 `--mount`）
2. 为此仓库启动隔离的 Docker 守护进程
3. 从 compose 文件自动生成 `.rediacc.json`
4. 按 A-Z 顺序在所有 Rediaccfile 中运行 `prep()`（快速失败）
5. 按 A-Z 顺序在所有 Rediaccfile 中运行 `up()`

## 步骤 8：停止服务

停止仓库中的所有服务：

```bash
rdc repo down my-app -m server-1
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `-m, --machine <name>` | 是 | 目标机器。 |
| `--unmount` | 否 | 停止服务后卸载加密仓库。这也会停止隔离的 Docker 守护进程并关闭 LUKS 卷。 |

执行顺序为：

1. 按 Z-A 反向顺序在所有 Rediaccfile 中运行 `down()`（尽力而为）
2. 停止隔离的 Docker 守护进程（如果指定了 `--unmount`）
3. 卸载并关闭 LUKS 加密卷（如果指定了 `--unmount`）

## 其他常用操作

### 挂载和卸载（不启动服务）

```bash
rdc repo mount my-app -m server-1     # 解密并挂载
rdc repo unmount my-app -m server-1   # 卸载并重新加密
```

### 检查仓库状态

```bash
rdc repo status my-app -m server-1
```

### 列出所有仓库

```bash
rdc repo list -m server-1
```

### 调整仓库大小

```bash
rdc repo resize my-app -m server-1 --size 20G    # 设置为指定大小
rdc repo expand my-app -m server-1 --size 5G      # 在当前大小基础上增加 5G
```

### 删除仓库

```bash
rdc repo delete my-app -m server-1
```

> 此操作将永久销毁加密磁盘映像及其中的所有数据。

### 复刻仓库

创建现有仓库当前状态的副本：

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

此命令创建一个具有独立 GUID 和网络 ID 的新加密副本。复刻仓库与源仓库共享相同的 LUKS 凭据。

### 验证仓库

检查仓库的文件系统完整性：

```bash
rdc repo validate my-app -m server-1
```

## 完整示例：部署 Web 应用

这个端到端示例部署一个包含 PostgreSQL、Redis 和 API 服务器的 Web 应用。

### 1. 设置环境

```bash
# 安装 rdc
curl -fsSL https://get.rediacc.com | sh

# 创建本地上下文
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# 注册您的服务器
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# 配置服务器
rdc context setup-machine prod-1

# 创建加密仓库（10 GB）
rdc repo create webapp -m prod-1 --size 10G
```

### 2. 挂载并准备仓库

```bash
rdc repo mount webapp -m prod-1
```

通过 SSH 登录服务器，在已挂载的仓库中创建应用文件。挂载路径显示在输出中（通常为 `/mnt/rediacc/repos/{guid}`）。

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
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
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
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. 启动所有服务

```bash
rdc repo up webapp -m prod-1
```

此命令将：
1. 自动生成 `.rediacc.json`，为 `api`、`postgres` 和 `redis` 分配槽位
2. 运行 `prep()` 创建目录并拉取镜像
3. 运行 `up()` 启动所有容器

### 5. 启用开机自启

```bash
rdc repo autostart enable webapp -m prod-1
```

服务器重启后，仓库将自动挂载并启动所有服务。
