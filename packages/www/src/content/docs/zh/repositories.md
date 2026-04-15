---
title: 仓库
description: 在远程机器上创建、管理和操作 LUKS 加密仓库。
category: Guides
order: 4
language: zh
sourceHash: "83f2c9fa5ae53864"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# 仓库

**仓库**是远程服务器上的一个 LUKS 加密磁盘映像。挂载后，它提供：
- 应用数据的隔离文件系统
- 专用的 Docker 守护进程（与主机的 Docker 分离）
- 在 /26 子网内为每个服务分配唯一的回环 IP

## 创建仓库

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `-m, --machine <name>` | 是 | 将要创建仓库的目标机器 |
| `--size <size>` | 是 | 加密磁盘映像的大小（例如 `5G`、`10G`、`50G`） |
| `--skip-router-restart` | 否 | 跳过操作后重启路由服务器 |

输出将显示三个自动生成的值：

- **仓库 GUID** -- 用于在服务器上标识加密磁盘映像的 UUID。
- **凭据** -- 用于加密/解密 LUKS 卷的随机密码短语。
- **网络 ID** -- 一个整数（从 2816 开始，每次递增 64），用于确定此仓库服务的 IP 子网。

> **请安全存储凭据。** 它是您仓库的加密密钥。如果丢失，数据将无法恢复。凭据存储在您的本地 `config.json` 中，但不会存储在服务器上。

## 挂载和卸载

挂载操作解密并使仓库文件系统可访问。卸载操作关闭加密卷。

```bash
rdc repo mount --name my-app -m server-1  # 解密并挂载
rdc repo unmount --name my-app -m server-1  # 卸载并重新加密
```

| 选项 | 描述 |
|------|------|
| `--checkpoint` | 挂载/卸载前创建 CRIU 检查点（用于带有 `rediacc.checkpoint=true` 标签的容器） |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

## 检查状态

```bash
rdc repo status --name my-app -m server-1
```

## 列出仓库

```bash
rdc repo list -m server-1
```

## 调整大小

将仓库设置为指定大小或扩展指定容量：

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # 设置为指定大小
rdc repo expand --name my-app -m server-1 --size 5G  # 在当前大小基础上增加 5G
```

> 调整大小前必须先卸载仓库。

## 复刻

创建现有仓库当前状态的副本：

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

复刻使用 name:tag 模型：生成的复刻命名为 `my-app:staging`。此命令创建一个具有独立 GUID 和网络 ID 的新加密副本，同时共享父仓库的名称。复刻仓库与源仓库共享相同的 LUKS 凭据。

## 验证

检查仓库的文件系统完整性：

```bash
rdc repo validate --name my-app -m server-1
```

## 所有权

将仓库内的文件所有权设置为通用用户（UID 7111）。通常在从工作站上传文件后需要执行此操作，因为上传的文件会使用您本地的 UID。

```bash
rdc repo ownership --name my-app -m server-1
```

此命令会自动检测 Docker 容器数据目录（可写绑定挂载）并将其排除。这可以防止破坏使用自身 UID 管理文件的容器（例如 MariaDB=999、www-data=33）。

| 选项 | 描述 |
|------|------|
| `--uid <uid>` | 设置自定义 UID，而非默认的 7111 |
| `--skip-router-restart` | 跳过操作后重启路由服务器 |

强制对所有文件（包括容器数据）设置所有权：

```bash
rdc repo ownership --name my-app -m server-1
```


有关迁移过程中何时以及如何使用所有权命令的完整说明，请参阅[迁移指南](/en/docs/migration)。

## 模板

应用模板以使用文件初始化仓库：

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## 删除

永久销毁仓库及其中的所有数据：

```bash
rdc repo delete --name my-app -m server-1
```

> 此操作将永久销毁加密磁盘映像。此操作无法撤销。

## 迁移仓库

以最短停机时间将仓库从一台机器实时迁移到另一台机器。

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| 选项 | 描述 |
|------|------|
| `--provision` | 迁移前在目标机器上预置仓库（创建 LUKS 映像并注册配置） |
| `--checkpoint` | 在切换前为正在运行的容器创建 CRIU 检查点 |
| `--bwlimit <kbps>` | 以千字节/秒为单位限制 rsync 带宽 |
| `--skip-dns` | 切换后跳过更新 DNS 记录 |

**三阶段流程：**

1. **热预复制** - 仓库在源端继续运行时，rsync 传输数据。大文件在任何停机之前就已传输完毕。
2. **切换** - 仓库在源端停止，最后一次 rsync 同步剩余更改，然后仓库在目标端启动。
3. **在目标端启动** - renet 在目标机器上挂载并启动仓库。除非传入 `--skip-dns`，否则 DNS 会被更新。

![仓库实时迁移](/img/repo-migrate-flow.svg)

**push 与迁移的对比：**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| 操作 | 复制 | 移动 |
| 操作后源端 | 不变 | 已停止 |
| 停机时间 | 无（仅复制） | 短暂的切换窗口 |
| DNS 更新 | 否 | 是（除非使用 `--skip-dns`） |
| 使用场景 | 备份、预发布克隆 | 机器更换、服务器迁移 |

## 清理

删除仓库或从失败操作中恢复后，可能残留孤立的挂载目录、锁定文件和不可移动标记。清理操作会安全地删除这些内容：

```bash
# 预览将被删除的内容
rdc machine prune --name server-1 --dry-run

# 删除孤立资源
rdc machine prune --name server-1
```

只有没有对应仓库映像的资源才会受到影响。非空的挂载目录不会被删除。
