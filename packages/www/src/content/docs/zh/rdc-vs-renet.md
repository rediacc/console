---
title: rdc vs renet
description: 什么时候使用 rdc，什么时候使用 renet。
category: Concepts
order: 1
language: zh
sourceHash: e0ef5f051cefb407
---

# rdc vs renet

Rediacc 有两个二进制文件。以下是各自的使用场景。

| | rdc | renet |
|---|-----|-------|
| **运行于** | 您的工作站 | 远程服务器 |
| **连接方式** | SSH | 以 root 权限在本地运行 |
| **使用者** | 所有人 | 仅用于高级调试 |
| **安装方式** | 由您安装 | `rdc` 会自动配置 |

> 日常工作中请使用 `rdc`。您很少需要直接使用 `renet`。

## 它们如何协同工作

`rdc` 通过 SSH 连接到您的服务器，并代替您运行 `renet` 命令。您在工作站上输入一条命令，`rdc` 处理剩下的一切：

1. 读取本地配置（`~/.config/rediacc/rediacc.json`）
2. 通过 SSH 连接到服务器
3. 如有需要，更新 `renet` 二进制文件
4. 在服务器上运行对应的 `renet` 操作
5. 将结果返回到您的终端

## 日常工作使用 `rdc`

所有常见任务都通过工作站上的 `rdc` 完成：

```bash
# Set up a new server
rdc config setup-machine server-1

# Create and start a repository
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Stop a repository
rdc repo down my-app -m server-1

# Check machine health
rdc machine health server-1
```

完整操作流程请参阅[快速入门](/zh/docs/quick-start)。

## 服务器端调试使用 `renet`

只有在通过 SSH 登录服务器进行以下操作时，才需要直接使用 `renet`：

- `rdc` 无法连接时的紧急调试
- 检查通过 `rdc` 无法获取的系统内部信息
- 底层恢复操作

所有 `renet` 命令都需要 root 权限（`sudo`）。完整的 `renet` 命令列表请参阅[服务器参考](/zh/docs/server-reference)。

## 实验性功能：`rdc ops`（本地虚拟机）

`rdc ops` 封装了 `renet ops`，用于在工作站上管理本地 VM 集群：

```bash
rdc ops setup              # Install prerequisites (KVM or QEMU)
rdc ops up --basic         # Start a minimal cluster
rdc ops status             # Check VM status
rdc ops ssh 1              # SSH into bridge VM
rdc ops ssh 1 hostname     # Run a command on bridge VM
rdc ops down               # Destroy cluster
```

> 需要本地适配器。云适配器不支持此功能。

这些命令在本地运行 `renet`（不通过 SSH）。完整文档请参阅[实验性虚拟机](/zh/docs/experimental-vms)。

## Rediaccfile 说明

您可能会在 `Rediaccfile` 中看到 `renet compose -- ...`。这是正常的 — Rediaccfile 函数在 `renet` 可用的服务器上运行。

从工作站启动和停止工作负载请使用 `rdc repo up` 和 `rdc repo down`。
