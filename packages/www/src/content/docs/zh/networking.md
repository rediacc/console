---
title: 网络
description: 通过反向代理、Docker 标签、TLS 证书、DNS 和 TCP/UDP 端口转发来暴露服务。
category: Guides
order: 6
language: zh
sourceHash: "536db0c93646cad6"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# 网络

本页面介绍运行在隔离 Docker 守护进程中的服务如何从互联网访问。涵盖反向代理系统、用于路由的 Docker 标签、TLS 证书、DNS 以及 TCP/UDP 端口转发。

有关服务如何获取回环 IP 和 `.rediacc.json` 槽位系统的信息，请参阅[服务](/zh/docs/services#服务网络rediaccjson)。

## 网络隔离

每个仓库通过网络钩子在内核级别自动隔离。需要 Linux kernel 6.1 或更高版本。无需任何配置。

- **自动绑定地址重写**: 服务可以像往常一样绑定到 `0.0.0.0` 或 `127.0.0.1`。内核会透明地将地址重写为服务分配的回环 IP。无需显式绑定到 `${SERVICE_IP}`。
- **跨仓库连接阻断**: 如果服务尝试连接到其仓库 `/26` 子网之外的回环 IP，内核会阻止该连接。仓库 A 中的进程无法访问仓库 B 中的服务。
- **无需应用程序变更**: 服务使用 `0.0.0.0` 或 `localhost` 进行绑定，内核确保它们只在正确的回环 IP 上监听。隔离完全透明。

## 工作原理

Rediacc 使用双组件代理系统将外部流量路由到容器：

1. **路由服务器**, 一个 systemd 服务，用于发现所有仓库 Docker 守护进程中运行的容器。它检查容器标签并生成路由配置，以 YAML 端点形式提供。
2. **Traefik**, 一个反向代理，每 5 秒轮询路由服务器并应用发现的路由。它处理 HTTP/HTTPS 路由、TLS 终止和 TCP/UDP 转发。

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

当您为容器添加正确的标签并使用 `renet compose` 启动时，它会自动变为可路由，无需手动配置代理。

> 路由服务器二进制文件与您的 CLI 版本保持同步。当 CLI 在机器上更新 renet 二进制文件时，路由服务器会自动重启（约 1-2 秒）。这不会造成任何停机，Traefik 在重启期间继续使用其最后已知的配置提供服务，并在下次轮询时获取新配置。现有的客户端连接不受影响。您的应用程序容器不会被改动。

## Docker 标签

路由通过 Docker 容器标签控制。分为两个层级：

### 第一层：`rediacc.*` 标签（自动注入）

这些标签在使用 `renet compose` 启动服务时**自动注入**。您无需手动添加。

| 标签 | 描述 | 示例 |
|------|------|------|
| `rediacc.service_name` | 服务标识 | `myapp` |
| `rediacc.service_ip` | 分配的回环 IP | `127.0.11.2` |
| `rediacc.network_id` | 仓库的守护进程 ID | `2816` |
| `rediacc.repo_name` | 仓库名称 | `marketing` |
| `rediacc.tcp_ports` | 服务监听的 TCP 端口 | `8080,8443` |
| `rediacc.udp_ports` | 服务监听的 UDP 端口 | `53` |

当容器仅有 `rediacc.*` 标签（没有 `traefik.enable=true`）时，路由服务器会使用仓库名称和机器子域名生成**自动路由**：

```
{service}.{repoName}.{machineName}.{baseDomain}
```

例如，一个名为 `myapp` 的服务，位于机器 `server-1` 上名为 `marketing` 的仓库中，基础域名为 `example.com`，将获得：

```
myapp.marketing.server-1.example.com
```

对于派生版本，服务名称与保留字 `fork` 和标签组合：

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

例如，标记为 `staging` 的 `marketing` 派生版本将获得：

```
myapp-fork-staging.marketing.server-1.example.com
```

每个派生版本的 URL 位于父仓库子域名下，并由其现有的通配符证书覆盖，因此不需要新证书。`-fork-` 分隔符防止与生产仓库中的真实服务名称发生冲突。对于需要自定义域名的服务，请使用第二层标签或 `rediacc.domain` 标签。

#### 通过 `rediacc.domain` 自定义域名

您可以在 `docker-compose.yml` 中使用 `rediacc.domain` 标签为服务设置自定义域名。支持短名称和完整域名：

```yaml
labels:
  # 短名称, 使用机器的 baseDomain 解析为 cloud.example.com
  - "rediacc.domain=cloud"

  # 完整域名, 按原样使用
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

1. 已在机器上配置基础设施（[机器设置, 基础设施配置](/zh/docs/setup#基础设施配置)）：

   ```bash
   # 共享凭据（每个配置一次，适用于所有机器）
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # 机器特定设置
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. DNS 记录将您的域名指向服务器的公网 IP（参见下方的 [DNS 配置](#dns-配置)）。

### 添加标签

在 `docker-compose.yml` 中为需要暴露的服务添加 `traefik.*` 标签：

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # 无 traefik 标签, 仅供内部使用
```

| 标签 | 用途 |
|------|------|
| `traefik.enable=true` | 为此容器启用自定义 Traefik 路由 |
| `traefik.http.routers.{name}.rule` | 路由规则, 通常为 `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | 监听的端口：`websecure`（HTTPS IPv4）、`websecure-v6`（HTTPS IPv6） |
| `traefik.http.routers.{name}.tls.certresolver` | 证书解析器, 使用 `letsencrypt` 自动获取 Let's Encrypt 证书 |
| `traefik.http.services.{name}.loadbalancer.server.port` | 应用在容器内监听的端口 |

标签中的 `{name}` 是任意标识符，只需在相关的路由器/服务/中间件标签之间保持一致即可。

> **注意：** `rediacc.*` 标签（`rediacc.service_name`、`rediacc.service_ip`、`rediacc.network_id`）由 `renet compose` 自动注入。您无需将它们添加到 compose 文件中。

## TLS 证书

TLS 证书通过 Let's Encrypt 使用 Cloudflare DNS-01 挑战自动获取。凭据每个配置设置一次（在所有机器间共享）：

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

自动路由使用仓库子域名级别的**通配符证书**（`*.marketing.server-1.example.com`）代替每个服务单独的证书。证书在第一次 `repo up` 时由 Traefik 自动签发，无需任何手动步骤。派生版本重用父仓库现有的通配符，因此永远不会触发新的证书请求。自定义域名路由使用机器级通配符（`*.server-1.example.com`）。

> **需要 Cloudflare 凭据。**通配符证书使用 DNS-01 挑战。没有 `--cf-dns-token`（以及可选的 `--cert-email`），Traefik 无法完成挑战，HTTPS 将无法使用。HTTP 仍然可用。在首次部署前，使用 `rdc config infra set` 配置凭据。

对于使用 `traefik.http.routers.{name}.tls.certresolver=letsencrypt` 的第二层路由，通配符域名 SAN 会根据路由的主机名自动注入。

Cloudflare DNS API 令牌需要对您要保护的域名具有 `Zone:DNS:Edit` 权限。

### TLS 证书生命周期

Let's Encrypt 证书从签发到到达每个仓库容器的完整路径：

1. **在宿主机签发。** 机器级 Traefik 容器（`rediacc-proxy`，部署于 `/opt/rediacc/proxy/`）负责 ACME 续期。它将所有状态存储在宿主机上的 `/opt/rediacc/proxy/letsencrypt/acme.json` 中。续期在到期前约 30 天自动触发；只要配置了 `--cf-dns-token`，无需任何操作员干预。

2. **按仓库转储（可选）。**需要在其自身容器内存放证书文件的服务（例如直接读取 `.pem` 文件的邮件服务器），会在自身旁边部署一个小型 `traefik-certs-dumper` 容器。转储器以只读方式绑定挂载 `/opt/rediacc/proxy/letsencrypt`，并将提取的证书和密钥作为 `cert.pem` / `key.pem` 写入仓库的数据卷。为使其正常工作，每个仓库的 Docker 守护进程必须在其挂载命名空间允许列表中包含 `/opt/rediacc/proxy`。默认情况下已包含此项。

3. **客户端缓存（`rediacc.json`）。** CLI 在配置文件的 `acmeCertCache` 下缓存 `acme.json` 的压缩副本，以 `baseDomain` 为键。这使多台机器可以共享证书（通过 `rdc config cert-cache push -m <machine>`），并充当离线清单。

**客户端缓存的同步触发条件：**

- 在 `rdc repo up` 之后自动触发，但仅当机器 `baseDomain` 的本地缓存超过 6 小时时。新鲜的缓存保持不变，以防止连续部署对 SSH 造成压力。
- 按需触发：`rdc config cert-cache pull -m <machine>`（强制拉取）或 `rdc machine query --name <machine> --sync-certs`（作为状态查询副作用的拉取）。
- 在 `rdc config infra push` 时，缓存被推送到机器（到期时间更长的本地证书优先于远程证书）。

**缓存维护：**

- 旧的自动路由条目（带旧网络 ID 标签的域名，如 `service-3200.rediacc.io`）在每次拉取时被清除。
- `notAfter` 超过 7 天的证书将被彻底删除。它们已失效，只会使缓存膨胀。
- `rdc config cert-cache clear` 清除所有内容；`rdc config cert-cache status` 显示清单。

**故障排查：** 如果 `traefik-certs-dumper` 以 `/traefik/acme.json: no such file or directory` 崩溃，说明每个仓库的守护进程看不到宿主机的 letsencrypt 存储。请验证 (a) 宿主机上存在 `/opt/rediacc/proxy/letsencrypt/acme.json`（这是宿主机级 `rediacc-proxy` 的职责），以及 (b) 每个仓库的守护进程是以足够新版本的 renet 启动的（该版本将 `/opt/rediacc/proxy` 加入允许列表）。升级 renet 后使用 `rdc repo up` 重新部署仓库以应用更改。

> **实验性：** 自动同步节奏和基于过期的清理在 renet 0.9+ 中推出。旧版 CLI/renet 仅使用通过 `rdc config cert-cache pull` 的纯手动同步。

## TCP/UDP 端口转发

对于非 HTTP 协议（邮件服务器、DNS、对外暴露的数据库），使用 TCP/UDP 端口转发。

### 步骤 1：注册端口

在基础设施配置时添加所需的端口：

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

此操作创建名为 `tcp-{port}` 和 `udp-{port}` 的 Traefik 入口点。

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

      # IMAPS（端口 993），TLS 透传
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

关键概念：
- **`HostSNI(\`*\`)`** 匹配任何主机名（用于不发送 SNI 的协议，如纯 SMTP）
- **`tls.passthrough=true`** 表示 Traefik 转发原始 TLS 连接而不解密，由应用自行处理 TLS
- 入口点名称遵循 `tcp-{port}` 或 `udp-{port}` 的命名约定

### 简单 TCP 示例（数据库）

在没有 TLS 透传的情况下将数据库暴露到外部（Traefik 转发原始 TCP）：

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

端口 5432 已预配置（见下文），因此无需 `--tcp-ports` 设置。

> **安全注意：** 将数据库暴露给互联网存在风险。仅在远程客户端需要直接访问时才使用此方法。对于大多数配置，请保持数据库内部，通过您的应用程序进行连接。

### 预配置端口

以下 TCP/UDP 端口已默认配置入口点（无需通过 `--tcp-ports` 添加）。入口点仅为已配置的地址族生成，IPv4 入口点需要 `--public-ipv4`，IPv6 入口点需要 `--public-ipv6`：

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
| 10000-10010 | TCP | 动态范围（自动分配） |

## DNS 配置

### 自动 DNS（Cloudflare）

当配置了 `--cf-dns-token` 时，`rdc config infra push` 会自动在 Cloudflare 中创建必要的 DNS 记录：

| 记录 | 类型 | 内容 | 创建者 |
|------|------|------|--------|
| `server-1.example.com` | A / AAAA | 机器的公网 IP | `push-infra` |
| `*.server-1.example.com` | A / AAAA | 机器的公网 IP | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | 机器的公网 IP | `repo up` |

机器级记录由 `push-infra` 创建，覆盖自定义域名路由（`rediacc.domain`）。每个仓库的通配符记录由 `repo up` 自动创建，覆盖该仓库的自动路由。

此操作是幂等的，如果 IP 发生变化，现有记录将被更新；如果已经正确，则保持不变。

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
| 502 Bad Gateway | 应用未在声明的端口上监听 | 验证应用正在运行且端口与 `loadbalancer.server.port` 匹配 |
| TCP 端口不可达 | 端口未在基础设施中注册 | 运行 `rdc config infra set --tcp-ports ...` 和 `push-infra` |
| 路由服务器运行旧版本 | 二进制文件已更新但服务未重启 | 在配置时自动发生；手动：`sudo systemctl restart rediacc-router` |
| STUN/TURN 中继不可达 | 中继地址在启动时缓存 | 在 DNS 或 IP 更改后重建服务以获取新的网络配置 |

## 完整示例

以下示例部署一个包含 PostgreSQL 数据库的 Web 应用。应用通过 `app.example.com` 公开访问并启用 TLS；数据库仅供内部使用。

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
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
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # 无 traefik 标签, 仅供内部使用
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
rdc repo up --name my-app -m server-1
```

几秒钟内，路由服务器发现容器，Traefik 获取路由，请求 TLS 证书，`https://app.example.com` 即可上线访问。
