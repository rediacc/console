---
title: "rdc repo diff"
description: "显示两个写时复制(copy-on-write)分支仓库之间的类Git风格的文件级差异,通过在块级别比较其加密镜像,无需解密。"
category: Reference
subcategory: advanced
order: 40
language: zh
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` 报告两个相关仓库之间哪些文件发生了变更:一个分支与其父仓库,或任何共享写时复制祖先的两个仓库。传递 `--name <fork>` 以针对本地配置记录的分支父仓库进行差异比较,或添加 `--base <repo>` 以针对任意相关仓库进行差异比较,其中 `--base` 是基础(旧)端, `--name` 是目标(新)端。此命令只读,永不解密镜像。它在远程机器上的块级别比较它们,因此成本由改变的块数量决定,而不是仓库的大小:一个1GB的仓库和一个100GB的仓库,如果进行相同的编辑,耗时相同。如果整个仓库发生变更,块数量会随大小而扩展,成本也会随之增加。

## 何时使用

总之:在推广分支之前,使用 `repo diff` 命令。一个AI代理在生产环境的分支副本中失控,你想在合并更改前准确看到它修改了哪些文件: `repo diff --name <fork> -m <machine>` 在几秒内为你提供文件列表。几秒钟。灾难恢复还原后,将已还原的分支与其应该复制的快照进行差异比较,以确认预期的文件集已返回且没有其他内容漂移。对于与父仓库并行运行数周的长期分支,差异比较显示累积的发散(配置编辑、日志增加、模式迁移),无需手动挂载和遍历两棵树。

不要跨不相关的仓库使用它。两端必须共享一个写时复制祖先,因为比较在共享的块历史上工作。这也不是一个二进制差异工具: `--content` 仅为文本文件产生行级输出,二进制文件报告 `Binary files differ` 。

## 命令参考

### 概览

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### 选项

| 选项 | 说明 | 默认值 |
|--------|-------------|---------|
| `--name <name>` | 要检查的仓库(目标,新端)。必需。| 必需 |
| `--base <name>` | 要进行差异比较的仓库(基础,旧端)。默认为 `--name` 的父仓库,从本地配置解析。| `--name` 的父仓库 |
| (无格式标志) | 名称状态输出:每个更改文件显示彩色的 `A` / `M` / `D` / `R` 字母加一行摘要。| 启用 |
| `--name-only` | 每行一个更改路径,无状态字母。便于管道。| 禁用 |
| `--stat` | 每个文件的更改幅度(字节和块增量)及总计页脚。| 禁用 |
| `--content <path>` | 单个文件的统一文本差异。仅文本;二进制文件报告 `Binary files differ` 。| 禁用 |
| `--json` | 用于代理和脚本的结构化输出。| 禁用 |
| `--fast` | 跳过内容哈希确认步骤,信任块筛选器。更快,但可能将文件过度报告为已修改。| 禁用 |
| `-m, --machine <name>` | 目标机器。必需。| 必需 |
| `--debug` | stderr上的详细诊断。| 禁用 |
| `--skip-router-restart` | 跳过路由器重启步骤。| 禁用 |

## 示例

### 默认名称状态与父仓库比较

仅使用 `--name` 时,分支与本地配置中记录的父仓库进行差异比较。此处分支 `test-1gb:fork1` 有一个已修改的文件:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### 与显式基础比较

传递 `--base` 以针对任意相关仓库进行差异比较。 `--base` 是基础(旧)端, `--name` 是目标(新)端:

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### 使用 `--stat` 显示更改幅度

`--stat` 添加每个文件的字节和块增量及总计页脚:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### 仅路径,用管道输入工具

`--name-only` 每行打印一个路径,无状态字母,准备好输入到另一条命令:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### 单个文件的行级差异

`--content` 生成单个文本文件的统一差异:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### 使用 jq 筛选JSON

`--json` 在stdout上发出结构化信封,因此它可以干净地输入到 `jq` :

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## 输出格式

### 名称状态(默认)

每个更改文件获得一个状态字母和其路径。 `A` 表示已添加, `M` 表示已修改, `D` 表示已删除, `R` 表示已重命名(显示旧路径)。后面是总结行,显示每个类别的计数。

### `--name-only`

每行一个路径,无状态字母,无总结。当下游命令需要干净的文件列表时使用。

### `--stat`

每行显示文件的字节增量和块增量。页脚报告总文件数和总修改字节数。这显示了变更的重点在哪里,而不仅仅是哪些文件移动。

### `--content <path>`

单个文本文件的标准统一差异( `---` / `+++` 头部, `@@` 块)。二进制文件报告 `Binary files differ` 并产生无块。

### `--json`

完整的结构化结果。数据输出到stdout;进度和诊断输出到stderr,因此JSON可以干净地输入到 `jq` 或另一个解析器,即使进度正在打印。

## JSON模式

CLI将renet结果包装在标准信封中( `success` 、 `command` 、 `data` 、 `errors` 、 `warnings` 、 `metrics` )。差异结果位于 `data` 中,使用snake_case字段:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

`entries[]` 中的每个对象描述一个更改路径:

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | 已添加、已修改、已删除或已重命名。 |
| `path` | string | 目标端上的路径(或删除的基础端路径)。 |
| `old_path` | string | 之前的路径。仅在重命名时存在。 |
| `type` | `file` \| `dir` \| `symlink` \| `other` | 条目类型。 |
| `old_size` | number | 基础端的大小(字节)。 |
| `size` | number | 目标端的大小(字节)。 |
| `bytes_changed` | number | 不同的字节数,向上舍入到整数块。 |
| `blocks_changed` | number | 已更改块的数量。 |
| `inode` | number | inode数字,用于重命名检测。 |
| `content_changed` | boolean | 文件内容(而不仅仅是元数据)是否已更改。 |
| `mode_changed` | boolean | 文件模式是否已更改。当为真时存在 `old_mode` / `new_mode` 。 |
| `uid_changed` | boolean | 所有者是否已更改。当为真时存在 `old_uid` / `new_uid` 。 |
| `gid_changed` | boolean | 组是否已更改。当为真时存在 `old_gid` / `new_gid` 。 |
| `old_target` / `new_target` | string | 符号链接目标。对于更改的符号链接存在。 |

有关信封字段和在非TTY环境中发出JSON的自动检测规则,请参阅 [JSON输出参考](/en/docs/ai-agents-json-output) 。

## 工作原理

仓库是btrfs池上的LUKS2镜像文件,分支是该镜像的常数时间reflink副本。 `repo diff` 通过FIEMAP在块级别比较两个加密镜像,仅读取文件系统元数据,永不解密任何内容。它通过LUKS数据偏移移动更改的密文偏移,以获得ext4设备偏移,然后通过每个文件的ext4extent映射将这些偏移映射回文件名。两个挂载的最终inode身份遍历将结果协调为已添加、已修改、已删除和已重命名条目。因为工作受已更改块数量的限制,所以差异与仓库大小无关,因为它在适当位置重用实时挂载,所以它永不扰乱运行中的仓库。完整机制在 [Git diff for encrypted disk images](/en/blog/git-diff-for-encrypted-disk-images) 中描述。

## 限制

- **仅相关分支。** 两端必须共享写时复制祖先。不相关仓库之间没有有意义的块级比较。
- **重命名检测基于inode。** 当相同inode出现在新路径上时,文件被报告为已重命名。删除后重新创建(新inode)显示为已删除加已添加条目,而不是重命名。
- **`--content` 仅文本。** 它为文本文件产生行级块。二进制文件报告 `Binary files differ` 。
- **`--fast` 可能过度报告已修改。** 它信任块筛选器并跳过内容哈希确认,因此块移动但内容未更改的文件可能显示为已修改。
- **Extent遍历时间随碎片化扩展,而非大小。** 高度碎片化的文件系统有更多extent要映射,即使更改的字节量很小,也会延长遍历时间。

## 另请参阅

- [rdc repo fork](/en/docs/repositories) 。创建此命令比较的写时复制分支。
- [rdc repo status](/en/docs/repositories) 。单个仓库的当前状态。
- [rdc repo cat](/en/docs/repositories) 。从仓库中读取单个文件。
