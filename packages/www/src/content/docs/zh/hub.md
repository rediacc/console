---
title: "Hub"
description: "提供经过身份验证的按用户容器化环境，支持每用户 Docker daemon、多模板选择、CRIU 检查点/恢复、审计日志和 data-root 垃圾回收。"
category: "Guides"
order: 14
language: zh
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Hub 在 OAuth 认证之后为每个用户提供独立的容器化环境。用户访问单一 URL，通过任意 OAuth2 提供商完成认证，随即被透明路由至各自的专属容器。容器按需创建，每位用户拥有独立的 Docker daemon，闲置会话通过 CRIU 检查点保存以实现即时恢复。

所有配置均通过 `docker-compose.yml` 标签完成。Hub 本身作为主机 systemd 服务运行，由仓库 Compose 文件中的 `renet hub install` 命令生成。仓库定义行为，Hub 负责认证、路由、生命周期管理以及用户间的隔离。

## 工作原理

1. 用户访问 `code.example.com`（或 `term.`、`desktop.`，或其他任何已配置的前缀）。
2. Hub 检查会话 Cookie。若不存在，则将用户重定向到已配置的 OAuth2 提供商（Nextcloud、Keycloak、GitHub 等）。
3. 认证完成后，Hub 识别用户并查找其容器。
4. 若容器不存在，Hub 在主机上为该用户创建专用的 Docker daemon，随后启动其容器。
5. 请求通过 loopback 网络反向代理至用户容器。
6. 闲置容器会进行 CRIU 检查点保存，同时停止该用户的 daemon 以释放内存。下次登录时 daemon 重新启动，CRIU 在数秒内恢复容器状态。

## 快速开始

在仓库的 `docker-compose.yml` 中将 Hub 添加为服务。该服务标记为 `install_as=systemd`，以便作为主机服务而非 Docker 容器运行（用户级 daemon 管理需要 systemd 支持）。

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # 路由映射：子域名前缀 -> 用户容器端口
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # 容器模板
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik 路由（文件提供商；rediacc-router 也读取这些标签）
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

使用 OAuth2 提供商凭据创建 `hub/.env`：

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

安装主机 systemd 单元（一次性操作，需要 root 权限）：

```bash
sudo renet hub install /path/to/docker-compose.yml
```

此命令读取 `install_as=systemd` 服务并写入：

- `/etc/systemd/system/rediacc-hub.service`（单元文件）
- `/etc/rediacc/hub/hub.labels.yaml`（模板标签）
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml`（Traefik 文件提供商路由）

然后执行 `systemctl daemon-reload && systemctl enable --now rediacc-hub`。若要移除：`sudo renet hub uninstall /path/to/docker-compose.yml`。

## install 命令参考

| 命令 | 用途 |
|---------|---------|
| `sudo renet hub install <compose-file>` | 将 Compose 文件中的 `install_as=systemd` 服务转换为主机制品并启动单元。 |
| `sudo renet hub uninstall <compose-file>` | 停止、禁用并删除服务的所有制品。`<workspace>/<user>-docker/` 下的 data-root 将被保留。 |
| `sudo renet hub gc <workspace-dir>` | 清理废弃的用户 data-root（默认：无活跃 daemon 超过 30 天）。标志：`--max-age=30d`、`--dry-run`。 |
| `renet hub status` | 通过运行中的 Hub API 获取所有容器的 JSON 状态。 |
| `renet hub stop <username>` | 停止指定用户的容器。 |

## 配置

所有 Hub 配置均位于 Hub 服务的 Compose 标签中。密钥（OAuth client_secret、session_secret）放入 `hub/.env`，不放入标签。

### 路由映射

将子域名前缀映射到用户容器上的端口。Hub 读取这些标签以确定将每个请求代理到何处。

| 标签 | 描述 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | 将 `{prefix}.{domain}` 映射到用户容器的该端口 | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

每条路由还需要一个指向 Hub 端口（7112）的匹配 Traefik 路由器。Hub 根据主机名在内部处理用户级路由。

### 容器模板

定义用户容器的外观。Hub 读取这些标签，在创建新容器时使用。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.image` | 容器镜像 | `--container-image` 标志的值 |
| `rediacc.hub.command` | 启动命令（bash -c 兼容） | 无 |
| `rediacc.hub.user` | 容器用户（建议非 root） | `vscode` |
| `rediacc.hub.workspace` | 容器内的工作区挂载点 | `/workspace` |
| `rediacc.hub.shm_size` | 共享内存大小（字节） | `1073741824`（1 GB） |
| `rediacc.hub.docker` | `per-user` 为每个用户创建专用 dockerd（强烈建议） | `""` |

`command` 标签支持 `${SERVICE_IP}` 和 `__SERVICE_IP__` 扩展（后者避免 Compose 预展开），用于容器分配的 loopback IP。

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### 每用户 Docker Daemon

当设置 `rediacc.hub.docker=per-user` 时，每位用户在主机上获得专用的 `dockerd` 实例，以 `/var/run/docker.sock` 的形式挂载到其容器内。这提供了：

- 无需特权容器或 Docker-in-Docker，即可在用户环境内完整使用 `docker ps`、`docker run`、`docker build`。
- 用户间的完全隔离（用户 A 无法看到用户 B 的容器或镜像）。
- 每用户 BTRFS data-root 位于 `<workspace-dir>/<user>-docker/.rediacc/docker/data`，在会话间持久保存，使缓存镜像能够跨越闲置检查点周期。

Daemon 在以 32768 起始的专用网络 ID 范围内分配。每个用户 data-root 中的 `.networkid` 标记文件记录其分配的 ID，使回访用户能够获得同一 daemon。

### 资源限制

设置每用户资源限制，防止单个用户耗尽所有主机资源。限制同时适用于用户容器及其每用户 dockerd 实例（通过 systemd `CPUQuota=` / `MemoryMax=`）。

| 标签 | 描述 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota 值 | `200%`（2 核） |
| `rediacc.hub.limits.memory` | systemd MemoryMax 值 | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemon 被放置在 `rediacc.slice` systemd 切片中，以继承切片级别的限制。

### 多模板支持

提供多种环境类型。用户在登录时通过访问 `https://code.example.com/_hub/login?template=python` 选择模板（选择通过 OAuth state 传递）。在后续登录时切换模板会重建容器。

使用 `rediacc.hub.templates.<name>.<field>` 标签定义模板。扁平的 `rediacc.hub.image` / `rediacc.hub.command` 等标签继续为未选择模板的用户定义隐式"默认"模板。

```yaml
labels:
  # 省略 ?template=... 时的默认模板。
  - "rediacc.hub.template=fulldev"

  # 完整的 VS Code + 桌面 + 终端环境。
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # 仅 VS Code，轻量版。
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python 专用环境。
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### 生命周期钩子

在生命周期节点于用户容器内运行命令。钩子以容器用户身份运行（非 root）。

| 标签 | 触发时机 | 示例 |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | 容器创建后（首次登录） | 克隆仓库、安装依赖 |
| `rediacc.hub.hook.checkpoint.pre_dump` | 对闲置会话进行 CRIU 检查点之前 | 停止无法被检查点保存的 daemon（X server、dbus） |
| `rediacc.hub.hook.checkpoint.post_restore` | CRIU 恢复之后 | 重启在 pre_dump 中停止的 daemon |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### 检查点 / 恢复

设置 `--checkpoint` 后，闲置的用户容器会进行 CRIU 检查点保存，同时停止其每用户 daemon 以释放内存。下次登录时 daemon 重新启动，CRIU 从磁盘恢复容器状态，保留打开的文件、运行中的进程和终端会话。典型恢复时间为数秒，与工作负载无关。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | 为用户容器启用 CRIU 检查点 | `false` |

在 Hub 命令中传入 `--checkpoint` 及非零的 `--idle-timeout`（例如 `30m`）。检查点目录位于 `<workspace-dir>/<user>/.checkpoint/`。

若 CRIU 对某用户连续失败 3 次，则该用户的检查点功能将被禁用，回退策略变为停止并重建。

### 临时模式

默认情况下，用户工作区是持久的（重启后仍保留）。临时模式在每次登录时提供干净的环境，适用于演示、培训或 CI。

| 标签 | 描述 | 默认值 |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` 或 `ephemeral` | `persistent` |

在临时模式下，工作区使用 tmpfs（内存支持），容器停止时自动删除。

### 闲置超时

| 标志 | 描述 | 默认值 |
|------|-------------|---------|
| `--idle-timeout=<dur>` | 对闲置时间超过此值的容器执行停止/检查点 | `0`（禁用） |

`0` 使容器永久运行。实际推荐值为 `30m`：闲置用户在半小时后释放内存，回访用户通过 CRIU 在数秒内恢复。

### 访问控制

| 变量 | 描述 |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | 以逗号分隔的允许使用 Hub 的用户组（当提供商暴露组声明时） |
| `HUB_ADMIN_USERS` | 以逗号分隔的管理员用户名。管理员可在仪表板中查看并控制其他用户的容器。 |

## 审计日志

每用户 daemon 上的每个由用户发起的容器/镜像事件（create、start、stop、destroy、kill、pull、push）均以换行符分隔的 JSON 记录追加到 `/var/log/rediacc/hub/<user>.log`：

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

条目在 CRIU 检查点/恢复后仍然保留（恢复时审计流会重新武装）。使用 `logrotate` 控制磁盘用量；示例配置：

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## 仪表板

Hub 在 `/_hub/dashboard` 提供自助服务仪表板，显示：

- 所有运行中的环境及其状态
- 已选择的模板
- 服务链接（一键打开代码、终端、桌面或其他任意路由）
- 闲置计时器
- 每用户磁盘用量、运行容器数量和镜像数量
- 管理员可查看所有容器；普通用户仅能看到自己的

统计数据每 30 秒采样一次。

## Data-Root 垃圾回收

在长期运行的主机上，每用户 data-root 会不断积累。调度 `renet hub gc` 来清理废弃的 data-root。systemd 定时器非常适合此用途：

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` 仅记录候选项，不执行删除。当 `.networkid` 标记文件的时间早于 `--max-age` 且记录的 daemon 不再在主机上配置时，该 data-root 即符合清理条件。

## OAuth 配置

Hub 支持任何标准 OAuth2 提供商，通过环境变量进行配置。

| 变量 | 描述 | 是否必需 |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 客户端 ID | 是 |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 客户端密钥 | 是 |
| `HUB_OAUTH_AUTHORIZE_URL` | 提供商的授权端点 | 是 |
| `HUB_OAUTH_TOKEN_URL` | 提供商的令牌端点 | 是 |
| `HUB_OAUTH_USERINFO_URL` | 提供商的用户信息端点 | 是 |
| `HUB_OAUTH_USERINFO_PATH` | 从 JSON 响应中提取用户名的点分路径 | 是 |
| `HUB_OAUTH_REDIRECT_URI` | 覆盖回调 URL（为空时自动计算） | 否 |
| `HUB_OAUTH_SCOPES` | 额外的授权范围（空格分隔） | 否 |
| `HUB_SESSION_SECRET` | 用于 Cookie 签名的 32+ 字节十六进制字符串 | 建议设置 |

### 提供商示例

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

## 示例

### 开发环境（VS Code + 终端 + 桌面）

包含 OpenVSCode Server、Web 终端（ttyd）和 noVNC 桌面的完整开发环境。用户在其中拥有自己的 Docker daemon。

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... 每个前缀对应的 Traefik 路由器 ...
```

### Jupyter Notebook 环境

使用 JupyterLab 的数据科学环境：

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### 简单 Web 应用（临时模式）

每次登录从头开始的单服务环境：

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## 相关指南

- [**服务**](/zh/docs/services) -- Rediaccfile 生命周期、Compose 模式
- [**网络**](/zh/docs/networking) -- Docker 标签、Traefik 路由、TLS 证书
- [**备份与恢复**](/zh/docs/backup-restore) -- 工作区持久性与恢复
- [**开发环境**](/zh/docs/development-environments) -- 面向开发环境的生产克隆
