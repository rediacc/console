---
title: "自动启动与恢复"
description: "自动启动的工作原理、在启动后发生故障的仓库的周期性协调器，以及如何检查恢复状态。"
category: "Guides"
order: 5
language: zh
sourceHash: "00a1796a0b0d20da"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 自动启动与恢复

启用了自动启动的仓库会在开机时自动启动并运行。如果之后停止了，周期性协调器会自动将其恢复。无需提示。无需手动重启。

如需了解如何为仓库启用或禁用自动启动，请参阅[服务: 开机自启](/zh/docs/services#autostart-on-boot)。

## 自动启动的工作原理

为仓库启用自动启动时，Rediacc 会生成一个 256 字节的随机 LUKS 密钥文件，并将其添加到加密卷的 LUKS 槽位 1 中。密钥文件存储在：

```
{datastore}/.credentials/keys/{guid}.key
```

这使得机器无需输入密码短语即可挂载仓库。LUKS 槽位 0（您的密码短语）不会被更改。

启动时，名为 `rediacc-autostart.service` 的一次性 systemd 服务会读取已启用自动启动的仓库列表，使用各自的密钥文件逐一挂载，启动每个仓库的 Docker 守护进程，并运行 Rediaccfile 的 `up()` 钩子。关机时，该服务会运行 `down()`，停止 Docker，并关闭 LUKS 卷。

> **安全说明：** 密钥文件允许在不输入密码短语的情况下获得仓库的 root 级访问权限。任何拥有服务器 root 访问权限的人都可以挂载已启用自动启动的仓库。在对敏感仓库启用自动启动之前，请根据您的威胁模型进行评估。

## 恢复空白

启动时的自动启动每次启动只运行一次。之后持续运行的路由器 watchdog 只能重启*已运行且挂载的仓库内，拥有活跃 Docker 守护进程的容器*。它无法重新挂载 LUKS 卷或重启已停止的仓库级 Docker 守护进程。

这意味着，如果服务器启动后某个仓库的 LUKS 卷被卸载或其 Docker 守护进程停止，启动服务和 watchdog 都无法恢复它。在协调器出现之前，处于此状态的仓库会一直停机，直到运维人员手动介入。

## 周期性协调器

`rediacc-autostart-reconcile.timer` systemd 定时器大约每 3 分钟触发一次，并运行 `renet repository reconcile`。对于每个已启用自动启动的仓库，协调器检查三件事：

1. LUKS 卷是否已挂载？
2. 仓库级 Docker 守护进程是否在运行？
3. 仓库的服务是否已启动？

如果任何检查失败，协调器将使用密钥文件恢复仓库：挂载卷、启动 Docker 守护进程并运行 `up()`。无需密码短语。

状态正常的仓库、当前被冷备份运行占用的仓库，或处于退避窗口内的仓库将被跳过。

### 退避与永久失败标记

恢复失败的仓库不会在每个 tick 上立即重试。协调器使用指数退避：

| 失败次数 | 下次尝试前的等待时间 |
|----------|---------------------|
| 1 | 1 分钟 |
| 2 | 2 分钟 |
| 3 | 5 分钟 |
| 4 | 15 分钟 |
| 5 次及以上 | 30 分钟，然后 60 分钟 |

连续失败 5 次后，协调器会在以下位置写入一个持久化标记文件：

```
/var/lib/rediacc/reconcile/failed/{guid}
```

此文件在日志轮转后仍然存在。文件的存在意味着该仓库需要运维人员介入。协调器会以错误级别记录失败，并停止对该仓库尝试自动恢复，直到标记被清除。

持久恢复失败的常见原因：

- **不受信任或已过期的仓库许可证**: 许可证检查在 `up()` 之前运行。
- **密钥文件丢失**: 如果 `{datastore}/.credentials/keys/{guid}.key` 处的密钥文件被删除，协调器将无法在没有密码短语的情况下挂载卷。
- **损坏的 Rediaccfile**: 语法错误或总是以非零值退出的 `up()` 钩子。

### 与路由器 Watchdog 的关系

协调器和路由器 watchdog 处理不同层级的故障，设计上相互补充：

| 层级 | 处理内容 |
|------|----------|
| **路由器 watchdog** | 已运行且挂载的仓库内，拥有活跃 Docker 守护进程的容器级重启 |
| **协调器（`rediacc-autostart-reconcile.timer`）** | 仓库级恢复：重新挂载 LUKS、重启 Docker 守护进程、重新运行 `up()` |

如果单个容器在正常的仓库内崩溃，由 watchdog 处理。如果整个仓库的守护进程停止，由协调器处理。

## 检查恢复状态

### 定时器和服务状态

```bash
systemctl status rediacc-autostart-reconcile.timer
systemctl list-timers rediacc-autostart-reconcile.timer
```

### 协调器日志

```bash
journalctl -u rediacc-autostart-reconcile.service
journalctl -u rediacc-autostart-reconcile.service --since "1 hour ago"
```

### 永久失败标记

列出具有持久失败标记的仓库：

```bash
ls /var/lib/rediacc/reconcile/failed/
```

每个文件名是一个仓库 GUID。与 `rdc config repository list` 交叉对照，将 GUID 映射到仓库名称。

在解决了根本问题后，删除文件以清除标记：

```bash
rm /var/lib/rediacc/reconcile/failed/{guid}
```

协调器将在下一个定时器 tick 时再次尝试恢复。

## 相关页面

- [服务: 开机自启](/zh/docs/services#autostart-on-boot): 启用和禁用自动启动、密钥文件管理
- [备份与恢复](/zh/docs/backup-restore): 冷备份与运行中服务的交互
