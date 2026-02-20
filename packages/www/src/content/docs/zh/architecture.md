---
title: 架构
description: Rediacc 的工作原理：双工具架构、运行模式、安全模型和配置结构。
category: Guides
order: 2
language: zh
sourceHash: 8f910f7827c8e958
---

# 架构

如果你不确定该使用哪个工具，请参考 [rdc vs renet](/zh/docs/rdc-vs-renet)。

本页面介绍 Rediacc 的内部工作原理：双工具架构、运行模式、安全模型和配置结构。

## 双工具架构

Rediacc 采用两个通过 SSH 协同工作的二进制文件：

![双工具架构](/img/arch-two-tool.svg)

- **rdc** 运行在您的工作站上（macOS、Linux 或 Windows）。它读取您的本地配置，通过 SSH 连接到远程机器，并调用 renet 命令。
- **renet** 以 root 权限运行在远程服务器上。它管理 LUKS 加密磁盘映像、隔离的 Docker 守护进程、服务编排和反向代理配置。

您在本地输入的每条命令都会转化为一个 SSH 调用，在远程机器上执行 renet。您无需手动 SSH 登录服务器。

## 运行模式

Rediacc 支持三种模式，每种模式决定了状态的存储位置和命令的执行方式。

![运行模式](/img/arch-operating-modes.svg)

### 本地模式

自托管使用的默认模式。所有状态存储在工作站的 `~/.rediacc/config.json` 中。

- 直接通过 SSH 连接到机器
- 无需外部服务
- 单用户、单工作站
- 使用 `rdc context create-local` 创建上下文

### 云模式（实验性）

使用 Rediacc API 进行状态管理和团队协作。

- 状态存储在云 API 中
- 支持基于角色的多用户团队访问
- Web 控制台提供可视化管理
- 使用 `rdc context create` 创建上下文

> **注意：**云模式命令为实验性功能。使用 `rdc --experimental <command>` 或设置 `REDIACC_EXPERIMENTAL=1` 来启用。

### S3 模式

将加密状态存储在兼容 S3 的存储桶中。结合了本地模式的自托管特性和跨工作站的可移植性。

- 状态以 `state.json` 形式存储在 S3/R2 存储桶中
- 使用 AES-256-GCM 加密和主密码保护
- 可移植：任何拥有存储桶凭据的工作站都可以管理基础设施
- 使用 `rdc context create-s3` 创建上下文

三种模式使用相同的 CLI 命令。模式仅影响状态的存储位置和认证方式。

## rediacc 用户

运行 `rdc context setup-machine` 时，renet 会在远程服务器上创建一个名为 `rediacc` 的系统用户：

- **UID**：7111
- **Shell**：`/sbin/nologin`（无法通过 SSH 登录）
- **用途**：拥有仓库文件并运行 Rediaccfile 函数

`rediacc` 用户无法直接通过 SSH 访问。rdc 以您配置的 SSH 用户（例如 `deploy`）连接，renet 通过 `sudo -u rediacc /bin/sh -c '...'` 执行仓库操作。这意味着：

1. 您的 SSH 用户需要 `sudo` 权限
2. 所有仓库数据归 `rediacc` 用户所有，而非您的 SSH 用户
3. Rediaccfile 函数（`prep()`、`up()`、`down()`）以 `rediacc` 用户身份运行

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

## LUKS 加密

仓库是存储在服务器数据存储中（默认：`/mnt/rediacc`）的 LUKS 加密磁盘映像。每个仓库：

1. 拥有一个随机生成的加密密码短语（"凭据"）
2. 以文件形式存储：`{datastore}/repos/{guid}.img`
3. 访问时通过 `cryptsetup` 挂载

凭据存储在本地 `config.json` 中，但**绝不**存储在服务器上。没有凭据，仓库数据将无法读取。启用开机自启时，会在服务器上存储一个辅助 LUKS 密钥文件，以便启动时自动挂载。

## 配置结构

所有配置存储在 `~/.rediacc/config.json` 中。以下是一个注释示例：

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
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
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**关键字段：**

| 字段 | 描述 |
|------|------|
| `mode` | `"local"`、`"s3"` 或省略表示云模式 |
| `apiUrl` | `"local://"` 表示本地模式，云模式使用 API URL |
| `ssh.privateKeyPath` | 用于所有机器连接的 SSH 私钥路径 |
| `machines.<name>.user` | 连接到机器的 SSH 用户名 |
| `machines.<name>.knownHosts` | 来自 `ssh-keyscan` 的 SSH 主机密钥 |
| `repositories.<name>.repositoryGuid` | 标识加密磁盘映像的 UUID |
| `repositories.<name>.credential` | LUKS 加密密码短语（**不存储在服务器上**） |
| `repositories.<name>.networkId` | 确定 IP 子网的网络 ID（2816 + n*64），自动分配 |
| `nextNetworkId` | 用于分配网络 ID 的全局计数器 |
| `universalUser` | 覆盖默认系统用户（`rediacc`） |

> 此文件包含敏感数据（SSH 密钥路径、LUKS 凭据）。它以 `0600` 权限存储（仅所有者可读写）。请勿共享或提交到版本控制系统。
