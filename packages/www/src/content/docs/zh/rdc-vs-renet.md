---
title: "rdc vs renet"
description: "何时使用 rdc，何时使用 renet。"
category: "Concepts"
order: 1
language: zh
sourceHash: "2ccc8590bc6f67c6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc vs renet

Rediacc 有两个二进制文件。两个任务，两个地方。以下是各自的使用场景。

| | rdc | renet |
|---|-----|-------|
| **运行于** | 您的工作站 | 远程服务器 |
| **连接方式** | SSH | 以 root 权限在本地运行 |
| **使用者** | 所有人 | 仅用于高级调试 |
| **安装方式** | 由您安装 | `rdc` 会自动配置 |

> 日常工作中请使用 `rdc`。您很少需要直接使用 `renet`。

## 它们如何协同工作

在工作站上运行 `rdc`。它会打开一个到服务器的 SSH 连接，并在那里为你运行匹配的 `renet` 命令。一条命令，一处执行：

1. 读取本地配置（`~/.config/rediacc/rediacc.json`）
2. 通过 SSH 连接到服务器
3. 如有需要，更新 `renet` 二进制文件
4. 在服务器上运行对应的 `renet` 操作
5. 将结果返回到您的终端

## 日常工作使用 `rdc`

所有常见任务都通过工作站上的 `rdc` 完成：

```bash
# 配置新服务器
rdc config machine setup --name server-1

# 创建并启动仓库
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# 停止仓库
rdc repo down --name my-app -m server-1

# 检查机器健康状态
rdc machine health --name server-1
```

完整操作流程请参阅[快速入门](/zh/docs/quick-start)。

## 服务器端调试使用 `renet`

只有在通过 SSH 登录服务器进行以下操作时，才需要直接使用 `renet`：

- `rdc` 无法连接时的紧急调试
- 检查通过 `rdc` 无法获取的系统内部信息
- 底层恢复操作

所有 `renet` 命令都需要 root 权限（`sudo`）。`rdc` 并不包装每个 `renet` 子命令；对于未涵盖的功能，请 SSH 登录并直接调用 `renet`。完整的 `renet` 命令列表请参阅[服务器参考](/zh/docs/server-reference)。

## 实验性功能：`rdc ops`（本地虚拟机）

`rdc ops` 封装了 `renet ops`，用于在工作站上管理本地 VM 集群：

```bash
rdc ops setup              # 安装前置条件（KVM 或 QEMU）
rdc ops up --basic         # 启动最小集群
rdc ops status             # 检查 VM 状态
rdc ops ssh --vm-id 1  # SSH 连接到 bridge VM
rdc ops ssh --vm-id 1 -c hostname  # 在 bridge VM 上执行命令
rdc ops down               # 销毁集群
```

> 需要本地适配器。云适配器不支持此功能。

这些命令在本地运行 `renet`（不通过 SSH）。完整文档请参阅[实验性虚拟机](/zh/docs/experimental-vms)。

## Rediaccfile 说明

你会在 `Rediaccfile` 中看到 `renet compose -- ...`。不必担心。Rediaccfile 函数在服务器上运行，而 `renet` 已经安装在那里。

从工作站启动和停止工作负载请使用 `rdc repo up` 和 `rdc repo down`。
