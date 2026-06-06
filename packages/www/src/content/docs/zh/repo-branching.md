---
title: "类 Git 分支管理"
description: "将写时复制 fork 当作 git 提交使用：将 fork 冻结为不可变提交、命名分支、将提交检出为可写 fork、遍历历史记录，以及在不改变任何实时仓库的情况下进行合并。"
category: Reference
subcategory: advanced
order: 41
language: zh
sourceHash: "2448559f0fcfc0e0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# 类 Git 分支管理

思维模型如下：Rediacc 将写时复制 fork 转换为类似 git 的版本历史。每个不可变 fork 都是一个**提交**：字节稳定的冻结镜像，拒绝挂载。分支是指向提交的命名引用。`rdc repo checkout` 将提交通过 reflink 克隆回可写的工作 fork，`rdc repo merge` 在不改变任何实时仓库的情况下合并两条历史线。

该模型映射到两个存储层。**机器是对象存储**：提交是驻留在数据存储上的不可变 fork 镜像。**CLI 配置是引用存储**：分支名称、当前 `HEAD` 和引用日志存在于本地配置中，而非机器上。这与 git 在 `.git/objects` 和 `.git/refs` 之间的分割方式相同。

## 何时使用

当一个 fork 值得命名时，就该使用分支管理。AI 智能体在生产仓库的 fork 中自由运行，结果看起来不错，你希望有一个冻结的、命名的检查点可以随时返回或在之后推广：`rdc repo commit` 冻结它，`rdc repo branch` 命名它。在进行高风险迁移之前，提交工作 fork 以便获得一个保证永远不会改变的精确回滚点（不可变提交拒绝挂载，因此没有任何内容可以写入它）。要比较两个检查点，`rdc repo diff` 可以在任意两个提交之间工作，因为它们共享写时复制祖先。要将已审查的工作线带回目标 fork，`rdc repo merge` 在 reflink 克隆中构建结果并原子性地交换进去，因此运行中的目标在合并过程中永远不会损坏。

不要在只需要临时副本时用它来替代 `rdc repo fork`。普通 fork 是临时的、每次测试隔离的正确单元。当某个状态值得保留、命名或发布时，提交才有价值。

## 提交与 fork 的关系

仓库是 btrfs 存储池上的一个 LUKS 镜像文件。fork 是该镜像的常数时间 reflink，因此 fork 一个 1 GB 仓库和 fork 一个 100 GB 仓库的成本相同。**提交**是被标记为不可变的 fork：renet 拒绝挂载它，这使其镜像永久字节稳定。字节稳定性正是使提交成为可靠回滚点和跨机器增量推送的确定性基础的原因。

`rdc repo commit` 在卷**内部**记录提交消息、作者、时间戳和父提交（这样元数据在推送时随镜像一起传输），同时在卷外部镜像这些信息（这样 `rdc repo log` 可以在不解锁任何内容的情况下遍历历史记录）。你提交的工作 fork 保持不变，就像 git 在提交后保持工作树完整一样。

## 命令

### rdc repo commit

将已挂载的工作 fork 冻结为新的不可变提交。

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `--name <name>` | 要提交的工作 fork，必须已挂载，必填。 | 必填 |
| `--message <msg>` | 提交消息，必填。 | 必填 |
| `--author <author>` | 提交元数据中记录的作者。 | 未设置 |
| `-m, --machine <name>` | 目标机器，必填。 | 必填 |
| `--debug` | 在 stderr 上输出详细诊断信息。 | 关闭 |

新提交在本地配置中以 `immutable: true` 注册，工作 fork 的 `headCommit` 更新以指向它。提交不可变仓库将被拒绝：请先将其检出到可写 fork 中。

### rdc repo branch

创建指向工作 fork 当前提交的命名分支引用。

```bash
rdc repo branch --branch <name> --name <fork>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `--branch <branch>` | 新分支的名称，必填。 | 必填 |
| `--name <name>` | 分支所指向的当前提交所在的工作 fork，必填。 | 必填 |

这是纯配置操作，不在机器上执行任何工作。分支引用将名称映射到工作 fork 的 `headCommit`，因此 fork 必须至少有一个提交。

### rdc repo checkout

将不可变提交（或分支尖端）通过 reflink 克隆到新的可写工作 fork 中。

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `--ref <commit\|branch>` | 要检出的提交 GUID，或在给定 `--from` 时的分支名称，必填。 | 必填 |
| `--tag <name>` | 新的可写工作 fork 的名称，必填。 | 必填 |
| `-m, --machine <name>` | 目标机器，必填。 | 必填 |
| `--from <workingFork>` | 在此工作 fork 的分支集上将 `--ref` 解析为分支名称。 | 直接提交 |
| `--debug` | 在 stderr 上输出详细诊断信息。 | 关闭 |
| `--skip-router-restart` | 跳过路由器重启步骤。 | 关闭 |

检出复用 fork reflink 路径，因此无论仓库大小如何都几乎是即时的常数时间操作。新工作 fork 的 `headCommit` 被设置为检出的提交。

### rdc repo log

遍历从工作 fork 或提交可达的提交历史记录。

```bash
rdc repo log --name <fork> -m <machine>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `--name <name>` | 开始历史遍历的工作 fork 或提交，必填。 | 必填 |
| `-m, --machine <name>` | 目标机器，必填。 | 必填 |
| `--json` | 以 JSON 格式输出提交历史记录。 | 关闭 |
| `--debug` | 在 stderr 上输出详细诊断信息。 | 关闭 |

`log` 遍历由 `rdc repo commit` 记录的父链，读取卷外状态镜像，因此不会解锁或挂载任何提交。这是只读操作。

### rdc repo merge

将源提交或 fork 合并到目标工作 fork 中，而不就地改变实时目标。

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `--name <name>` | 要合并到的目标工作 fork，必填。 | 必填 |
| `--from <source>` | 合并来源的提交或 fork，必填。 | 必填 |
| `-m, --machine <name>` | 目标机器，必填。 | 必填 |
| `--force` | 先静默已挂载或运行中的目标，然后合并。永不改变实时挂载。 | 关闭 |
| `--resolve <ours\|theirs>` | 逐文件三方合并：将源的逐文件变更叠加到目标上，对两侧都变更的文件保留 (`ours`) 或采用 (`theirs`) 源的版本。省略则使用全镜像取源。 | 关闭 |
| `--base <guid>` | 三方合并的公共祖先提交（与 `--resolve` 一起使用）。默认为源提交的父提交，或目标的当前提交。 | 自动 |
| `--debug` | 在 stderr 上输出详细诊断信息。 | 关闭 |

结果在 reflink 克隆中构建，并通过崩溃安全标记原子性地交换进来，因此中断的合并会保持原始目标完整。已挂载或运行中的目标将被拒绝，除非使用 `--force`，这会在交换前干净地关闭目标。

不使用 `--resolve` 时，合并是全镜像取源（目标变为源）。使用 `--resolve` 时，它是针对源提交记录的父提交的逐文件三方合并：只在一侧变更的文件从那一侧获取，两侧都变更的文件按标志解决。冲突路径会被报告。

### rdc repo gc

垃圾回收机器上没有任何分支或 HEAD 可达的不可变提交对象。

```bash
rdc repo gc -m <machine>            # 干跑预览（默认）
rdc repo gc --apply -m <machine>    # 删除不可达的提交
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `-m, --machine <name>` | 要回收的机器，必填。 | 必填 |
| `--apply` | 实际删除不可达的提交（否则为干跑预览）。 | 关闭 |
| `--debug` | 在 stderr 上输出详细诊断信息。 | 关闭 |

可达性从本地配置（引用存储）计算：通过跟随每个分支尖端和 HEAD 沿父链向下可达的提交集合。机器上不在该集合中的不可变提交是不可达的。已挂载的对象或工作 fork 永远不会被回收。

### rdc repo fsck

验证配置引用与机器上存在的对象。

```bash
rdc repo fsck -m <machine>
```

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `-m, --machine <name>` | 要检查的机器，必填。 | 必填 |

报告悬挂引用（分支尖端或 HEAD 指向机器上没有对象的 GUID）和孤立提交（机器上没有任何引用可达的不可变提交）。这是只读操作；使用 `rdc repo gc --apply` 回收孤立提交。

### 不可变 fork

`rdc repo fork --immutable` 在创建时将新 fork 标记为只读，无需单独的 `commit` 步骤即可产生等同于提交的基础。

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

不可变 fork 拒绝挂载，这使其镜像永久字节稳定。这对于跨机器增量推送的冻结基础很有用，其中基础在两端必须完全相同。要进行更改，请将其检出（或再次 fork）到可写副本中。

## 示例

### 提交工作 fork

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### 带明确作者的提交

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### 在当前提交处命名分支

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### 将提交检出到新的可写 fork

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### 按名称检出分支尖端

使用 `--from` 时，`--ref` 值在给定工作 fork 的分支集上解析为分支名称：

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### 遍历历史记录

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### JSON 格式的历史记录

`--json` 按从新到旧的顺序输出结构化遍历：

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### 对比两个提交

`rdc repo diff` 可以在任意两个提交之间工作，因为它们共享写时复制祖先。检出一个提交，然后将其与另一个对比：

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

完整的 diff 参考请参阅 [rdc repo diff](/zh/docs/repo-diff)。

### 将已审查的工作线合并回来

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### 合并到运行中的目标

已挂载或运行中的目标将被拒绝，除非使用 `--force`，它会先静默目标：

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### 逐文件三方合并

两个从同一提交检出的 fork（`feature` 和 `hotfix`）各自更改了一些文件。`--resolve theirs` 将源（`hotfix`）叠加到目标（`feature`）：只有一侧更改的文件从那一侧获取，两侧都更改的文件解析为源的版本。基础从共同祖先自动检测（或用 `--base` 固定）：

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` 在两侧都有更改，被解析为源的版本；只有 `hotfix` 新增的文件被应用，只有 `feature` 更改的文件被保留。冲突路径会被报告以便审查。

### 直接创建不可变基础

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## 增量推送与拉取

不可变的、字节稳定的镜像也是**块级增量传输**的基础。当两台机器上存在相同的不可变基础时，推送或拉取可以对比该基础计算变更的块，只移动这些块，而不是扫描整个加密镜像。一个有几个变更块的 1 GB 仓库可以以兆字节的方式传输。

通常不需要手动传递基础。完整推送后，CLI 在两台机器上将已推送的镜像保留为不可变基础并加以记录，这样该仓库的**下一次**推送会自动只发送增量，无需任何标志，即使是已存在于目标上的 fork 也是如此。（已存在 fork 的*完整*重新推送仍需要 `--force`，因为这会替换整个镜像而不是应用验证过的增量。）使用 `--delta-base <guid>` 固定特定基础，使用 `--strategy <auto|physical|shared>` 控制如何检测变更的块（`auto` 在几乎所有情况下都是正确的）。

```bash
# 第一次推送是完整传输；它还在两端保留可复用的基础。
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# 本地更改后，下一次推送只发送变更的块，无需标志。
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# 固定明确的基础（两台机器上都存在的不可变提交）。
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# 增量也适用于反向操作，只从机器源拉取变更的块。
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# 使用 --force 重新拉取已有的本地仓库（覆盖它）。
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

增量传输仅适用于机器之间（使用 FIEMAP 基础的远程端）。推送到云对象存储始终传输完整镜像。基础在两端必须字节相同，这正是不可变提交或 `--immutable` fork 所保证的。

## JSON 模式

`rdc repo log --json` 将 renet 结果包装在标准信封中。遍历的历史记录在 `entries` 中，按从新到旧排列：

| 字段 | 类型 | 描述 |
|------|------|------|
| `success` | boolean | 遍历是否完成。 |
| `start` | string | 遍历起始的 GUID。 |
| `entries` | array | 每个提交一个对象，从新到旧排列。 |
| `entries[].guid` | string | 提交 GUID。 |
| `entries[].message` | string | 提交消息，为空时省略。 |
| `entries[].author` | string | 提交作者，为空时省略。 |
| `entries[].parent` | string | 父提交 GUID，在根提交处省略。 |
| `entries[].committed_at` | string | RFC 3339 提交时间戳，未设置时省略。 |
| `entries[].immutable` | boolean | 提交是否标记为只读（真正的提交始终为 true）。 |

有关信封字段和在非 TTY 环境中发出 JSON 的自动检测规则，请参阅 [JSON 输出参考](/zh/docs/ai-agents-json-output)。

## 限制

- **引用是本地的。** 分支名称、`HEAD` 和引用日志存在于 CLI 配置中，而非机器上。将提交推送到另一台机器会传输提交对象及其卷内元数据，但分支引用是配置侧的概念。
- **提交拒绝挂载。** 这正是目的所在：不可变性使提交字节稳定。要运行或编辑提交，请先将其检出到可写工作 fork 中。
- **合并解决是文件级的，不是行级的。** 全镜像取源（不使用 `--resolve`）和逐文件三方（`--resolve ours|theirs`）都受支持。三方合并按标志逐文件解决冲突；它不会在文件内产生行级块或合并标记。
- **历史记录是父链。** `rdc repo log` 遍历提交时记录的单一 `parent` 链接。当它到达一个在被查询机器上没有元数据的提交时停止。

## 另请参阅

- [rdc repo diff](/zh/docs/repo-diff)。任意两个相关提交或 fork 之间的文件级 diff。
- [仓库](/zh/docs/repositories)。创建、fork、挂载和操作仓库。
