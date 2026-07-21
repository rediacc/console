---
title: 架构
description: >-
  Rediacc 的工作原理：双工具架构、适配器检测、安全模型和配置结构。
category: Concepts
order: 0
language: zh
sourceHash: "16b02000a82f3acd"
sourceCommit: "5fab1177d6ceae5211c25cf8fa0176d67259d40e"
---

# 架构

概括地说：rdc 运行在您的工作站，renet 运行在您的服务器，两者通过 SSH 通信。Rediacc 的整个架构都建立在这种划分之上。本页介绍这两个工具如何划分职责、适配器检测如何路由状态、安全模型的样子，以及配置的结构。

## 全栈概览

流量从互联网经由反向代理流入隔离的 Docker 守护进程，每个守护进程均由加密存储提供支撑：

![全栈架构](/img/arch-full-stack.svg)

每个仓库拥有独立的 Docker 守护进程、loopback IP 子网（/26 = 64 个 IP）以及 LUKS 加密的 BTRFS 卷。路由服务器发现所有守护进程上运行的容器，并将路由配置提供给 Traefik。

## 双工具架构

Rediacc 采用两个通过 SSH 协同工作的二进制文件：

![双工具架构](/img/arch-two-tool.svg)

- **rdc** 运行在您的工作站上（macOS、Linux 或 Windows）。它读取您的本地配置，通过 SSH 连接到远程机器，并调用 renet 命令。
- **renet** 以 root 权限运行在远程服务器上。它管理 LUKS 加密磁盘映像、隔离的 Docker 守护进程、服务编排和反向代理配置。

您在本地输入的每条命令都会转化为一个 SSH 调用，在远程机器上执行 renet。您无需手动 SSH 登录服务器。

如需以运维为中心的使用规则，请参阅 [rdc vs renet](/en/docs/rdc-vs-renet)。您也可以使用 `rdc ops` 运行本地虚拟机集群进行测试，请参阅[实验性虚拟机](/en/docs/experimental-vms)。

## 配置

所有 CLI 状态存储在 `~/.config/rediacc/` 下的扁平 JSON 配置文件中。

所有状态存储在工作站的配置文件中（例如 `~/.config/rediacc/rediacc.json`）。

- 直接通过 SSH 连接到机器
- 无需外部服务
- 默认配置会在首次使用 CLI 时自动创建。命名配置通过 `rdc config init <name>` 创建
- 可选的加密配置同步将同一文件存储在配置存储中，按团队限定范围

## rediacc 用户

运行 `rdc machine setup` 时，renet 会在远程服务器上创建一个名为 `rediacc` 的系统用户：

- **UID**：7111
- **Shell**：`/sbin/nologin`（无法通过 SSH 登录）
- **用途**：拥有仓库文件并运行 Rediaccfile 函数

`rediacc` 用户无法直接通过 SSH 访问。rdc 以您配置的 SSH 用户（例如 `deploy`）连接，renet 通过 `sudo -u rediacc /bin/sh -c '...'` 执行仓库操作。这意味着：

1. 您的 SSH 用户需要 `sudo` 权限
2. 所有仓库数据归 `rediacc` 用户所有，而非您的 SSH 用户
3. Rediaccfile 函数（`up()`、`down()`）以 `rediacc` 用户身份运行

这种分离确保仓库数据具有一致的所有权，不受管理它的 SSH 用户影响。

## Docker 隔离

每个仓库拥有自己的隔离 Docker 守护进程。当仓库被挂载时，renet 会启动一个专用的 `dockerd` 进程，使用唯一的套接字：

![Docker 隔离](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

例如，网络 ID 为 `2816` 的仓库使用：
```
/var/run/rediacc/docker-2816.sock
```

这意味着：
- 不同仓库的容器彼此不可见
- 每个仓库拥有独立的镜像缓存、网络和卷
- 主机的 Docker 守护进程（如果有的话）完全独立

Rediaccfile 函数会自动设置 `DOCKER_HOST` 为正确的套接字。

当 AI 智能体通过 `rdc term connect <repo>` 进入仓库时，同样的隔离机制适用：会话以非特权 `rediacc` 用户（UID 7111）身份运行，处于独立的挂载命名空间中，且 `DOCKER_HOST` 仅限于该单个仓库的守护进程套接字。fork 优先工作流将这种运行时隔离与 CoW 克隆原语结合：智能体在每个任务的 fork 上操作，绝不在主（生产）仓库上操作。完整的沙箱模型、覆盖语义以及外部服务凭据的开发者责任边界，请参阅 [AI 智能体安全与防护机制](/en/docs/ai-agents-safety)。

### 守护进程路径布局

Docker 数据和配置存储在仓库的挂载点内部，使每个守护进程与主机及其他仓库完全隔离。

**每仓库布局：**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker 数据根目录
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker 配置
```

**独立布局**（未挂载到仓库挂载点的守护进程）：
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**共享运行时路径**（不变）：
```
/run/rediacc/docker-{N}.sock
```

这种统一布局消除了守护进程路径在主机文件系统和加密卷之间分割时出现的只读与读写挂载冲突。每仓库守护进程和独立守护进程遵循相同的目录结构，因此工具和诊断在两种情况下均以相同方式工作。

## LUKS 加密

仓库是存储在服务器数据存储中（默认：`/mnt/rediacc`）的 LUKS 加密磁盘映像。每个仓库：

1. 拥有一个随机生成的加密密码短语（"凭据"）
2. 以文件形式存储：`{datastore}/repos/{guid}.img`
3. 访问时通过 `cryptsetup` 挂载

凭据存储在本地配置文件中，但**绝不**存储在服务器上。没有凭据，仓库数据将无法读取。启用开机自启时，会在服务器上存储一个辅助 LUKS 密钥文件，以便启动时自动挂载。

## 存储后端

数据存储（datastore）是每台机器上容纳仓库镜像的存储池。它有两种后端，在 `datastore init` 时选择：

- **本地（默认）**：机器自身磁盘上基于 loop 设备的 BTRFS 文件系统。仓库镜像是其中的 LUKS 加密文件；fork 只是一次 `cp --reflink=always`。这是每一个单机部署都使用的后端，除了服务器自身的磁盘外不需要任何其他东西。
- **Ceph RBD**：数据存储位于从外部 Ceph 集群映射的 RBD 镜像上，其上是普通的 BTRFS（此层没有 LUKS，因为 Ceph 节点从不打开 LUKS）。fork 和只读多客户端架构使用 RBD 自身的写时复制（copy-on-write）原语（snapshot、protect、clone）以及 RADOS 命名空间实现按租户隔离。

两种后端为其上层的一切呈现相同的仓库模型，因此 `repo` 命令、备份和 fork 的行为完全一致。区别在于字节实际存储在哪里，以及 fork 使用哪种写时复制机制（BTRFS reflink 还是 RBD 克隆）。有关如何初始化每种后端，请参阅[机器设置](/en/docs/setup)；有关 renet 层面的数据存储命令，请参阅[服务器参考](/en/docs/server-reference)。

## Kubernetes 仓库

除了 Docker 仓库外，一台机器还可以承载**集群**。Rediacc 通过反转通常的对象模型来保持仓库理念：集群就是容器，而 Kubernetes 仓库就是其中的一个命名空间。

- 集群状态（每个节点的 k3s 数据目录）存储在由数据存储支持的写时复制镜像文件中，每个节点一个，因此集群作为一组镜像进行 fork 和迁移。
- Kubernetes 仓库就是命名空间 `<repo>` 加上它的卷。持久卷是**独立**的写时复制单元（Ceph 上的 RBD 镜像，或通过本地 PV 供应器提供的小型数据存储镜像文件），绝不是单一不透明集群镜像内部的目录。正是这种分离使得按仓库的 fork 能够独立地进行写时复制。
- `KUBECONFIG` 作为 `DOCKER_HOST` 的类比被注入，`renet kube` 包装器以 `renet compose` 运行 Docker 的方式从 `up()` 中应用清单。

整集群的克隆和迁移位于 `rdc cluster fork` 和 `rdc cluster migrate`。这是差异化能力所在：以较短的切换时间，将一个正在运行的集群（包括其数据）fork 或迁移到另一台机器或数据中心。完整模型、命令和实测切换数字请参阅 [Kubernetes](/en/docs/kubernetes) 指南。

## 配置结构

每个配置是存储在 `~/.config/rediacc/` 中的扁平 JSON 文件。默认配置为 `rediacc.json`；命名配置使用名称作为文件名（例如 `production.json`）。字段按用途分为几个部分：`resources` 存储部署、`credentials` 存储密钥、`account` 存储云端默认值、`infra` 存储 TLS/DNS、`encryption` 存储每字段的静态加密状态。顶级 `schemaVersion: 2` 判别器确保向前兼容。

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**主要部分：**

| 部分 | 描述 |
|---|---|
| `schemaVersion` | 判别器（当前为 `2`）。加载程序会拒绝未知版本。 |
| `id` / `version` | 不可变的 UUID 加单调递增计数器；用于远程配置存储上的乐观锁定。 |
| `defaults.*` | 非敏感的运行时默认值（`machine`、`language`、`pruneGraceDays`、`universalUser`、`nextNetworkId`）。 |
| `credentials.ssh` | 内联 SSH 密钥对加 `knownHosts`。取代了旧的 `ssh.privateKeyPath`（不再进行文件路径间接寻址；内容在加载时解析并内联存储）。 |
| `credentials.cfDnsApiToken` | Cloudflare DNS-01 ACME 令牌。 |
| `credentials.masterPasswordVerifier` | 仅在 `encryption.mode === "master-password"` 时存在。 |
| `resources.machines.*` | 每台机器的 SSH 连接详情。 |
| `resources.storages.*` | rclone 兼容的离线备份凭据。 |
| `resources.repositories.*` | 每仓库 GUID 加 LUKS 凭据加用于沙盒隔离智能体访问的 SSH 密钥。 |
| `infra.acmeCertCache.*` | 缓存的 Traefik acme.json，gzip 加 base64 编码，按域名作为键。 |
| `encryption.mode` | `"plaintext"`（默认）或 `"master-password"`。 |
| `encryption.encryptedFields` | 加密时，按指针的 AES-GCM blob 映射（`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`）。一个解锁提示符可解密会话中读取的所有字段。 |
| `remote` | 仅当配置已同步到加密配置存储时存在；请参阅[加密配置存储](/en/docs/config-storage)。 |

**使用 CLI 安全编辑，而非 `vim`：**

```bash
# 按指针的单字段编辑（对敏感路径进行知识门控）
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# 使用编辑型编辑器及编辑好的 JSONC 投影（仅限人工）
rdc config edit

# 只读 JSONC dump，适合脚本和智能体
rdc config edit --dump

# 审计日志中的每次变更、拒绝和揭示
rdc config audit log --since 24h
rdc config audit verify
```

> 此文件包含敏感数据（SSH 私钥、LUKS 凭据、Cloudflare 令牌）。它以 `0600` 权限存储（仅所有者可读写）。请勿共享或提交到版本控制系统。当任何 `rdc` 命令读取此文件时，敏感字段默认会被[编辑](/en/docs/ai-agents-safety)：纯文本仅在交互式人工 TTY 上使用 `--reveal` 时显示。

### Envelope v2 和服务器端强制执行

当配置同步到[加密配置存储](/en/docs/config-storage)时，CLI 为每个敏感字段包装一个按字段 HMAC 承诺，并在纯文本 envelope 中携带这些承诺。服务器仅看到十六进制摘要：绝不看到值：但可对每次写操作强制执行知识门控：

- **前置条件检查**：在 `PUT /configs/<id>` 上，客户端提交它声称知道的摘要以及它想要变更的路径。服务器与存储的 envelope 的承诺进行比较。不匹配→ `409 precondition_failed` 伴随 `mismatchedPaths`。零知识：服务器永不看到明文。
- **防降级**：新 envelope 必须承诺前一个 envelope 承诺的每条敏感路径。智能体无法从承诺中删除路径以绕过将来的前置条件。
- **Envelope 版本锁定**：服务器拒绝缺少 `envelopeVersion: 2` 的 envelope，返回 `400 unsupported_envelope_version`。没有双接受窗口。
- **按字段加密静态**（CLI 端）：当 `encryption.mode === "master-password"` 时，每个密钥变成以主密码为密钥的独立 AES-GCM blob。除非命令实际触及密钥，否则读取不会触发提示符（因此 `rdc machine list` 保持无提示符）。

承诺密钥（FCK）通过 `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` 及按配置盐在客户端派生。轮换 `fckSalt` 使所有先前承诺失效，强制完全重新计算：对轮换 CEK 有用。
