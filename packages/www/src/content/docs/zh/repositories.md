---
title: "仓库"
description: "在远程机器上创建、管理和操作 LUKS 加密仓库。"
category: Guides
order: 4
language: zh
sourceHash: "65fd6e7f9e6a83c1"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 仓库

**仓库**是远程服务器上的 LUKS 加密磁盘镜像。挂载后，它提供：
- 用于应用程序数据的隔离文件系统
- 专用 Docker 守护进程（独立于主机的 Docker）
- /26 子网内每个服务的唯一环回 IP

## 创建仓库

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| 选项 | 必需 | 描述 |
|--------|----------|-------------|
| `-m, --machine <name>` | 是 | 将创建仓库的目标机器 |
| `--size <size>` | 是 | 加密磁盘镜像的大小（例如 `5G`、`10G`、`50G`） |
| `--skip-router-restart` | 否 | 跳过操作后重启路由服务器 |

输出会显示三个自动生成的值：

- **仓库 GUID** -- 标识服务器上加密磁盘镜像的 UUID。
- **凭证** -- 用于加密/解密 LUKS 卷的随机密码短语。
- **网络 ID** -- 整数（从 2816 开始，每次增加 64），确定此仓库的服务的 IP 子网。

> **安全保存凭证。** 它是仓库的加密密钥。如果丢失，数据无法恢复。凭证存储在本地 `config.json` 中，但不存储在服务器上。

## 挂载和卸载

挂载解密并使仓库文件系统可访问。卸载关闭加密卷。

```bash
rdc repo mount --name my-app -m server-1  # 解密并挂载
rdc repo unmount --name my-app -m server-1  # 卸载并重新加密
```

| 选项 | 描述 |
|--------|-------------|
| `--checkpoint` | 在挂载/卸载前创建 CRIU 检查点（用于标记 `rediacc.checkpoint=true` 的容器） |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

## 检查状态

```bash
rdc repo status --name my-app -m server-1
```

## 列出仓库

```bash
rdc repo list -m server-1
```

### 类型列和状态镜像

输出表格包括一个 `Type` 列，有三个值：

- **`grand`**。在本地 CLI 配置中注册的顶级仓库，没有父级。这是基本情况。
- **`fork`**。另一个仓库的写时复制分支。通过本地配置中的 `grandGuid` **或** 机器上的 renet `.interim/state` 镜像标识。任一源都是权威的；一旦镜像被填充，两者应该一致。
- **`unknown`**。两个信号都无法分类仓库。通常是镜像前的遗留分支（在镜像代码发布前创建，之后从未重新挂载过），或本地配置条目被误删的陈旧 `grand`。CLI 拒绝猜测；操作员应运行[镜像反填](/zh/docs/pruning#migration-state-mirror-backfill)或删除目录（如果确实是孤立的）。

`.interim/state/<guid>/.rediacc.json` 镜像是在 LUKS 加密卷**外**写入的小伴侣文件，因此备份工具和 `repo list` 可以读取分支族谱而无需解锁每个镜像。它具有与卷内 `.rediacc.json` 相同的形状（`is_fork`、`grand_guid`、`name` 等），并在每个 `Repository.SaveState` 时刷新。即每次挂载和每次状态变化。它是计划备份中分支检测的真实来源：具有说 `is_fork: true` 的镜像的未挂载分支从 `cold` 和 `hot` 上传中正确跳过。

例行清理未知条目，请参阅[`rdc machine prune --prune-unknown`](/zh/docs/pruning#phase-3---prune-unknown-surgical)。

## 调整大小

将仓库设置为精确大小或按给定数量扩展：

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # 设置为精确大小
rdc repo expand --name my-app -m server-1 --size 5G  # 在当前大小基础上增加 5G
```

> 调整大小前，仓库必须处于卸载状态。`repo expand` 支持在线执行。调整大小会改变仓库的最大容量上限；若只想将已释放的块归还给存储池而不改变上限，请改用 [`repo trim`](#reclaim-space-trim)。

## 回收空间（trim）

删除仓库内的文件会为该仓库释放空间，而 `repo trim` 会将这些已释放的块归还给共享数据存储池。此操作在线执行，不产生任何停机：

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

工作原理：仓库镜像是稀疏文件，加密卷会透传 discard 请求。trim 命令通知仓库内的文件系统释放所有未使用的块，在底层镜像中打孔，并立即缩减存储池占用量。

注意事项：

- 正在进行备份的仓库会被跳过并报告。在备份进行期间执行 trim 不会释放空间，因为备份快照仍持有对这些块的引用。
- 连续执行两次 trim 时，第二次报告回收量为 0 字节。文件系统会记住哪些块组已被 trim；这是正常行为，并非故障。
- `--docker` 不会删除已打标签的镜像，仅删除悬空镜像、已停止的容器和构建缓存。加上 `--docker-volumes` 还可删除未使用的卷（此操作会删除数据，仅限 CLI）。

## 自动容量策略

无需手动调整大小，可以让机器自行管理仓库容量。策略启用在线自动扩容（当仓库占满时自动增大其最大容量上限）以及定时 trim。机器通过 `rediacc-storage-maintain` systemd 定时器每隔几分钟应用一次策略。

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

策略字段：

| 字段 | 含义 | 默认值 |
|---|---|---|
| `--auto-grow` | 当仓库文件系统使用率超过阈值时自动在线扩容 | 关闭 |
| `--max-quota` | 自动扩容的容量上限。必填：设置此项是您明确同意超量分配存储池的承诺 | 无 |
| `--grow-threshold` | 触发扩容的文件系统使用百分比 | 85 |
| `--grow-step` | 每次扩容的增量：绝对值（`10G`）或当前大小的百分比（`20%`） | 20% |
| `--auto-trim` | 执行定时 trim | 关闭 |
| `--trim-interval` | 两次自动 trim 之间的最小间隔小时数 | 24 |

安全护栏：当存储池剩余空间低于保留量（10 GB 或存储池的 5%，取较大者）时，自动扩容拒绝执行；同一仓库两次扩容之间至少等待 30 分钟；扩容量永不超过 `--max-quota`。不支持自动缩减：减小仓库最大容量上限仍需手动执行离线的 [`repo resize`](#调整大小)。

每仓库设置会覆盖机器全局默认值。多次调用 `policy set` 仅更改您传入的字段。

## 分支

创建现有仓库在其当前状态的副本：

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

分支使用 name:tag 模型：生成的分支命名为 `my-app:staging`。这创建了一个具有自己 GUID 和网络 ID 的新加密副本，同时共享父级的名称。分支与父级共享相同的 LUKS 凭证。

> 分支通过 BTRFS reflink 与父级共享数据，包括磁盘上存储的任何凭证。关于当这些凭证授权 Stripe、AWS 或 Railway 等外部服务时的含义，请参阅 [Rediacc 不隔离的内容](/zh/docs/ai-agents-safety#what-rediacc-does-not-isolate)。要使部署时凭证不被分支访问，使用[每仓库密钥](#secrets)而不是将值硬编码到仓库内的 `.env` 文件。

在分支创建时，`repo fork` 立即在 `<datastore>/.interim/state/<fork-guid>/.rediacc.json` 处写入[状态镜像伴侣文件](#type-column-and-the-state-mirror)。无需解锁卷。因此新分支从创建时刻正确标识为 `is_fork: true`。这使计划备份可以跳过它（分支默认从上传管道中排除），即使它从未挂载过。分支一个分支时，`grand_guid` 正确链接：新分支的镜像指向原始祖先的 GUID，而不是中间分支。

### 一步完成分支并启动

`--up` 以一次远程操作完成分支、挂载和服务启动。加上 `--detach` 可在容器启动后立即归还终端，健康检查在后台继续，代理会持续重试直到各服务就绪：

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

实测数据：一个 128 GB 的仓库从分支到服务运行约需 57 秒，使用 `--detach` 约需 31 秒。后台模式下命令会打印进度查询提示：`rdc machine query --containers --name <machine>`。

### 耗时分布

运行时间超过几秒时，命令结束会输出一份时序摘要：逐步耗时、并行步骤瀑布图，以及将 Rediacc 流水线耗时与服务自身启动耗时分开统计的归因行：

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

服务启动耗时取决于容器镜像拉取、初始化脚本和健康检查等，由仓库的 Rediaccfile 定义，因应用而异。图表仅在交互式终端下渲染；如需在管道输出中强制显示，请设置 `RDC_TIMING_CHART=1`。

## 类 Git 版本控制

分支可以充当 git 提交的角色。`rdc repo commit` 将工作分支冻结为不可变的、字节稳定的提交；`rdc repo branch` 命名历史线；`rdc repo checkout` 将提交通过 reflink 克隆回可写分支；`rdc repo log` 遍历父链；`rdc repo merge` 在不就地改变实时仓库的情况下合并两条历史线。`rdc repo fork --immutable` 一步产生等同于提交的基础。

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

完整的命令集、选项和示例请参阅[类 Git 分支管理参考](/zh/docs/repo-branching)。

## 密钥

每仓库密钥是部署时凭证，注入容器而不写入加密仓库镜像。它们与仓库数据保持在独立平面上，因此 `rdc repo fork` 不会传播它们。分支以空密钥映射开始，其容器启动时将自己标识为不同于父级的外部主体。

> 想要逐步演练？请参阅[管理密钥教程](/zh/docs/tutorial-managing-secrets)了解完整的设置/列出/部署/验证/轮换周期。

**仅写模型 (GitHub 风格)：** `get` 仅返回 SHA-256 摘要。纯文本值永远不会返回给任何人，人类或代理。如果忘记值是什么，在密码管理器中查找并轮换；根据设计，你无法从 Rediacc 读取它回来。这消除了整个泄漏类别：终端录像、shell 历史、意外重定向、肩头冲浪。

两种交付模式：

- `env`。密钥在目标机器上的 renet shell 中导出为 `REDIACC_SECRET_<KEY>`。通过 `${REDIACC_SECRET_<KEY>}` 插值从 `docker-compose.yml` 中引用它。在容器环境中可见，因此使用此模式处理应用程序已期望在 env 中的连接字符串形状的值。
- `file`。密钥写入主机上的 `/var/run/rediacc/secrets/<networkID>/<KEY>`（tmpfs，从不持久化）。通过带 `file:` 源的顶级 `secrets:` 声明以及每个服务的 `secrets:` 列表从 compose 文件中引用它。容器从 `/run/secrets/<key>` 读取。对任何敏感数据优选此模式。它不会出现在 `docker inspect` 或 `/proc/<pid>/environ` 中。

```bash
# 设置、列出、获取（仅摘要）、取消设置
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — 无值
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**对称变化门。** 人类和代理都需要 `--current <previous-value>` 来覆盖或取消设置密钥（passwd 风格前置条件）。对于新密钥的首次写入，传递 `--current ""`（空）。要在不验证先前值的情况下轮换，改用 `--rotate-secret`。这会被大声审计为轮换。`--current` 和 `--rotate-secret` 互斥。

传递 `--value -` 从 stdin 而不是 argv 读取（避免 shell 历史泄漏以用于一次写入）。

在 `docker-compose.yml` 中：

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

小写服务端引用（`stripe_live_key`）是容器内 `/run/secrets/<name>` 文件名；主机路径尾部的大写（`STRIPE_LIVE_KEY`）与使用 `--key` 设置的内容匹配。`${REDIACC_NETWORK_ID}` 由 `renet compose` 自动插值。

> **跨仓库隔离执行**：renet 的 compose 验证器拒绝引用任何其他仓库网络 ID 的 `secrets: file:`（以及 `configs: file:` 和 `env_file:`）路径。字面 `${REDIACC_NETWORK_ID}` 令牌（或你自己网络的整数）是 `/var/run/rediacc/secrets/...` 引用的唯一接受形式。`--unsafe` **不会**覆盖此检查。Rediaccfile bash 子进程周围的 Landlock 沙箱也仅将文件系统访问限定于你自己网络的密钥目录，所以来自 Rediaccfile 的恶意 `cat /var/run/rediacc/secrets/<other>/X` 在内核层面失败，错误码为 EACCES。

> **分支**：`rdc repo fork` **不会**复制密钥。要在分支中使用密钥，在分支上显式运行 `rdc repo secret set --name <fork>`。这是负载承载安全属性。分支的容器不应能在外部服务上充当生产主体。

> **代理** (Claude Code、Cursor 等)：`repo secret list` 和 `repo secret get` 作为 MCP 工具公开（读安全。仅名称和摘要，永不值）。`set` 和 `unset` 仅限 CLI，因为 `--current`/`--rotate-secret` 仪式需要人工审视；通过 shell 调用它们的代理获得与人类相同的门。前置条件失败时，JSON 封装包含结构化 `errors[].next.options[].run` 字段。代理应将这些命令逐字中继给用户。完整模型请参阅 [AI 代理安全](/zh/docs/ai-agents-safety)。

## 验证

检查仓库的文件系统完整性：

```bash
rdc repo validate --name my-app -m server-1
```

## 所有权

将仓库内的文件所有权设置为通用用户（UID 7111）。这通常在从工作站上传文件后需要，那些文件到达时带有本地 UID。

```bash
rdc repo ownership --name my-app -m server-1
```

命令自动检测 Docker 容器数据目录（可写绑定挂载）并排除它们。这防止破坏用自己的 UID 管理文件的容器（例如 MariaDB=999、www-data=33）。

| 选项 | 描述 |
|--------|-------------|
| `--uid <uid>` | 设置自定义 UID 而不是 7111 |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

要强制对所有文件设置所有权，包括容器数据：

```bash
rdc repo ownership --name my-app -m server-1
```


查看[迁移指南](/zh/docs/migration)了解项目迁移期间何时以及如何使用所有权的完整演练。

## 模板

应用模板以使用文件初始化仓库：

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## 删除

永久销毁仓库及其内所有数据：

```bash
rdc repo delete --name my-app -m server-1
```

> 这会永久销毁加密磁盘镜像。此操作无法撤销。

## 迁移仓库

将仓库从一台机器实时迁移到另一台。唯一的停机时间是最后的增量同步阶段：通常是几秒到数分钟，具体取决于转换时的写入速率。

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| 选项 | 描述 |
|--------|-------------|
| `--provision` | 在迁移前在目标机器上预配仓库（创建 LUKS 镜像并注册配置） |
| `--checkpoint` | 转换前创建运行容器的 CRIU 检查点 |
| `--bwlimit <kbps>` | 限制 rsync 带宽，单位为每秒千字节 |
| `--skip-dns` | 转换后跳过更新 DNS 记录 |

**三阶段流程：**

1. **热预复制** - rsync 在仓库继续在源上运行时传输数据。大文件在任何停机前传输。
2. **转换** - 仓库在源上停止，最后的 rsync 传递同步剩余变化，仓库在目标上启动。
3. **在目标上启动** - renet 在目标机器上挂载并启动仓库。DNS 已更新，除非传递 `--skip-dns`。

![仓库实时迁移](/img/repo-migrate-flow.svg)

**Push vs migrate：**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| 操作 | 复制 | 移动 |
| 源之后 | 不变 | 已停止 |
| 停机时间 | 无（仅复制） | 简短转换窗口 |
| DNS 更新 | 否 | 是（除非 `--skip-dns`） |
| 用例 | 备份、暂存克隆 | 机器替换、服务器移动 |

## 清理

删除仓库或从失败操作恢复后，孤立的挂载目录、锁文件和不可移动的标记可能保留。清理安全删除这些：

```bash
# 预览将删除的内容
rdc machine prune --name server-1 --dry-run

# 删除孤立资源
rdc machine prune --name server-1
```

只有无匹配仓库镜像的资源受影响。非空挂载目录永不删除。
