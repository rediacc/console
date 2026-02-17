---
title: "快速入门"
description: "开始使用 Rediacc -- 在您自己的服务器上部署加密隔离基础设施。"
category: "Getting Started"
order: -1
language: zh
---

# 快速入门

欢迎使用 Rediacc。本节将引导您完成在自己的服务器上部署加密、隔离基础设施所需的一切。

## 入门指南

请按顺序阅读以下页面：

1. **[系统要求](/zh/docs/requirements)** -- 工作站和远程服务器支持的操作系统及前提条件。

2. **[安装](/zh/docs/installation)** -- 在 Linux、macOS 或 Windows（WSL2）上安装 `rdc` CLI。

3. **[分步指南](/zh/docs/guide)** -- 创建上下文、添加机器、创建加密仓库并部署服务。

4. **[安装后配置](/zh/docs/post-installation)** -- 配置开机自启、理解上下文配置并排查常见问题。

5. **[工具](/zh/docs/tools)** -- 文件同步、SSH 终端、VS Code 集成、CLI 更新和诊断。

## 什么是 Rediacc？

Rediacc 将容器化服务部署到您控制的远程服务器上。所有数据使用 LUKS 进行静态加密，每个仓库拥有独立的隔离 Docker 守护进程，所有编排操作通过 SSH 从您的工作站完成。

无需云账户。无需 SaaS 依赖。您的数据留在您自己的服务器上。

## 后续步骤

- **[CLI 参考](/zh/docs/cli-application)** -- `rdc` CLI 的完整命令参考。
- **[Web 应用](/zh/docs/web-application)** -- 通过 Web 控制台管理基础设施。
