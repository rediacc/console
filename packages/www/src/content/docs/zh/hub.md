---
title: "Hub"
description: "提供经过身份验证的、按用户分配的容器化环境，支持自动配置、空闲管理和检查点/恢复。"
category: "Guides"
order: 14
language: zh
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Hub 在 OAuth 身份验证后为每个用户提供容器化环境。用户访问单一 URL，通过任意 OAuth2 提供者进行身份验证，然后被透明地路由到其个人容器。容器按需创建并自动管理。

所有配置通过 `docker-compose.yml` 标签完成。Hub 不知道也不关心容器内运行的内容 -- 它处理身份验证、路由和生命周期管理。仓库定义行为。

## 工作原理

![Hub 架构](/img/hub-architecture.svg)

1. 用户访问 `code.example.com`
2. Hub 检查会话 cookie。如果不存在，用户将被重定向到配置的 OAuth2 提供者（Nextcloud、Keycloak、GitHub 等）
3. 身份验证后，Hub 识别用户并查找其容器
4. 如果不存在容器，将根据配置的模板按需创建一个
5. 请求通过反向代理转发到用户的容器
6. Hub 根据主机名确定代理到哪个端口（例如 `code.` -> 端口 8080，`term.` -> 端口 7681）

空闲容器会自动停止或通过检查点（CRIU）保存，以便下次登录时即时恢复。

## 快速开始

在仓库的 `docker-compose.yml` 中将 Hub 添加为服务：

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # 路由映射：子域名前缀 -> 用户容器上的端口
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # 容器模板
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Traefik 路由（每个子域名一个）
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

创建包含 OAuth2 提供者凭据的 `hub.env`：

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

使用 `rdc repo up` 部署。

## 配置

所有 Hub 配置都在 Hub 服务本身的 Compose 标签中。Hub 二进制文件内没有配置文件。

### 路由映射

将子域名前缀映射到用户容器上的端口。Hub 读取这些标签以了解将每个请求路由到哪里。

| 标签 | 描述 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | 将 `{prefix}.{domain}` 映射到用户容器上的此端口 | `rediacc.hub.route.code=8080` |

您可以定义任意数量的路由。前缀与主机名的第一个段进行匹配：

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

每个路由还需要一个对应的 Traefik 路由器指向 Hub 的端口（7112）。Hub 在内部处理按用户路由。

### 容器模板

定义用户容器的外观。Hub 读取这些标签，并在为用户创建新容器时使用。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.image` | 容器镜像 | `--container-image` 标志的值 |
| `rediacc.hub.command` | 启动命令（兼容 bash -c） | 无 |
| `rediacc.hub.user` | 容器用户（建议非 root） | `vscode` |
| `rediacc.hub.workspace` | 容器内的工作空间挂载点 | `/workspace` |
| `rediacc.hub.shm_size` | 共享内存大小（字节） | `1073741824`（1 GB） |

`command` 标签支持 `${SERVICE_IP}` 展开，在创建时替换为容器分配的回环 IP。

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **提示：** 在 Compose 标签中使用 `$$` 表示字面量 `$`，以防止 Docker Compose 过早展开环境变量。

### 资源限制

设置每用户资源限制，防止单个用户消耗所有主机资源。

| 标签 | 描述 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | CPU 限制（核心数） | `2` |
| `rediacc.hub.limits.memory` | 内存限制 | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### 生命周期钩子

在生命周期的特定时间点在用户容器内执行命令。

| 标签 | 执行时机 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | 容器创建后（首次登录） | 克隆仓库、安装依赖 |
| `rediacc.hub.hook.on_start` | 容器启动或恢复后 | 挂载密钥、刷新令牌 |
| `rediacc.hub.hook.on_idle` | 容器停止或创建检查点前 | 保存状态、推送更改 |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### 检查点 / 恢复

启用后，空闲容器将使用 CRIU 创建检查点而非停止。下次登录时，容器从检查点在数秒内恢复，保持精确状态：打开的文件、运行的进程、终端会话。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | 为用户容器启用 CRIU 检查点 | `false` |

启动 Hub 时也传递 `--checkpoint`：

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...其他标志...
```

> **注意：** 检查点/恢复要求主机上有可用的 CRIU 二进制文件，且容器必须在主机网络模式下运行（Rediacc 服务的默认模式）。

### 访问控制

限制谁可以使用 Hub 以及谁拥有管理员权限。

| 标签 | 描述 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | 逗号分隔的允许使用 Hub 的组 | `developers,ops` |
| `rediacc.hub.admin_users` | 逗号分隔的管理员用户名 | `alice,bob` |

管理员用户可以在仪表板中查看和管理所有容器。普通用户只能看到自己的。

### 临时模式

默认情况下，用户工作空间是持久的（在容器重启后保留）。临时模式在每次登录时提供干净的环境，适用于演示、培训或 CI。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` 或 `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

在临时模式下，工作空间使用 tmpfs（基于 RAM），容器停止时自动删除。

### 多模板支持

提供多种环境类型。用户可以在首次登录时选择模板，或通过仪表板切换。

```yaml
labels:
  # 默认模板
  - "rediacc.hub.template.default=fulldev"

  # 完整开发环境
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # 轻量级选项
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## OAuth 设置

Hub 可与任何标准 OAuth2 提供者配合使用。配置通过环境变量完成，而非 Compose 标签（密钥不应放在标签中）。

| 变量 | 描述 | 必需 |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 客户端 ID | 是 |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 客户端密钥 | 是 |
| `HUB_OAUTH_AUTHORIZE_URL` | 提供者的授权端点 | 是 |
| `HUB_OAUTH_TOKEN_URL` | 提供者的令牌端点 | 是 |
| `HUB_OAUTH_USERINFO_URL` | 提供者的用户信息端点 | 是 |
| `HUB_OAUTH_USERINFO_PATH` | 从 JSON 响应中提取用户名的点分路径 | 是 |
| `HUB_OAUTH_REDIRECT_URI` | 覆盖回调 URL（为空时自动计算） | 否 |
| `HUB_OAUTH_SCOPES` | 附加范围（空格分隔） | 否 |
| `HUB_SESSION_SECRET` | 用于 cookie 签名的 32+ 字节十六进制字符串 | 建议 |

### 提供者示例

**Nextcloud：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub：**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` 是 JSON 响应中的点分路径。对于 Nextcloud 的 `{"ocs":{"data":{"id":"alice"}}}` 等嵌套对象，使用 `ocs.data.id`。

## 仪表板

Hub 在 `/_hub/dashboard` 包含一个自助服务仪表板。显示内容：

- 所有运行中的环境及其状态
- 服务链接（一键打开代码、终端或桌面）
- 空闲计时器和资源使用情况
- 启动/停止控制
- 管理员用户可以查看和管理所有容器

通过身份验证后访问 `https://code.example.com/_hub/dashboard` 进入仪表板。

## 示例

### 开发环境（VS Code + 终端 + 桌面）

使用 OpenVSCode Server、Web 终端（ttyd）和 noVNC 桌面的完整开发环境：

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Jupyter Notebook 环境

使用 JupyterLab 的数据科学环境：

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### 简单 Web 应用

用于 Web 框架的单服务环境：

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## 相关指南

- [**服务**](/zh/docs/services) -- Rediaccfile 生命周期、Compose 模式
- [**网络**](/zh/docs/networking) -- Docker 标签、Traefik 路由、TLS 证书
- [**备份与恢复**](/zh/docs/backup-restore) -- 工作空间持久化和恢复
- [**开发环境**](/zh/docs/development-environments) -- 用于开发环境的生产克隆
