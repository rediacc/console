---
title: 备份与恢复
description: 将加密仓库备份到外部存储、从备份恢复以及配置定时备份。
category: Guides
order: 7
language: zh
sourceHash: "14cf2fb4ac3dc4d6"
sourceCommit: "35b53352026ae87fb6800c7fed10b793223ca1da"
---

# 备份与恢复

Rediacc 可以将加密仓库备份到外部存储提供商，并在同一台或不同的机器上进行恢复。备份是加密的，恢复时需要仓库的 LUKS 凭据。

## 配置存储

在推送备份之前，需要注册一个存储提供商。Rediacc 支持任何兼容 rclone 的存储：S3、B2、Google Drive 等。

### 从 rclone 导入

如果您已经配置了 rclone 远程存储：

```bash
rdc config storage import --file rclone.conf
```

此命令将 rclone 配置文件中的存储配置导入到当前配置中。支持的类型：S3、B2、Google Drive、OneDrive、Mega、Dropbox、Box、Azure Blob 和 Swift。

### 查看存储

```bash
rdc config storage list
```

## 推送备份

将仓库备份推送到外部存储：

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

推送操作在写入前始终检查目标仓库是否已挂载。如果未挂载，操作将中止。

| 选项 | 描述 |
|------|------|
| `--to <storage>` | 目标存储位置 |
| `--to-machine <machine>` | 用于机器到机器备份的目标机器 |
| `--dest <filename>` | 自定义目标文件名 |
| `--checkpoint` | 推送前创建CRIU检查点（用于带有`rediacc.checkpoint=true`标签的容器）。目标在`repo up`时自动恢复 |
| `--force` | 覆盖已有备份 |
| `--bwlimit <limit>` | rsync 传输的带宽限制（例如 `10M`、`500K`） |
| `--tag <tag>` | 为备份添加标签 |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |
| `--skip-router-restart` | 操作后跳过路由服务器重启 |

## 拉取/恢复备份

从外部存储拉取仓库备份：

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

拉取操作在写入前始终检查目标仓库是否已挂载。如果未挂载，操作将中止。

| 选项 | 描述 |
|------|------|
| `--from <storage>` | 源存储位置 |
| `--from-machine <machine>` | 用于机器到机器恢复的源机器 |
| `--force` | 覆盖已有本地备份 |
| `--bwlimit <limit>` | rsync 传输的带宽限制（例如 `10M`、`500K`） |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |
| `--skip-router-restart` | 操作后跳过路由服务器重启 |

## 列出备份

查看存储位置中的可用备份：

```bash
rdc repo backup list --from my-storage -m server-1
```

## 批量同步

一次推送或拉取所有仓库：

### 推送所有到存储

```bash
rdc repo push --to my-storage -m server-1
```

### 从存储拉取所有

```bash
rdc repo pull --from my-storage -m server-1
```

| 选项 | 描述 |
|------|------|
| `--to <storage>` | 目标存储（推送方向） |
| `--from <storage>` | 源存储（拉取方向） |
| `--repo <name>` | 同步指定仓库（可重复使用） |
| `--override` | 覆盖已有备份 |
| `--debug` | 启用详细输出 |
| `--skip-router-restart` | 操作后跳过路由服务器重启 |

## 定时备份

Rediacc 使用具名备份策略。每个策略定义了一个计划、备份模式、可选的带宽限制和文件过滤器。机器通过名称引用策略来确定在其上运行哪些备份。

### 备份模式

| 模式 | 行为 | 停机时间 |
|------|------|---------|
| `hot` | 服务运行时创建 BTRFS 快照（崩溃一致性） | 无 |
| `cold` | 停止服务、创建快照、重启服务、上传快照（应用一致性） | 每个仓库的停止+启动窗口，跨仓库并行。见下方"估算冷备份停机时间"。 |

对于可以接受崩溃一致性快照的服务，使用 `hot`。当需要保证一致性且可以接受短暂重启时，使用 `cold`。

### 冷备份语义

冷备份对每个包含的仓库执行三个阶段：**停止 -- 快照 -- 启动**。了解保证的边界有助于运维人员及早发现部分故障。

**冷备份保证的内容：**

- 在快照之前，每个包含仓库中正在运行的所有容器都通过 Rediaccfile 的 `down()` 钩子优雅地停止，并且每仓库的 Docker daemon 处于静默状态。因此快照是应用一致的，而不仅仅是崩溃一致的。
- 快照前正在运行的容器 ID 集合被持久化到 `/var/run/rediacc/cold-backup-<guid>.running.json` 的 sidecar 文件中。这是"完成后应该恢复运行的内容"的真实来源。
- 快照后，调用仓库的 Rediaccfile `up()` 钩子来恢复完整的 compose 堆栈。
- `/var/run/rediacc/cold-backup-<guid>.status.json` 的每次运行状态 sidecar 记录每次尝试的阶段、结果和任何错误。

**冷备份不保证的内容：**

- `up()` 是尽力而为的。它可能因冷备份控制范围之外的原因而失败（`depends_on: service_healthy` 条件仍在等待、compose 文件语法错误、拉取镜像时的瞬时网络故障）。失败时，冷备份以错误级别记录错误，写入状态 sidecar，并继续处理下一个仓库。
- 当 `up()` 失败时，会启动**直接回退重启**：读取运行 sidecar，通过直接 Docker API（无 compose）重启每个记录的容器 ID。即使 compose 流程存在问题，这也能让服务恢复运行，但不会重新执行任何 Rediaccfile 钩子。
- 如果某些容器 ID 的回退也失败（例如 Docker daemon 本身已关闭），sidecar **保留在原位**，以便路由器 watchdog 可以在每个 tick 继续重试。

**Watchdog 恢复：** 在每个 tick，watchdog 检查运行 sidecar 是否存在。其中列出的任何当前已停止的容器 ID 都会被重启，*无论容器保存的 `restart_policy` 如何*。这意味着配置了 `restart: on-failure` 的服务（Docker 在干净停止后不会重启）在冷备份后仍然会恢复。一旦所有列出的容器都在运行，sidecar 将被删除。

**运维人员如何检测故障：**

- `rdc machine query --name <machine> --containers` 显示运行状态。与预期集合进行比较。
- 机器上的 `/var/run/rediacc/cold-backup-<guid>.status.json`。通过 `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` 检查。`success: false` 加上过时的 `startedAt` 表示上次备份未正常完成。
- renet 备份运行的日志（`journalctl -u renet-*` 或直接的 `rdc machine deploy-backup` 调用）会输出 `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` 形式的最终摘要行。非空的 `failed_repos` 是 grep 的目标。

### 估算冷备份停机时间

每个仓库仅在其自身的 `down()` + `up()` 窗口内处于停机状态。在热态主机上，这些时间通常为：

| 仓库规模 | 典型停止+启动 |
|----------|---------------|
| 小型（1-2 个容器，无数据库） | 5-15 秒 |
| 中型（Web 应用 + 缓存） | 20-45 秒 |
| 重型（数据库 + 队列 + 邮件） | 60-120 秒 |

快照步骤（`btrfs subvolume snapshot -r`）与仓库大小无关，为 O(1)：0.1-1 秒。一个仓库不会因其他仓库的快照而保持停机。上传器随后针对只读快照运行，此时所有仓库都已恢复。

**整个运行的总墙钟时间** 由并行重启的仓库数量决定。renet 从主机派生此值：

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

示例：

| 主机 | 仓库 | 并发数 | 重启墙钟时间 |
|------|------|--------|--------------|
| 4 CPU 虚拟机 | 5 个仓库，平均每个 30 秒 | 2 | ~75 秒 |
| 16 CPU 服务器 | 10 个仓库，平均每个 40 秒 | 8 | ~80 秒 |
| 64 CPU 集群节点 | 50 个仓库，平均每个 40 秒 | 8 | ~4 分钟 |

**通过环境变量覆盖：** 在备份服务的环境中（通常通过 systemd drop-in）设置 `REDIACC_COLD_BACKUP_CONCURRENCY=N` 以固定特定值。`=1` 强制严格串行重启，在调试某个仓库 `up()` 钩子中的崩溃循环时很有用。

如果您运行延迟敏感的仓库（公共 Web 应用、邮件），其停机时间受限于自身的停止+启动（通常 30-90 秒），而不是整个运行的总长度。仓库按发现顺序分配到并发槽位；没有优先级队列。如果需要更细粒度的调度，将重型仓库拆分到各自的 `--exclude` 范围策略中。

### 长时间运行的备份和重叠的计划

超过自身计划间隔的冷备份（例如，通过中等链路首次播种 500 GB 仓库可能合法地需要超过 24 小时，在此期间夜间定时器再次触发）不会排队或启动第二次运行。systemd `Type=oneshot` 单元是单实例：当定时器触发且服务已处于 `activating` 状态时，systemd 将启动合并到现有作业中。不会启动新进程，也不会为以后排队运行。

具体而言，从周一 03:00 UTC 开始到周四中午结束的运行：

| 日期 | 03:00 UTC 触发 | 结果 |
|------|---------------|------|
| 周一 | 首次触发 | 运行开始 |
| 周二 | 第二次触发 | 静默丢弃（上次运行仍处于活动状态） |
| 周三 | 第三次触发 | 静默丢弃（上次运行仍处于活动状态） |
| 周四 | 运行在中午结束 | 无补偿；下次运行是周五 03:00 UTC |

定时器的 `Persistent=true` 指令**不会**挽救这些触发。`Persistent=true` 重放因定时器本身处于非活动状态（系统关机、定时器禁用）而错过的触发。因服务繁忙而丢弃的触发会丢失。

此默认值是有意的。对同一个 datastore 并行运行两个冷备份会争夺 BTRFS 快照路径、rclone 远端以及 `/var/run/rediacc/cold-backup-<guid>.status.json` 的每仓库 sidecar。串行在长时间运行的实例之后是安全的结果。

**监控含义。** 一个挂起的备份（例如，rclone 卡在网络黑洞上）会静默丢弃每个后续的定时器触发。调度器不会发出警报。监视 `systemctl show <unit> -p ActiveEnterTimestamp`：如果服务处于 `activating` 状态的时间超过预期的运行时长（例如，在夜间定时器上超过 48 小时），请进行调查。

**如果您需要每个计划触发都运行**，将定时器从 `OnCalendar=<cron>` 切换为 `OnUnitInactiveSec=<间隔>`。这会在上次运行完成 N 小时后触发，而不是按固定的挂钟计划，因此长时间运行不会导致丢弃。只会将下一次运行推迟。代价是计划漂移：您的 03:00 夜间变为"上次结束后 24 小时"。

### 定义策略

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

| 选项 | 描述 |
|------|------|
| `--name <name>` | 策略名称（用于机器绑定） |
| `--destination <storage>` | 上传目标存储提供商 |
| `--cron <expression>` | cron 表达式（例如 `"0 2 * * *"` 表示每天凌晨 2 点） |
| `--mode <hot\|cold>` | 备份模式 |
| `--bwlimit <limit>` | 上传带宽限制（例如 `10M`） |
| `--include <pattern>` | 包含过滤器（可重复使用） |
| `--exclude <pattern>` | 排除过滤器（可重复使用） |
| `--enable` / `--disable` | 启用或禁用策略 |

### 查看策略

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name nightly-cold
```

### 删除策略

```bash
rdc config backup-strategy remove --name nightly-cold
```

### 将策略绑定到机器

在配置中，将一个或多个策略名称绑定到机器：

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## 备份操作

### 将计划部署到机器

将绑定的策略作为 systemd 定时器推送到机器：

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

部署是一个状态协调器。它读取机器上当前的单元文件和 systemd 状态，与配置会生成的内容进行比较（每个文件 SHA-256），只触及内容实际发生变化的单元。在没有配置变更的情况下重新运行是 no-op：无写入、无 `daemon-reload`、无定时器扰动。

`--dry-run` 为每个策略打印计划（`created`、`updated (service, timer, env)`、`unchanged`、`removed`），不触及机器。与 `--debug` 组合使用还会打印生成的单元内容；rclone token 会被编辑。

如果您即将更新或删除的策略当前正在运行备份，部署会快速失败，并提示取消它或传递 `--force`。使用 `--force` 时，正在运行的调用保留其内存中的单元，新配置在下次定时器触发时生效，正在运行的备份因此永远不会被终止。

`--reset-failed` 是可选的。传递时，它会在部署成功后清除已修改服务上 systemd 的 failed 状态。默认关闭，以便以前的故障信号对告警保持可见。

### 立即运行备份

无需等待定时器即可立即触发备份。即使没有部署定时器也可使用 `systemd-run` 进行临时执行：

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
```

### 查看备份状态

显示备份定时器的当前状态和最近的作业结果：

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### 取消正在运行的备份

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy nightly-cold
```

## 仓库迁移

将仓库从一台机器移动到另一台机器：

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| 选项 | 描述 |
|------|------|
| `--name <repo>` | 要迁移的仓库 |
| `--from <machine>` | 源机器 |
| `--to <machine>` | 目标机器 |
| `--provision` | 在传输前在目标上配置仓库 |
| `--checkpoint` | 迁移前创建 CRIU 检查点 |
| `--skip-dns` | 迁移后跳过 DNS 记录更新 |
| `--bwlimit <limit>` | 传输的带宽限制（例如 `50M`） |

迁移通过 rsync 传输加密的仓库数据。源仓库保持完整，直到您显式删除它。

## 浏览存储

浏览存储位置的内容：

```bash
rdc storage browse --name my-storage
```

## 最佳实践

- 为关键数据的应用一致性快照安排每日冷备份
- 对于需要零停机的高频快照，使用热备份
- 定期测试恢复以验证备份完整性
- 对关键数据使用多个存储提供商（例如 S3 + B2）
- 妥善保管凭据；备份是加密的，但恢复时需要 LUKS 凭据
