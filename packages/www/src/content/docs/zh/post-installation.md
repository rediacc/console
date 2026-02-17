---
title: "安装后配置"
description: "Rediacc 的开机自启配置、上下文结构和故障排除。"
category: "Guides"
order: 3
language: zh
---

# 安装后配置

完成[分步指南](/zh/docs/guide)后，本页面介绍开机自启配置、上下文配置文件的理解以及常见问题的排查。

## 开机自启

默认情况下，服务器重启后需要手动挂载和启动仓库。**开机自启**功能可配置仓库在服务器启动时自动挂载、启动 Docker 并运行 Rediaccfile `up()`。

### 工作原理

当您为仓库启用开机自启时：

1. 生成一个 256 字节的随机 LUKS 密钥文件，并添加到仓库的 LUKS 槽位 1（槽位 0 仍为用户密码短语）。
2. 密钥文件存储在 `{datastore}/.credentials/keys/{guid}.key`，权限为 `0600`（仅 root 可读）。
3. 安装一个 systemd 服务（`rediacc-autostart`），在启动时挂载所有已启用的仓库并启动其服务。

在系统关机或重启时，该服务会优雅地停止所有服务（Rediaccfile `down()`）、停止 Docker 守护进程并关闭 LUKS 卷。

> **安全提示：**启用开机自启会将 LUKS 密钥文件存储在服务器磁盘上。任何拥有服务器 root 权限的人都可以在无需密码短语的情况下挂载仓库。这是在便利性（自动启动）和安全性（需要手动输入密码短语）之间的权衡。请根据您的威胁模型进行评估。

### 启用开机自启

```bash
rdc repo autostart enable my-app -m server-1
```

系统将提示您输入仓库密码短语。这是授权将密钥文件添加到 LUKS 卷所必需的。

### 为所有仓库启用开机自启

```bash
rdc repo autostart enable-all -m server-1
```

### 禁用开机自启

```bash
rdc repo autostart disable my-app -m server-1
```

此操作将删除密钥文件并清除 LUKS 槽位 1。仓库将不再在启动时自动挂载。

### 查看开机自启状态

```bash
rdc repo autostart list -m server-1
```

显示哪些仓库已启用开机自启以及 systemd 服务是否已安装。

## 理解上下文配置

所有上下文配置存储在 `~/.rediacc/config.json` 中。以下是完成指南后该文件的注释示例：

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**关键字段：**

| 字段 | 描述 |
|------|------|
| `mode` | `"local"` 表示本地模式，`"s3"` 表示 S3 支持的上下文。 |
| `apiUrl` | `"local://"` 表示本地模式（无远程 API）。 |
| `ssh.privateKeyPath` | 用于所有机器连接的 SSH 私钥路径。 |
| `machines.<name>.knownHosts` | 来自 `ssh-keyscan` 的 SSH 主机密钥，用于验证服务器身份。 |
| `repositories.<name>.repositoryGuid` | 标识服务器上加密磁盘映像的 UUID。 |
| `repositories.<name>.credential` | LUKS 加密密码短语。**不存储在服务器上。** |
| `repositories.<name>.networkId` | 确定 IP 子网的网络 ID（2816 + n*64）。自动分配。 |

> 此文件包含敏感数据（SSH 密钥路径、LUKS 凭据）。它以 `0600` 权限存储（仅所有者可读写）。请勿共享或提交到版本控制系统。

## 故障排除

### SSH 连接失败

- 验证您可以手动连接：`ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- 运行 `rdc context scan-keys server-1` 刷新主机密钥
- 检查 SSH 端口是否匹配：`--port 22`

### 机器设置失败

- 确保用户拥有免密码 sudo 权限，或为所需命令配置 `NOPASSWD`
- 检查服务器上的可用磁盘空间
- 使用 `--debug` 获取详细输出：`rdc context setup-machine server-1 --debug`

### 仓库创建失败

- 验证设置已完成：数据存储目录必须存在
- 检查服务器上的磁盘空间
- 确保 renet 二进制文件已安装（如需要，请重新运行设置）

### 服务无法启动

- 检查 Rediaccfile 语法：必须是有效的 Bash
- 确保 `docker compose` 文件使用 `network_mode: host`
- 验证 Docker 镜像可访问（考虑在 `prep()` 中使用 `docker compose pull`）
- 检查容器日志：通过 SSH 登录服务器并使用 `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### 权限被拒绝错误

- 仓库操作需要服务器上的 root 权限（renet 通过 `sudo` 运行）
- 验证您的用户在 `sudo` 组中
- 检查数据存储目录的权限是否正确

### 运行诊断

使用内置的 doctor 命令诊断问题：

```bash
rdc doctor
```

此命令检查您的环境、renet 安装、上下文配置和认证状态。
