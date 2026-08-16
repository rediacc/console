---
title: 备份与恢复
description: 通过两种方式备份加密仓库：仅上传变更单元的按内容寻址分块存储，或推送到任何与 rclone 兼容的存储的完整备份。在任何机器上恢复，并通过具名策略和 systemd 定时器自动执行。
category: Guides
order: 7
language: zh
sourceHash: "df8a9d53f6991817"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# 备份与恢复

Rediacc 可以将加密仓库备份到外部存储，并在同一台或不同的机器上进行恢复。备份是加密的，恢复时需要仓库的 LUKS 凭据。

## 两种备份方式

Rediacc 提供两种独立的备份方式，本指南将同时介绍。它们使用不同的存储和不同的命令，因此通过一种方式备份的仓库并不代表已通过另一种方式备份。

**分块存储**（`rdc backup snapshot`）以按内容寻址的固定大小单元上传仓库镜像。首次运行会上传全部非零清单；此后每次运行只会上传发生变化的单元，其判断依据是文件系统的分配元数据，而不是读取整个镜像。相同的单元在各个快照之间以及整个派生家族中只存储一次，使用量会计入您的存储配额（`rdc backup usage`）。

**存储推送已停用。** `rdc repo push --to <storage>` 曾用于将整个备份文件复制到您自行注册的兼容 rclone 的提供商。rclone 这条分支已被彻底移除，push、pull、list 和 restore 现在都会拒绝存储目标并将您指向本页。机器到机器传输不受影响：它本来就不经过 rclone。

从分块存储恢复已支持：`rdc backup restore <repo> --at <snapshot-id>` 可以物化一个已存储的快照，`--at` 也接受 RFC 3339 时间戳，将根据快照清单进行解析。添加 `--as <name>` 可以用不同的名称进行恢复，添加 `--up` 可在恢复后启动仓库。分块存储还提供上传（`rdc backup snapshot`）、验证（`rdc backup verify`，使用 `--deep` 可重新哈希每个单元而不仅仅是样本）、快照清单（`rdc backup manifests`）和配额会计（`rdc backup usage`）。

### 分块存储命令

```bash
# 上传快照。首次运行播种数据，之后的运行仅发送变更单元。
rdc backup snapshot my-app

# 规划而不上传：报告将会移动哪些内容。
rdc backup snapshot my-app --dry-run

# 不信任本地锚点，重新上传整个清单。
# 这会重新上传所有内容并重新计入配额；仅在确认锚点
# 已损坏时使用。
rdc backup snapshot my-app --reseed

# 检查已存储的清单和您的配额。
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

## 冷快照（`--cold`）

冷快照会在冻结仓库之前先把它停下来，因此存下来的镜像是应用一致的，而不只是崩溃一致的。这个命令在机器上直接运行：

```bash
# 默认数据存储上的每个仓库。
sudo renet backup snapshot --cold

# 只处理指定的仓库。--repo 接受仓库 GUID，可以重复使用。
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` 不能和 `--dry-run` 一起用。会停止容器的演练算不上演练，不停容器的运行也算不上冷备份，所以 renet 会直接拒绝这个组合，而不是替您挑一种含义。

### 一次冷运行做了什么

对每个选中的仓库，按以下顺序：

1. 停止它的容器。
2. 把仓库挂载点和数据存储刷写到磁盘。
3. 确认容器确实停下来了。
4. 为仓库镜像创建写时复制 reflink。
5. 重新启动容器。

之后才开始上传，此时所有仓库都已经恢复运行。

停机时间来自冻结，而不是传输。reflink 只涉及元数据，所以无论仓库装的是 1 GB 还是 100 GB，耗时都一样。上传不是这样：它随变化的字节数增长，首次快照要上传全部非零清单。如果一直等到上传结束才启动容器，停机时间就会和数据量绑定，首次备份就是几小时而不是几毫秒。

所有选中的仓库会在同一个窗口内一起停止，而不是逐个停止。这让每个仓库的停机时间略长一些，换来的是整组仓库共享同一个一致性点。

没有容器在运行的仓库本来就是静止的。它的快照完全不需要停机，这是正常结果，不是失败。

### 停机时间的代价

在真实机器上测得的整体停机时间为 **222 ms**：

| 阶段 | 实测 | 发生了什么 |
|------|------|------|
| `cold_down` | 64 ms | 容器停止 |
| `cold_sync` | 26 ms | 仓库挂载点和数据存储刷写到磁盘 |
| `cold_verify` | 31 ms | 确认容器已停止 |
| `cold_stage` | 0 ms | 仓库镜像的 reflink |
| `cold_up` | 99 ms | 容器重新启动 |

占大头的是容器重启，而暂存几乎不花时间：reflink 在毫秒精度下根本看不出来。不过这个零要和每个仓库的记录一起看，而不是单独看。把所有仓库都拒绝掉的运行同样会报告 `cold_stage=0ms`，只有记录才能说明您面对的是哪一种情况。

这份明细是证据，不是装饰。这五个阶段都不读取、也不发送仓库数据，所以备份变大时它们都不会变长。会变长的是上传，而上传发生在停机结束之后。

renet 在运行结束时会打印同样的数字，您可以自己在机器上测量，而不必只听我们的：

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

每个仓库的 JSON 记录也带着同样的停机时间和各阶段耗时，因此以后无需靠耗时猜测，就能分辨一个快照是冷的还是热的。

### 何时选择冷快照

热快照是默认选项，对大多数仓库来说也是正确选择。热快照是崩溃一致的，相当于仓库在断电之后的状态，而且完全不需要停机。大多数数据库和队列都能自行从这种状态恢复。

对那些在写入过程中无法安全捕获的数据，请选择冷快照。自带预写日志和内存状态的数据库就是最典型的例子。您用一段短暂且已被测量的停机时间，换来一个应用无需先做恢复就能打开的快照。

### 一次冷运行会拒绝什么

拒绝正是这里的功能。一个挂着冷标签、实际上什么都没有停下来的备份，是您只有在恢复时才会发现的谎言，所以 renet 绝不会悄悄把冷运行降级成热运行：

- **没有真正停止的容器。** 停止之后，renet 会向仓库自己的 Docker 套接字确认是否还有东西在运行。如果有，这个仓库会被拒绝，而不是被快照。这项检查向安全一侧收敛：如果套接字无法访问，或者容器列表读不出来，静止状态就算未经确认，未经确认即拒绝。
- **读不出来的许可证。** 许可证在停机之前检查，而不是之后，因为许可证读不出来的仓库本来就无法上传任何东西。这样的仓库会被跳过，而不会被停止。如果选中的仓库中没有一个拥有可读的许可证，整次运行会在任何容器停下之前就被拒绝。
- **同一数据存储上的第二次冷运行。** 该锁覆盖整个数据存储，锁被占用时会立即拒绝，并且什么都没有停止。两次重叠的运行会各自停止对方认为归自己管的容器，第二次还会启动第一次仍在冻结的仓库。跳过这次运行、等待下一次要好得多。

如果运行在容器停止期间被打断，比如遇到 `systemctl stop` 或重启，renet 会在退出前把它们重新启动。机器上的恢复机制是兜底：它会发现所有者已经消失的冷备份，并把这些仓库重新拉起来。

## 配置存储

在推送备份之前，需要注册一个存储提供商。Rediacc 支持任何兼容 rclone 的存储：S3、B2、Google Drive 等。

### 从 rclone 导入

如果您已经配置了 rclone 远程存储：

```bash
rdc storage import rclone.conf
```

此命令将 rclone 配置文件中的存储配置导入到当前配置中。支持的类型：S3、B2、Google Drive、OneDrive、Mega、Dropbox、Box、Azure Blob 和 Swift。

### 查看存储

```bash
rdc storage list
```

## 将备份推送到另一台机器

通过 SSH 将仓库复制到第二台机器：

```bash
rdc repo push my-app --to-machine server-1
```

加密镜像会以相同的 GUID 被复制，因此这是一次备份或迁移，而不是派生。要获得独立副本，请先运行 `rdc repo fork`，再推送该派生。

如需某个时间点的备份，请改用分块存储：`rdc backup snapshot my-app` 只上传发生变化的单元，`rdc backup restore my-app --at <snapshot>` 可以取回其中任意一个。

| 选项 | 描述 |
|------|------|
| `--to-machine <machine>` | 用于机器到机器备份的目标机器 |
| `--dest <filename>` | 自定义目标文件名 |
| `--checkpoint` | 推送前创建 CRIU 检查点（用于带有 `rediacc.checkpoint=true` 标签的容器）。目标在 `repo up` 时自动恢复 |
| `--force` | 覆盖已有备份 |
| `--bwlimit <limit>` | rsync 传输的带宽限制（例如 `10M`、`500K`） |
| `--tag <tag>` | 为备份添加标签 |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |
| `--skip-router-restart` | 操作后跳过路由服务器重启 |

## 从另一台机器拉取备份

从存放仓库的机器上将其取回：

```bash
rdc repo pull my-app --from-machine server-1
```

若要改从分块存储恢复，请使用
`rdc backup restore my-app --at <snapshot-id>`。

拉取操作会拒绝覆盖当前**已挂载**的仓库。请先卸载仓库，执行拉取，然后使用 `rdc repo up` 重新启动。基于目录的仓库是例外：即使处于挂载状态，它们也会原地同步。

| 选项 | 描述 |
|------|------|
| `--from-machine <machine>` | 用于机器到机器恢复的源机器 |
| `--force` | 覆盖已有本地备份 |
| `--bwlimit <limit>` | rsync 传输的带宽限制（例如 `10M`、`500K`） |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |
| `--skip-router-restart` | 操作后跳过路由服务器重启 |

## 列出备份

列出分块存储中的快照：

```bash
rdc backup manifests my-app
```

要查看某台机器上的备份产物：

```bash
rdc backup list -m server-1
```

输出列出该仓库在分块存储中保存的所有快照：

| 列 | 含义 |
|---|---|
| `Mode` | `hot` 或 `cold`。此条目所属的定时备份文件夹 |
| `Name` | 从本地配置解析的仓库名称（对于不在配置中的仓库回退到 GUID） |
| `GUID` | 磁盘上的仓库 GUID |
| `Size` | 备份文件的可读大小 |
| `Modified` | 来自存储后端的 UTC 时间戳 |

列出存储后端的功能已随 rclone 分支一并停用；该命令会被拒绝，并指出以下两个替代方式。

### hot 和 cold 到底意味着什么

`--mode hot` 和 `--mode cold` 描述的是备份过程中如何对待仓库，而不是数据最终落在哪里。

**hot** 会对正在运行的仓库做快照。容器持续对外服务，镜像是在写入过程中被捕获的，因此备份是崩溃一致的：相当于机器在那一瞬间断电时的状态。这对任何能从自身日志恢复的东西都没问题，而大多数数据库正是如此。

**cold** 会先停止容器、刷写到磁盘、确认容器确已停止，冻结镜像后才重新启动容器。这会带来真实的停机，但这段停机是耗时恒定的冻结过程，而不是传输过程，其结果是应用一致的。

两者都写入同一个分块存储。单元按内容寻址，因此一个仓库如果同时被每小时的 hot 计划和每周的 cold 计划备份，共享的块只会存储一次而不是两次，派生家族之间也同样共享。使用量会通过 `rdc backup usage` 计入您的配额。

## 一次同步一个仓库

推送和拉取一次只作用于一个仓库，通过 ref（`name`、`name:tag` 或 `name@machine`）指定。没有"一次处理所有仓库"的形式：请为每个仓库各运行一次命令。

### 推送到另一台机器

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### 从另一台机器拉取

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| 选项 | 描述 |
|--------|-------------|
| `--to-machine <machine>` | 用于机器到机器推送的目标机器 |
| `--from-machine <machine>` | 用于机器到机器拉取的源机器 |
| `--force` | 覆盖已有的备份或仓库 |
| `--checkpoint` | 推送前创建 CRIU 检查点（仅推送） |
| `--up` | 拉取后挂载并部署仓库（仅拉取） |
| `--bwlimit <limit>` | rsync 传输的带宽限制（例如 `10M`） |
| `--delta-base <guid>` | 仅传输相对于不可变基准 GUID 发生变化的块 |
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

冷备份对每个包含的仓库执行三个阶段：**停止 → 快照 → 启动**。了解保证的边界有助于运维人员及早发现部分故障。

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

- `rdc machine status <machine> --containers` 显示运行状态。与预期集合进行比较。
- 机器上的 `/var/run/rediacc/cold-backup-<guid>.status.json`。通过 `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"` 检查。`success: false` 加上过时的 `startedAt` 表示上次备份未正常完成。
- renet 备份运行的日志（`journalctl -u renet-*` 或直接的 `rdc backup schedule` 调用）会输出 `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` 形式的最终摘要行。非空的 `failed_repos` 是 grep 的目标。

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
| 4 CPU 虚拟机 | 5 个仓库，平均每个 30 秒 | 2 | 约 75 秒 |
| 16 CPU 服务器 | 10 个仓库，平均每个 40 秒 | 8 | 约 80 秒 |
| 64 CPU 集群节点 | 50 个仓库，平均每个 40 秒 | 8 | 约 4 分钟 |

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

此默认值是有意的。对同一个 datastore 并行运行两个冷备份会争夺 BTRFS 快照路径、rclone 远端以及 `/var/run/rediacc/cold-backup-<guid>.status.json` 的每仓库 sidecar。等待正在运行的实例比从两个方向同时操作同一数据要稳妥得多。

**监控含义。** 一个挂起的备份（例如，rclone 卡在网络黑洞上）会静默丢弃每个后续的定时器触发。调度器不会发出警报。监视 `systemctl show <unit> -p ActiveEnterTimestamp`：如果服务处于 `activating` 状态的时间超过预期的运行时长（例如，在夜间定时器上超过 48 小时），请进行调查。

**如果您需要每个计划触发都运行**，将定时器从 `OnCalendar=<cron>` 切换为 `OnUnitInactiveSec=<间隔>`。这会在上次运行完成 N 小时后触发，而不是按固定的挂钟计划，因此长时间运行不会导致丢弃。只会将下一次运行推迟。代价是计划漂移：您的 03:00 夜间变为"上次结束后 24 小时"。

### 快照、中断与存储池空间

每次推送都基于数据存储的瞬时快照进行，因此即使仓库持续写入，上传的数据也是一致的。备份运行期间，该快照持续引用与存活仓库共享的所有块：在周期完成、快照被删除之前，删除操作和 [trim](/zh/docs/repositories#reclaim-space-trim) 释放的存储池空间会减少。[存储健康报告](/zh/docs/monitoring#storage-health) 显示备份快照当前占用的空间。

中断是安全的。停止服务（或重启机器）会使备份中止传输并在退出前删除快照；下一次计划运行会从中断处续传，因为内容未变的文件会通过校验和跳过。如果进程被强制终止（如断电）导致无法正常清理，孤立快照会由存储维护程序在数分钟内自动检测并清除。

### 定义策略

规范的默认设置是双策略组合：一个快速的每小时 hot 流，覆盖每个仓库；一个较慢的每周 cold 流，为了应用一致性快照而暂停容器。两者写入同一个分块存储，共享的块只存储一次，而不是按流各存一份。

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

cold 策略上的 `--exclude` 过滤器是针对体积过大、无法纳入每周维护窗口的仓库的推荐逃生口。每小时 hot 策略仍然覆盖它们；cold 只是跳过。`--exclude` 中的仓库名称匹配本地配置的仓库名称（不带 `:tag`）。

| 选项 | 描述 |
|------|------|
| `<strategy>`（位置参数） | 策略名称（用于机器绑定） |
| `--destination <storage>` | 上传目标存储提供商 |
| `--cron <expression>` | cron 表达式（例如 `"0 2 * * *"` 表示每天凌晨 2 点） |
| `--mode <hot\|cold>` | 备份模式 |
| `--bwlimit <limit>` | 上传带宽限制（例如 `10M`） |
| `--include <pattern>` | 包含过滤器（可重复使用） |
| `--exclude <pattern>` | 排除过滤器（可重复使用） |
| `--enable` / `--disable` | 启用或禁用策略 |

### 查看策略

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### 删除策略

```bash
rdc backup strategy remove weekly-cold
```

### 将策略绑定到机器

在配置中，将一个或多个策略名称绑定到机器：

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **绑定仅作用于本地配置。** 定义策略并将其绑定到机器并不会改动机器本身。运行 `rdc backup schedule -m <machine>`（参见[将计划部署到机器](#将计划部署到机器)）以部署 systemd 定时器，并在任何策略或绑定更改后重新运行。

## 选择热备份或冷备份以及按仓库筛选

### 热备份与冷备份一览

| | 热备份 | 冷备份 |
|---|--------|--------|
| **一致性** | 崩溃一致性（运行中进行 BTRFS 快照） | 应用一致性（停止 → 快照 → 启动） |
| **停机时间** | 无 | 每个仓库的停止+启动窗口（通常 5-120 秒） |
| **适合频率** | 高频（例如每小时） | 低频（例如每天或每周） |
| **典型用途** | 频繁的安全网 | 计划的保证一致性备份 |

**热备份**是高频运行的正确默认选择。服务在快照期间保持运行，因此备份窗口不会中断用户。快照是崩溃一致的：相当于异常关机后获得的状态。对于大多数现代数据库和消息队列，这是可以接受的。

**冷备份**适用于需要保证应用一致性快照且可以接受短暂的每仓库重启的场景。服务在快照前停止，并在上传开始前重启，因此缓慢或失败的上传不会延长停机窗口。完整的保证模型请参见[冷备份语义](#冷备份语义)。

### 按策略筛选仓库

每个策略可以携带 `--include` 和 `--exclude` 过滤器。与 `--exclude` 模式匹配的仓库名称将在该策略中被跳过；`--include` 将运行限制为仅匹配的名称。过滤器匹配本地配置的仓库名称（不带 `:tag`）。

```bash
# 热备份策略：每小时备份所有内容
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# 冷备份策略：每周备份所有内容，排除大型派生数据集
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### 何时从高频热备份策略中排除仓库

在以下情况下将仓库从高频运行中排除：

- 仓库较大且**完全可以从卷上已有的源数据重新生成**，因此每次每小时备份都会浪费大量带宽而不增加实质的恢复价值。
- 按您的可用上传速度，备份运行会超过其自身的计划间隔。

**示例。** `analytics-demo` 仓库包含大约 114 GB 的派生 Postgres 表，这些表可以从同一个卷中已存储的原始 CSV 转储文件完全重建。在 6 MB/s 上传限制下，该仓库的单次热备份需要超过 5 小时。每小时运行意味着每次运行在下一次触发时仍在进行，导致所有后续运行被静默丢弃（参见[长时间运行的备份和重叠的计划](#长时间运行的备份和重叠的计划)）。从 `hourly-hot` 中排除并保留在 `weekly-cold` 中意味着每周备份一次，而不是永远不备份。

> **如果数据是纯粹可再生的**，请考虑是否需要备份它。另一种方法是只备份原始源输入（在本例中是 CSV 转储），完全跳过派生副本。源输入的每周冷备份要小得多，完全足以用于恢复。

不被任一策略排除的仓库会被两者同时捕获，因此它既有每小时的崩溃一致性快照，也有每周的应用一致性快照。`rdc backup manifests <repo>` 会把它们一起显示出来，两者共享的块只存储一次。

## 备份操作

### 将计划部署到机器

将绑定的策略作为 systemd 定时器推送到机器：

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

部署是一个状态协调器。它读取机器上当前的单元文件和 systemd 状态，与配置会生成的内容进行比较（每个文件 SHA-256），只触及内容实际发生变化的单元。在没有配置变更的情况下重新运行是 no-op：无写入、无 `daemon-reload`、无定时器扰动。

`--dry-run` 为每个策略打印计划（`created`、`updated (service, timer, env)`、`unchanged`、`removed`），不触及机器。与 `--debug` 组合使用还会打印生成的单元内容；rclone token 会被编辑。

如果您即将更新或删除的策略当前正在运行备份，部署会快速失败，并提示取消它或传递 `--force`。使用 `--force` 时，正在运行的调用保留其内存中的单元，新配置在下次定时器触发时生效，正在运行的备份因此永远不会被终止。

`--reset-failed` 是可选的。传递时，它会在部署成功后清除已修改服务上 systemd 的 failed 状态。默认关闭，以便以前的故障信号对告警保持可见。

### 立即运行备份

无需等待定时器即可立即触发备份。即使没有部署定时器也可使用 `systemd-run` 进行临时执行：

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### 查看备份状态

显示备份定时器的当前状态和最近的作业结果：

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### 取消正在运行的备份

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## 仓库迁移

将仓库从一台机器移动到另一台机器：

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| 选项 | 描述 |
|------|------|
| `<ref>`（位置参数） | 要迁移的仓库引用，其 `@machine` 部分指定源 |
| `--to <place>` | 目标机器或集群 |
| `--provision` | 在传输前在目标上配置仓库 |
| `--checkpoint` | 迁移前创建 CRIU 检查点 |
| `--skip-dns` | 迁移后跳过 DNS 记录更新 |
| `--bwlimit <limit>` | 传输的带宽限制（例如 `50M`） |

迁移通过 rsync 传输加密的仓库数据。源仓库保持完整，直到您显式删除它。

## 浏览存储

`rdc storage browse` 和 `rdc storage import` 是这次停用的例外：它们会从 PATH 启动您自己的 rclone，而不是内置副本，并且仍然是读取变更之前所写归档的方式。

```bash
rdc storage browse my-storage
```

浏览是只读的。推送到、从中拉取以及列出存储后端均已停用；每个命令都会被拒绝，并指出取代它的分块存储命令。

## 最佳实践

- 为关键数据的应用一致性快照安排每日冷备份
- 对于需要零停机的高频快照，使用热备份
- 定期测试恢复以验证备份完整性
- 对关键数据使用多个存储提供商（例如 S3 + B2）
- 妥善保管凭据；备份是加密的，但恢复时需要 LUKS 凭据
