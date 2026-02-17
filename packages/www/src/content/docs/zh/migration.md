---
title: "迁移指南"
description: "将现有项目迁移到加密的 Rediacc 仓库中。"
category: "Guides"
order: 11
language: zh
---

# 迁移指南

将现有项目（文件、Docker 服务、数据库）从传统服务器或本地开发环境迁移到加密的 Rediacc 仓库中。

## 前提条件

- 已安装 `rdc` CLI（[安装](/zh/docs/installation)）
- 已添加并配置好机器（[设置](/zh/docs/setup)）
- 服务器上有足够的磁盘空间用于您的项目（使用 `rdc machine status` 检查）

## 步骤 1：创建仓库

创建一个大小适合您项目的加密仓库。为 Docker 镜像和容器数据预留额外空间。

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **提示：** 如有需要，您可以稍后使用 `rdc repo resize` 调整大小，但仓库必须先卸载。从一开始就分配足够的空间会更简单。

## 步骤 2：上传文件

使用 `rdc sync upload` 将项目文件传输到仓库中。

```bash
# 预览将要传输的内容（不做任何更改）
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# 上传文件
rdc sync upload -m server-1 -r my-project --local ./my-project
```

上传前仓库必须已挂载。如果尚未挂载：

```bash
rdc repo mount my-project -m server-1
```

对于后续需要远程目录与本地目录完全匹配的同步：

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> `--mirror` 标志会删除远程上本地不存在的文件。请先使用 `--dry-run` 进行验证。

## 步骤 3：修复文件所有权

上传的文件带有您本地用户的 UID（例如 1000）。Rediacc 使用通用用户（UID 7111），以便 VS Code、终端会话和工具都具有一致的访问权限。运行所有权命令进行转换：

```bash
rdc repo ownership my-project -m server-1
```

### Docker 感知排除

如果 Docker 容器正在运行（或曾经运行过），所有权命令会自动检测其可写数据目录并**跳过它们**。这可以防止破坏那些使用不同 UID 管理自有文件的容器（例如，MariaDB 使用 UID 999，Nextcloud 使用 UID 33）。

该命令会报告其操作：

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### 何时运行

- **上传文件后** — 将您的本地 UID 转换为 7111
- **启动容器后** — 如果您希望 Docker 卷目录被自动排除。如果容器尚未启动，则没有需要排除的卷，所有目录都会被更改（这是正常的 — 容器将在首次启动时重新创建其数据）

### 强制模式

要跳过 Docker 卷检测并更改所有内容的所有权，包括容器数据目录：

```bash
rdc repo ownership my-project -m server-1 --force
```

> **警告：** 这可能会破坏正在运行的容器。如有需要，请先使用 `rdc repo down` 停止容器。

### 自定义 UID

要设置默认 7111 以外的 UID：

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## 步骤 4：设置 Rediaccfile

在项目根目录创建一个 `Rediaccfile`。这个 Bash 脚本定义了服务如何准备、启动和停止。

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

三个生命周期函数：

| 函数 | 用途 | 错误行为 |
|------|------|----------|
| `prep()` | 拉取镜像、运行迁移、安装依赖 | 快速失败：任何错误都会停止一切 |
| `up()` | 启动服务 | 根目录失败是致命的；子目录失败会被记录并继续 |
| `down()` | 停止服务 | 尽力而为：始终尝试全部 |

> **重要：** 在 Rediaccfile 中直接使用 `docker` — 绝不要使用 `sudo docker`。`sudo` 命令会重置环境变量，导致 `DOCKER_HOST` 丢失，容器被创建在系统 Docker 守护进程上，而不是仓库的隔离守护进程上。Rediaccfile 函数已经以足够的权限运行。详见 [服务](/zh/docs/services#environment-variables)。

关于 Rediaccfile、多服务布局和执行顺序的完整详情，请参阅 [服务](/zh/docs/services)。

## 步骤 5：配置服务网络

Rediacc 为每个仓库运行一个隔离的 Docker 守护进程。服务使用 `network_mode: host` 并绑定到唯一的环回 IP，以便在仓库之间无冲突地使用标准端口。

### 调整 docker-compose.yml

**之前（传统方式）：**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**之后（Rediacc）：**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

主要更改：

1. **为每个服务添加 `network_mode: host`**
2. **移除 `ports:` 映射**（主机网络模式下不需要）
3. **将服务绑定到 `${SERVICE_IP}` 环境变量**（由 Rediacc 自动注入）
4. **通过 IP 引用其他服务**，而不是 Docker DNS 名称（例如，使用 `${POSTGRES_IP}` 替代 `postgres`）

`{SERVICE}_IP` 变量从 compose 文件的服务名称自动生成。命名约定：大写字母、连字符替换为下划线、加 `_IP` 后缀。例如，`listmonk-app` 变为 `LISTMONK_APP_IP`。

关于 IP 分配和 `.rediacc.json` 的详情，请参阅 [服务网络](/zh/docs/services#service-networking-rediaccjson)。

## 步骤 6：启动服务

挂载仓库（如果尚未挂载）并启动所有服务：

```bash
rdc repo up my-project -m server-1 --mount
```

这将：
1. 挂载加密仓库
2. 启动隔离的 Docker 守护进程
3. 自动生成包含服务 IP 分配的 `.rediacc.json`
4. 执行所有 Rediaccfile 中的 `prep()`
5. 执行所有 Rediaccfile 中的 `up()`

验证您的容器正在运行：

```bash
rdc machine containers server-1
```

## 步骤 7：启用自动启动（可选）

默认情况下，服务器重启后需要手动挂载和启动仓库。启用自动启动以使服务自动运行：

```bash
rdc repo autostart enable my-project -m server-1
```

系统将提示您输入仓库密码短语。

> **安全提示：** 自动启动会在服务器上存储 LUKS 密钥文件。拥有 root 访问权限的任何人都可以在没有密码短语的情况下挂载仓库。详见 [自动启动](/zh/docs/services#autostart-on-boot)。

## 常见迁移场景

### WordPress / PHP 与数据库

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress 文件（运行时 UID 33）
├── database/data/          # MariaDB 数据（运行时 UID 999）
└── wp-content/uploads/     # 用户上传
```

1. 上传项目文件
2. 先启动服务（`rdc repo up`），让容器创建其数据目录
3. 运行所有权修复 — MariaDB 和应用数据目录会自动排除

### Node.js / Python 与 Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # 应用源代码
├── node_modules/           # 依赖
└── redis-data/             # Redis 持久化（运行时 UID 999）
```

1. 上传项目（考虑排除 `node_modules` 并在 `prep()` 中拉取）
2. 容器启动后运行所有权修复

### 自定义 Docker 项目

对于任何使用 Docker 服务的项目：

1. 上传项目文件
2. 调整 `docker-compose.yml`（参见步骤 5）
3. 创建包含生命周期函数的 `Rediaccfile`
4. 运行所有权修复
5. 启动服务

## 故障排除

### 上传后权限被拒绝

文件仍然具有您的本地 UID。运行所有权命令：

```bash
rdc repo ownership my-project -m server-1
```

### 容器无法启动

检查服务是否绑定到其分配的 IP，而不是 `0.0.0.0` 或 `localhost`：

```bash
# 检查分配的 IP
rdc term server-1 my-project -c "cat .rediacc.json"

# 检查容器日志
rdc term server-1 my-project -c "docker logs <container-name>"
```

### 仓库之间的端口冲突

每个仓库获得唯一的环回 IP。如果出现端口冲突，请验证您的 `docker-compose.yml` 使用 `${SERVICE_IP}` 进行绑定，而不是 `0.0.0.0`。绑定到 `0.0.0.0` 的服务会监听所有接口，并与其他仓库冲突。

### 所有权修复破坏了容器

如果您运行了 `rdc repo ownership --force` 并且容器停止工作，则容器的数据文件已被更改。停止容器，删除其数据目录，然后重新启动 — 容器将重新创建它：

```bash
rdc repo down my-project -m server-1
# 删除容器的数据目录（例如 database/data）
rdc repo up my-project -m server-1
```
