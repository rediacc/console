---
title: "备份与网络"
description: "一起观看和操作：配置备份计划、存储提供商和网络基础设施。"
category: "Tutorials"
order: 6
language: zh
sourceHash: "d611f5597b819085"
---

# 教程: 备份与网络

本教程涵盖备份调度、存储配置和基础设施网络设置：用于保护数据和暴露服务的命令。

## 前提条件

- The `rdc` CLI installed with a config initialized
- A provisioned machine (see [Tutorial: Machine Setup](/zh/docs/tutorial-setup))

## 交互式录像

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

## 内容说明

The recording above walks through each step below. Use the playback bar to navigate between commands.

### 步骤1: 查看当前存储

```bash
rdc config storages
```

列出从 rclone 配置导入的所有已配置存储提供商（S3、B2、Google Drive 等）。存储用作备份目标。

### 步骤2: 配置备份计划

```bash
rdc backup schedule set --destination my-s3 --cron "0 2 * * *" --enable
```

设置自动备份计划：每天凌晨2点将所有仓库推送到 `my-s3` 存储。计划保存在配置中，可以作为 systemd 定时器部署到机器上。

### 步骤3: 查看备份计划

```bash
rdc backup schedule show
```

显示当前备份计划配置：目标、cron 表达式和启用状态。

### 步骤4: 配置基础设施

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

配置机器的公共网络：外部 IP、自动路由的基础域名以及 Let's Encrypt TLS 证书的电子邮件。

### 步骤5: 添加 TCP/UDP 端口

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

为反向代理注册额外的 TCP/UDP 端口。这些创建 Traefik 入口点（`tcp-25`、`udp-53` 等），可以在 Docker 标签中引用。

### 步骤6: 查看基础设施配置

```bash
rdc config show-infra server-1
```

显示机器的完整基础设施配置：公共 IP、域名、电子邮件和已注册端口。

### 步骤7: 禁用备份计划

```bash
rdc backup schedule set --disable
rdc backup schedule show
```

禁用自动备份计划。配置将被保留，以便以后重新启用。

## 后续步骤

- [Backup & Restore](/zh/docs/backup-restore) — full reference for push, pull, list, and sync commands
- [Networking](/zh/docs/networking) — Docker labels, TLS certificates, DNS, and TCP/UDP forwarding
- [Tutorial: Machine Setup](/zh/docs/tutorial-setup) — initial configuration and provisioning
