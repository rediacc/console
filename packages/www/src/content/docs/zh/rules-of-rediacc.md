---
title: "Rediacc 规则"
description: "在 Rediacc 平台上构建应用程序的基本规则和约定。涵盖 Rediaccfile、compose、网络、存储、CRIU 和部署。"
category: "Guides"
order: 5
language: zh
sourceHash: "fd0fa925e9b76434"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Rediacc 规则

每个 Rediacc 仓库都在隔离的环境中运行，拥有独立的 Docker 守护进程、加密的 LUKS 卷和专用的 IP 范围。这些规则确保您的应用程序在此架构中正常工作。

## Rediaccfile

- **每个仓库都需要一个 Rediaccfile**, 一个包含生命周期函数的 bash 脚本。
- **生命周期函数**：`up()`、`down()`。可选：`info()`。
- `up()` 启动您的服务。`down()` 停止它们。
- `info()` 提供状态信息（容器状态、最近日志、健康状况）。
- Rediaccfile 由 renet source 加载, 它可以访问 shell 变量，而不仅仅是环境变量。

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

- **使用 `renet compose`，永远不要使用 `docker compose`**, renet 会注入网络隔离、主机网络、回环 IP 和服务标签。
- **不要在 compose 文件中设置 `network_mode`**, renet 会对所有服务强制设置 `network_mode: host`。您设置的任何值都会被覆盖。
- **不要设置 `rediacc.*` 标签**, renet 会自动注入 `rediacc.network_id`、`rediacc.service_ip` 和 `rediacc.service_name`。
- **`ports:` 映射在主机网络模式下被忽略**。为 HTTP 路由添加 `rediacc.service_port` 标签（没有此标签的服务不会获得 HTTP 路由）。使用 `rediacc.tcp_ports`/`rediacc.udp_ports` 标签进行 TCP/UDP 转发。
- **重启策略（`restart: always`、`on-failure` 等）可以安全使用**, renet 会自动剥离它们以兼容 CRIU。路由器 watchdog 会根据保存在 `.rediacc.json` 中的原始策略自动恢复已停止的容器。
- **危险设置默认被阻止**, `privileged: true`、`pid: host`、`ipc: host` 以及对系统路径的绑定挂载会被拒绝。使用 `renet compose --unsafe` 可自行承担风险覆盖此行为。

### 容器内的环境变量

Renet 会自动将以下变量注入每个容器：

| 变量 | 描述 |
|------|------|
| `SERVICE_IP` | 此容器的专用回环 IP |
| `REDIACC_NETWORK_ID` | 网络隔离 ID |

### 服务命名和路由

- compose 中的**服务名**成为自动路由 URL 前缀。
- **Grand repos**：`https://{service}.{repo}.{machine}.{baseDomain}`（例如：`https://myapp.marketing.server-1.example.com`）。
- **Fork repos**：`https://{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`（例如：`https://myapp-fork-staging.marketing.server-1.example.com`）。`-fork-` 分隔符可防止与 grand repo 服务名的 URL 冲突。Fork URL 始终使用父仓库现有的 wildcard 证书，因此不需要新证书。
- 对于自定义域名，请使用 Traefik 标签（注意：自定义域名不兼容 fork, 域名属于 grand repo）。

## 网络

- **每个仓库获得自己的 Docker 守护进程**，位于 `/var/run/rediacc/docker-<networkId>.sock`。
- **每个服务在 /26 子网内获得唯一的回环 IP**（例如 `127.0.24.192/26`）。
- **绑定是自动的**：服务可以绑定到 `0.0.0.0` 或 `localhost`，内核会透明地将地址重写为分配给服务的回环 IP。显式绑定到 `${SERVICE_IP}` 仍然有效，但不再是必需的。
- **健康检查可以使用 `localhost`** 或 `${SERVICE_IP}`。示例：`healthcheck: test: ["CMD", "curl", "-f", "http://localhost:8080/health"]`
- **跨仓库连接被内核阻止**：内核会自动阻止对仓库 `/26` 子网之外的回环 IP 的连接。一个仓库中的服务无法访问另一个仓库中的服务。
- **服务间通信**：使用**服务名**（例如 `db`、`redis`），renet 会自动将每个服务名注入为解析到正确 IP 的主机名。Docker DNS 名称在主机模式下无法工作，但通过 `/etc/hosts` 的服务名可以工作。避免在持久配置文件中嵌入 `${DB_IP}` 或类似内容（例如存储在数据库中的连接字符串），如果进行 fork，原始 IP 会被保留并指向错误的仓库。服务名始终按仓库正确解析。
- **仓库之间不可能发生端口冲突**, 每个仓库都有自己的 Docker 守护进程和 IP 范围。
- **TCP/UDP 端口转发**：添加标签以公开非 HTTP 端口：
  ```yaml
  labels:
    - "rediacc.tcp_ports=5432,3306"
    - "rediacc.udp_ports=53"
  ```

## 存储

- **所有 Docker 数据都存储在加密仓库内**, Docker 的 `data-root` 位于 LUKS 卷内的 `{mount}/.rediacc/docker/data`。命名卷、镜像和容器层全部加密、备份，并自动 fork。
- **推荐使用 `${REDIACC_WORKING_DIR}/...` 绑定挂载**以保持清晰，但命名卷也可以安全使用。
  ```yaml
  volumes:
    - ${REDIACC_WORKING_DIR}/data:/data        # 绑定挂载（推荐）
    - pgdata:/var/lib/postgresql/data      # 命名卷（同样安全）
  ```
- LUKS 卷挂载在 `/mnt/rediacc/mounts/<guid>/`。
- BTRFS 快照捕获整个 LUKS 后备文件，包括所有绑定挂载的数据。
- 数据存储是系统磁盘上固定大小的 BTRFS 池文件。使用 `rdc machine query --name <name> --system` 查看有效可用空间。使用 `rdc datastore resize` 扩容。

## CRIU（实时迁移）

- **通过标签选择性启用**：为需要创建检查点的容器添加 `rediacc.checkpoint=true`。没有此标签的容器（数据库、缓存）将全新启动并通过自身机制（WAL、LDF、AOF）恢复。
- **`repo down --checkpoint`** 在停止前保存进程状态，下次 `repo up` 自动恢复。**这是同机上的主要流程**，已验证可用。
- **`backup push --checkpoint`** 捕获已标记容器的运行进程内存 + 磁盘状态，然后将卷传输到另一台机器。在目标机器上通过 `repo up` 恢复。
- **`repo fork --checkpoint`** 在 fork 前捕获进程状态，并将检查点与 fork 一起 CoW 克隆。⚠️ 在同一台机器上，当父仓库仍在运行时，随后对 fork 执行的 `repo up` **目前会失败**，提示 `criu failed: type RESTORE errno 0`。上游 CRIU bug [checkpoint-restore/criu#478](https://github.com/checkpoint-restore/criu/issues/478) / [#514](https://github.com/checkpoint-restore/criu/issues/514)。原地保存/恢复请使用 `repo down --checkpoint`，跨机迁移请使用 `backup push --checkpoint`。
- **`repo up`** 自动检测检查点数据并在找到时恢复。使用 `--skip-checkpoint` 强制全新启动。
- **依赖感知恢复**：使用 compose 的 `depends_on` 先启动数据库（等待 healthy），然后再通过 CRIU 恢复应用容器。
- **TCP 连接在恢复后变为过期**，应用程序必须处理 `ECONNRESET` 并重新连接。在任何受支持的流程中，CRIU 都不会跨恢复保留活动的 TCP 连接状态。
- **Docker 实验模式**在每个仓库的守护进程上自动启用。
- **CRIU** 在 `rdc config machine setup` 期间安装。
- **`/etc/criu/runc.conf`** 默认配置了 `tcp-established`。
- **容器安全设置为已标记容器自动注入**，`renet compose` 会为带有 `rediacc.checkpoint=true` 的容器添加以下内容：
  - `cap_add`：`CHECKPOINT_RESTORE`、`SYS_PTRACE`、`NET_ADMIN`（内核 5.9+ 上 CRIU 的最小集合）
  - `security_opt`：`apparmor=unconfined`（CRIU 的 AppArmor 支持在上游尚不稳定）
  - `userns_mode: host`（CRIU 需要访问 init 命名空间中的 `/proc/pid/map_files`）
- 没有此标签的容器以更干净的安全姿态运行（无额外 capabilities）。
- Docker 的默认 seccomp 配置文件被保留，CRIU 使用 `PTRACE_O_SUSPEND_SECCOMP`（内核 4.3+）在 checkpoint/restore 期间临时暂停过滤器。
- **请勿在 compose 文件中手动设置 CRIU capabilities**，renet 会根据标签自动处理。
- 参见 [heartbeat 模板](https://github.com/rediacc/console/tree/main/packages/json/templates/monitoring/heartbeat) 了解 CRIU 兼容的参考实现。

### CRIU 兼容的应用模式

- 在所有持久连接（数据库连接池、WebSocket、消息队列）上处理 `ECONNRESET`。
- 使用支持自动重连的连接池库。
- 添加 `process.on("uncaughtException")` 作为内部库对象产生的陈旧套接字错误的安全网。
- 重启策略由 renet 自动管理（为 CRIU 剥离，watchdog 处理恢复）。
- 避免依赖 Docker DNS, 使用回环 IP 进行服务间通信。

### 按操作系统划分的主机安全策略

在五个官方支持的服务器操作系统（参见[系统要求](/en/docs/requirements)）上，每个仓库的 Docker 守护进程及其运行的容器均使用**默认容器标签**。`rdc config machine setup` 不会安装自定义 SELinux 策略或 AppArmor 配置文件。

- **Ubuntu 24.04 / openSUSE Leap 16.0**：AppArmor 默认启用。容器在默认的 docker-container 配置文件下运行。唯一的例外是 CRIU（对带有 `rediacc.checkpoint=true` 的容器添加 `apparmor=unconfined`，详见上方说明）。
- **Fedora 43 / Oracle Linux 10**：SELinux 默认以 enforcing 模式运行。容器获得标准的 `container_t` 上下文。无需安装额外的策略。如果某个设置步骤因 AVC 拒绝而失败，请参阅[故障排除: SELinux 拒绝](/en/docs/troubleshooting)。
- **Debian 13**：AppArmor 可用，但默认不对所有域强制执行。容器仍使用 docker-container 配置文件。

无需针对操作系统指定安全姿态标志；`rdc` 和 `renet` 会自动检测运行环境，在所有五个发行版上提供相同的仓库级隔离。

## 安全

- **LUKS 加密**对标准仓库是强制性的。每个仓库都有自己的加密密钥。
- **凭据存储在 CLI 配置中**（`~/.config/rediacc/rediacc.json`）。丢失配置意味着失去对加密卷的访问权限。
- **永远不要将凭据提交**到版本控制。使用 `env_file` 并在 `up()` 中生成密钥。
- **仓库隔离**：每个仓库的 Docker 守护进程、网络和存储与同一台机器上的其他仓库完全隔离。
- **代理隔离**：AI 代理默认以仅 fork 模式运行。每个仓库都有自己的 SSH 密钥，带有服务器端沙箱执行（ForceCommand `sandbox-gateway`）。所有连接都通过 Landlock LSM、OverlayFS home 覆盖层和每仓库 TMPDIR 进行沙箱隔离。跨仓库的文件系统访问被内核阻止。
- **仓库沙箱内 `sudo` 按设计被禁用。** Landlock 文件系统隔离要求 `NoNewPrivs`，这会阻止任何权限提升，因此 `sudo` 会以 `no new privileges flag is set` 失败。仓库的所有者用户已经拥有对仓库挂载和 Docker 套接字内所有内容所需的权限。对于确实需要特权的操作（安装主机软件包、内核调优），请在沙箱之外运行，或通过基础架构路径执行的 Rediaccfile `up()` 函数中运行。
- **每个仓库的 Docker daemon 都禁用了 bridge 网络。** 每个仓库的 `daemon.json` 都带有 `"bridge": "none"` 和 `"iptables": false`，因此一个简单的 `docker run <image>` 创建的容器只有 loopback 接口，没有出站连接。这不是 bug，而是跨仓库隔离的强制方式：阻止一个仓库访问另一个仓库 loopback IP 的内核级 eBPF 钩子，只对位于主机网络命名空间中的容器生效。生产服务请使用 `renet compose`，它会自动注入 `network_mode: host`。在 shell 中运行临时一次性容器时，请显式传递 `--network host`。

## 部署

- **`rdc repo up`** 如果 LUKS 卷未挂载则自动挂载，然后在所有 Rediaccfile 中执行 `up()`。
- **`rdc repo down`** 执行 `down()` 并停止 Docker 守护进程。
- **`rdc repo down --unmount`** 还会关闭 LUKS 卷（锁定加密存储）。
- **Fork**（`rdc repo fork`）创建具有新 GUID 和 networkId 的 CoW（写时复制）克隆，**耗时与仓库大小无关，是常数时间**。BTRFS reflink 只复制镜像元数据而非数据，因此 100 GB 的仓库 fork 和 1 GB 的仓库 fork 一样只需几秒钟。Fork 共享父级的加密密钥。
- **接管**（`rdc repo takeover <fork> -m <machine>`）将 grand 仓库的数据替换为 fork 的数据。Grand 保留其身份（GUID、networkId、域名、自动启动、备份链）。旧的生产数据作为备份 fork 保留。用途：在 fork 上测试升级，验证后接管到生产。使用 `rdc repo takeover <backup-fork> -m <machine>` 回滚。
- **代理路由**在部署后约 3 秒后变为活跃。`repo up` 期间的 "Proxy is not running" 警告在 ops/dev 环境中是信息性的。
- **`rdc repo up` 和 `rdc repo fork --up` 会在部署结束时打印带有 `rediacc.service_port` 标签的服务的 URL 模式**。将 `{service}` 替换为你暴露的服务名以获得确切的 URL。没有 `rediacc.service_port` 的服务（数据库、工作进程）不会获得路由，也不会显示。

## 常见错误

- 使用 `docker compose` 而不是 `renet compose`, 容器将无法获得网络隔离。
- 重启策略是安全的, renet 自动剥离它们，watchdog 处理恢复。
- 使用 `privileged: true`, 没有必要，renet 会改为注入特定的 CRIU capabilities。
- 在持久配置文件中硬编码原始 IP - 连接请使用服务名以保持 fork 隔离的完整性。
- 使用 `rdc term connect -c` 作为失败命令的变通方法, 请改为报告 bug。
- `repo delete` 执行完整清理，包括回环 IP 和 systemd 单元。运行 `rdc machine prune <name>` 清理旧版删除操作遗留的残余。
