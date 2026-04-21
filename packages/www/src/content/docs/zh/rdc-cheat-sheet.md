---
title: RDC CLI 快速参考
description: 所有 rdc 命令的快速参考，包括配置、仓库、机器、同步、容器等。
category: Guides
order: 3
language: zh
sourceHash: c552951bebd937b0
sourceCommit: 35b53352026ae87fb6800c7fed10b793223ca1da
---

# RDC CLI 快速参考

最常用 `rdc` 命令的快速参考。在任意命令后加 `--help` 可查看完整选项。

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
| `rdc config machine set <machine> --backup-strategies <s1,s2>` | 将策略绑定到机器 |

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
| `rdc machine vault-status --name <machine>` | 显示 LUKS 保险库状态 |

## 终端与同步

| 命令 | 说明 |
|------|------|
| `rdc term connect -m <machine>` | 打开到机器的 SSH 终端 |
| `rdc term connect -m <machine> -r <repo>` | 打开到仓库的 SSH 终端（设置 DOCKER_HOST） |
| `rdc term connect -m <machine> -c "<command>"` | 在机器上运行命令 |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | 将文件、目录或多个来源上传到仓库 |
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
