---
title: "机器设置"
description: "创建配置文件、注册远程机器、验证 SSH 连接，并配置基础设施设置。"
category: "Tutorials"
order: 2
language: zh
sourceHash: "c85a5f51a95e07bb"
---

# 如何使用 Rediacc 设置机器

每个 Rediacc 部署都从配置文件和已注册的机器开始。在本教程中，您将创建配置、注册远程服务器、验证 SSH 连接、运行环境诊断并配置基础设施网络。完成后，您的机器将准备好进行仓库部署。

## 前提条件

- 已安装 `rdc` CLI
- 可通过 SSH 访问的远程服务器（或本地虚拟机）
- 可以对服务器进行身份验证的 SSH 私钥

## 交互式录像

![教程：机器设置和配置](/assets/tutorials/setup-tutorial.cast)

### 步骤 1：创建新配置

配置文件存储机器定义、SSH 凭据和基础设施设置。为此环境创建一个。

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

这将在 `~/.config/rediacc/tutorial-demo.json` 创建一个命名配置文件。

### 步骤 2：查看配置

验证新配置文件是否出现在配置列表中。

```bash
rdc config list
```

列出所有可用的配置，包括其适配器类型（本地或云端）和机器数量。

### 步骤 3：添加机器

使用 IP 地址和 SSH 用户注册机器。CLI 会通过 `ssh-keyscan` 自动获取并存储服务器的主机密钥。

```bash
rdc config add-machine bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### 步骤 4：查看机器

确认机器已正确注册。

```bash
rdc config machines --config tutorial-demo
```

显示当前配置中的所有机器及其连接详情。

### 步骤 5：设置默认机器

设置默认机器可以避免在每个命令中重复 `-m bridge-vm`。

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### 步骤 6：测试连接

在部署任何内容之前，验证机器是否可通过 SSH 访问。

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

两个命令都在远程机器上运行并立即返回结果。如果任何一个失败，请检查您的 SSH 密钥是否正确以及服务器是否可访问。

### 步骤 7：运行诊断

```bash
rdc doctor
```

检查您的本地环境：CLI 版本、Docker、renet 二进制文件、配置状态、SSH 密钥和虚拟化前提条件。每项检查报告 **OK**、**Warning** 或 **Error**。

### 步骤 8：配置基础设施

对于面向公众的服务，机器需要网络配置 - 其外部 IP、基础域名和用于 TLS 的证书邮箱。

```bash
rdc config set-infra bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

验证配置：

```bash
rdc config show-infra bridge-vm
```

使用 `rdc config push-infra bridge-vm` 将生成的 Traefik 代理配置部署到服务器。

## 故障排除

**"SSH key not found" 或 "Permission denied (publickey)"**
验证传递给 `config init` 的密钥路径是否存在并与服务器的 `authorized_keys` 匹配。检查权限：私钥文件必须为 `600`（`chmod 600 ~/.ssh/id_ed25519`）。

**SSH 命令出现 "Connection refused"**
确认服务器正在运行且 IP 正确。检查端口 22 是否开放：`nc -zv <ip> 22`。如果使用非标准端口，请在添加机器时传递 `--port`。

**"Host key verification failed"**
存储的主机密钥与服务器的当前密钥不匹配。这在服务器重建或 IP 重新分配后发生。运行 `rdc config scan-keys <machine>` 来刷新密钥。

## 后续步骤

您已创建配置文件、注册机器、验证连接并配置了基础设施网络。要部署应用程序：

- [机器设置](/zh/docs/setup) — 所有配置和设置命令的完整参考
- [教程：仓库生命周期](/zh/docs/tutorial-repos) — 创建、部署和管理仓库
- [快速入门](/zh/docs/quick-start) — 端到端部署容器化应用程序
