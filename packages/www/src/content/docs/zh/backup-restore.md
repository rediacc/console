---
title: "备份与恢复"
description: "将加密仓库备份到外部存储、从备份恢复以及配置定时备份。"
category: "Guides"
order: 7
language: zh
---

# 备份与恢复

Rediacc 可以将加密仓库备份到外部存储提供商，并在同一台或不同的机器上进行恢复。备份是加密的 — 恢复时需要仓库的 LUKS 凭据。

## 配置存储

在推送备份之前，需要注册一个存储提供商。Rediacc 支持任何兼容 rclone 的存储：S3、B2、Google Drive 等。

### 从 rclone 导入

如果您已经配置了 rclone 远程存储：

```bash
rdc context import-storage my-storage
```

此命令将 rclone 配置中的存储配置导入到当前上下文中。

### 查看存储

```bash
rdc context storages
```

## 推送备份

将仓库备份推送到外部存储：

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| 选项 | 描述 |
|------|------|
| `--to <storage>` | 目标存储位置 |
| `--to-machine <machine>` | 用于机器到机器备份的目标机器 |
| `--dest <filename>` | 自定义目标文件名 |
| `--checkpoint` | 推送前创建检查点 |
| `--force` | 覆盖已有备份 |
| `--tag <tag>` | 为备份添加标签 |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |

## 拉取/恢复备份

从外部存储拉取仓库备份：

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| 选项 | 描述 |
|------|------|
| `--from <storage>` | 源存储位置 |
| `--from-machine <machine>` | 用于机器到机器恢复的源机器 |
| `--force` | 覆盖已有本地备份 |
| `-w, --watch` | 监视操作进度 |
| `--debug` | 启用详细输出 |

## 列出备份

查看存储位置中的可用备份：

```bash
rdc backup list --from my-storage -m server-1
```

## 批量同步

一次推送或拉取所有仓库：

### 推送所有到存储

```bash
rdc backup sync --to my-storage -m server-1
```

### 从存储拉取所有

```bash
rdc backup sync --from my-storage -m server-1
```

| 选项 | 描述 |
|------|------|
| `--to <storage>` | 目标存储（推送方向） |
| `--from <storage>` | 源存储（拉取方向） |
| `--repo <name>` | 同步指定仓库（可重复使用） |
| `--override` | 覆盖已有备份 |
| `--debug` | 启用详细输出 |

## 定时备份

使用 cron 计划自动化备份，在远程机器上作为 systemd 定时器运行。

### 设置计划

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| 选项 | 描述 |
|------|------|
| `--destination <storage>` | 默认备份目标 |
| `--cron <expression>` | cron 表达式（例如 `"0 2 * * *"` 表示每天凌晨 2 点） |
| `--enable` | 启用计划 |
| `--disable` | 禁用计划 |

### 将计划推送到机器

将计划配置作为 systemd 定时器部署到机器：

```bash
rdc backup schedule push server-1
```

### 查看计划

```bash
rdc backup schedule show
```

## 浏览存储

浏览存储位置的内容：

```bash
rdc storage browse my-storage -m server-1
```

## 最佳实践

- **安排每日备份**到至少一个存储提供商
- **定期测试恢复**以验证备份完整性
- **使用多个存储提供商**存储关键数据（例如 S3 + B2）
- **妥善保管凭据** — 备份是加密的，但恢复时需要 LUKS 凭据
