---
title: "清理"
description: "删除孤立备份、过期快照和未使用的仓库镜像以回收磁盘空间。"
category: "Guides"
order: 12
language: zh
sourceHash: "9b28efe3bd8ca2dc"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# 清理

清理会移除不再被任何配置文件引用的资源。有两个清理命令，分别针对不同的资源类型：

- **`rdc storage prune`** -- 从云端/外部存储中删除孤立的备份文件
- **`rdc machine prune`** -- 清理数据存储工件，以及（可选地）机器上的孤立仓库镜像

## Storage Prune

扫描存储提供商，并删除其 GUID 不再出现在任何配置文件中的备份。

```bash
# Dry-run (default), shows what would be deleted
rdc storage prune --name my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune --name my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune --name my-s3 -m server-1 --grace-days 14
```

### 检查内容

1. 列出指定存储中的所有备份 GUID。
2. 扫描磁盘上的所有配置文件（`~/.config/rediacc/*.json`）。
3. 如果备份的 GUID 未被任何配置的仓库部分引用，则该备份为**孤立**状态。
4. 在宽限期内最近归档的仓库即使已从活跃配置中移除，仍然**受到保护**。

## Machine Prune

分两个阶段清理机器上的资源。

### 阶段 1：数据存储清理（始终执行）

移除删除仓库或机器级别重构淘汰命名约定后可能残留的各种资源。每一类别都会独立扫描，并且清理是一次幂等的过程，因此可以安全地重复执行 prune，最终会收敛到干净的数据存储状态。

| 类别 | 清理内容 |
|------|----------|
| 空挂载目录 | 没有对应仓库镜像的 `mounts/<guid>/` 目录 |
| 孤立的 immovable 目录 | 没有对应仓库镜像的 `immovable/<guid>/` 目录 |
| 过期锁文件 | 已删除仓库的 `repositories/.lock-<guid>` |
| 过期备份快照 | 被中止的备份运行遗留的 `.snapshot-*` 和 `.backup-*` |
| 孤立的 VS Code 沙箱目录 | 不再在机器上活跃的仓库对应的 `.interim/sandbox/<name>` |
| 孤立的 iptables 链 | 已删除网络对应的 `REDIACC_WILDCARD_<N>` 和 `DOCKER_ISOLATED_NET_<N>` 链 |
| 孤立的 authorized_keys 条目 | `sandbox-gateway <repo> --guid <uuid>` 行，其 `--guid` 不再匹配任何活跃挂载目录 |

authorized_keys 扫描会检查 `/home/*/.ssh/authorized_keys` 和 `/root/.ssh/authorized_keys`。只有当条目的 `--guid` 标签映射到一个存活的挂载目录 GUID 时才会保留，因此当前部署在该机器上的仓库始终会被保留，无论其名称是否恰好出现在磁盘的某个位置。在 renet 开始添加 `--guid` 标签之前写入的旧条目无法被验证，会始终被报告为孤立项。

```bash
# Dry-run, shows what would be removed (no changes applied)
rdc machine prune --name server-1 --dry-run

# Execute cleanup
rdc machine prune --name server-1
```

> **级联清理。** 某些类别依赖于更早的类别。例如，删除空挂载目录可能会暴露更多沙箱孤立项，因为它们所依赖的挂载刚刚消失。再次运行 `rdc machine prune` 可以捕获这种级联效应并完成清理。当没有任何内容需要处理时，最后一次 dry-run 会以 `No orphaned resources found. Datastore is clean.` 结尾。

### 阶段 2：孤立的仓库镜像（可选启用）

使用 `--orphaned-repos` 时，CLI 还会识别机器上未出现在任何配置文件中的 LUKS 仓库镜像并将其删除。

```bash
# Dry-run (default behavior when is set)
rdc machine prune --name server-1

# Actually delete orphaned repos
rdc machine prune --name server-1

# Custom grace period
rdc machine prune --name server-1 --grace-days 30
```

## 安全模型

清理被设计为在多配置环境中默认安全。

### 多配置感知

两个清理命令都会扫描 `~/.config/rediacc/` 中的**所有**配置文件，而不仅仅是活跃的配置文件。被 `production.json` 引用的仓库不会被删除，即使它不在 `staging.json` 中。这可以防止在配置针对不同环境时发生意外删除。

### 宽限期

当仓库从配置中移除时，它可能会被带时间戳地归档。清理命令遵守宽限期（默认 7 天），在此期间最近归档的仓库受到保护，不会被删除。这给您时间在仓库被意外移除时进行恢复。

### 默认 Dry-run

`storage prune` 和 `machine prune` 默认为 dry-run 模式。它们显示将要移除的内容而不进行实际更改。传入 `--no-dry-run` 或 `--force` 以执行实际删除。

## 配置

### `pruneGraceDays`

在配置文件中设置自定义的默认宽限期，这样您就不需要每次都传入 `--grace-days`：

```bash
# Set grace period to 14 days in the active config
rdc config set --key pruneGraceDays --value 14
```

CLI 标志 `--grace-days` 在提供时会覆盖此值。

### 优先级

1. `--grace-days <N>` 标志（最高优先级）
2. 配置文件中的 `pruneGraceDays`
3. 内置默认值：7 天

## 最佳实践

- **先运行 dry-run。** 在执行破坏性清理之前务必先预览，尤其是在生产存储上。
- **保持多个配置文件为最新状态。** 清理会检查配置目录中的所有配置。如果配置文件过期或被删除，其仓库将失去保护。请保持配置文件准确。
- **为生产环境使用较长的宽限期。** 默认的 7 天宽限期适合大多数工作流程。对于维护窗口不频繁的生产环境，建议使用 14 天或 30 天。
- **在备份运行后安排 storage prune。** 将 `storage prune` 与您的备份计划配对，以在无需手动干预的情况下控制存储成本。
- **将 machine prune 与 backup schedule 结合使用。** 在部署备份计划（`rdc machine backup schedule`）后，添加定期的机器清理以清除过期快照和孤立的数据存储工件。
- **在使用 `--force` 前进行审核。** `--force` 标志会绕过宽限期。仅在您确定没有其他配置引用相关仓库时才使用它。
