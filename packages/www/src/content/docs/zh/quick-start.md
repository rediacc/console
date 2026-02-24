---
title: 快速开始
description: 5分钟内在您的服务器上运行容器化服务。
category: Guides
order: -1
language: zh
sourceHash: b368b94e7064efe1
---

# 快速开始

5分钟内在您自己的服务器上部署加密、隔离的容器环境。无需云账户或SaaS依赖。

## 前提条件

- 一台Linux或macOS工作站
- 一台远程服务器（Ubuntu 24.04+、Debian 12+或Fedora 43+），需要SSH访问权限和sudo权限
- 一对SSH密钥（例如 `~/.ssh/id_ed25519`）

## 1. 安装CLI

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. 创建配置

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. 添加服务器

```bash
rdc config add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. 配置服务器

```bash
rdc config setup-machine server-1
```

此命令会在您的服务器上安装Docker、cryptsetup和renet二进制文件。

## 5. 创建加密仓库

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. 部署服务

挂载仓库，在其中创建`docker-compose.yml`和`Rediaccfile`，然后启动：

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. 验证

```bash
rdc machine containers server-1
```

您应该能看到容器正在运行。

## 什么是Rediacc？

Rediacc将容器化服务部署到您控制的远程服务器上。所有数据使用LUKS进行静态加密，每个仓库拥有独立的隔离Docker守护进程，所有编排操作通过SSH从您的工作站完成。

无需云账户。无需SaaS依赖。您的数据留在您自己的服务器上。

## 后续步骤

- **[架构](/zh/docs/architecture)** — 了解Rediacc的工作原理：适配器检测、安全模型、Docker隔离
- **[rdc vs renet](/zh/docs/rdc-vs-renet)** — 了解日常操作与底层远程工作分别使用哪个CLI
- **[服务器设置](/zh/docs/setup)** — 详细设置指南：配置、机器、基础设施配置
- **[仓库](/zh/docs/repositories)** — 创建、管理、调整大小、分叉和验证仓库
- **[服务](/zh/docs/services)** — Rediaccfile、服务网络、部署、自动启动
- **[备份与恢复](/zh/docs/backup-restore)** — 备份到外部存储并安排自动备份
- **[监控](/zh/docs/monitoring)** — 服务器健康状况、容器、服务、诊断
- **[工具](/zh/docs/tools)** — 文件同步、SSH终端、VS Code集成
- **[迁移指南](/zh/docs/migration)** — 将现有项目迁移到Rediacc仓库
- **[故障排除](/zh/docs/troubleshooting)** — 常见问题的解决方案
- **[CLI参考](/zh/docs/cli-application)** — 完整的命令参考
