---
title: 仓库
description: 在远程机器上创建、管理和操作 LUKS 加密仓库。
category: Guides
order: 4
language: zh
sourceHash: 04fe287348176b64
---

# 仓库

**仓库**是远程服务器上的一个 LUKS 加密磁盘映像。挂载后，它提供：
- 应用数据的隔离文件系统
- 专用的 Docker 守护进程（与主机的 Docker 分离）
- 在 /26 子网内为每个服务分配唯一的回环 IP

## 创建仓库

```bash
rdc repo create my-app -m server-1 --size 10G
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `-m, --machine <name>` | 是 | 将要创建仓库的目标机器。 |
| `--size <size>` | 是 | 加密磁盘映像的大小（例如 `5G`、`10G`、`50G`）。 |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

输出将显示三个自动生成的值：

- **仓库 GUID** -- 用于在服务器上标识加密磁盘映像的 UUID。
- **凭据** -- 用于加密/解密 LUKS 卷的随机密码短语。
- **网络 ID** -- 一个整数（从 2816 开始，每次递增 64），用于确定此仓库服务的 IP 子网。

> **请安全存储凭据。**它是您仓库的加密密钥。如果丢失，数据将无法恢复。凭据存储在您的本地 `config.json` 中，但不会存储在服务器上。

## 挂载和卸载

挂载操作解密并使仓库文件系统可访问。卸载操作关闭加密卷。

```bash
rdc repo mount my-app -m server-1       # 解密并挂载
rdc repo unmount my-app -m server-1     # 卸载并重新加密
```

| 选项 | 描述 |
|------|------|
| `--checkpoint` | 挂载/卸载前创建检查点 |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## 检查状态

```bash
rdc repo status my-app -m server-1
```

## 列出仓库

```bash
rdc repo list -m server-1
```

## 调整大小

将仓库设置为指定大小或扩展指定容量：

```bash
rdc repo resize my-app -m server-1 --size 20G    # 设置为指定大小
rdc repo expand my-app -m server-1 --size 5G      # 在当前大小基础上增加 5G
```

> 调整大小前必须先卸载仓库。

## 复刻

创建现有仓库当前状态的副本：

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

此命令创建一个具有独立 GUID 和网络 ID 的新加密副本。复刻仓库与源仓库共享相同的 LUKS 凭据。

## 验证

检查仓库的文件系统完整性：

```bash
rdc repo validate my-app -m server-1
```

## 所有权

将仓库内的文件所有权设置为通用用户（UID 7111）。通常在从工作站上传文件后需要执行此操作，因为上传的文件会使用您本地的 UID。

```bash
rdc repo ownership my-app -m server-1
```

此命令会自动检测 Docker 容器数据目录（可写绑定挂载）并将其排除。这可以防止破坏使用自身 UID 管理文件的容器（例如 MariaDB=999、www-data=33）。

| 选项 | 描述 |
|------|------|
| `--uid <uid>` | 设置自定义 UID，而非默认的 7111 |
| `--force` | 跳过 Docker 卷检测，对所有文件执行 chown |
| `--skip-router-restart` | Skip restarting the route server after the operation |

强制对所有文件（包括容器数据）设置所有权：

```bash
rdc repo ownership my-app -m server-1 --force
```

> **警告：**对运行中的容器使用 `--force` 可能会导致容器损坏。如有需要，请先使用 `rdc repo down` 停止服务。

有关迁移过程中何时以及如何使用所有权命令的完整说明，请参阅[迁移指南](/zh/docs/migration)。

## 模板

应用模板以使用文件初始化仓库：

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## 删除

永久销毁仓库及其中的所有数据：

```bash
rdc repo delete my-app -m server-1
```

> 此操作将永久销毁加密磁盘映像。此操作无法撤销。
