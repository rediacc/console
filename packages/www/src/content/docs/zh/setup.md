---
title: "机器设置"
description: "创建上下文、添加机器、配置服务器和设置基础设施。"
category: "Guides"
order: 3
language: zh
---

# 机器设置

本页面将引导您完成首台机器的设置：创建上下文、注册服务器、配置服务器，以及可选的公网访问基础设施配置。

## 步骤 1：创建本地上下文

**上下文**是一个命名配置，用于存储您的 SSH 凭据、机器定义和仓库映射。可以将其理解为一个项目工作区。

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| 选项 | 必填 | 描述 |
|------|------|------|
| `--ssh-key <path>` | 是 | SSH 私钥路径。波浪号（`~`）会自动展开。 |
| `--renet-path <path>` | 否 | 远程机器上 renet 二进制文件的自定义路径。默认为标准安装位置。 |

此命令创建一个名为 `my-infra` 的本地上下文，并将其存储在 `~/.rediacc/config.json` 中。

> 您可以拥有多个上下文（例如 `production`、`staging`、`dev`）。在任何命令上使用 `--context` 标志在它们之间切换。

## 步骤 2：添加机器

将您的远程服务器注册为上下文中的机器：

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| 选项 | 必填 | 默认值 | 描述 |
|------|------|--------|------|
| `--ip <address>` | 是 | - | 远程服务器的 IP 地址或主机名。 |
| `--user <username>` | 是 | - | 远程服务器上的 SSH 用户名。 |
| `--port <port>` | 否 | `22` | SSH 端口。 |
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上 Rediacc 存储加密仓库的路径。 |

添加机器后，rdc 会自动运行 `ssh-keyscan` 获取服务器的主机密钥。您也可以手动运行：

```bash
rdc context scan-keys server-1
```

查看所有已注册的机器：

```bash
rdc context machines
```

## 步骤 3：设置机器

为远程服务器安装所有必需的依赖项：

```bash
rdc context setup-machine server-1
```

此命令将：
1. 通过 SFTP 将 renet 二进制文件上传到服务器
2. 安装 Docker、containerd 和 cryptsetup（如果尚未安装）
3. 创建 `rediacc` 系统用户（UID 7111）
4. 创建数据存储目录并为加密仓库做准备

| 选项 | 必填 | 默认值 | 描述 |
|------|------|--------|------|
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上的数据存储目录。 |
| `--datastore-size <size>` | 否 | `95%` | 分配给数据存储的可用磁盘空间比例。 |
| `--debug` | 否 | `false` | 启用详细输出以进行故障排除。 |

> 每台机器只需运行一次设置。如果需要，可以安全地重新运行。

## 主机密钥管理

如果服务器的 SSH 主机密钥发生变化（例如重新安装后），刷新已存储的密钥：

```bash
rdc context scan-keys server-1
```

此命令更新配置中该机器的 `knownHosts` 字段。

## 测试 SSH 连接

在继续之前，验证您的机器是否可达：

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

此命令测试 SSH 连接并报告：
- 连接状态
- 使用的认证方式
- SSH 密钥配置
- 已知主机条目

您可以使用 `--save -m server-1` 将已验证的主机密钥保存到机器配置中。

## 基础设施配置

对于需要公开提供流量的机器，配置基础设施设置：

### 设置基础设施

```bash
rdc context set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| 选项 | 描述 |
|------|------|
| `--public-ipv4 <ip>` | 用于外部访问的公网 IPv4 地址 |
| `--public-ipv6 <ip>` | 用于外部访问的公网 IPv6 地址 |
| `--base-domain <domain>` | 应用的基础域名（例如 `example.com`） |
| `--cert-email <email>` | 用于 Let's Encrypt TLS 证书的电子邮件 |
| `--cf-dns-token <token>` | 用于 ACME DNS-01 挑战的 Cloudflare DNS API 令牌 |
| `--tcp-ports <ports>` | 逗号分隔的额外转发 TCP 端口（例如 `25,143,465,587,993`） |
| `--udp-ports <ports>` | 逗号分隔的额外转发 UDP 端口（例如 `53`） |

### 查看基础设施

```bash
rdc context show-infra server-1
```

### 推送到服务器

生成并部署 Traefik 反向代理配置到服务器：

```bash
rdc context push-infra server-1
```

此命令根据您的基础设施设置推送代理配置。Traefik 处理 TLS 终止、路由和端口转发。

## 设置默认值

设置默认值以避免在每条命令中重复指定：

```bash
rdc context set machine server-1    # 默认机器
rdc context set team my-team        # 默认团队（云模式，实验性）
```

设置默认机器后，您可以在命令中省略 `-m server-1`：

```bash
rdc repo create my-app --size 10G   # 使用默认机器
```

## 多上下文管理

使用命名上下文管理多个环境：

```bash
# 创建独立的上下文
rdc context create-local production --ssh-key ~/.ssh/id_prod
rdc context create-local staging --ssh-key ~/.ssh/id_staging

# 使用特定上下文
rdc repo list -m server-1 --context production
rdc repo list -m staging-1 --context staging
```

查看所有上下文：

```bash
rdc context list
```

显示当前上下文详情：

```bash
rdc context show
```
