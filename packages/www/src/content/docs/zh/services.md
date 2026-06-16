---
title: 服务
description: >-
  使用 Rediaccfile、服务网络和开机自启来部署和管理容器化服务。
category: Guides
order: 5
language: zh
sourceHash: "011bc5d87114f105"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# 服务

本页面涵盖的内容：部署和管理容器化服务，包括 Rediaccfile、服务网络、启动/停止、批量操作和开机自启。

## Rediaccfile

**Rediaccfile** 是一个 Bash 脚本，用于定义服务的启动和停止方式。该文件通过 **source** 加载（而不是作为单独进程执行），因此其函数共享相同的 shell 上下文，可以访问所有导出的环境变量。文件必须命名为 `Rediaccfile` 或 `rediaccfile`（不区分大小写），并放置在仓库的已挂载文件系统中。

Rediaccfile 在两个位置被发现：
1. 仓库挂载路径的**根目录**
2. 挂载路径的**第一级子目录**（不递归）

隐藏目录（名称以 `.` 开头）将被跳过。

### 生命周期函数

一个 Rediaccfile 最多包含两个函数：

| 函数 | 运行时机 | 用途 | 错误行为 |
|------|----------|------|----------|
| `up()` | 启动时 | 启动服务（例如 `renet compose -- up -d`） | 根 Rediaccfile 失败是**关键性的**（停止所有操作）。子目录失败是**非关键性的**（记录日志，继续下一个） |
| `down()` | 停止时 | 停止服务（例如 `renet compose -- down`） | **尽力而为** -- 失败会被记录，但所有 Rediaccfile 都会被执行 |

两个函数都是可选的。如果某个函数未定义，它会被静默跳过。

### 执行顺序

- **启动（`up`）：** 先执行根 Rediaccfile，然后按**字母顺序**（A 到 Z）执行子目录中的 Rediaccfile。
- **停止（`down`）：** 先按**反向字母顺序**（Z 到 A）执行子目录中的 Rediaccfile，最后执行根 Rediaccfile。

### 环境变量

当 Rediaccfile 函数执行时，以下环境变量可用：

| 变量 | 描述 | 示例 |
|------|------|------|
| `REDIACC_WORKING_DIR` | 仓库的挂载路径 | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | 仓库 GUID | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | 网络 ID（整数） | `2816` |
| `DOCKER_HOST` | 此仓库隔离守护进程的 Docker 套接字 | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | `.rediacc.json` 中定义的每个服务的回环 IP | `POSTGRES_IP=127.0.11.2` |

`{SERVICE}_IP` 变量从 `.rediacc.json` 中的槽位映射自动生成，在 Rediaccfile 函数运行前导出。命名规则是将服务名称转换为大写，连字符替换为下划线，然后追加 `_IP`。例如，`listmonk-app` 变为 `LISTMONK_APP_IP=127.0.11.2`。

> **警告：请勿在 Rediaccfile 中使用 `sudo docker`。** `sudo` 命令会重置环境变量，导致 `DOCKER_HOST` 丢失，Docker 命令将指向系统守护进程而非仓库的隔离守护进程。这会破坏容器隔离并可能导致端口冲突。如果 Rediacc 检测到未带 `-E` 的 `sudo docker`，将阻止执行。
>
> 在 Rediaccfile 中请使用 `renet compose`，它会自动处理 `DOCKER_HOST`，注入路由发现所需的网络标签，并配置服务网络。有关服务如何通过反向代理暴露的详细信息，请参阅[网络](/zh/docs/networking)。如果直接调用 Docker，请使用不带 `sudo` 的 `docker`，Rediaccfile 函数已拥有充分权限。如果必须使用 sudo，请使用 `sudo -E docker` 来保留环境变量。
>
> `renet` 是远程低级别工具。对于从工作站执行的正常用户工作流，请优先使用 `rdc` 命令，如 `rdc repo up` 和 `rdc repo down`。参阅 [rdc vs renet](/zh/docs/rdc-vs-renet)。

### 示例

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **重要：** 请始终使用 `renet compose --` 而非 `docker compose`。`renet compose` 封装器强制实施主机网络、IP 分配和 renet-proxy 所需的服务发现标签。CRIU 检查点/恢复功能会添加到带有 `rediacc.checkpoint=true` 标签的容器。直接使用 `docker compose` 会被 Rediaccfile 验证拒绝。详情请参阅[网络](/zh/docs/networking)。

### 能力标签

容器默认以最小 Linux 能力集运行。服务可通过在 `docker-compose.yml` 中添加标签来申请额外能力：

| 标签 | 授权内容 | 适用场景 |
|-------|--------|---------|
| `rediacc.checkpoint=true` | `CHECKPOINT_RESTORE`、`SYS_PTRACE`、`NET_ADMIN` | CRIU 检查点/恢复（热迁移、保存与恢复） |
| `rediacc.wireguard=true` | `NET_ADMIN` 及 `/dev/net/tun` 设备 | 在容器内运行 WireGuard 客户端 |

```yaml
services:
  vpn:
    image: alpine
    labels:
      - "rediacc.wireguard=true"
```

`rediacc.wireguard` 允许服务建立 WireGuard 隧道，例如将某个进程的流量通过远端节点转发出去。由于所有服务均使用主机网络，应将隧道限制在容器内的网络命名空间中，避免影响宿主机的路由表。`privileged: true`、`pid: host`、`ipc: host` 等宽泛特权选项无论是否添加标签，均会被验证器拒绝。

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

每个仓库获得一个 /26 子网（64 个 IP），位于 `127.x.x.x` 回环地址范围内。服务绑定到唯一的回环 IP，因此可以使用相同的端口而不会产生冲突。

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

1. 扫描所有包含 Rediaccfile 的目录中的 compose 文件（`docker-compose.yml`、`docker-compose.yaml`、`compose.yml` 或 `compose.yaml`）
2. 从每个 compose 文件的 `services:` 部分提取服务名称
3. 为新服务分配下一个可用槽位
4. 将结果保存到 `{repository}/.rediacc.json`

### IP 计算

服务的 IP 根据仓库的网络 ID 和服务的槽位计算。网络 ID 分布在 `127.x.y.z` 回环地址的第二、第三和第四个八位组中。服务从偏移量 2 开始：

| 偏移量 | 地址 | 用途 |
|--------|---------|---------|
| .0 | `127.0.11.0` | 网络地址（保留） |
| .1 | `127.0.11.1` | 网关（保留） |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | 服务（`slot + 2`） |
| .63 | `127.0.11.63` | 广播（保留） |

**示例**：网络 ID 为 `2816`（`0x0B00`）时，基础地址为 `127.0.11.0`：

| 服务 | 槽位 | IP 地址 |
|------|------|---------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

每个仓库最多支持 **61 个服务**（槽位 0 到 60）。

### 在 Docker Compose 中使用服务 IP

由于每个仓库运行隔离的 Docker 守护进程，`renet compose` 会自动为所有服务配置 `network_mode: host`。内核透明地将 `bind()` 调用重写到服务分配的回环 IP，因此服务可以绑定到 `0.0.0.0` 或 `localhost` 而不会产生冲突。对于**连接到其他服务**，请使用**服务名称**。renet 将每个服务名称作为主机名注入，始终解析到正确的 IP，即使在 fork 中也是如此：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # 无需显式 listen_addresses -- 内核会将 bind 重写到正确的回环 IP

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # 使用服务名称
      LISTEN_ADDR: 0.0.0.0:8080                                      # 内核重写到服务 IP
```

> **连接用服务名称：** 使用**服务名称**（如 `postgres`、`redis`）**连接到**其他服务 -- renet 通过 `/etc/hosts` 自动将每个服务名称映射到其回环 IP。在数据库或配置文件中存储的连接字符串中嵌入 `${POSTGRES_IP}` 会固化原始 IP，这会破坏 fork 隔离并且是**验证错误**。`${SERVICE_IP}` 变量仍可用于显式使用，但绑定由内核自动处理。

> **注意：** 不要手动添加 `network_mode: host`，`renet compose` 会自动注入。重启策略（如 `restart: always`）可以安全使用，renet 会为了 CRIU 兼容性自动删除它们，路由器看门狗负责容器恢复。

### 容器恢复与重启策略

renet 和 Docker 有意在如何处理容器重启方面存在分工。在调试容器为什么恢复或未能恢复时，理解这种分工很重要。

**重启策略转换。** 当您在 compose 文件中写入 `restart: always`（或 `unless-stopped`，或 `on-failure`）时，renet 在合成实际 compose 部署时会**删除**它，并用 `restart: no` 替换。原始值保存到仓库的 `.rediacc.json` 中 `services.<name>.restart_policy` 下。这可以防止 Docker 守护进程级别的自动重启干扰 CRIU 检查点/恢复（守护进程驱动的重启会从过时的检查点前状态恢复）。

**看门狗执行。** 路由器看门狗在每台机器上定期运行。每次滴答时：

1. 读取每个仓库的 `.rediacc.json`，找到具有可恢复 `restart_policy` 的服务
2. 列出该仓库守护进程的所有容器，识别已停止的容器，并按保存的策略重启它们。30 秒的宽限期防止与刚刚运行 `docker stop` 的操作员发生冲突
3. 同一循环还处理 `/var/run/rediacc/cold-backup-<guid>.running.json`（参见[冷备份语义](backup-restore.md#cold-backup-semantics)）。列出的容器无论保存的策略如何都会重启，因为 sidecar 意味着"renet 有意停止了这些容器，欠操作员一次重启"

**为什么 `on-failure` 看起来像坏掉了。** Docker 的 `on-failure` 策略仅在容器以非零代码退出时重启。来自 `docker stop` 或守护进程关闭的正常停止（exit 0）不是"失败"，不会触发重启，无论是通过 Docker 的原生逻辑还是看门狗的保存策略路径。冷备份 sidecar 是安全网：有意停止的任何容器都会重启，无论其策略如何。

**如何解读运行时状态：**

- `docker inspect <container>` → `RestartPolicy.Name`：对于 renet 管理的容器始终为 `no`。不要依赖这个来判断语义策略
- 仓库挂载根目录的 `.rediacc.json` → `services.<name>.restart_policy`：真实意图
- `docker ps --format '{{.Status}}'`：运行时状态

**如何修复偏差。** 如果容器的 `.rediacc.json` 保存策略错误（例如，因为您编辑了 compose 但未重新创建容器），请重新运行 `rdc repo up --name <repo> -m <machine>`。容器将以更新的策略重新创建。

> **实验性：** 基于冷备份 sidecar 的恢复和 `rdc machine query` 上的 `--sync-certs` 标志在 renet 0.9+ 中发布。旧版本仅依赖保存的 `restart_policy` 进行看门狗恢复，这可能在冷备份后使 `on-failure` 容器搁浅。

> **每个仓库的守护进程禁用了 Docker bridge 网络。** 每个仓库的守护进程（`FlavorRediacc`）都配置了 `"bridge": "none"` 和 `"iptables": false`。在仓库 shell 内运行一个简单的 `docker run <image>` 仍然能启动容器，但该容器只有 loopback 接口，没有 DNS 或出站连接。这是设计使然，因为仓库之间的 loopback 隔离由 eBPF cgroup 钩子强制执行，而 bridge 容器会绕过这些钩子。生产服务应使用 `renet compose`（它会自动为您注入主机网络）；对于临时调试，请显式传递 `--network host`：`docker run --rm --network host -it ubuntu bash`。
>
> 每个用户的 Hub 守护进程（`FlavorHub`，用于开发环境）是例外：它们设置 `bridge="docker0"`、`iptables=true` 和 `live-restore=true`，使用户运行的容器拥有正常的 bridge 网络和出站连接。

> **注意：** Fork 仓库在父仓库子域下获得自动路由：`{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`。自定义域名在 fork 中被跳过。

## 启动服务

挂载仓库并启动所有服务：

```bash
rdc repo up --name my-app -m server-1
```

| 选项 | 描述 |
|------|------|
| `--detach` | 容器启动后立即返回；健康检查在后台继续运行 |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

执行顺序为：
1. 挂载 LUKS 加密仓库（未挂载时自动挂载）
2. 启动此仓库的隔离 Docker 守护进程
3. 从 compose 文件自动生成 `.rediacc.json`
4. 按 A-Z 顺序在所有 Rediaccfile 中运行 `up()`

部署后，输出显示 **PROXY ROUTES** 部分，其中包含每个服务的实际 URL。具有自定义 Traefik 标签的服务将其自定义域名显示为主要 URL：

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

未具有自定义 Traefik 标签的服务仅显示自动生成的路由。使用这些 URL（而非 CLI 输出的通用模式）进行浏览器访问、API 调用和跨服务配置。

### 后台启动

加上 `--detach`，命令在容器启动后即返回，不等待健康检查完成。启动过程在后台继续：代理持续重试上游连接，直到各服务就绪，路由自动恢复。可通过 `rdc machine query --containers --name <machine>` 查看进度。适合一次性临时分支和无需等待服务就绪即可进行下一步的脚本化流程。

### 就绪探测

`up()` 执行完成后，renet 会对每个 HTTP 服务发起 TCP 探测，确认其接受连接，避免首次浏览器请求遭遇代理 502。容器已定义 Docker 健康检查的服务可直接信任：状态为 `healthy` 的容器跳过探测；仍处于 `start_period` 内的容器记录信息日志而非警告。探测最长等待 15 秒（可通过机器上的环境变量 `REDIACC_READINESS_TIMEOUT` 以秒为单位覆盖）；后台模式启动跳过探测。

## 停止服务

```bash
rdc repo down --name my-app -m server-1
```

| 选项 | 描述 |
|------|------|
| `--unmount` | 停止服务后卸载加密仓库。如果此操作未生效，请单独使用 `rdc repo unmount`。 |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

执行顺序为：
1. 按 Z-A 反向顺序在所有 Rediaccfile 中运行 `down()`（尽力而为）
2. 停止隔离的 Docker 守护进程（如果指定了 `--unmount`）
3. 卸载并关闭 LUKS 加密卷（如果指定了 `--unmount`）

## 批量操作

一次启动或停止机器上的所有仓库：

```bash
rdc repo up -m server-1
```

| 选项 | 描述 |
|------|------|
| `--include-forks` | 包含 fork 仓库 |
| `--mount-only` | 仅挂载，不启动容器 |
| `--dry-run` | 显示将要执行的操作 |
| `--parallel` | 并行运行操作 |
| `--concurrency <n>` | 最大并发操作数（默认：3） |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

## 开机自启

默认情况下，服务器重启后需要手动挂载和启动仓库。**开机自启**功能可配置仓库在服务器启动时自动挂载、启动 Docker 并运行 Rediaccfile `up()`。

### 工作原理

当您为仓库启用开机自启时：

1. 生成一个 256 字节的随机 LUKS 密钥文件，并添加到仓库的 LUKS 槽位 1（槽位 0 仍为用户密码短语）
2. 密钥文件存储在 `{datastore}/.credentials/keys/{guid}.key`，权限为 `0600`（仅 root 可读）
3. 安装一个 systemd 服务（`rediacc-autostart`），在启动时挂载所有已启用的仓库并启动其服务

在系统关机或重启时，该服务会优雅地停止所有服务（Rediaccfile `down()`）、停止 Docker 守护进程并关闭 LUKS 卷。

> **安全提示：** 启用开机自启会将 LUKS 密钥文件存储在服务器磁盘上。任何拥有服务器 root 权限的人都可以在无需密码短语的情况下挂载仓库。请根据您的威胁模型进行评估。

### 启用

```bash
rdc repo autostart enable --name my-app -m server-1
```

系统将提示您输入仓库密码短语。

### 为所有仓库启用

```bash
rdc repo autostart enable -m server-1
```

### 禁用

```bash
rdc repo autostart disable --name my-app -m server-1
```

此操作将删除密钥文件并清除 LUKS 槽位 1。

### 部署时刷新密钥文件

当开机自启已启用时，`rdc repo up` 会验证 LUKS 槽位 1 的密钥文件。
如果磁盘上的密钥文件仍与 LUKS 槽位匹配，则不会进行任何更改。

通过 `repo push` / `repo pull` 在机器之间传输仓库后，
新机器上的密钥文件将不匹配。此时，`repo up` 会自动重新生成密钥文件并更新 LUKS 槽位 1。您将看到以下日志消息：

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

这是安全的，槽位 0（您的密码短语）永远不会被修改。如果未启用开机自启，
此检查将静默跳过。失败不是致命的，不会阻止部署。

### 查看状态

```bash
rdc repo autostart list -m server-1
```

有关周期性协调器在启动后如何恢复停止的仓库的详细信息，请参阅[自动启动与恢复](/zh/docs/autostart-recovery)。

## 完整示例

以下示例部署一个包含 PostgreSQL、Redis 和 API 服务器的 Web 应用。

### 1. 设置环境

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. 挂载并准备

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. 创建应用文件

在仓库内创建以下文件：

**docker-compose.yml：**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile：**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up --name webapp -m prod-1
```

### 5. 启用开机自启

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## 在 compose 中使用按仓库的密钥

上面 `POSTGRES_PASSWORD: changeme` 占位符对于教程来说没问题，但真实应用需要真实凭证。将它们提交到 compose 文件（或仓库内的 `.env` 文件）意味着 fork 也会继承它们。对于部署时凭证，请使用 `rdc repo secret`。值存储在加密仓库镜像之外，因此 fork 开始时具有空的密钥映射。

compose 中两种传递模式有效：

**`env` 模式**。通过 `${REDIACC_SECRET_<KEY>}` 在任何 `environment:` 值中进行内插。renet 封装器在部署时将值传递到容器的环境中。

**`file` 模式**。值输入到主机端 tmpfs 文件 `/var/run/rediacc/secrets/<networkID>/<KEY>`，您通过 Docker compose 的标准 `secrets:` 块将其挂载到容器中。容器读取 `/run/secrets/<key>`。对于任何敏感内容，请优先选择此模式。值永远不会出现在 `docker inspect` 或 `/proc/<pid>/environ` 中。

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

使用 `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` 和等效的文件模式来设定值。参阅[仓库 - 密钥](/zh/docs/repositories#secrets)了解完整的操作方法和[按仓库的密钥](/zh/docs/rdc-cheat-sheet#per-repo-secrets)在速查表中了解命令参考。

> **跨仓库路径在验证时被拒绝。** 指向另一仓库的 `/var/run/rediacc/secrets/<other-networkID>/` 目录的 compose `secrets: file:`（或 `configs: file:`，或 `env_file:`）在 docker compose 运行前由 renet 封装器硬拒绝。`--unsafe` 不会覆盖。纵深防御：Rediaccfile shell 周围的 Landlock 沙箱限制读取到当前网络的密钥目录，因此即使绕过 YAML 验证器，来自 Rediaccfile bash 的 `cat /var/run/rediacc/secrets/<other>/X` 也会以 EACCES 失败。您无需选择加入；这对每个 `repo up` 都默认启用。
