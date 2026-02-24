---
title: "故障排除"
description: "SSH、设置、仓库、服务和Docker常见问题的解决方案。"
category: "Guides"
order: 10
language: zh
sourceHash: 4c3163007e6a3326
---

# 故障排除

常见问题及其解决方案。如有疑问，请先运行 `rdc doctor` 进行全面诊断检查。

## SSH连接失败

- 验证您是否可以手动连接: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- 运行 `rdc config scan-keys server-1` 以刷新主机密钥
- 检查SSH端口是否匹配: `--port 22`
- 使用简单命令测试: `rdc term server-1 -c "hostname"`

## 主机密钥不匹配

如果服务器被重新安装或其SSH密钥已更改，您将看到 "host key verification failed"：

```bash
rdc config scan-keys server-1
```

此命令获取新的主机密钥并更新您的配置。

## 机器设置失败

- 确保SSH用户拥有无密码的sudo访问权限，或为所需命令配置 `NOPASSWD`
- 检查服务器上的可用磁盘空间
- 使用 `--debug` 运行以获取详细输出: `rdc config setup-machine server-1 --debug`

## 仓库创建失败

- 验证设置已完成：数据存储目录必须存在
- 检查服务器上的磁盘空间
- 确保renet二进制文件已安装（如需要请重新运行设置）

## 服务启动失败

- 检查Rediaccfile语法：必须是有效的Bash
- 确保 `docker compose` 文件使用 `network_mode: host`
- 验证Docker镜像是否可访问（考虑在 `prep()` 中使用 `docker compose pull`）
- 通过仓库的Docker套接字检查容器日志:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
```

或查看所有容器:

```bash
rdc machine containers server-1
```

## 权限被拒绝错误

- 仓库操作需要服务器上的root权限（renet通过 `sudo` 运行）
- 验证您的SSH用户是否在 `sudo` 组中
- 检查数据存储目录是否具有正确的权限

## Docker套接字问题

每个仓库都有自己的Docker daemon。手动运行Docker命令时，必须指定正确的套接字:

```bash
# 使用rdc term（自动配置）:
rdc term server-1 my-app -c "docker ps"

# 或手动指定套接字:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

将 `2816` 替换为您仓库的网络ID（可在 `rediacc.json` 或 `rdc repo status` 中找到）。

## 容器在错误的Docker daemon上创建

如果您的容器出现在主机系统的Docker daemon上而不是仓库的隔离daemon上，最常见的原因是在Rediaccfile中使用了 `sudo docker`。

`sudo` 会重置环境变量，因此 `DOCKER_HOST` 丢失，Docker默认使用系统套接字（`/var/run/docker.sock`）。Rediacc会自动阻止此行为，但如果您遇到此问题:

- **直接使用 `docker`** — Rediaccfile函数已经以足够的权限运行
- 如果必须使用sudo，请使用 `sudo -E docker` 以保留环境变量
- 检查您的Rediaccfile中是否有 `sudo docker` 命令，并删除 `sudo`

## 终端无法工作

如果 `rdc term` 无法打开终端窗口:

- 使用 `-c` 的内联模式直接运行命令:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- 如果内联模式有问题，使用 `--external` 强制打开外部终端
- 在Linux上，确保已安装 `gnome-terminal`、`xterm` 或其他终端模拟器

## 运行诊断

```bash
rdc doctor
```

此命令检查您的环境、renet安装、配置文件和身份验证状态。每项检查会报告OK、Warning或Error，并附带简要说明。
