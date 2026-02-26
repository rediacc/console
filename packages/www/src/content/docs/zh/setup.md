---
title: "机器设置"
description: "创建配置、添加机器、配置服务器和设置基础设施。"
category: "Guides"
order: 3
language: zh
sourceHash: "0c725f9eb65e6c0f"
---

# 机器设置

本页面将引导您完成首台机器的设置：创建配置、注册服务器、配置服务器，以及可选的公网访问基础设施配置。

## 步骤 1：创建配置

**配置**是一个命名配置文件，用于存储您的 SSH 凭据、机器定义和仓库映射。可以将其理解为一个项目工作区。

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| 选项 | 必填 | 描述 |
|--------|----------|-------------|
| `--ssh-key <path>` | 是 | SSH 私钥路径。波浪号（`~`）会自动展开。 |
| `--renet-path <path>` | 否 | 远程机器上 renet 二进制文件的自定义路径。默认为标准安装位置。 |

此命令创建一个名为 `my-infra` 的配置并将其存储在 `~/.config/rediacc/my-infra.json` 中。默认配置（未指定名称时）存储为 `~/.config/rediacc/rediacc.json`。

> 您可以拥有多个配置（例如 `production`、`staging`、`dev`）。在任何命令上使用 `--config` 标志在它们之间切换。

## 步骤 2：添加机器

将您的远程服务器注册为配置中的机器：

```bash
rdc config add-machine server-1 --ip 203.0.113.50 --user deploy
```

| 选项 | 必填 | 默认值 | 描述 |
|--------|----------|---------|-------------|
| `--ip <address>` | 是 | - | 远程服务器的 IP 地址或主机名 |
| `--user <username>` | 是 | - | 远程服务器上的 SSH 用户名 |
| `--port <port>` | 否 | `22` | SSH 端口 |
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上 Rediacc 存储加密仓库的路径 |

添加机器后，rdc 会自动运行 `ssh-keyscan` 获取服务器的主机密钥。您也可以手动运行：

```bash
rdc config scan-keys server-1
```

查看所有已注册的机器：

```bash
rdc config machines
```

## 步骤 3：设置机器

为远程服务器安装所有必需的依赖项：

```bash
rdc config setup-machine server-1
```

此命令将：
1. 通过 SFTP 将 renet 二进制文件上传到服务器
2. 安装 Docker、containerd 和 cryptsetup（如果尚未安装）
3. 创建 `rediacc` 系统用户（UID 7111）
4. 创建数据存储目录并为加密仓库做准备

| 选项 | 必填 | 默认值 | 描述 |
|--------|----------|---------|-------------|
| `--datastore <path>` | 否 | `/mnt/rediacc` | 服务器上的数据存储目录 |
| `--datastore-size <size>` | 否 | `95%` | 分配给数据存储的可用磁盘空间比例 |
| `--debug` | 否 | `false` | 启用详细输出以进行故障排除 |

> 每台机器只需运行一次设置。如果需要，可以安全地重新运行。

## 主机密钥管理

如果服务器的 SSH 主机密钥发生变化（例如重新安装后），刷新已存储的密钥：

```bash
rdc config scan-keys server-1
```

此命令更新配置中该机器的 `knownHosts` 字段。

## 测试 SSH 连接

添加机器后，验证其是否可达：

```bash
rdc term server-1 -c "hostname"
```

此命令打开到机器的 SSH 连接并运行命令。如果成功，您的 SSH 配置正确。

如需更详细的诊断，运行：

```bash
rdc doctor
```

> **仅限云适配器**：`rdc machine test-connection` 命令提供详细的 SSH 诊断，但需要云适配器。对于本地适配器，请直接使用 `rdc term` 或 `ssh`。

## 基础设施配置

对于需要公开提供流量的机器，配置基础设施设置：

### 设置基础设施

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| 选项 | 描述 |
|--------|-------------|
| `--public-ipv4 <ip>` | 用于外部访问的公网 IPv4 地址 |
| `--public-ipv6 <ip>` | 用于外部访问的公网 IPv6 地址 |
| `--base-domain <domain>` | 应用的基础域名（例如 `example.com`） |
| `--cert-email <email>` | 用于 Let's Encrypt TLS 证书的电子邮件 |
| `--cf-dns-token <token>` | 用于 ACME DNS-01 挑战的 Cloudflare DNS API 令牌 |
| `--tcp-ports <ports>` | 逗号分隔的额外转发 TCP 端口（例如 `25,143,465,587,993`） |
| `--udp-ports <ports>` | 逗号分隔的额外转发 UDP 端口（例如 `53`） |

### 查看基础设施

```bash
rdc config show-infra server-1
```

### 推送到服务器

生成并部署 Traefik 反向代理配置到服务器：

```bash
rdc config push-infra server-1
```

此命令根据您的基础设施设置推送代理配置。Traefik 处理 TLS 终止、路由和端口转发。

## 设置默认值

设置默认值以避免在每条命令中重复指定：

```bash
rdc config set machine server-1    # 默认机器
rdc config set team my-team        # 默认团队（云适配器，实验性）
```

设置默认机器后，您可以在命令中省略 `-m server-1`：

```bash
rdc repo create my-app --size 10G   # 使用默认机器
```

## 多配置管理

使用命名配置管理多个环境：

```bash
# 创建独立的配置
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# 使用特定配置
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

查看所有配置：

```bash
rdc config list
```

显示当前配置详情：

```bash
rdc config show
```
