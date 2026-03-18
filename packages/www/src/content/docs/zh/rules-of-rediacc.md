---
title: "Rediacc 规则"
description: "在 Rediacc 平台上构建应用程序的基本规则和约定。涵盖 Rediaccfile、compose、网络、存储、CRIU 和部署。"
category: "Guides"
order: 5
language: zh
sourceHash: "091701909c0c8d32"
sourceCommit: "ebe4a9b9ea6ace2a0faee3694a632135cd61ef9b"
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
| `REDIACC_WORKING_DIR` | `/mnt/rediacc/mounts/abc123/` | 已挂载仓库的根路径 |
| `REDIACC_NETWORK_ID` | `6336` | 网络隔离标识符 |
| `REDIACC_REPOSITORY` | `abc123-...` | 仓库 GUID |
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
- **重启策略（`restart: always`、`on-failure` 等）可以安全使用** — renet 会自动剥离它们以兼容 CRIU。路由器 watchdog 会根据保存在 `.rediacc.json` 中的原始策略自动恢复已停止的容器。
- **危险设置默认被阻止** — `privileged: true`、`pid: host`、`ipc: host` 以及对系统路径的绑定挂载会被拒绝。使用 `renet compose --unsafe` 可自行承担风险覆盖此行为。

### 容器内的环境变量

Renet 会自动将以下变量注入每个容器：

| 变量 | 描述 |
|------|------|
| `SERVICE_IP` | 此容器的专用回环 IP |
| `REDIACC_NETWORK_ID` | 网络隔离 ID |

### 服务命名和路由

- The compose **service name** becomes the auto-route URL prefix.
- **Grand repos**: `https://{service}.{repo}.{machine}.{baseDomain}` (e.g., `https://myapp.marketing.server-1.example.com`).
- **Fork repos**: `https://{service}-{tag}.{machine}.{baseDomain}` — uses the machine wildcard cert to avoid Let's Encrypt rate limits.
- For custom domains, use Traefik labels (but note: custom domains are NOT fork-friendly — the domain belongs to the grand repo).

## 网络

- **每个仓库获得自己的 Docker 守护进程**，位于 `/var/run/rediacc/docker-<networkId>.sock`。
- **每个服务在 /26 子网内获得唯一的回环 IP**（例如 `127.0.24.192/26`）。
- **绑定到 `SERVICE_IP`** — 每个服务获得唯一的回环 IP。
- **健康检查必须使用 `${SERVICE_IP}`**，而不是 `localhost`。示例：`healthcheck: test: ["CMD", "curl", "-f", "http://${SERVICE_IP}:8080/health"]`
- **服务间通信**：使用回环 IP 或 `SERVICE_IP` 环境变量。Docker DNS 名称在主机模式下不起作用。
- **仓库之间不可能发生端口冲突** — 每个仓库都有自己的 Docker 守护进程和 IP 范围。
- **TCP/UDP 端口转发**：添加标签以公开非 HTTP 端口：
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## 存储

- **所有 Docker 数据都存储在加密仓库内** — Docker 的 `data-root` 位于 LUKS 卷内的 `{mount}/.rediacc/docker/data`。命名卷、镜像和容器层全部加密、备份，并自动 fork。
- **推荐使用 `${REDIACC_WORKING_DIR}/...` 绑定挂载**以保持清晰，但命名卷也可以安全使用。
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # 绑定挂载（推荐）
    - pgdata:/var/lib/postgresql/data      # 命名卷（同样安全）
  ```
- LUKS 卷挂载在 `/mnt/rediacc/mounts/<guid>/`。
- BTRFS 快照捕获整个 LUKS 后备文件，包括所有绑定挂载的数据。
- 数据存储是系统磁盘上固定大小的 BTRFS 池文件。使用 `rdc machine query <name> --system` 查看有效可用空间。使用 `rdc datastore resize` 扩容。

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
- 重启策略由 renet 自动管理（为 CRIU 剥离，watchdog 处理恢复）。
- 避免依赖 Docker DNS — 使用回环 IP 进行服务间通信。

## 安全

- **LUKS 加密**对标准仓库是强制性的。每个仓库都有自己的加密密钥。
- **凭据存储在 CLI 配置中**（`~/.config/rediacc/rediacc.json`）。丢失配置意味着失去对加密卷的访问权限。
- **永远不要将凭据提交**到版本控制。使用 `env_file` 并在 `up()` 中生成密钥。
- **仓库隔离**：每个仓库的 Docker 守护进程、网络和存储与同一台机器上的其他仓库完全隔离。
- **代理隔离**：AI 代理默认以仅 fork 模式运行。每个仓库都有自己的 SSH 密钥，带有服务器端沙箱执行（ForceCommand `sandbox-gateway`）。所有连接都通过 Landlock LSM、OverlayFS home 覆盖层和每仓库 TMPDIR 进行沙箱隔离。跨仓库的文件系统访问被内核阻止。

## 部署

- **`rdc repo up`** 在所有Rediaccfile中执行 `up()`。
- **`rdc repo up --mount`** 先打开 LUKS 卷，然后执行生命周期。在 `backup push` 到新机器后需要此选项。
- **`rdc repo down`** 执行 `down()` 并停止 Docker 守护进程。
- **`rdc repo down --unmount`** 还会关闭 LUKS 卷（锁定加密存储）。
- **Fork**（`rdc repo fork`）创建具有新 GUID 和 networkId 的 CoW（写时复制）克隆。Fork 共享父级的加密密钥。
- **接管**（`rdc repo takeover <fork> -m <machine>`）将 grand 仓库的数据替换为 fork 的数据。Grand 保留其身份（GUID、networkId、域名、自动启动、备份链）。旧的生产数据作为备份 fork 保留。用途：在 fork 上测试升级，验证后接管到生产。使用 `rdc repo takeover <backup-fork> -m <machine>` 回滚。
- **代理路由**在部署后约 3 秒后变为活跃。`repo up` 期间的 "Proxy is not running" 警告在 ops/dev 环境中是信息性的。

## 常见错误

- 使用 `docker compose` 而不是 `renet compose` — 容器将无法获得网络隔离。
- 重启策略是安全的 — renet 自动剥离它们，watchdog 处理恢复。
- 使用 `privileged: true` — 没有必要，renet 会改为注入特定的 CRIU capabilities。
- 不绑定到 `SERVICE_IP` — 会导致仓库之间的端口冲突。
- 硬编码 IP — 使用 `SERVICE_IP` 环境变量；IP 按 networkId 动态分配。
- 在 `backup push` 后首次部署时忘记 `--mount` — LUKS 卷需要显式打开。
- 使用 `rdc term -c` 作为失败命令的变通方法 — 请改为报告 bug。
- `repo delete` 执行完整清理，包括回环 IP 和 systemd 单元。运行 `rdc machine prune <name>` 清理旧版删除操作遗留的残余。
