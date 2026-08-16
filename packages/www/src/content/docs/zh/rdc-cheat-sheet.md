---
title: RDC CLI 快速参考
description: "rdc 快速参考：配置、仓库、机器、文件同步和容器。完整选项集：在任意命令后添加 --help。"
category: Guides
order: 3
language: zh
sourceHash: "ae49dd7fbc179d35"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# RDC CLI 快速参考

此处并未列出所有 `rdc` 命令，仅包含每次部署中常见的命令。要查看完整选项集，请在任意 rdc 命令后添加 `--help`。边界情况和较少使用的选项详见完整参考。

## 仓库生命周期

| 命令 | 说明 |
|------|------|
| `rdc repo create <repo> -m <machine>` | 在机器上创建新仓库 |
| `rdc repo up <repo>@<machine>` | 部署或更新仓库 |
| `rdc repo down <repo>@<machine>` | 停止仓库 |
| `rdc repo delete <repo>@<machine>` | 删除仓库 |
| `rdc repo fork <repo>@<machine> --tag <tag>` | 派生仓库（近乎瞬时，BTRFS reflink） |
| `rdc repo promote <repo>:<tag>` | 将已验证的派生仓库以父仓库的名称提升为生产仓库 |
| `rdc repo list` | 列出所有仓库及其名称和 GUID |

## 仓库机密

仅供部署时使用的一次性凭证。`get` 仅返回摘要，不返回值。完整指南请参阅 [仓库 § 机密](/en/docs/repositories#secrets)。

| 命令 | 说明 |
|------|------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | 创建新机密（首次写入时使用 `--current ""`） |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | 覆盖现有机密（密码风格的前置条件） |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | 覆盖而不验证先前的值（作为轮换进行审计） |
| `rdc repo secret list <repo>` | 列出机密名称和交付模式（从不返回值或摘要） |
| `rdc repo secret get <repo> --key <KEY>` | 显示机密摘要和模式（永不返回明文值） |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | 删除机密 |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | 删除而不验证先前的值 |

> 派生仓库不继承机密。需在派生仓库上显式设置，使用 `rdc repo secret set <repo>:<tag>`。

## 备份与恢复

| 命令 | 说明 |
|------|------|
| `rdc repo push ... --bwlimit <limit>` | 推送时限制 rsync 带宽（如 `10M`） |
| `rdc repo pull ... --bwlimit <limit>` | 拉取时限制 rsync 带宽 |
| `rdc repo push ... --checkpoint` | 推送前对容器创建检查点 |
| `rdc backup manifests <repo-ref>` | 列出分块存储保存的快照 |
| `rdc backup browse <repo-ref>` | 列出仓库包含的文件（本地，只读） |
| `rdc backup snapshot <repo>` | 上传分块存储快照：首次为完整清单，之后仅为变更单元 |
| `rdc backup snapshot <repo> --dry-run` | 规划快照而不上传；报告将会移动哪些内容 |
| `rdc backup verify <repo>` | 对照分块存储验证仓库的备份锚点 |
| `rdc backup usage` | 显示分块存储中已存储的字节数与配额的对比 |
| `rdc backup manifests <repo>` | 列出服务器上记录的快照清单 |
| `rdc storage browse <storage>` | 浏览存储内容 |

## 仓库迁移

| 命令 | 说明 |
|------|------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | 在机器之间迁移仓库 |
| `rdc repo migrate ... --provision` | 传输前在目标机器上进行配置 |
| `rdc repo migrate ... --checkpoint` | 迁移前创建检查点 |
| `rdc repo migrate ... --skip-dns` | 迁移后跳过 DNS 更新 |
| `rdc repo migrate ... --bwlimit <limit>` | 限制传输带宽 |

## 备份策略

| 命令 | 说明 |
|------|------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | 创建或更新命名备份策略 |
| `rdc backup strategy list` | 列出所有已定义的备份策略 |
| `rdc backup strategy show <name>` | 显示策略详情 |
| `rdc backup strategy remove <name>` | 删除策略 |
| `rdc backup schedule -m <machine>` | 将已配置的备份策略部署到机器 |

## 备份操作

| 命令 | 说明 |
|------|------|
| `rdc backup schedule -m <machine>` | 将绑定的策略部署为 systemd 定时器 |
| `rdc backup schedule -m <machine> --dry-run` | 预览定时器单元而不部署（令牌已遮蔽） |
| `rdc backup run -m <machine>` | 立即运行所有绑定的策略 |
| `rdc backup run <name> -m <machine>` | 立即运行指定策略 |
| `rdc backup status -m <machine>` | 显示定时器状态和最近的任务结果 |
| `rdc backup status <name> -m <machine>` | 显示指定策略的状态 |
| `rdc backup cancel -m <machine>` | 取消正在运行的备份 |
| `rdc backup cancel <name> -m <machine>` | 取消指定的正在运行的备份 |

## 机器管理

| 命令 | 说明 |
|------|------|
| `rdc machine status <machine>` | 完整机器状态（系统、容器、服务、仓库、网络） |
| `rdc machine status <machine> --system` | 仅系统信息 |
| `rdc machine status <machine> --containers` | 仅容器列表 |
| `rdc machine status <machine> --repositories` | 仅仓库列表 |
| `rdc machine status <machine> --services` | 仅服务列表 |
| `rdc machine status <machine> --network` | 仅网络信息 |
| `rdc machine status <machine> --block-devices` | 仅块设备信息 |
| `rdc machine list` | 列出配置中的所有机器 |
| `rdc machine setup <machine>` | 运行机器初始配置 |
| `rdc machine prune <machine>` | 从机器中删除未使用的资源 |
| `rdc machine deprovision <machine>` | 完全取消配置机器 |

## 终端与同步

| 命令 | 说明 |
|------|------|
| `rdc term connect <machine>` | 打开到机器的 SSH 终端 |
| `rdc term connect <repo>@<machine>` | 打开到仓库的 SSH 终端（设置 DOCKER_HOST） |
| `rdc term connect <machine> -c "<command>"` | 在机器上运行命令 |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | 将一个或多个本地文件或目录上传到仓库 |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | 将单个本地文件上传到指定的远程路径 |
| `rdc repo sync download <repo>@<machine> --local <dir>` | 将仓库目录下载到本地 |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | 将单个远程文件下载到本地目录 |
| `rdc vscode connect <repo>@<machine>` | 打开 VS Code Remote SSH 会话 |

## 配置

| 命令 | 说明 |
|------|------|
| `rdc config init <name>` | 创建命名配置文件 |
| `rdc machine add <machine> --ip <host> --user <user>` | 向配置中添加机器 |
| `rdc storage import rclone.conf` | 从 rclone 配置导入存储提供商 |
| `rdc storage list` | 列出已配置的存储提供商 |
| `rdc backup strategy set ...` | 定义命名备份策略 |
| `rdc --config <name> <command>` | 使用命名配置文件 |

## 调试与直接访问

| 命令 | 说明 |
|------|------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | 列出仓库中的容器 |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | 获取容器日志 |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | 在容器中执行命令 |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | 重启容器 |
