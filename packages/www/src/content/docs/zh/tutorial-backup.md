---
title: "备份与网络"
description: "配置自动备份计划、管理存储提供商、设置基础设施网络并注册服务端口。"
category: "Tutorials"
order: 6
language: zh
sourceHash: "26db200e730fff43"
---

# 如何使用 Rediacc 配置备份和网络

自动备份保护您的仓库，基础设施网络将服务暴露给外部世界。在本教程中，您将使用存储提供商配置备份计划、使用 TLS 证书设置公共网络、注册服务端口并验证配置。完成后，您的机器将准备好接收生产流量。

## 前提条件

- 已安装 `rdc` CLI 并初始化配置
- 已配置的机器（参见[教程：机器设置](/zh/docs/tutorial-setup)）

## 交互式录像

![Tutorial: Backup & Networking](/assets/tutorials/backup-tutorial.cast)

### 步骤 1：查看当前存储

存储提供商（S3、B2、Google Drive 等）用作备份目标。检查已配置的提供商。

```bash
rdc config storages
```

列出从 rclone 配置导入的所有已配置存储提供商。如果为空，请先添加存储提供商 — 参见[备份与恢复](/zh/docs/backup-restore)。

### 步骤 2：配置备份计划

设置按 cron 计划运行的自动备份。

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
```

您可以为不同的计划配置多个目标：

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

这会安排每天凌晨 2 点备份到 `my-s3`，凌晨 6 点备份到 `azure-backup`。每个目标都有自己的计划。计划保存在您的配置中，可以作为 systemd 定时器部署到机器上。

### 步骤 3：查看备份计划

验证计划是否已应用。

```bash
rdc config backup-strategy show
```

显示当前备份配置：目标、cron 表达式和启用状态。

### 步骤 4：配置基础设施

对于面向公众的服务，机器需要其外部 IP、基础域名和用于 Let's Encrypt TLS 的证书电子邮件。

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com
```

Rediacc 根据这些设置生成 Traefik 反向代理配置。

### 步骤 5：添加 TCP/UDP 端口

如果您的服务需要非 HTTP 端口（例如 SMTP、DNS），请将它们注册为 Traefik 入口点。

```bash
rdc config set-infra server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53
```

这会创建 Traefik 入口点（`tcp-25`、`udp-53` 等），Docker 服务可以通过标签引用它们。

### 步骤 6：查看基础设施配置

验证完整的基础设施配置。

```bash
rdc config show-infra server-1
```

显示公共 IP、域名、证书电子邮件和所有已注册端口。

### 步骤 7：禁用备份计划

要在不删除配置的情况下停止自动备份：

```bash
rdc config backup-strategy set --disable
rdc config backup-strategy show
```

配置将被保留，以后可以使用 `--enable` 重新启用。

## 故障排除

**"Invalid cron expression"**
Cron 格式为 `minute hour day month weekday`。常见计划：`0 2 * * *`（每天凌晨 2 点）、`0 */6 * * *`（每 6 小时）、`0 0 * * 0`（每周日午夜）。

**"Storage destination not found"**
目标名称必须与已配置的存储提供商匹配。运行 `rdc config storages` 查看可用名称。通过 rclone 配置添加新提供商。

**部署时出现 "Infrastructure config incomplete"**
三个字段全部必填：`--public-ipv4`、`--base-domain` 和 `--cert-email`。运行 `rdc config show-infra <machine>` 检查缺少哪些字段。

## 后续步骤

您已配置自动备份、设置基础设施网络、注册服务端口并验证了配置。要管理备份：

- [备份与恢复](/zh/docs/backup-restore) — push、pull、list 和 sync 命令的完整参考
- [网络](/zh/docs/networking) — Docker 标签、TLS 证书、DNS 和 TCP/UDP 转发
- [教程：机器设置](/zh/docs/tutorial-setup) — 初始配置和配置
