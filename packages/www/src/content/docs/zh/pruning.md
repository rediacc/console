---
title: "清理"
description: "删除孤立备份、过期快照和未使用的仓库镜像以回收磁盘空间。"
category: "Guides"
order: 12
language: zh
sourceHash: "39df2a50797597f6"
---

# 清理

清理会移除不再被任何配置文件引用的资源。有两个清理命令，分别针对不同的资源类型：

- **`rdc storage prune`** -- 从云端/外部存储中删除孤立的备份文件
- **`rdc machine prune`** -- 清理数据存储工件，以及（可选地）机器上的孤立仓库镜像

## Storage Prune

扫描存储提供商，并删除其 GUID 不再出现在任何配置文件中的备份。

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### 检查内容

1. 列出指定存储中的所有备份 GUID。
2. 扫描磁盘上的所有配置文件（`~/.config/rediacc/*.json`）。
3. 如果备份的 GUID 未被任何配置的仓库部分引用，则该备份为**孤立**状态。
4. 在宽限期内最近归档的仓库即使已从活跃配置中移除，仍然**受到保护**。

## Machine Prune

分两个阶段清理机器上的资源。

### 阶段 1：数据存储清理（始终执行）

移除空的挂载目录、过期的锁文件和过期的 BTRFS 快照。

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### 阶段 2：孤立的仓库镜像（可选启用）

使用 `--orphaned-repos` 时，CLI 还会识别机器上未出现在任何配置文件中的 LUKS 仓库镜像并将其删除。

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
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
rdc config set pruneGraceDays 14
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
- **将 machine prune 与 deploy-backup 结合使用。** 在部署备份计划（`rdc machine deploy-backup`）后，添加定期的机器清理以清除过期快照和孤立的数据存储工件。
- **在使用 `--force` 前进行审核。** `--force` 标志会绕过宽限期。仅在您确定没有其他配置引用相关仓库时才使用它。
