---
title: 监控
description: 监控机器健康状况、容器、服务、仓库，并运行诊断。
category: Guides
order: 9
language: zh
sourceHash: "f56ab0bacb657043"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 监控

Rediacc 提供内置的监控命令，用于检查机器健康状况、运行中的容器、服务、仓库状态和系统诊断。

## 机器健康状况

获取机器的完整健康报告：

```bash
rdc machine health --name server-1
```

报告内容：
- **System**：运行时间、磁盘使用率、数据存储使用率
- **容器**：运行中、健康和不健康的容器数量
- **存储**：SMART 健康状态
- **问题**：已识别的问题

使用 `--output json` 获取机器可读的输出。

## 列出容器

查看机器上所有仓库中运行的全部容器：

```bash
rdc machine containers --name server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 容器名称 |
| Status | 运行时间或退出原因 |
| State | 运行中、已退出等 |
| Health | 健康、不健康、无 |
| CPU | CPU 使用百分比 |
| Memory | 内存使用量 / 限制 |
| Repository | 容器所属的仓库 |

选项：
- `--health-check`, 对容器执行主动健康检查
- `--output json`, 机器可读的 JSON 输出

JSON 输出包含完整的容器详情（`labels`、`port_mappings`、`image`、`id`），以及 `repository`（解析后的名称）、`repository_guid`（原始 GUID）、`domain` 和 `autoRoute`。

## 列出服务

查看机器上与 Rediacc 相关的 systemd 服务：

```bash
rdc machine services --name server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 服务名称 |
| State | 活跃、非活跃、失败 |
| Sub-state | 运行中、已停止等 |
| Restarts | 重启次数 |
| Memory | 服务内存使用量 |
| Repository | 关联的仓库 |

选项：
- `--stability-check`, 标记不稳定的服务（失败、超过 3 次重启、自动重启）
- `--output json`, 机器可读的 JSON 输出

JSON 输出包含完整的服务详情，并带有 `repository`（解析后的名称）和 `repository_guid`（原始 GUID）。

## 列出仓库

查看机器上的仓库及详细统计信息：

```bash
rdc machine repos --name server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 仓库名称 |
| Size | 磁盘镜像大小 |
| Mount | 已挂载或未挂载 |
| Docker | Docker daemon 运行中或已停止 |
| Containers | 容器数量 |
| Disk Usage | 仓库内的实际磁盘使用量 |
| Modified | 最后修改时间 |

选项：
- `--search <text>`, 按名称或挂载路径筛选
- `--output json`, 机器可读的 JSON 输出

JSON 输出包含 `name`（解析后的名称）和 `guid`（原始 GUID），并为每个仓库嵌套 `containers`（包含 `domain`、`autoRoute`、`repository`/`repository_guid`）和 `services` 数组。

## 存储健康状况

检查机器上所有仓库的 BTRFS 碎片化程度和 reflink 共享情况：

```bash
rdc machine query --name server-1 --storage-health
```

| 列名 | 描述 |
|--------|-------------|
| Quota | 仓库的最大容量上限（其扩容天花板，在创建时或通过 resize/auto-grow 设置） |
| Allocated | 稀疏镜像当前在存储池中实际占用的空间 |
| Unique | 仅属于该仓库的实际唯一数据 |
| Shared | 通过 BTRFS reflink 在仓库间共享的数据块（免费副本） |
| Reclaimable | 已分配与已使用之间的差额，可通过 [`repo trim`](/zh/docs/repositories#reclaim-space-trim) 归还给存储池。未挂载的仓库显示 `-` |
| Discards | 加密卷是否透传 discard（当前版本挂载的任何仓库均显示 `on`） |
| Divergence | 镜像中属于该仓库独有而非共享的数据百分比（越高意味着删除后可回收的空间越多） |
| Frag | 写时复制镜像中每 GB 的 extent 数量（仅供参考） |

Quota 与 Allocated 是两个有意区分的数值：一个配额为 20 GB、实际存储 6 GB 的仓库，在存储池中只占用其已分配的空间。因此存储池可以承诺的总配额超过其物理容量，而 Reclaimable 列显示每个仓库中有多少已分配空间已不再使用、可通过 trim 收回。

表格下方，存储池摘要报告数据存储的填充水位以及备份快照当前占用的空间：

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

备份运行期间，其快照持续引用与存活仓库共享的所有块，因此在该备份周期完成、快照被删除之前，删除操作和 trim 释放的存储池空间会减少。中断备份留下的孤立快照由存储维护程序在数分钟内自动检测并清除。

摘要显示 BTRFS reflink 节省的总量：

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **虚拟大小**是所有仓库镜像大小的总和。这是仓库的表观大小，但通过 reflink 共享的块会被重复计算。
- **唯一数据**是仅存在于一个仓库中的仓库数据实际占用的存储空间。这是删除仓库时将释放的空间。
- **共享**是通过 BTRFS reflink 在仓库间共享的数据。对仓库进行 fork 会创建 reflink 副本，在任一方写入新数据之前共享数据块，此后数据块开始分歧。
- **效率**是通过 reflink 共享的数据百分比。越高越好。具有大量来自同一父仓库 fork 的机器将显示接近 100% 的效率。

Frag 列仅供参考。它统计的是写时复制镜像文件的 extent 数量，而非应用程序在其中读取的文件，因此在正常的随机写工作负载下（数据库、容器层）读数会偏高，并不预示 SSD 存储上的读取性能。Rediacc 有意不提供碎片整理命令：`btrfs filesystem defragment` 会解除 reflink fork 和快照的共享，在存储池接近满载时可能导致使用量急剧膨胀，而基准测试表明读取性能没有可测量的提升。完整的测量数据和分析见[你的碎片化数值看起来触目惊心。我测了一下它到底有多大代价。](/zh/blog/i-benchmarked-btrfs-fragmentation)。

扫描并行运行，根据仓库数量和大小需要 5-15 秒。未指定 `--storage-health` 时，查询输出后会显示一行提示作为提醒。

## BTRFS Scrub

Rediacc 会在每台机器上自动安排每周 BTRFS scrub。Scrub 读取数据存储中的每个数据块，验证校验和，并报告任何损坏。这可在静默数据损坏（位衰减）传播到备份和 fork 之前将其检测出来。

Scrub 每周日 02:00 本地时间（机器时区）运行，带有最多 1 小时的随机延迟。它以最低 I/O 优先级（`ionice idle`、`nice 19`）运行，不会干扰正在运行的服务。在 SSD 支持的机器上，每 100 GB 数据存储大约需要 8 分钟。

Scrub 计时器在 renet 升级后的第一次 daemon 启动时自动安装。当 scrub 策略在未来的 renet 版本中更改时，它会在下次 daemon 启动时自动更新，无需用户操作。

### Scrub 状态

最后一次 scrub 的结果保存在 BTRFS 卷外部（位于 `/var/lib/rediacc/scrub-last-result.json`），即使卷出现问题也能保持可读。`rdc machine query --system` 的输出包含 `scrub_status` 字段：

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| 状态 | 含义 |
|------|------|
| `ok` | 最后一次 scrub 无错误完成 |
| `never_run` | Scrub 尚未运行（计时器刚安装） |
| `overdue` | 最后一次 scrub 超过 14 天前 |
| `errors_found` | Scrub 发现校验和不匹配（检查 `total_errors` 和 `uncorrectable` 计数） |
| `failed` | Scrub 进程以非零代码退出 |

如果 `uncorrectable` 大于零，受影响的块无法自动修复（单盘 BTRFS 没有冗余副本）。请从最近的备份恢复受影响的仓库。

### 手动 scrub

立即运行 scrub（例如，在断电或磁盘迁移后）：

```bash
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

结果保存到同一 JSON 文件，并在下次 `rdc machine query --system` 时立即可见。

## Vault 状态

获取机器的完整概览，包括部署信息：

```bash
rdc machine vault-status --name server-1
```

提供的信息：
- 主机名和运行时间
- 内存、磁盘和数据存储使用情况
- 仓库总数、已挂载数量和运行中的 Docker 数量
- 每个仓库的详细信息

使用 `--output json` 获取机器可读的输出。

## 测试连接

> **仅限云适配器。** 使用本地适配器时，使用 `rdc term connect -m server-1 -c "hostname"` 验证连接。

验证与机器的 SSH 连接：

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

报告内容：
- 连接状态（成功/失败）
- 使用的认证方式
- SSH 密钥配置
- 公钥部署状态
- Known hosts 条目

选项：
- `--port <number>`, SSH 端口（默认：22）
- `--save -m server-1`, 将已验证的主机密钥保存到机器配置中

## 诊断 (doctor)

对 Rediacc 环境运行完整的诊断检查：

```bash
rdc doctor
```

| 类别 | 检查项 |
|----------|--------|
| **环境** | Node.js 版本、CLI 版本、SEA 模式、Go 安装、Docker 可用性 |
| **Renet** | 二进制文件位置、版本、CRIU、rsync、SEA 嵌入式资源 |
| **配置** | 活跃配置、适配器、机器、SSH 密钥 |
| **虚拟化** | 检查系统是否可以运行本地虚拟机（`rdc ops`） |

每项检查报告 **OK**、**警告** 或 **错误**。在排查任何问题时，请将此作为第一步。

退出代码：`0` = 全部通过，`1` = 有警告，`2` = 有错误。

## 服务就绪检查

执行 `repo up` 期间，renet 会等待 HTTP 服务接受连接后再宣告其就绪。等待过程具有健康检查感知能力：

- Docker 报告状态为 **healthy** 的容器直接信任，不再发起 TCP 探测。
- 仍处于健康检查 `start_period` 内的容器记录信息日志而非警告；代理持续重试直到其就绪。
- 没有运行中容器的 Compose 服务（例如被非活跃 profile 排除的服务）直接跳过。
- 其余服务通过 TCP 探测，最长等待 15 秒（通过 `REDIACC_READINESS_TIMEOUT` 环境变量以秒为单位调整）。

对启动较慢的服务定义 [Docker 健康检查](https://docs.docker.com/reference/dockerfile/#healthcheck)，可为 renet 提供权威的就绪信号，同时减少部署输出中的探测噪声。
