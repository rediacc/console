---
title: 网络
description: 通过反向代理、Docker 标签、TLS 证书、DNS 和 TCP/UDP 端口转发来暴露服务。
category: Guides
order: 6
language: zh
sourceHash: "911dde41922454ec"
---

# 网络

本页面介绍运行在隔离 Docker 守护进程中的服务如何从互联网访问。涵盖反向代理系统、用于路由的 Docker 标签、TLS 证书、DNS 以及 TCP/UDP 端口转发。
| Route server running old version | Binary was updated but service not restarted | Happens automatically on provisioning; manual: `sudo systemctl restart rediacc-router` |
| STUN/TURN relay not reachable | Relay addresses cached at startup | Recreate the service after DNS or IP changes so it picks up the new network config |

有关服务如何获取回环 IP 和 `.rediacc.json` 槽位系统的信息，请参阅[服务](/zh/docs/services#服务网络rediaccjson)。

## 工作原理

Rediacc 使用双组件代理系统将外部流量路由到容器：

1. **路由服务器** — 一个 systemd 服务，用于发现所有仓库 Docker 守护进程中运行的容器。它检查容器标签并生成路由配置，以 YAML 端点形式提供。
2. **Traefik** — 一个反向代理，每 5 秒轮询路由服务器并应用发现的路由。它处理 HTTP/HTTPS 路由、TLS 终止和 TCP/UDP 转发。

流程如下：

```
互联网 → Traefik（端口 80/443/TCP/UDP）
               ↓ 每 5 秒轮询
           路由服务器（发现容器）
               ↓ 检查标签
           Docker 守护进程（/var/run/rediacc/docker-*.sock）
               ↓
           容器（绑定到 127.x.x.x 回环 IP）
```

当您为容器添加正确的标签并使用 `renet compose` 启动时，它会自动变为可路由 — 无需手动配置代理。

> The route server binary is kept in sync with your CLI version. When the CLI updates the renet binary on a machine, the route server is automatically restarted (~1–2 seconds). This causes no downtime — Traefik continues serving traffic with its last known configuration during the restart and picks up the new config on the next poll. Existing client connections are not affected. Your application containers are not touched.

## Docker 标签

路由通过 Docker 容器标签控制。分为两个层级：

### 第一层：`rediacc.*` 标签（自动注入）

这些标签在使用 `renet compose` 启动服务时**自动注入**。您无需手动添加。

| 标签 | 描述 | 示例 |
|------|------|------|
| `rediacc.service_name` | 服务标识 | `myapp` |
| `rediacc.service_ip` | 分配的回环 IP | `127.0.11.2` |
| `rediacc.network_id` | 仓库的守护进程 ID | `2816` |
| `rediacc.repo_name` | Repository name | `marketing` |
| `rediacc.tcp_ports` | TCP ports the service listens on | `8080,8443` |
| `rediacc.udp_ports` | UDP ports the service listens on | `53` |

当容器仅有 `rediacc.*` 标签（没有 `traefik.enable=true`）时，路由服务器会使用仓库名称和机器子域名生成**自动路由**：

```
{service}.{repoName}.{machineName}.{baseDomain}
```

例如，一个名为 `myapp` 的服务，位于机器 `server-1` 上名为 `marketing` 的仓库中、基础域名为 `example.com`，将获得：

```
myapp.marketing.server-1.example.com
```

每个仓库拥有独立的子域名层级，因此分支和不同仓库永远不会冲突。当您 fork 一个仓库（例如 `marketing-staging`）时，fork 会自动获得不同的路由。对于需要自定义域名的服务，请使用第二层标签或 `rediacc.domain` 标签。

#### 通过 `rediacc.domain` 自定义域名

您可以在 `docker-compose.yml` 中使用 `rediacc.domain` 标签为服务设置自定义域名。支持短名称和完整域名：

```yaml
labels:
  # 短名称 — 使用机器的 baseDomain 解析为 cloud.example.com
  - "rediacc.domain=cloud"

  # 完整域名 — 按原样使用
  - "rediacc.domain=cloud.example.com"
```

不含点号的值被视为短名称，机器的 `baseDomain` 会自动追加。含点号的值被视为完整域名。

当配置了 `machineName` 时，自定义域名服务会获得**两条路由**：一条在基础域名上（`cloud.example.com`），一条在机器子域名上（`cloud.server-1.example.com`）。

### 第二层：`traefik.*` 标签（用户定义）

当您需要自定义域名路由、TLS 或特定入口点时，将这些标签添加到 `docker-compose.yml` 中。设置 `traefik.enable=true` 告诉路由服务器使用您的自定义规则而非生成自动路由。

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

这些使用标准的 [Traefik v3 标签语法](https://doc.traefik.io/traefik/routing/providers/docker/)。

> **提示：**仅供内部使用的服务（数据库、缓存、消息队列）**不应**设置 `traefik.enable=true`。它们只需要 `rediacc.*` 标签，这些标签会自动注入。

## 暴露 HTTP/HTTPS 服务

### 前提条件

1. 已在机器上配置基础设施（[机器设置 — 基础设施配置](/zh/docs/setup#基础设施配置)）：

   ```bash
   # 共享凭据（每个配置一次，适用于所有机器）
   rdc config infra set server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # 机器特定设置
   rdc config infra set server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push server-1
   ```

2. DNS 记录将您的域名指向服务器的公网 IP（参见下方的 [DNS 配置](#dns-配置)）。

### 添加标签

在 `docker-compose.yml` 中为需要暴露的服务添加 `traefik.*` 标签：

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=${MYAPP_IP}:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    command: ["-c", "listen_addresses=${DATABASE_IP}"]
    # 无 traefik 标签 — 仅供内部使用
```

| 标签 | 用途 |
|------|------|
| `traefik.enable=true` | 为此容器启用自定义 Traefik 路由 |
| `traefik.http.routers.{name}.rule` | 路由规则 — 通常为 `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | 监听的端口：`websecure`（HTTPS IPv4）、`websecure-v6`（HTTPS IPv6） |
| `traefik.http.routers.{name}.tls.certresolver` | 证书解析器 — 使用 `letsencrypt` 自动获取 Let's Encrypt 证书 |
| `traefik.http.services.{name}.loadbalancer.server.port` | 应用在容器内监听的端口 |

标签中的 `{name}` 是任意标识符 — 只需在相关的路由器/服务/中间件标签之间保持一致即可。

> **注意：** `rediacc.*` 标签（`rediacc.service_name`、`rediacc.service_ip`、`rediacc.network_id`）由 `renet compose` 自动注入。您无需将它们添加到 compose 文件中。

## TLS 证书

TLS 证书通过 Let's Encrypt 使用 Cloudflare DNS-01 挑战自动获取。凭据每个配置设置一次（在所有机器间共享）：

```bash
rdc config infra set server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

自动路由使用仓库子域名级别的**通配符证书**（`*.marketing.server-1.example.com`）代替每个服务单独的证书。这避免了 Let's Encrypt 的速率限制并加速启动。自定义域名路由使用机器级通配符（`*.server-1.example.com`）。

对于使用 `traefik.http.routers.{name}.tls.certresolver=letsencrypt` 的第二层路由，通配符域名 SAN 会根据路由的主机名自动注入。

Cloudflare DNS API 令牌需要对您要保护的域名具有 `Zone:DNS:Edit` 权限。

## TCP/UDP 端口转发

对于非 HTTP 协议（邮件服务器、DNS、对外暴露的数据库），使用 TCP/UDP 端口转发。

### 步骤 1：注册端口

在基础设施配置时添加所需的端口：

```bash
rdc config infra set server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push server-1
```

此操作创建名为 `tcp-{port}` 和 `udp-{port}` 的 Traefik 入口点。

### Plain TCP Example (Database)

To expose a database externally without TLS passthrough (Traefik forwards raw TCP):

```yaml
services:
  postgres:
    image: postgres:17
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

Port 5432 is pre-configured (see below), so no `--tcp-ports` setup is needed.

> **Security note:** Exposing a database to the internet is a risk. Use this only when remote clients need direct access. For most setups, keep the database internal and connect through your application.

> 添加或移除端口后，务必重新运行 `rdc config infra push` 以更新代理配置。

### 步骤 2：添加 TCP/UDP 标签

在 compose 文件中使用 `traefik.tcp.*` 或 `traefik.udp.*` 标签：

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP（端口 25）
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS（端口 993）— TLS 透传
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

关键概念：
- **`HostSNI(\`*\`)`** 匹配任何主机名（用于不发送 SNI 的协议，如纯 SMTP）
- **`tls.passthrough=true`** 表示 Traefik 转发原始 TLS 连接而不解密 — 由应用自行处理 TLS
- 入口点名称遵循 `tcp-{port}` 或 `udp-{port}` 的命名约定

### 预配置端口

以下 TCP/UDP 端口已默认配置入口点（无需通过 `--tcp-ports` 添加）。入口点仅为已配置的地址族生成 — IPv4 入口点需要 `--public-ipv4`，IPv6 入口点需要 `--public-ipv6`：

| 端口 | 协议 | 常见用途 |
|------|------|----------|
| 80 | HTTP | Web（自动重定向到 HTTPS） |
| 443 | HTTPS | Web（TLS） |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000–10010 | TCP | 动态范围（自动分配） |

## DNS 配置

### 自动 DNS（Cloudflare）

当配置了 `--cf-dns-token` 时，`rdc config infra push` 会自动在 Cloudflare 中创建必要的 DNS 记录：

| 记录 | 类型 | 内容 | 创建者 |
|------|------|------|--------|
| `server-1.example.com` | A / AAAA | 机器的公网 IP | `push-infra` |
| `*.server-1.example.com` | A / AAAA | 机器的公网 IP | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | 机器的公网 IP | `repo up` |

机器级记录由 `push-infra` 创建，覆盖自定义域名路由（`rediacc.domain`）。每个仓库的通配符记录由 `repo up` 自动创建，覆盖该仓库的自动路由。

此操作是幂等的 — 如果 IP 发生变化，现有记录将被更新；如果已经正确，则保持不变。

如果使用自定义域名标签（如 `rediacc.domain=erp`），则必须手动创建基础域名通配符（`*.example.com`）。

### 手动 DNS

如果不使用 Cloudflare 或手动管理 DNS，请创建 A（IPv4）和/或 AAAA（IPv6）记录：

```
# 机器子域名（用于自定义域名路由，如 rediacc.domain=erp）
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# 每个仓库的通配符（用于自动路由，如 myapp.marketing.server-1.example.com）
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# 基础域名通配符（用于自定义域名服务，如 rediacc.domain=erp）
*.example.com                  A     203.0.113.50
```

配置 Cloudflare DNS 后，每个仓库的通配符记录由 `repo up` 自动创建。使用多台机器时，每台机器获得各自的 DNS 记录，指向其自己的 IP。

## 中间件

Traefik 中间件用于修改请求和响应。通过标签应用中间件。

### HSTS（HTTP 严格传输安全）

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### 大文件上传缓冲

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### 多中间件组合

使用逗号分隔来链接多个中间件：

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

有关所有可用中间件的完整列表，请参阅 [Traefik 中间件文档](https://doc.traefik.io/traefik/middlewares/overview/)。

## 诊断

如果服务无法访问，通过 SSH 登录服务器并检查路由服务器端点：

### 健康检查

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

显示整体状态、已发现的路由器和服务数量，以及自动路由是否已启用。

### 已发现的路由

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

列出所有 HTTP、TCP 和 UDP 路由器及其规则、入口点和后端服务。

### 端口分配

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

显示动态分配端口的 TCP 和 UDP 端口映射。

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 服务不在路由中 | 容器未运行或缺少标签 | 在仓库的守护进程上使用 `docker ps` 验证；检查标签 |
| 证书未签发 | DNS 未指向服务器，或 Cloudflare 令牌无效 | 验证 DNS 解析；检查 Cloudflare API 令牌权限 |
| 502 Bad Gateway | 应用未在声明的端口上监听 | 验证应用绑定到其 `{SERVICE}_IP` 且端口与 `loadbalancer.server.port` 匹配 |
| TCP 端口不可达 | 端口未在基础设施中注册 | 运行 `rdc config infra set --tcp-ports ...` 和 `push-infra` |

## 完整示例

以下示例部署一个包含 PostgreSQL 数据库的 Web 应用。应用通过 `app.example.com` 公开访问并启用 TLS；数据库仅供内部使用。

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      LISTEN_ADDR: ${WEBAPP_IP}:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # 无 traefik 标签 — 仅供内部使用
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

创建一条 A 记录，将 `app.example.com` 指向您服务器的公网 IP：

```
app.example.com   A   203.0.113.50
```

### 部署

```bash
rdc repo up my-app -m server-1 --mount
```

几秒钟内，路由服务器发现容器，Traefik 获取路由，请求 TLS 证书，`https://app.example.com` 即可上线访问。
