---
title: 监控
description: 监控机器健康状况、容器、服务、仓库，并运行诊断。
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: zh
sourceHash: "acef592a7065cac7"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# 监控

Rediacc 提供内置的监控命令，用于检查机器健康状况、运行中的容器、服务、仓库状态和系统诊断。

## 机器健康状况

获取机器的完整健康报告：

```bash
rdc machine health server-1
```

报告内容：
- **系统**：运行时间、内存（超过 80% 为警告，超过 90% 为错误）、磁盘和数据存储使用率（超过 85% 为警告，超过 95% 为错误）
- **容器**：运行中、健康和不健康的容器数量；处于 `Restarting` 循环的容器为严重
- **服务**：失败的 systemd 单元（错误）和不断重启的单元（严重）
- **存储**：SMART 健康状态（即将损坏的磁盘为严重）和磁盘温度
- **仓库**：未挂载的自动启动仓库，以及每个仓库的文件系统使用率（超过 85% 为警告，超过 95% 为错误）
- **备份**：超过 10 天未备份、落后于计划或目标，或上次验证失败的仓库
- **许可证**：已过期、缺失、不匹配或无效的仓库许可证，以及需要刷新的许可证
- **renet 进程**：仍在运行已被替换的 renet 二进制文件的守护进程
- **仓库健康**：每个已挂载仓库自身的 `health()` 结果（见下文）
- **证书**：代理中即将到期的证书，以及共享的 ACME 质询 CNAME
- **问题**：已识别的问题

退出码就是结论：`0` 无发现（没有 `health()` 检查的仓库会列为“无检查”，绝不算作健康），`1` 警告，`2` 错误，`3` 严重（磁盘即将损坏，或容器、服务陷入重启循环）。使用 `--output json` 获取机器可读的输出；其中包含 `repo_health`（每个仓库一份报告）和 `findings`，每条发现都带有代码、严重程度（`info`、`warning`、`error` 或 `critical`）、对象、详情，以及（存在修复方法时）`fix`（见[修复](#repair)）。

## 仓库健康

Rediaccfile 可以定义一个 `health()` 函数来检查仓库自身的服务（[服务](/zh/docs/services)）：退出码 `0` 正常，`1` 警告，`2` 错误。对单个仓库运行：

```bash
rdc repo health my-app@server-1
```

该命令以仓库所有 Rediaccfile 中最差的级别退出。没有任何 Rediaccfile 定义 `health()` 的仓库会输出**无检查**并以 `0` 退出；它绝不会被报告为健康。超时、被终止或以其他退出码结束的 `health()` 算错误，无法连接机器同样如此（退出码 `2`）。

`rdc machine health` 会一次调用运行所有已挂载仓库的 `health()`，并把最差的级别并入自己的退出码，每个仓库对应一条警告（`repo.health.warning`）或错误（`repo.health.error`）级别的发现。没有检查的仓库只会列出，不会作为问题报告。当机器上的 renet 早于仓库健康检查的版本时，结果是一条警告 `renet.repo-health.unsupported`，直到 `rdc machine setup` 将其更新。

## 证书到期与 ACME 质询

`rdc machine health` 会读取代理的 ACME 证书，对距离到期不足 21 天的证书报告 `cert.expiry.near`（警告），不足 7 天则为错误。代理会提前 30 天续期，所以证书不足 21 天意味着它的续期已经至少失败了九天。

当证书名称的 `_acme-challenge.<name>` 记录通过 CNAME 指向一个本身并非 `_acme-challenge.` 的名称，或者两个名称最终指向同一个名称时，它还会报告 `acme.challenge.cname-shared`。属于 CNAME 的通配符记录会造成这种情形：所有质询都落到同一个名称上，续期互相冲突。有意的委派（例如 `_acme-challenge.mail.example.com` 指向 `_acme-challenge.mail.example.io`）不会被报告；其他有意的委派请列在代理 `config.env` 的 `ACME_DELEGATED_NAMES` 中（以逗号分隔的证书名称列表）。质询链无法解析的名称（没有 DNS 解析器对它作出应答）会报告为 `acme.challenge.unknown`，这是一条警告，因为针对它的检查没有运行。

## 修复

每条发现都带有代码；如果存在安全的修复方法，还带有 `fix`，其中包含 `action`、安全 `class` 和 `window_only`。`rdc machine health` 保持只读；真正执行操作的是 `rdc machine repair`：

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| 类别 | 含义 |
|---|---|
| `auto-safe` | 默认运行：重启容器或 Traefik、trim 和清理、写入 ACME 锚点 |
| `auto-with-backup` | 仅在使用 `--with-backup` 且仓库快照成功之后运行；快照失败会取消修复 |
| `operator-only` | 绝不运行。命令会输出需要手动运行的确切命令。所有会删除命名数据或产生费用的操作都属于此类 |

`window_only` 是在类别之上的附加条件：修复只在机器的维护窗口内运行，格式为 UTC 的 `HH:MM-HH:MM`（可以跨越午夜）。没有窗口的机器绝不会自行运行这些修复；`--window-override` 可手动运行它们。按如下方式设置或清除窗口：

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

每个修复都会先确认其对应的发现仍然存在，因此第二次运行会报告无事可做。作用于同一对象的修复只运行一次（一次 Traefik 重启即可覆盖所有证书）。每个修复都会以标签 `rediacc-repair` 记录到机器日志，并记录在 JSON 的 `actions` 中（`code`、`subject`、`action`、`class`、`result`、`before`、`after`），运行结束时会做一次完整的重新检查。没有剩余问题时退出码为 `0`，剩下警告或 operator-only 项时为 `1`，剩下错误或严重发现，或有修复失败时为 `2`。`rdc machine repair` 从不以 `3` 退出，只有 `rdc machine health` 会。

| 发现 | 修复 | 类别 |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | 先 trim，再清理已停止的容器、匿名的孤立卷和未使用的镜像 | auto-safe |
| `container.unhealthy`, `container.restart-loop` | 重启容器 | auto-safe |
| `renet.binary.replaced` | 重启受影响的仓库监督进程（`rdc machine restart-services --include-docker`，仅限这些进程） | auto-safe，仅限窗口内 |
| `cert.expiry.near` | 重启 Traefik，让它重试续期 | auto-safe |
| `acme.challenge.cname-shared` | 写入 ACME 锚点（见下文） | auto-safe（已声明委派且没有可用的 Cloudflare 令牌时为 operator-only） |
| `repo.health.warning`, `repo.health.error` | 运行仓库的 `repair()`（[服务](/zh/docs/services)） | Rediaccfile 声明的类别 |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | 以需要运行的命令形式输出 | operator-only |

没有修复方法的发现（SMART 故障、温度、内存、系统盘、验证失败）只会被报告，留给运维人员处理。

清理绝不会触碰 hub：带有 `rediacc.hub.*` 标签的容器，以及带有 `rediacc.hub.user` 标签或名为 `rediacc-hub-home-*` 的卷都会被排除，因此 hub 用户的主目录在每次空间回收中都能保留。trim 和清理都无法释放的残余（命名卷、大型应用数据）仍由运维人员决定。

### 仓库修复

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` 按同样的类别运行仓库的 `repair()` 函数：`auto-safe` 会运行，`auto-with-backup` 需要 `--with-backup`，而未声明的（`operator-only`）`repair()` 只有在回答其确认提示后或使用 `--yes` 时才运行。之后 `health()` 会再次运行，退出码取决于最终的级别：`0` 正常或无检查，`1` 警告，`2` 错误或 `repair()` 失败。

### ACME 锚点

属于 CNAME 的通配符 DNS 记录会让每个 `_acme-challenge.<host>` 名称都跟随它，于是所有质询落到同一个名称上，续期互相冲突（`acme.challenge.cname-shared`）。修复会通过代理的 Cloudflare 令牌，在每个发生冲突的 `_acme-challenge.<name>` 上写入值为 `rediacc-acme-anchor` 的 TXT 记录，然后重启 Traefik。显式记录会让该名称脱离通配符的作用范围，质询便会落到该去的地方。该修复只添加记录，已有的锚点保持原样。本身就是 CNAME 的质询名称无法在旁边再放 TXT 记录：Cloudflare 会拒绝写入，修复会采用与令牌无法写入的区域相同的回退方式（见下一段）。

列在 `ACME_DELEGATED_NAMES`（代理 `config.env` 中以逗号分隔的证书名称列表）里的名称是有意的委派：它们不会被写入锚点，也不会被报告。当代理没有可用的 Cloudflare 令牌时，修复会退而使用 `config.env` 中的 `LEGO_DISABLE_CNAME_SUPPORT=true`，但仅限没有声明任何委派名称的情况，因为该变量会对所有名称关闭 CNAME 跟随；声明了委派时，这条发现仍然是 operator-only。同一个修复会在每次代理安装时运行（`rdc machine infra push`），也可以在机器上用 `renet proxy acme-fix` 单独运行。

## 列出容器

查看机器上所有仓库中运行的全部容器：

```bash
rdc machine status server-1 --containers
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
rdc machine status server-1 --services
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
rdc machine status server-1 --repositories
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
rdc machine status server-1 --storage-health
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

最后一次 scrub 的结果保存在 BTRFS 卷外部（位于 `/var/lib/rediacc/scrub-last-result.json`），即使卷出现问题也能保持可读。`rdc machine status --system` 的输出包含 `scrub_status` 字段：

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
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

结果保存到同一 JSON 文件，并在下次 `rdc machine status --system` 时立即可见。

## 机器概览

获取机器的完整概览，包括部署信息：

```bash
rdc machine status server-1
```

提供的信息：
- 主机名和运行时间
- 内存、磁盘和数据存储使用情况
- 仓库总数、已挂载数量，以及 Docker daemon 正常响应的仓库数量
- 每个仓库的详细信息

使用 `--output json` 获取机器可读的输出。

## 测试连接

验证与机器的 SSH 连接：

```bash
rdc term connect server-1 -c "hostname"
```

该命令在成功时打印远程主机名，失败时打印连接错误，一步即可验证 DNS、SSH 端口和密钥认证。

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
