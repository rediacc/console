---
title: 快速开始
description: 几分钟内在您的服务器上运行容器化服务。
category: Guides
order: -1
language: zh
sourceHash: "afd4d22ddc8e02e1"
sourceCommit: "ff9c470edf8760f63f12baf681c04db51a0c202f"
---

# 快速开始

在您自己的服务器上安装 Rediacc。加密、隔离的容器环境，无需云账户或 SaaS 依赖。您的硬件，您的掌控。

---

## 简介

### 核心概念

仓库是磁盘上的一个加密文件。可以移动、备份、分叉。它就是一个文件。挂载后，它变成一个文件夹，内含专属的 Docker 守护进程和您的应用数据。

把仓库想象成一个 USB 驱动器：插入任何机器，应用和数据立即挂载，随时可以运行。跨机器或云服务商迁移无需重新构建任何内容。即插即用。

**两个工具，两种角色：**

- **rdc** = 笔记本电脑上的 CLI（TypeScript，全局安装）
- **renet** = 服务器上的编排器（Go 二进制文件，管理守护进程/网络/隔离）
- RDC 在 `config machine setup` 过程中自动配置 renet。无需在服务器上手动设置。

> [架构](/en/docs/architecture)介绍了安全模型。[rdc vs renet](/en/docs/rdc-vs-renet)说明了何时使用哪个工具。

### 1. 安装 CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # 验证：Node、SSH 密钥、renet、Docker
```

> Windows、Alpine、Arch：参见[安装指南](/en/docs/installation)。完整系统要求：[系统要求](/en/docs/requirements)。

### 2. SSH 密钥设置

rdc 通过 SSH 连接。服务器必须先信任您的公钥，rdc 才能访问。

```bash
# 生成密钥（如果已有则跳过）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 将公钥复制到服务器（会提示输入密码）
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# 告诉 rdc 使用哪个密钥
rdc config ssh set --key ~/.ssh/id_ed25519
```

此后每个 rdc 命令都使用此密钥进行认证。无需密码。

### 3. 添加服务器

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user admin
rdc config machine setup --name my-server  # 配置 renet + 创建数据存储
```

**过程说明：** 扫描 SSH 主机密钥，上传 renet 二进制文件，在服务器上初始化加密数据存储。准备好接收仓库。

> 数据存储大小、Ceph RBD、云服务商：[服务器设置](/en/docs/setup)。SSH 故障：[故障排除](/en/docs/troubleshooting)。

### 4. 配置文件

```bash
rdc config show                            # 可读的摘要信息
cat ~/.config/rediacc/rediacc.json         # 原始 JSON：机器、仓库、存储、SSH 密钥
```

**一个文件 = 一个环境。** 复制到另一台笔记本电脑即可使用。

---

## 使用仓库

### 1. 创建仓库

```bash
rdc repo create --name my-app -m my-server --size 2G  # 创建 2 GB 加密仓库
```

创建加密卷，挂载它，并启动其 Docker 守护进程。仓库已注册到您的配置中，可以使用了。

> 调整大小、删除、验证：[仓库](/en/docs/repositories)。

### 2. 应用模板

```bash
rdc repo template list                                        # 显示内置模板
rdc repo template apply --name app-postgres -m my-server -r my-app  # 部署 docker-compose.yml + Rediaccfile
```

模板提供 `docker-compose.yml`、`Rediaccfile` 和辅助文件。如果没有模板（或您自己的 compose 文件），就没有可启动的内容。使用内置模板作为您第一个仓库的起点。这是从头到尾体验完整工作流程的最快途径。

### 3. 启动仓库

```bash
rdc repo up --name my-app -m my-server  # 运行 Rediaccfile up()
rdc repo list -m my-server                           # 查看机器上的所有仓库
rdc repo status --name my-app -m my-server  # 挂载状态、Docker、大小、加密
```

`repo up` 会在需要时自动挂载。无需额外参数。

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # 打开 VS Code SSH，进入仓库沙箱
```

您正在加密卷*内部*编辑文件。`docker ps` 只显示此仓库的容器。保存、compose up、迭代。

### 5. `rdc repo up` 与 `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **运行位置** | 您的笔记本电脑（CLI） | VS Code 沙箱内 |
| **功能** | SSH → 自动挂载 → 运行 Rediaccfile `up()` | 直接运行 Rediaccfile `up()` |
| **使用场景** | CI/CD、自动化、远程运维 | 开发者内循环 |
| **隔离性** | 从外部编排 | 已在沙箱内部 |

**演示流程：** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → 编辑 `docker-compose.yml` → `renet dev up` → 看到应用运行 → 迭代。

> Rediaccfile 结构：[服务](/en/docs/services)。何时使用哪个工具：[rdc vs renet](/en/docs/rdc-vs-renet)。

### 6. 隔离模型

- **通用用户**（`rediacc`）：所有机器上使用相同的 UID。将仓库迁移到另一台服务器，文件所有权直接生效。无需为 `chown` 烦恼。
- **每仓库独立 Docker 守护进程**：每个仓库拥有自己的隔离 Docker 守护进程。`docker ps` 只显示本仓库的容器。
- **Landlock + OverlayFS 沙箱**：VS Code shell 受文件系统限制。无法读取其他仓库。对 `$HOME` 的写入是每仓库的覆盖层。

> 隔离工作原理：[架构](/en/docs/architecture)。Rediaccfile 生命周期：[服务](/en/docs/services)。

### 7. 终端、同步与隧道

**终端：**
```bash
rdc term connect -m my-server -r my-app                            # SSH 进入仓库沙箱
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # 运行命令并退出
rdc term connect -m my-server                                   # SSH 到机器（无沙箱）
```

**文件同步（通过 SSH 的 rsync）：**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src                                   # 上传目录
rdc repo sync upload -m my-server -r my-app --local ./config.yml --remote conf              # 上传单个文件
rdc repo sync download -m my-server -r my-app --local ./backup                              # 下载目录
rdc repo sync download -m my-server -r my-app --remote-file conf/config.yml --local ./dl    # 下载单个文件
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run                    # 先预览
```

**隧道（SSH 端口转发到容器）：**
```bash
rdc repo tunnel -m my-server -r my-app -c app  # 自动检测 app 容器的端口
rdc repo tunnel -m my-server -r my-app -c db --port 5432  # 隧道连接 Postgres
rdc repo tunnel -m my-server -r my-app -c db --port 5432 --local 15432  # 自定义本地端口
```

运行隧道 → 在浏览器中打开 `localhost:3000` → 从远程服务器访问实时应用。

> 同步、终端、VS Code 详情：[工具](/en/docs/tools)。

---

## 分叉与备份

### 1. 主仓库与分叉仓库

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # 即时 CoW 克隆 + 启动
rdc repo list -m my-server                                  # 显示：my-app（主仓库）+ my-app:experiment（分叉）
rdc repo delete --name my-app:experiment -m my-server  # 删除分叉，主仓库不受影响
```

**即时、零拷贝克隆。** CoW（写时复制）。微秒级完成，不复制数据。块在一方写入前保持共享。

**使用场景：**
- **AI / ML：** 分叉生产数据集，运行实验，丢弃或提升
- **DevOps：** 分叉 → 测试迁移 → 失败则删除，成功则提升
- **备份：** 分叉 = 即时快照，推送到异地

> 分叉生命周期、跨机器分叉：[仓库](/en/docs/repositories)。

### 2. 推送到另一台机器

```bash
# 将仓库推送到另一台机器
rdc repo push --name my-app -m my-server --to backup-server

# 推送并在目标机器上自动部署
rdc repo push --name my-app -m my-server --to backup-server --up

# 使用 CRIU 检查点推送（实时迁移，保留内存状态）
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# 推送到新机器（通过云服务商自动配置）
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. 推送到云存储（OneDrive、Google Drive、S3）

```bash
# 导入您的 rclone 配置作为存储后端
rdc config storage import --file ~/rclone.conf

# 列出可用的存储
rdc storage list

# 将仓库推送到云存储
rdc repo push --name my-app -m my-server --to my-s3-backup

# 列出存储上的备份
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` 自动检测目标是机器还是存储后端。支持所有 rclone 支持的提供商：S3、R2、B2、OneDrive、Google Drive、SFTP 等。

### 4. 从远程拉取

```bash
# 从云机器拉取仓库到本地服务器
rdc repo pull --name my-app -m my-local-server --from cloud-server

# 从云存储拉取
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# 拉取并立即启动
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**为什么要拉取？** 您的本地机器在 NAT 之后。云端无法推送到您这里。但您可以访问云端。拉取将仓库带回本地。

**完整流程：** 在开发机上创建 → 推送到云端 → 在生产环境拉取 → `--up`。一个仓库，任意机器，任意云。

> 计划任务、自动备份、恢复：[备份与恢复](/en/docs/backup-restore)。

---

## 代理与 SSL

### 1. 基础设施配置

```bash
rdc config infra set -m my-server  # 配置：基础域名、公共 IP、端口范围
rdc config infra show -m my-server  # 查看配置
rdc config infra push -m my-server  # 将代理配置推送到远程
```

**路由工作原理：**
- Traefik 通过 `rediacc.service_name` 和 `rediacc.service_port` 标签自动发现容器
- 路由：`{service}-{networkId}.{baseDomain}` → 容器 IP:端口
- SSL：通过 Cloudflare DNS-01 验证使用 Let's Encrypt（自动续期，通配符证书）

### 2. 代理模板

```bash
rdc repo template apply --name proxy -m my-server -r infra  # 将代理部署到仓库
rdc repo up --name infra -m my-server  # 启动 Traefik
```

Traefik 现在将外部流量路由到此机器上的所有仓库。每个容器自动获得 HTTPS 端点。

```bash
# 访问 https://my-app.example.com → 路由到容器
# 数据库的 TCP/UDP 转发：
#   rediacc.tcp_ports=3306,5432 → 自动分配的外部端口
```

> 路由规则、DNS、TLS 配置：[网络](/en/docs/networking)。

---

## 后续步骤

- **[迁移指南](/en/docs/migration)** - 将现有项目迁移到 Rediacc 仓库
- **[监控](/en/docs/monitoring)** - 机器健康状况、容器、服务、诊断
- **[CLI 参考](/en/docs/cli-application)** - 完整的命令参考
- **[速查表](/en/docs/rdc-cheat-sheet)** - 快速命令查询
- **[故障排除](/en/docs/troubleshooting)** - 常见问题的解决方案
- **[Rediacc 规则](/en/docs/rules-of-rediacc)** - Rediaccfile 最佳实践和部署清单
