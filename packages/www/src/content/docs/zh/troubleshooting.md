---
title: 故障排除
description: SSH、设置、仓库、服务和Docker常见问题的解决方案。
category: Guides
order: 10
language: zh
sourceHash: 54e552831b2b125c
sourceCommit: d5c06171af0ef58b551a9682905d98af81e496cd
---

# 故障排除

常见问题及其解决方案。如有疑问，请先运行 `rdc doctor` 进行全面诊断检查。

## SSH连接失败

- 验证您是否可以手动连接: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- 运行 `rdc config machine scan-keys --name server-1` 以刷新主机密钥
- 检查SSH端口是否匹配: `--port 22`
- 使用简单命令测试: `rdc term connect -m server-1 -c "hostname"`

## 主机密钥不匹配

如果服务器被重新安装或其SSH密钥已更改，您将看到 "host key verification failed"：

```bash
rdc config machine scan-keys -m server-1
```

此命令获取新的主机密钥并更新您的配置。

## 机器设置失败

- 确保SSH用户拥有无密码的sudo访问权限，或为所需命令配置 `NOPASSWD`
- 检查服务器上的可用磁盘空间
- 使用 `--debug` 运行以获取详细输出: `rdc config machine setup --name server-1 --debug`

## 发行版特定的设置问题

五个官方支持的服务器操作系统（Ubuntu 24.04、Debian 13、Fedora 43、openSUSE Leap 16.0、Oracle Linux 10）附带不同的安全策略和包管理器。大多数设置可以正常工作；以下情况涵盖了不能正常工作的例外。

### SELinux 拒绝 (Fedora 43、Oracle Linux 10)

两者均以强制（enforcing）模式运行 SELinux。rdc setup 不安装自定义 SELinux 策略；每个仓库的 docker daemon 在标准 `container_t` 上下文下运行。如果 setup 因 AVC 拒绝而失败，请检查 audit 日志并确定域：

```bash
sudo ausearch -m AVC -ts recent | head -40
# 或者：
sudo tail -f /var/log/audit/audit.log | grep AVC
```

如果拒绝指向 renet 二进制文件或特定文件路径，解决方法几乎总是重新标记（`restorecon -v /path`），而不是禁用 SELinux。作为调查期间的临时解决方案，`sudo setenforce 0` 会将系统切换到宽容模式。确认重新标记生效后，使用 `sudo setenforce 1` 重新启用强制模式。

### AppArmor 拒绝 (Ubuntu 24.04、openSUSE Leap 16.0)

两者默认运行 AppArmor；每个仓库的 docker daemon 使用默认容器配置文件。如果仓库内的容器被阻止：

```bash
dmesg | grep -i apparmor
sudo aa-status
```

CRIU 是触发 AppArmor 的已知情况。Renet 自动为标记了 `rediacc.checkpoint=true` 的容器设置 `security_opt: apparmor=unconfined`。其他情况下您不需要手动配置 AppArmor 配置文件。请参阅 [Rediacc 规则](/en/docs/rules-of-rediacc) 中的 CRIU 说明。

### 包管理器错误特征

| 操作系统 | 包管理器 | 典型错误 | 解决方案 |
|---|---|---|---|
| Ubuntu / Debian | apt-get | `File has unexpected size (N != M). Mirror sync in progress?` | Cloudflare 边缘缓存落后于源站。约 15 秒后重试 `apt-get update`；下次轮询时完整性检查将通过。 |
| Fedora / Oracle | dnf | `Problem: nothing provides rediacc-cli` | 磁盘上缓存的 RPM 仓库元数据已过期。运行 `sudo dnf clean all && sudo dnf makecache`。 |
| openSUSE | zypper | `Repository 'rediacc' needs to be refreshed.` | 运行一次 `sudo zypper refresh rediacc`；后续安装应该成功。 |

### btrfs 模块缺失 (RHEL 10 / Rocky Linux 10 / AlmaLinux 10)

如果 `rdc config machine setup` 或 `renet system check-btrfs` 失败并显示：

```
Module btrfs not found
```

...服务器运行的是 RHEL 10 的标准内核，该内核不包含内置的 btrfs 模块。这不是 Rediacc 的 bug；RHEL 10 有意移除了 btrfs。解决方案是**改用 Oracle Linux 10**。Oracle 10 默认使用保留了 btrfs 的 Unbreakable Enterprise Kernel（UEK）。完整说明请参见 [要求 -- 为什么选择 UEK?](/en/docs/requirements)。

## 仓库创建失败

- 验证设置已完成：数据存储目录必须存在
- 检查服务器上的磁盘空间
- 确保renet二进制文件已安装（如需要请重新运行设置）

## 服务启动失败

- 检查Rediaccfile语法：必须是有效的Bash
- 确保你的Rediaccfile使用 `renet compose --`（而不是 `docker compose`）
- 验证Docker镜像是否可访问（考虑在 `up()` 中使用 `renet compose -- pull`）
- 通过仓库的Docker套接字检查容器日志:

```bash
rdc term connect -m server-1 -r my-app -c "docker logs <container-name>"
```

或查看所有容器:

```bash
rdc machine containers --name server-1
```

## 权限被拒绝错误

- 仓库操作需要服务器上的root权限（renet通过 `sudo` 运行）
- 验证您的SSH用户是否在 `sudo` 组中
- 检查数据存储目录是否具有正确的权限

## Docker套接字问题

每个仓库都有自己的Docker daemon。手动运行Docker命令时，必须指定正确的套接字:

```bash
# 使用rdc term（自动配置）:
rdc term connect -m server-1 -r my-app -c "docker ps"

# 或手动指定套接字:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

将 `2816` 替换为您仓库的网络ID（可在 `rediacc.json` 或 `rdc repo status` 中找到）。

## `docker run` 没有网络，`apt update` 失败，`curl` 挂起

在仓库 shell 内运行不带 `--network host` 的容器，你会得到一个隔离的容器，只有 loopback 接口，没有 DNS 和出站连接。像 `apt update`、`pip install`、`curl https://...` 或任何网络获取命令都会立即因 DNS 错误而失败。

这是有意为之的。Rediacc 的网络模型是**每个服务都使用主机网络**，由 `renet compose` 强制执行。默认的带 NAT 的 Docker bridge 会绕过内核级的 loopback 隔离，而这种隔离正是阻止一个仓库访问另一个仓库服务的机制。因此每个仓库的 Docker daemon 都配置了 `"bridge": "none"` 和 `"iptables": false`。对于一个简单的 `docker run` 容器，根本没有可连接的可路由 bridge。

**要在临时容器中获得网络访问，请使用主机网络：**

```bash
# 在仓库 shell 内 (rdc term connect -m <machine> -r <repo>)
docker run --rm --network host -it ubuntu bash
# 现在 apt update、curl、pip install 都能正常工作。
```

**对于生产服务，请使用带有 `renet compose` 的 Rediaccfile** 而不是原始的 `docker run`。`renet compose` 会自动注入 `network_mode: host`、服务 IP 标签和 Traefik 路由标签。详见 [服务](/zh/docs/services)。

## VS Code 在沙箱文件上 Permission Denied

当使用 `rdc vscode connect -m <machine> -r <repo>` 连接时，你可能在之前的 VS Code 会话之后看到过类似 `scp: .../.vscode-server/vscode-cli-*.tar.gz: Permission denied` 的错误。这是因为沙箱目录内存在混合的文件所有权，其中既有你的 SSH 用户写入的文件，也有内部 `rediacc` 用户写入的文件。

较新版本的 renet 通过以下方式修复了这个问题：

- 使用组 `rediacc` 和 set-group-ID 位（模式 `2775`）创建每仓库的沙箱工作区（`/mnt/rediacc/.interim/sandbox/<repo>/`），这样在其下写入的每个文件都会继承正确的组。
- 在沙箱运行时内应用 umask `002`，使新文件以组可写的方式（`0664`/`0775`）创建。
- 在启动时规范化现有的 `.vscode-server/` 子树，使修复前遗留的过期文件自动得到修复。

如果你仍然看到权限错误，请从机器上的 shell 使用 `sudo systemctl restart rediacc-docker-<network-id>` 重启仓库的 Docker daemon 一次，以便运行规范化过程，然后重试 `rdc vscode connect`。

## renet 升级后 daemon 无法启动

在每次启动之前，`renet daemon start-foreground` 都会根据当前模板重写仓库配置目录中的 `daemon.json` 和 `containerd.toml`，因此由旧版 renet 生成配置的仓库会自动采用新格式。你不需要运行任何迁移命令，也不需要手动重新生成 systemd 单元。只需重启服务：

```bash
sudo systemctl restart rediacc-docker-<network-id>
```

如果单元仍然启动失败，请检查 journal 获取具体错误：

```bash
sudo journalctl -u rediacc-docker-<network-id> --no-pager -n 50
```

## 容器在错误的Docker daemon上创建

如果您的容器出现在主机系统的Docker daemon上而不是仓库的隔离daemon上，最常见的原因是在Rediaccfile中使用了 `sudo docker`。

`sudo` 会重置环境变量，因此 `DOCKER_HOST` 丢失，Docker默认使用系统套接字（`/var/run/docker.sock`）。Rediacc会自动阻止此行为，但如果您遇到此问题:

- **直接使用 `docker`**, Rediaccfile函数已经以足够的权限运行
- 如果必须使用sudo，请使用 `sudo -E docker` 以保留环境变量
- 检查您的Rediaccfile中是否有 `sudo docker` 命令，并删除 `sudo`

## 终端无法工作

如果 `rdc term` 无法打开终端窗口:

- 使用 `-c` 的内联模式直接运行命令:
  ```bash
  rdc term connect -m server-1 -c "ls -la"
  ```
- 如果内联模式有问题，使用 `--external` 强制打开外部终端
- 在Linux上，确保已安装 `gnome-terminal`、`xterm` 或其他终端模拟器

## 运行诊断

```bash
rdc doctor
```

此命令检查您的环境、renet安装、配置文件和身份验证状态。每项检查会报告OK、Warning或Error，并附带简要说明。
