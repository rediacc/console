---
title: "备份下载"
description: "将仓库的加密镜像复制到本地目录或外接驱动器,后续运行时就地更新,也可以不依赖任何机器,直接从备份存储重建。"
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: zh
sourceHash: "c52e6a0471befc30"
---

# 备份下载

`rdc backup download` 会在本地目录或外接驱动器上保存仓库加密镜像的副本。副本与机器上的密文完全相同,因此传输途中不会解密任何内容。打开镜像所需的凭据保留在配置中,所以登记 [config storage](/zh/docs/config-storage) 是妥善保管凭据的办法。没有这份凭据,镜像无法打开。

来源有两种。默认来源是运行中的机器。另一种是备份存储,通过 `--store` 选择。

## 从机器下载

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` 指定一个已存在且可写的目录。该目录不会被创建,因此需要先挂载驱动器。镜像保存为 `<machine>/<name>.<tag>.img`,旁边会生成一个 `.state.json` 文件。

每次运行都会为仓库新建一个快照,只在传输期间保留,通过 rsync 发送差异,并将结果的 sha256 与机器上的快照进行比较。

| 标志 | 作用 |
|------|--------|
| `--all -m <machine>` | 复制放置在该机器上的所有 grand 仓库 |
| `--include-forks` | 与 `--all` 一起使用时,同时复制 fork |
| `--bwlimit <rate>` | 限制网络带宽,例如 `100Mbps` 或 `12.5M` |
| `--checkpoint` | 在快照之前对仓库做 checkpoint 并冻结(热备份) |
| `--retries <n>` | 网络故障后在本次运行内的重试次数(默认 3) |
| `--skip-verify` | 跳过 sha256 比较;rsync 自身的校验和仍会运行 |
| `--skip-space-check` | 目标可能缺少可用空间时,只警告而不拒绝 |

### 更新副本

再次运行时,会通过 rsync 增量就地更新现有镜像。每周运行一次也只发送变化的部分,目标上只需容纳一份镜像,而不是两份。运行开始前会对照镜像大小检查可用空间,`--skip-space-check` 可将拒绝改为警告。

### 中断的运行与续传

状态文件记录 `status`。从写入第一个字节之前,到运行通过验证为止,它的值都是 `incomplete`,而 `incomplete` 的镜像不可使用。按 Ctrl-C、连接中断或进程被强行终止,都会使其停留在这个状态。再次运行同一条命令即可续传,只发送差异。状态变为 `complete` 后,命令以退出码 0 结束。

### 要求

传输需要本机安装 rsync 3.1.3 或更高版本,且没有 SFTP 回退方案。Linux 发行版自带该工具。在 macOS 上,`brew install rsync` 会取代无法执行传输的内置 openrsync。在 Windows 上,需要安装带有 rsync 软件包的 MSYS2,或使用桌面应用。

### 外接驱动器

目标文件系统决定能存下什么。

- **FAT32** 无法容纳超过 4 GiB 的文件,命令会拒绝此次运行。
- 不支持稀疏文件的 **exFAT** 会按镜像完整的表观大小存储,因此可用空间检查也按这个大小计算。
- 在本地对目标创建的**写时复制快照**(btrfs、ZFS、APFS)会保留镜像的早期版本。此后每次就地更新,除旧块之外还要为变化的块占用空间。

## 从备份存储下载

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` 不经过任何机器,直接从分块存储重建镜像。`REDIACC_TOKEN` 中的令牌需要 `backup:read` 和 `backup:restore` 两个 scope。CLI 登录从不带有 `backup:restore`,因此需要在门户的 API Tokens 页面创建令牌。令牌必须属于某个团队,并由当前的组织所有者或管理员创建。

`--store` 只接受一个仓库名称。它不接受 `-m`、`--checkpoint`、`--all`、`--include-forks`、`--bwlimit`、`--retries`、`--skip-verify` 和 `--skip-space-check`:从存储获取有自己的续传机制,并会验证每一个分块。

镜像写入 `<dir>/<name>.<tag>.img`。获取中断时会保留部分副本,同一条命令会从中继续。

### 用 `--at` 选择快照

默认获取最新的快照。`--at <time|snapshot>` 可选择其他快照,可以是 ISO 8601 格式的时间,也可以是快照 id。它只在配合 `--store` 时生效。

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

在 Linux 以外的平台上,获取到的镜像处于加密状态,无法在本地打开。可通过 `rdc backup upload` 将其发送到 Linux 机器。

## 将副本上传回去

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` 会把下载的镜像发送到机器上,并注册为新仓库。传输中断后可以续传,机器在放置镜像之前会检查 sha256 和 LUKS 头。凭据来自镜像旁边的状态文件。该文件丢失时,用 `--from-repo <name>` 指定提供凭据的仓库。

| 标志 | 作用 |
|------|--------|
| `--as <name>` | 新仓库的名称(默认为镜像的名称) |
| `--datastore <name>` | 将镜像放到指定名称的数据存储上 |
| `--from-repo <name>` | 状态文件不可用时,提供凭据和谱系信息 |
| `--bwlimit <rate>`, `--retries <n>` | 与下载时相同 |
| `--up` | 注册完成后启动该仓库 |
| `--skip-verify` | 跳过与下载时记录的 sha256 的比较 |

## 过期的传输快照

被强行终止的传输可能在机器上留下它的快照。`rdc machine status` 会在存储池摘要中统计过期的传输快照,`rdc machine prune <machine> --dry-run` 会列出它们。运行 `rdc machine prune <machine>` 即可将其清除。

关于快照到分块存储的内容,参见[备份与恢复](/zh/docs/backup-restore)。
