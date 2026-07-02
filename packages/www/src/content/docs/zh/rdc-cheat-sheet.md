---
title: RDC CLI 快速参考
description: "rdc 快速参考：配置、仓库、机器、文件同步和容器。完整选项集：在任意命令后添加 --help。"
category: Guides
order: 3
language: zh
sourceHash: "8cde2c78200d226a"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# RDC CLI 快速参考

此处并未列出所有 `rdc` 命令，仅包含每次部署中常见的命令。要查看完整选项集，请在任意 rdc 命令后添加 `--help`。边界情况和较少使用的选项详见完整参考。

## 仓库生命周期

| 命令 | 说明 |
|------|------|
| `rdc repo create --name <repo> -m <machine>` | 在机器上创建新仓库 |
| `rdc repo up --name <repo> -m <machine>` | 部署或更新仓库 |
| `rdc repo down --name <repo> -m <machine>` | 停止仓库 |
| `rdc repo delete --name <repo> -m <machine>` | 删除仓库 |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | 派生仓库（近乎瞬时，BTRFS reflink） |
| `rdc repo takeover --name <repo> -m <machine>` | 接管现有仓库的所有权 |
| `rdc config repository list` | 列出所有仓库及其名称和 GUID |

## 仓库机密

仅供部署时使用的一次性凭证。`get` 仅返回摘要，不返回值。完整指南请参阅 [仓库 § 机密](/en/docs/repositories#secrets)。

| 命令 | 说明 |
|------|------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | 创建新机密（首次写入时使用 `--current ""`） |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | 覆盖现有机密（密码风格的前置条件） |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | 覆盖而不验证先前的值（作为轮换进行审计） |
| `rdc repo secret list --name <repo>` | 列出机密名称和交付模式（从不返回值或摘要） |
| `rdc repo secret get --name <repo> --key <KEY>` | 显示机密摘要和模式（永不返回明文值） |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | 删除机密 |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | 删除而不验证先前的值 |

> 派生仓库不继承机密。需在派生仓库上显式设置，使用 `rdc repo secret set --name <repo>:<tag>`。

## 备份与恢复

| 命令 | 说明 |
|------|------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | 将仓库备份推送到存储 |
| `rdc repo push --to <storage> -m <machine>` | 将所有仓库推送到存储 |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | 从存储恢复仓库 |
| `rdc repo pull --from <storage> -m <machine>` | 从存储恢复所有仓库 |
| `rdc repo push ... --bwlimit <limit>` | 推送时限制 rsync 带宽（如 `10M`） |
| `rdc repo pull ... --bwlimit <limit>` | 拉取时限制 rsync 带宽 |
| `rdc repo push ... --checkpoint` | 推送前对容器创建检查点 |
| `rdc repo backup list --from <storage> -m <machine>` | 列出存储中的可用备份 |
| `rdc storage browse --name <storage>` | 浏览存储内容 |

## 仓库迁移

| 命令 | 说明 |
|------|------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | 在机器之间迁移仓库 |
| `rdc repo migrate ... --provision` | 传输前在目标机器上进行配置 |
| `rdc repo migrate ... --checkpoint` | 迁移前创建检查点 |
| `rdc repo migrate ... --skip-dns` | 迁移后跳过 DNS 更新 |
| `rdc repo migrate ... --bwlimit <limit>` | 限制传输带宽 |

## 备份策略

| 命令 | 说明 |
|------|------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | 创建或更新命名备份策略 |
| `rdc config backup-strategy list` | 列出所有已定义的备份策略 |
| `rdc config backup-strategy show --name <name>` | 显示策略详情 |
| `rdc config backup-strategy remove --name <name>` | 删除策略 |
| `rdc machine backup schedule -m <machine>` | 将已配置的备份策略部署到机器 |

## 备份操作

| 命令 | 说明 |
|------|------|
| `rdc machine backup schedule -m <machine>` | 将绑定的策略部署为 systemd 定时器 |
| `rdc machine backup schedule -m <machine> --dry-run` | 预览定时器单元而不部署（令牌已遮蔽） |
| `rdc machine backup now -m <machine>` | 立即运行所有绑定的策略 |
| `rdc machine backup now -m <machine> --strategy <name>` | 立即运行指定策略 |
| `rdc machine backup status -m <machine>` | 显示定时器状态和最近的任务结果 |
| `rdc machine backup status -m <machine> --strategy <name>` | 显示指定策略的状态 |
| `rdc machine backup cancel -m <machine>` | 取消正在运行的备份 |
| `rdc machine backup cancel -m <machine> --strategy <name>` | 取消指定的正在运行的备份 |

## 机器管理

| 命令 | 说明 |
|------|------|
| `rdc machine query --name <machine>` | 完整机器状态（系统、容器、服务、仓库、网络） |
| `rdc machine query --name <machine> --system` | 仅系统信息 |
| `rdc machine query --name <machine> --containers` | 仅容器列表 |
| `rdc machine query --name <machine> --repositories` | 仅仓库列表 |
| `rdc machine query --name <machine> --services` | 仅服务列表 |
| `rdc machine query --name <machine> --network` | 仅网络信息 |
| `rdc machine query --name <machine> --block-devices` | 仅块设备信息 |
| `rdc machine list` | 列出配置中的所有机器 |
| `rdc config machine setup --name <machine>` | 运行机器初始配置 |
| `rdc machine prune --name <machine>` | 从机器中删除未使用的资源 |
| `rdc machine deprovision --name <machine>` | 完全取消配置机器 |

## 终端与同步

| 命令 | 说明 |
|------|------|
| `rdc term connect -m <machine>` | 打开到机器的 SSH 终端 |
| `rdc term connect -m <machine> -r <repo>` | 打开到仓库的 SSH 终端（设置 DOCKER_HOST） |
| `rdc term connect -m <machine> -c "<command>"` | 在机器上运行命令 |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | 将一个或多个本地文件或目录上传到仓库 |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | 将单个本地文件上传到指定的远程路径 |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | 将仓库目录下载到本地 |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | 将单个远程文件下载到本地目录 |
| `rdc vscode connect -m <machine> -r <repo>` | 打开 VS Code Remote SSH 会话 |

## 配置

| 命令 | 说明 |
|------|------|
| `rdc config init --name <name>` | 创建命名配置文件 |
| `rdc config machine add --name <machine> --host <host> --user <user>` | 向配置中添加机器 |
| `rdc config storage import --file rclone.conf` | 从 rclone 配置导入存储提供商 |
| `rdc config storage list` | 列出已配置的存储提供商 |
| `rdc config backup-strategy set ...` | 定义命名备份策略 |
| `rdc --config <name> <command>` | 使用命名配置文件 |

## 调试与直接访问

| 命令 | 说明 |
|------|------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | 列出仓库中的容器 |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | 获取容器日志 |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | 在容器中执行命令 |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | 重启容器 |
