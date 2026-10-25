---
title: "清理"
description: "删除孤立备份、过期快照、仓库镜像和本地配置遗留物，回收磁盘空间并保持状态一致。"
category: "Guides"
tags:
  - storage
  - operations
subcategory: data-protection
order: 12
language: zh
sourceHash: "5b0bc33572c2d9e2"
sourceCommit: "75e184930a3bbce02a1994f3d222c70f87d48f97"
---

# 清理

清理会清除不再对应于存活资源的状态。两个命令分别覆盖两个不同的范围。分块存储中的快照不在其列：服务器会按[保留策略](#backup-snapshots)清理它们。

| 命令 | 清理内容 | 真实来源所在位置 |
|---|---|---|
| `rdc machine prune <machine>` | 机器上的数据存储工件（始终）；孤立或未知的仓库镜像（可选启用） | 本地 CLI 配置 + 机器的 `.interim/state` 镜像 |
| `rdc config prune` | 本地配置遗留物（证书缓存、过期归档、悬空交叉引用） | 仅本地 CLI 配置 |

这两个命令相互独立，可以只运行其中一个。它们共享一个通用的安全模型，详见下方的[安全模型](#safety-model)。

清理命令清除的是已删除资源遗留的状态。若要回收*存活*仓库占用的空间（即文件系统已释放但存储池仍持有的块），请改用 [`rdc repo trim`](/zh/docs/repositories#reclaim-space-trim)；两者互为补充。

## 挂载安全预检

`machine prune --prune-unknown` 会在删除任何内容之前运行 **挂载安全预检**：它查询机器上当前已挂载或正在运行的仓库，将其与删除候选取交集，并 **拒绝删除仍在机器上存活的候选**。删除存活的仓库镜像是真实的数据丢失陷阱。预检让这种意外不可能发生。

如要覆盖（罕见；仅当您确实知道存活状态有误时），传入 `--force-delete-mounted`。这是与 `--force`（控制归档宽限期）独立的标志，所以两个逃生口保持区分。

## 备份快照

通过 `rdc backup snapshot` 上传的快照存放在分块存储中，由服务器负责清理。客户端没有清理命令：声明要保留多少历史，服务器会删除其余部分。

```bash
# 查看当前策略
rdc backup retention my-app

# 保留 7 个每日、4 个每周和 6 个每月快照
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# 重新保留所有快照
rdc backup retention clear my-app
```

策略规则见[备份与恢复](/zh/docs/backup-restore#retention)，`rdc backup usage` 会显示存储当前的内容。

## Machine Prune

分三阶段清理机器上的资源。阶段 1 始终运行；阶段 2 和 3 是可选启用的，可以组合使用。

### 阶段 1：数据存储清理（始终执行）

移除删除仓库或机器级别重构淘汰命名约定后可能残留的各种资源。每一类别都会独立扫描。运行 prune 一次是幂等的，所以可以安全地重复执行，最后一次运行遗漏的孤立项会被下一次运行捕获。

| 类别 | 清理内容 |
|------|----------|
| 空挂载目录 | 没有对应仓库镜像的 `mounts/<guid>/` 目录 |
| 孤立的 immovable 目录 | 没有对应仓库镜像的 `immovable/<guid>/` 目录 |
| 过期锁文件 | 已删除仓库的 `repositories/.lock-<guid>` |
| 过期备份快照 | 被中止的备份运行遗留的 `.snapshot-*` 和 `.backup-*` |
| 孤立的 VS Code 沙箱目录 | 不再在机器上活跃的仓库对应的 `.interim/sandbox/<name>` |
| 孤立的 iptables 链 | 已删除网络对应的 `REDIACC_WILDCARD_<N>` 和 `DOCKER_ISOLATED_NET_<N>` 链 |
| 孤立的 authorized_keys 条目 | `sandbox-gateway <repo> --guid <uuid>` 行，其 `--guid` 不再匹配任何活跃挂载目录 |

authorized_keys 扫描会检查 `/home/*/.ssh/authorized_keys` 和 `/root/.ssh/authorized_keys`。只有当条目的 `--guid` 标签映射到一个存活的挂载目录 GUID 时才会保留，因此当前部署在机器上的仓库始终会被保留，无论其名称是否恰好出现在磁盘上的任何位置。在 renet 开始添加 `--guid` 标签之前写入的旧条目无法被验证，会始终被报告为孤立项。

```bash
# Dry-run，显示将被移除的内容（不应用任何更改）
rdc machine prune server-1 --dry-run

# 执行清理
rdc machine prune server-1
```

> **级联清理。** 某些类别依赖于更早的类别。例如，删除空挂载目录可能会暴露更多沙箱孤立项，因为它们所依赖的挂载刚刚消失。再次运行 `rdc machine prune` 可以捕获这种级联效应并完成清理。当没有任何内容需要处理时，最后一次 dry-run 会以 `No orphaned resources found. Datastore is clean.` 结尾。

### 阶段 2：`--orphaned-repos`（粗放）

使用 `--orphaned-repos` 时，CLI 还会删除机器上未出现在 **任何** 本地配置文件中的仓库镜像。

```bash
rdc machine prune server-1 --orphaned-repos --dry-run
rdc machine prune server-1 --orphaned-repos
```

这是 **粗放的**。它会删除所有不在您本地配置中的内容，包括其他工具或其他操作员 CLI 检出管理的合法复刻。如果 renet `.interim/state` 镜像正确地将仓库标识为复刻，但本地配置从未见过它，此阶段仍会将其移除。如希望保守，请优先使用阶段 3（`--prune-unknown`）。

### 阶段 3：`--prune-unknown`（精准）

使用 `--prune-unknown` 时，CLI 仅删除两种信号都无法分类的仓库：既不在任何本地配置中，**也** 没有在机器的 `.interim/state` 镜像中存在 fork 标记条目（参见 [仓库. `Type` 列](/zh/docs/repositories#type-column-and-the-state-mirror)）。

```bash
rdc machine prune server-1 --prune-unknown --dry-run
rdc machine prune server-1 --prune-unknown
```

实践中，`--prune-unknown` 是您进行例行清理时所需要的；`--orphaned-repos` 仅在您确信本地配置是机器上每个仓库的完整且权威清单时才正确。镜像之前的遗留孤立项以及配置条目被误删的仓库都会落入 "unknown" 类别。它们的状态确实不确定，精准标志要求操作员明确确认这一点。

挂载安全预检在此阶段也会运行：当前挂载在 `--machine` 上的仓库会被报告并跳过，除非传入 `--force-delete-mounted`。

```bash
# 组合：使用精准的复刻感知路径进行完整机器清理
rdc machine prune server-1 --prune-unknown
```

## Config Prune

清扫 `~/.config/rediacc/<config>.json` **本地配置文件内** 的过期遗留物。纯本地。不涉及 SSH，不调用 renet。清理三类内容：

1. **ACME 证书缓存条目**，其锚点（GUID、仓库名称或机器名称）不再存在于活跃配置中。证书通配符无法路由到任何地方，因此是死重。
2. **过期的归档仓库**，存于 `resources.deletedRepositories[]` 中。`deletedAt` 早于 `defaults.pruneGraceDays`（默认 7 天）的条目。仍在宽限期内的条目会被报告（显示剩余天数）并保留。
3. **悬空的交叉引用**，存在于不同配置桶之间：
   - `resources.machines.<m>.backupStrategies[]` 中命名的策略不再存在。
   - `resources.backupStrategies.<s>.exclude[]` 和 `include[]` 中命名的仓库不再存在。
   - 存储目标的目标存储缺失。标记为警告，不自动移除（自动移除会改变策略语义）。

```bash
# 仅预览
rdc config prune --dry-run

# 应用（默认行为）
rdc config prune

# 限定到一个桶
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# 不论宽限期如何都丢弃所有归档仓库
rdc config prune --purge-archived

# 在此次调用中覆盖归档宽限窗口
rdc config prune --grace-days 30
```

### 不会触及的内容

- 活跃资源（机器、仓库、备份策略、云提供商）。
- 凭据、account 块、加密块、defaults。
- `knownHosts` 条目（自动刷新路径为 `rdc machine scan-keys`）。
- 压缩证书 blob 数组（`infra.acmeCertCache.<base>.data[]`）会从清理后的证书列表自动重建；您不会丢失任何仍覆盖保留名称的证书链。

### 实例

来自一台拥有四个孤立 GUID 通配符和两个过期机器名通配符的机器的真实运行输出：

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

锚点为存活机器、仓库或 GUID 的证书名称将保持不变，任何单标签 `<service>.<base>` 或根 `*.<base>` 通配符同样如此。

## 迁移：状态镜像回填

为 `--prune-unknown` 和 `rdc repo list -m` 中的 `Type` 列提供支持的 `.interim/state/<guid>/.rediacc.json` 镜像在以下时机写入：

- **复刻时**（`rdc repo fork`）。立即写入，甚至在复刻被挂载之前。
- **每次状态保存时**（`rdc repo up` 以及任何更新仓库状态的操作）。适用于在镜像代码发布之前创建的仓库。

在 **镜像存在之前创建且自升级以来未重新挂载** 的仓库没有镜像文件。它们在 `rdc repo list -m` 中显示为 `unknown`，即使其中一些是合法的复刻。要为遗留孤立项修复此问题，请在机器上运行一次性回填：

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

回填会为当前挂载的仓库将卷内的存活状态复制到镜像中，并为您在 `--mark-as-fork` 下列出的任何 GUID 写入合成的 fork 标记镜像。回填后，计划备份会停止上传所列复刻（上传管道会检查镜像中的 `is_fork: true`）。

## 安全模型

清理被设计为在多配置环境中默认安全。

### 多配置感知

`machine prune --orphaned-repos` 会扫描 `~/.config/rediacc/` 中的 **所有** 配置文件，而不仅仅是活跃的配置文件。被 `production.json` 引用的仓库不会被删除，即使它不在 `staging.json` 中。这可以防止配置针对不同环境时发生意外删除。

### 宽限期

当仓库通过 `--archive-config` 从配置中移除时，其凭据条目会被移到 `resources.deletedRepositories[]` 并带有 `deletedAt` 时间戳。清理命令遵守宽限期（默认 7 天），在此期间最近归档的仓库受到保护，不会被删除。这给您时间在仓库被意外移除时进行恢复（`rdc repo admin archive restore <guid>`）。一旦宽限期过期，`machine prune` 和 `config prune` 都会自动清除该条目。

### 挂载安全预检

如上所述。`machine prune --prune-unknown` 拒绝删除当前在机器上挂载或正在运行的仓库。仅使用 `--force-delete-mounted` 来覆盖。

### 默认应用；`--dry-run` 用于预览

两个 prune 命令默认 **应用** 更改。传入 `--dry-run` 以预览而不写入。这与命令动词相符："prune" 本身具有破坏性，dry-run 标志是显式的退出选项。

## 配置

### `pruneGraceDays`

在配置文件中设置自定义的默认宽限期，这样您就不需要每次都传入 `--grace-days`：

```bash
# 在活跃配置中将宽限期设为 14 天
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

CLI 标志 `--grace-days` 在提供时会覆盖此值。

### 优先级

1. `--grace-days <N>` 标志（最高优先级）
2. 配置文件中的 `pruneGraceDays`
3. 内置默认值：7 天

## 最佳实践

- **在生产环境上先运行 dry-run。** 在执行破坏性清理之前务必先预览。
- **保持多个配置文件为最新状态。** 机器清理会检查配置目录中的所有配置。如果配置文件过期或被删除，其仓库将失去保护。请保持配置文件准确。
- **优先使用 `--prune-unknown` 而非 `--orphaned-repos`。** 精准标志尊重 renet 镜像；粗放标志会愉快地删除其他工具创建的复刻。
- **为生产环境使用较长的宽限期。** 默认的 7 天宽限期适合大多数工作流程。对于维护窗口不频繁的生产环境，建议使用 14 天或 30 天。
- **声明保留策略。** `rdc backup retention set` 无需手动干预即可控制快照的存储成本。
- **将 machine prune 与备份计划结合使用。** 在部署备份计划（`rdc backup schedule`）后，添加定期的机器清理以清除过期快照和孤立的数据存储工件。
- **定期运行 `config prune`。** 本地配置膨胀（尤其是证书缓存）会悄无声息地累积；每季度一次的 `config prune --dry-run` 足以发现它。
- **在使用 `--force` 或 `--force-delete-mounted` 之前进行审核。** 这两个标志都会绕过安全检查。仅在您确信没有其他配置引用相关仓库时使用 `--force`；仅在您确信机器上的存活状态有误时使用 `--force-delete-mounted`。
