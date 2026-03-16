---
title: "Rediacc 规则"
description: "在 Rediacc 平台上构建应用程序的基本规则和约定。涵盖 Rediaccfile、compose、网络、存储、CRIU 和部署。"
category: "Guides"
order: 5
language: zh
sourceHash: 166f333b848c718b
sourceCommit: "ecb32701b07b8536282aea0d26f58ef06296288b"
---

# Rediacc 规则

每个 Rediacc 仓库都在隔离的环境中运行，拥有独立的 Docker 守护进程、加密的 LUKS 卷和专用的 IP 范围。这些规则确保您的应用程序在此架构中正常工作。

## Rediaccfile

- **每个仓库都需要一个 Rediaccfile** — 一个包含生命周期函数的 bash 脚本。
- **生命周期函数**：`up()`、`down()`。可选：`info()`。
- `up()` 启动您的服务。`down()` 停止它们。
- `info()` 提供状态信息（容器状态、最近日志、健康状况）。
- Rediaccfile 由 renet source 加载 — 它可以访问 shell 变量，而不仅仅是环境变量。

### Rediaccfile 中可用的环境变量

| 变量 | 示例 | 描述 |
|------|------|------|
| `REPOSITORY_PATH` | `/mnt/rediacc/mounts/abc123/` | 已挂载仓库的根路径 |
| `REPOSITORY_NETWORK_ID` | `6336` | 网络隔离标识符 |
| `REPOSITORY_NAME` | `abc123-...` | 仓库 GUID |
| `{SVCNAME}_IP` | `HEARTBEAT_IP=127.0.24.195` | 每个服务的回环 IP（服务名称大写） |

### 最小化 Rediaccfile

```bash
#!/bin/bash

_compose() {
  renet compose -- "$@"
}

up() {
  _compose up -d
}

down() {
  _compose down
}
```

## Compose

- **使用 `renet compose`，永远不要使用 `docker compose`** — renet 会注入网络隔离、主机网络、回环 IP 和服务标签。
- **不要在 compose 文件中设置 `network_mode`** — renet 会对所有服务强制设置 `network_mode: host`。您设置的任何值都会被覆盖。
- **不要设置 `rediacc.*` 标签** — renet 会自动注入 `rediacc.network_id`、`rediacc.service_ip` 和 `rediacc.service_name`。
- **`ports:` 映射在主机网络模式下被忽略**。使用 `rediacc.service_port` 标签将代理路由到非 80 端口。
- **不要使用 `restart: always` 或 `restart: unless-stopped`** — 这些与 CRIU 的 checkpoint/restore 冲突。使用 `restart: on-failure` 或省略它。
- **不要使用 Docker 命名卷** — 它们位于加密仓库之外，不会包含在备份或 fork 中。

### 容器内的环境变量

Renet 会自动将以下变量注入每个容器：

| 变量 | 描述 |
|------|------|
| `SERVICE_IP` | 此容器的专用回环 IP |
| `REPOSITORY_NETWORK_ID` | 网络隔离 ID |

### 服务命名和路由

- compose 中的**服务名称**会成为自动路由的 URL 前缀。
- 示例：基础域名为 `example.com`、networkId 为 6336 的服务 `myapp` 变为 `https://myapp-6336.example.com`。
- 对于自定义域名，使用 Traefik 标签（注意：自定义域名与 fork 不兼容）。

## 网络

- **每个仓库获得自己的 Docker 守护进程**，位于 `/var/run/rediacc/docker-<networkId>.sock`。
- **每个服务在 /26 子网内获得唯一的回环 IP**（例如 `127.0.24.192/26`）。
- **绑定到 `SERVICE_IP`**，而不是 `0.0.0.0` — 主机网络意味着 `0.0.0.0` 会与其他仓库冲突。
- **服务间通信**：使用回环 IP 或 `SERVICE_IP` 环境变量。Docker DNS 名称在主机模式下不起作用。
- **仓库之间不可能发生端口冲突** — 每个仓库都有自己的 Docker 守护进程和 IP 范围。
- **TCP/UDP 端口转发**：添加标签以公开非 HTTP 端口：
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## 存储

- **所有持久数据必须使用 `${REPOSITORY_PATH}/...` 绑定挂载。**
  ```yaml
  volumes:
    - ${REPOSITORY_PATH}/data:/data
    - ${REPOSITORY_PATH}/config:/etc/myapp
  ```
- Docker 命名卷位于 LUKS 仓库之外 — 它们**未加密**、**未备份**且**不包含在 fork 中**。
- LUKS 卷挂载在 `/mnt/rediacc/mounts/<guid>/`。
- BTRFS 快照捕获整个 LUKS 后备文件，包括所有绑定挂载的数据。

## CRIU（实时迁移）

- **`backup push --checkpoint`** 捕获运行中进程的内存 + 磁盘状态。
- **`repo up --mount --checkpoint`** 从检查点恢复容器（无需全新启动）。
- **TCP 连接在恢复后变得陈旧** — 应用程序必须处理 `ECONNRESET` 并重新连接。
- **Docker 实验模式**在每个仓库的守护进程上自动启用。
- **CRIU** 在 `rdc config machine setup` 期间安装。
- **`/etc/criu/runc.conf`** 配置了 `tcp-established` 以保持 TCP 连接。
- **容器安全设置由 renet 自动注入** — `renet compose` 会自动为每个容器添加以下内容以确保 CRIU 兼容性：
  - `cap_add`：`CHECKPOINT_RESTORE`、`SYS_PTRACE`、`NET_ADMIN`（内核 5.9+ 上 CRIU 的最小集）
  - `security_opt`：`apparmor=unconfined`（CRIU 的 AppArmor 支持在上游尚不稳定）
  - `userns_mode: host`（CRIU 需要 init 命名空间访问权限以访问 `/proc/pid/map_files`）
- Docker 的默认 seccomp 配置文件被保留 — CRIU 使用 `PTRACE_O_SUSPEND_SECCOMP`（内核 4.3+）在 checkpoint/restore 期间临时暂停过滤器。
- **不要在 compose 文件中手动设置这些** — renet 会处理。自行设置有重复或冲突的风险。
- 参见 [heartbeat 模板](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) 了解 CRIU 兼容的参考实现。

### CRIU 兼容的应用模式

- 在所有持久连接（数据库连接池、WebSocket、消息队列）上处理 `ECONNRESET`。
- 使用支持自动重连的连接池库。
- 添加 `process.on("uncaughtException")` 作为内部库对象产生的陈旧套接字错误的安全网。
- 避免使用 `restart: always` — 它会干扰 CRIU 恢复。
- 避免依赖 Docker DNS — 使用回环 IP 进行服务间通信。

## 安全

- **LUKS 加密**对标准仓库是强制性的。每个仓库都有自己的加密密钥。
- **凭据存储在 CLI 配置中**（`~/.config/rediacc/rediacc.json`）。丢失配置意味着失去对加密卷的访问权限。
- **永远不要将凭据提交**到版本控制。使用 `env_file` 并在 `up()` 中生成密钥。
- **仓库隔离**：每个仓库的 Docker 守护进程、网络和存储与同一台机器上的其他仓库完全隔离。
- **代理隔离**：AI 代理默认以仅 fork 模式运行，只能修改 fork 仓库，不能修改 grand（原始）仓库。通过 `term_exec` 或带仓库上下文的 `rdc term` 执行的命令会使用 Landlock LSM 在内核级进行沙箱隔离，从而阻止跨仓库文件系统访问。

## 部署

- **`rdc repo up`** 在所有Rediaccfile中执行 `up()`。
- **`rdc repo up --mount`** 先打开 LUKS 卷，然后执行生命周期。在 `backup push` 到新机器后需要此选项。
- **`rdc repo down`** 执行 `down()` 并停止 Docker 守护进程。
- **`rdc repo down --unmount`** 还会关闭 LUKS 卷（锁定加密存储）。
- **Fork**（`rdc repo fork`）创建具有新 GUID 和 networkId 的 CoW（写时复制）克隆。Fork 共享父级的加密密钥。
- **代理路由**在部署后约 3 秒后变为活跃。`repo up` 期间的 "Proxy is not running" 警告在 ops/dev 环境中是信息性的。

## 常见错误

- 使用 `docker compose` 而不是 `renet compose` — 容器将无法获得网络隔离。
- 使用 `restart: always` — 阻止 CRIU 恢复并干扰 `repo down`。
- 使用 Docker 命名卷 — 数据未加密、未备份、不会被 fork。
- 绑定到 `0.0.0.0` — 在主机网络模式下导致仓库之间的端口冲突。
- 硬编码 IP — 使用 `SERVICE_IP` 环境变量；IP 按 networkId 动态分配。
- 在 `backup push` 后首次部署时忘记 `--mount` — LUKS 卷需要显式打开。
- 使用 `rdc term -c` 作为失败命令的变通方法 — 请改为报告 bug。
