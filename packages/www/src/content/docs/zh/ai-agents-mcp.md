---
title: MCP 服务器设置
description: 使用模型上下文协议 (MCP) 服务器将 AI 代理连接到 Rediacc 基础设施。
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: zh
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
---

## 概述

`rdc mcp serve` 命令启动一个本地 MCP（模型上下文协议）服务器，AI 代理可以使用该服务器管理您的基础设施。服务器使用 stdio 传输方式，代理将其作为子进程启动，并通过 JSON-RPC 进行通信。

**前提条件：** 已安装并配置 `rdc`，且至少配置了一台机器。

## Claude Code

添加到项目的 `.mcp.json` 文件中：

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

或使用命名配置：

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

打开设置 → MCP 服务器 → 添加服务器：

- **名称**: `rdc`
- **命令**: `rdc mcp serve`
- **传输方式**: stdio

## 可用工具

<!-- >>> translated-table: mcp-tools -->

| 工具 | 破坏性 | 描述 |
|---|---|---|
| `backup_browse` | 否 | 列出仓库包含的文件。 |
| `backup_cancel` | 否 | 取消远程机器上正在运行的备份。 |
| `backup_check` | 否 | 通过恢复一个文件，验证已存储的快照能否用口令打开。 |
| `backup_immutability_show` | 否 | 显示当前生效的延迟删除窗口。 |
| `backup_list` | 否 | 列出机器上的备份产物。 |
| `backup_manifests` | 否 | 列出服务器上记录的备份快照清单。 |
| `backup_reconcile` | 是 | 将仓库的已存储字节账本重置为存储实际持有的数据量（绝不删除任何数据块）。 |
| `backup_repair` | 是 | 从本机的锚点重新上传存储丢失或保存有误的数据块。 |
| `backup_restore` | 是 | 将备份产物转换为可用的仓库。 |
| `backup_retention` | 否 | 显示服务器正在执行的快照保留策略。 |
| `backup_retention_preview` | 否 | 显示下一次清理会删除哪些快照，以及能释放多少空间。 |
| `backup_run` | 否 | 立即运行一次备份。 |
| `backup_snapshot` | 否 | 上传数据块存储的快照：先上传完整清单，再上传变化的单元。 |
| `backup_status` | 否 | 显示远程机器上的备份状态和定时器状态。 |
| `backup_strategy_list` | 否 | 列出所有备份策略。 |
| `backup_strategy_show` | 否 | 显示备份策略的详细信息。 |
| `backup_toc-key_sync` | 否 | 将仓库的列表密钥安装到其所在机器上，或替换为不同的密钥。 |
| `backup_undelete` | 否 | 在延迟删除快照生效之前取消删除。 |
| `backup_usage` | 否 | 显示备份存储配额、已存储字节数以及每个仓库的用量。 |
| `backup_verify` | 否 | 对照数据块存储，验证仓库的备份锚点。 |
| `cluster_snapshot_list` | 否 | 列出集群的分组快照。 |
| `cluster_status` | 否 | 列出所有集群；传入集群名称则显示该集群的完整配置。 |
| `config_access_list` | 否 | 列出配置的访问密钥。 |
| `config_prune` | 否 | 清理本地配置文件 ~/.config/rediacc/<config>.json 中的冗余内容。 |
| `config_reconcile` | 否 | 根据机器的实际状态重建本地状态存储（renet list all）。 |
| `config_show` | 否 | 显示当前配置的详细信息。 |
| `credits` | 否 | 显示此账户剩余的额度余额。 |
| `datastore_list` | 否 | 列出命名的数据存储、它们挂载的位置以及所存内容。 |
| `datastore_snapshot_list` | 否 | 列出数据存储的快照。 |
| `datastore_status` | 否 | 显示一个数据存储：后端、挂载情况、用量、仓库和快照。 |
| `feedback_list` | 否 | 列出此机器可见的反馈报告：ID、简短指纹、状态和日期。 |
| `feedback_report` | 否 | 根据最近一次失败的命令（--last）、已记录的命令（--command <n>）或仅一条消息生成报告，原样输出将要发送的内容，确认后发送。 |
| `feedback_show` | 否 | 按 ID（或唯一前缀）显示一份反馈报告，包括状态、出现次数和日期。 |
| `job_cancel` | 是 | 取消一个正在运行的分离作业。 |
| `job_dismiss` | 是 | 在本地放弃作业票据：其待办步骤被丢弃，该票据不再显示。 |
| `job_gc` | 是 | 删除已完成的作业及其日志。 |
| `job_list` | 否 | 按从新到旧的顺序列出机器上的分离作业。 |
| `job_logs` | 否 | 回放或实时跟踪分离作业的事件日志。 |
| `job_status` | 否 | 显示分离作业的状态。 |
| `job_wait` | 否 | 最多等待 50 秒，直到作业完成。 |
| `legal` | 否 | 输出以 CLI 语言显示的法律文件链接及具有约束力的英文链接、当前服务条款版本及其校验和与归档 URL、已记录的接受情况（登录时来自账户服务器，匿名时来自此配置）以及签约主体。 |
| `machine_access_show` | 否 | 显示绑定到某台机器的访问密钥，以及每个密钥在该机器上解析出的范围。 |
| `machine_add` | 否 | 注册一台可通过 SSH 访问的现有机器。 |
| `machine_containers` | 否 | 列出机器上的 Docker 容器。 |
| `machine_converge` | 是 | 逐个重启仍运行在旧运行时布局上的仓库守护进程，使其切换到当前布局。 |
| `machine_deprovision` | 是 | 销毁通过云端创建的机器，并将其从配置中移除。 |
| `machine_gpu_list` | 否 | 列出机器上检测到的 GPU、其规格定义的 CDI 设备名称，以及每个设备分配给的仓库。 |
| `machine_health` | 否 | 为 CI/CD 流水线检查机器的健康状况。 |
| `machine_infra_show` | 否 | 显示机器的基础设施配置（基础域名、公网 IP、端口）、共享的 TLS 设置（证书邮箱、CF DNS 令牌）以及 Cloudflare 区域 ID。 |
| `machine_list` | 否 | 列出机器。 |
| `machine_provider_add` | 否 | 添加云服务提供商。 |
| `machine_provider_list` | 否 | 列出已配置的、用于机器供应的云服务提供商。 |
| `machine_provider_remove` | 是 | 移除云服务提供商配置。 |
| `machine_provision` | 是 | 使用 OpenTofu 在云服务提供商上供应一台新机器。 |
| `machine_prune` | 是 | 从机器上移除孤立的数据存储资源和过期快照。 |
| `machine_remove` | 是 | 将机器从配置中移除。 |
| `machine_repos` | 否 | 列出机器上已部署的仓库。 |
| `machine_restart-services` | 是 | 将仍在运行已被替换的二进制文件的 renet 守护进程逐个单元切换到已安装的版本，并在处理下一个之前确认每个都已在新二进制文件上处于活动状态。 |
| `machine_scan-keys` | 否 | 将机器的 SSH 主机密钥记录到本地配置。 |
| `machine_services` | 否 | 列出机器上由 Rediacc 管理的 systemd 服务（名称、状态、子状态、重启次数、内存、解析为名称的仓库，原始值在 repository_guid 中）。 |
| `machine_setup` | 否 | 完成机器的接入：安装 renet，并将其准备好用于托管仓库。 |
| `machine_status` | 否 | 获取机器的连接详情（IP、用户、端口、数据存储）、系统信息、容器（仓库解析为名称，原始值在 repository_guid 中，域名，autoRoute）、服务（仓库解析为名称）、仓库（由 GUID 解析出的名称，原始值在 guid 中）以及资源用量。 |
| `repo_admin_fsck` | 否 | 对照机器上实际存在的对象，校验配置中的引用（分支/HEAD），并报告悬空引用和孤立提交。 |
| `repo_cat` | 否 | 将仓库中某个文件的一段有限范围读取到 stdout（诊断信息输出到 stderr）。 |
| `repo_checkout` | 是 | 通过 reflink 将不可变提交（或分支末端）克隆为新的可写工作分叉，并让 HEAD 指向它。 |
| `repo_commit` | 是 | 将已挂载的工作分叉冻结为新的不可变提交（类似 git）。 |
| `repo_create` | 是 | 创建新仓库。 |
| `repo_delete` | 是 | 删除仓库及其数据。 |
| `repo_diff` | 否 | 在两个写时复制的分叉仓库之间，输出 git 风格的文件级差异。 |
| `repo_down` | 是 | 停止仓库的 Docker 容器（运行 Rediaccfile 的 down）。 |
| `repo_exec` | 是 | 在仓库容器内运行命令。 |
| `repo_fork` | 是 | 为仓库创建一个近乎瞬时的 CoW 分叉，使用全新的 GUID 和 networkId（完全独立的副本）。 |
| `repo_gc` | 是 | 基于可达性的垃圾回收：删除机器上任何分支/HEAD 都无法到达的不可变提交对象。 |
| `repo_health` | 否 | 运行仓库 Rediaccfile 的 health() 检查，并以 0（正常）、1（警告）或 2（错误）退出。 |
| `repo_list` | 否 | 列出机器上的仓库。 |
| `repo_log` | 否 | 输出从工作分叉的当前提交（或某个提交引用）可达的提交历史，沿着 'rdc repo commit' 记录的父提交链回溯。 |
| `repo_logs` | 否 | 显示仓库容器的应用日志。 |
| `repo_merge` | 是 | 以不破坏生命周期的方式，将源提交/分叉合并到目标工作分叉。 |
| `repo_migrate` | 是 | 以最短停机时间将仓库迁移到另一台机器：分两阶段复制（运行中批量同步，然后短暂停止、增量同步并在目标端启动），并完成 DNS 切换。 |
| `repo_pull` | 是 | 从另一台机器拉取仓库。 |
| `repo_push` | 是 | 将仓库备份推送到存储，或直接推送到另一台机器。 |
| `repo_replicate` | 否 | 为仓库供应只读副本。 |
| `repo_replicate_remove` | 是 | 移除一个副本集：删除其生成的 k8s 对象（按标签限定），丢弃其分叉数据存储，放弃其快照，并清除状态。 |
| `repo_replicate_status` | 否 | 显示受管的副本集：副本、承载节点、分叉数据存储、快照和刷新时间戳。 |
| `repo_secret_get` | 否 | 显示密钥的 SHA-256 摘要。 |
| `repo_secret_list` | 否 | 列出密钥的键名和模式（绝不显示值，也不显示摘要）。 |
| `repo_status` | 否 | 获取仓库状态（挂载状态、Docker 守护进程是否运行、容器数量、磁盘用量）。 |
| `repo_trim` | 否 | 从已挂载的仓库回收数据存储池空间（在线进行，零停机）。 |
| `repo_up` | 是 | 部署或更新仓库（通过 renet compose 运行 Rediaccfile 的 up，并启动容器）。 |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| 工具 | 破坏性 | 描述 |
|---|---|---|
| `cluster_kubeconfig` | 否 | 通过 SSH 从集群控制节点获取 kubeconfig，并在本地缓存（0600）供 kubectl 使用。 |
| `config_audit_log` | 否 | 读取通过此配置所做变更的审计日志。 |
| `config_audit_verify` | 否 | 验证审计日志的哈希链未被篡改。 |
| `config_current` | 否 | 显示当前生效的配置：名称、文件、解析出的服务器和通道、令牌状态。 |
| `config_list` | 否 | 列出所有配置文件。 |
| `machine_infra_cert_status` | 否 | 显示已缓存的证书清单。 |
| `server_status` | 否 | 显示已安装服务器的健康状况、层级、证书和镜像。 |
| `version` | 否 | 输出 CLI 版本、平台、更新通道和当前许可证：登录时显示套餐，未登录时显示 "anonymous (FREE per repository)"，无法连接账户服务器时显示 "unknown (server unreachable)"。 |

<!-- <<< translated-table -->

### 读取工具（安全，无副作用）

| 工具 | 描述 |
|------|------|
| `machine_query` | 获取机器的系统信息、容器、服务和资源使用情况 |
| `machine_containers` | 列出 Docker 容器的状态、健康状况、资源使用、标签和自动路由域名 |
| `machine_services` | 列出 rediacc 管理的 systemd 服务（名称、状态、子状态、重启次数、内存、所属仓库） |
| `machine_repos` | 列出已部署的仓库（名称、GUID、大小、挂载状态、Docker 状态、容器数量、磁盘用量、修改日期、Rediaccfile 是否存在） |
| `machine_health` | 对机器执行健康检查（系统、容器、服务、存储） |
| `machine_list` | 列出所有已配置的机器 |
| `config_repositories` | 列出已配置的仓库及其名称与 GUID 的映射关系 |
| `config_show_infra` | 显示机器的基础设施配置（基础域名、公网 IP、TLS、Cloudflare 区域） |
| `config_providers` | 列出用于机器供应的已配置云服务商 |
| `agent_capabilities` | 列出所有可用的 rdc CLI 命令及其参数和选项 |
| `repo_secret_list` | 列出仓库的密钥名称和投递模式（不含值，不含摘要）。只读操作，安全无副作用。 |
| `repo_secret_get` | 获取密钥的 SHA-256 摘要和投递模式。出于设计原因，永远不返回明文值。可用于验证密钥是否存在或已完成轮换。 |

### 写入工具（具有破坏性）

| 工具 | 描述 |
|------|------|
| `repo_create` | 在机器上创建新的加密仓库 |
| `repo_up` | 部署/更新仓库（运行 Rediaccfile up，启动容器）。首次部署或拉取后使用 `mount` |
| `repo_down` | 停止仓库容器。默认不卸载。使用 `unmount` 同时关闭 LUKS 容器 |
| `repo_delete` | 删除仓库（销毁容器、卷和加密镜像）。凭据归档以供恢复 |
| `repo_fork` | 创建具有新 GUID 和 networkId 的 CoW 分叉（完全独立的副本，支持在线分叉） |
| `backup_push` | 将仓库备份推送到存储或其他机器（相同 GUID，备份/迁移，非分叉） |
| `backup_pull` | 从存储或机器拉取仓库备份。拉取后使用 `repo_up`（mount=true）进行部署 |
| `machine_provision` | 使用 OpenTofu 在云服务商上供应新机器 |
| `machine_deprovision` | 销毁云供应的机器并从配置中移除 |
| `config_add_provider` | 添加用于机器供应的云服务商配置 |
| `config_remove_provider` | 移除云服务商配置 |
| `term_exec` | 通过 SSH 在远程机器上执行命令 |

## 示例工作流

**检查机器状态：**
> "我的生产机器状态如何？"

代理调用 `machine_query` → 返回系统信息、运行中的容器、服务和资源使用情况。

**部署应用程序：**
> "在我的预发布机器上部署 gitlab"

代理调用 `repo_up`，参数为 `name: "gitlab"` 和 `machine: "staging"` → 部署仓库，返回成功/失败结果。

**调试故障服务：**
> "我的 nextcloud 很慢，找出问题所在"

代理调用 `machine_health` → `machine_containers` → `term_exec` 读取日志 → 识别问题并建议修复方案。

## 配置选项

| 选项 | 默认值 | 描述 |
|------|--------|------|
| `--config <name>` | （默认配置） | 用于所有命令的命名配置 |
| `--timeout <ms>` | `120000` | 默认命令超时时间（毫秒） |

## 安全

MCP 服务器通过两层保护机制来保障安全：

### 仅分叉模式（默认）

默认情况下，服务器以**仅分叉模式**运行：写入工具（`repo_up`、`repo_down`、`repo_delete`、`backup_push`、`backup_pull`、`term_exec`）只能操作分叉仓库。代理无法修改 grand（原始）仓库，此为设计行为。

> **每个仓库的密钥管理仅限 CLI 操作，此为设计决策。** `repo_secret_set` 和 `repo_secret_unset` 有意**不**作为 MCP 工具暴露。写入操作需要 `--current <previous-value>` 前置条件（或使用 `--rotate-secret` 确认未经验证的轮换），该操作需要人工审核。如果代理需要建议密钥轮换，应先调用 `repo_secret_get` 确认摘要，然后通过 JSON 错误信封中 `next.options[].run` 字段的结构化输出，将面向操作人员的 CLI 命令传递给用户。完整模式请参阅 [AI 代理安全](/en/docs/ai-agents-safety#structured-next-action-hints)，用户操作指南请参阅[仓库 § 密钥](/en/docs/repositories#secrets)。

要允许代理修改 grand 仓库，请在启动托管 MCP 服务器的代理**之前**在终端中导出 `REDIACC_ALLOW_GRAND_REPO`：

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # 一个仓库
# 或 'repo1,repo2,repo3'（条目周围的空白会被忽略），或 '*' 用于所有仓库
claude   # 或 cursor、gemini 等
```

覆盖是根据进程祖先验证的：仅当覆盖已存在于代理进程本身的环境中时才算数，这意味着你在代理（以及它启动的 MCP 服务器）启动之前导出了它。代理无法通过在会话中途设置该变量来自我授予访问权限。故意没有服务器标志用于此目的：MCP 服务器参数中的标志不能证明是谁设置的，而祖先检查可以。机器级访问（例如 `term connect <machine>` 不指定仓库）仍需要 `*`；仓库名称列表无法解锁该权限。

### 每仓库 SSH 密钥与服务端沙箱

每个仓库都有独立的 SSH 密钥对。公钥部署到 `authorized_keys` 时带有 `command=` 前缀，强制所有 SSH 会话通过 `renet sandbox-gateway <repo-name>` 进行，这是一个服务端 ForceCommand，任何客户端（包括 VS Code）都无法绕过。

**工作原理：**
1. `rdc repo create` 或 `rdc repo fork` 为每个仓库生成独立的 ed25519 密钥对
2. 公钥以 `command="renet sandbox-gateway <name>"` 形式部署到远端
3. 使用该密钥的所有 SSH 连接均通过网关，网关会执行：
   - **Landlock LSM**，内核级文件系统限制，作用范围为仓库的挂载路径
   - **OverlayFS 家目录覆盖**，对 `$HOME` 的写入按仓库捕获，读取则穿透到真实家目录
   - **每仓库 TMPDIR**，位于 `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Docker 访问**，通过仓库隔离的 Docker socket
   - **权限降级**，切换到通用用户（`rediacc`）
4. 仓库的 `.envrc` 会自动加载，用于 Docker 和环境配置

**允许读写（RW）**：仓库挂载路径、每仓库沙箱工作区、家目录（通过覆盖层）、Docker socket
**允许只读（RO）**：系统路径（`/usr`、`/bin`、`/etc`、`/proc`、`/sys`）
**阻止**：其他仓库的挂载路径、允许列表之外的系统文件

**VS Code 集成**：每个仓库在 `<datastore>/.interim/sandbox/<name>/.vscode-server/` 目录下拥有独立的 VS Code 服务器实例。多个仓库可同时打开，各自拥有独立的沙箱环境，仓库之间不共享服务器。

这可以防止横向移动。即使代理获得了对某个分叉的 shell 访问权限，也无法读取或修改同一机器上的其他仓库。机器级 SSH（不指定仓库）使用团队密钥，不受沙箱限制。

## 架构

MCP 服务器是无状态的。每次工具调用都会将 `rdc` 作为独立的子进程启动，并使用 `--output json --yes --quiet` 标志。这意味着：

- 工具调用之间不会发生状态泄漏
- 使用您现有的 `rdc` 配置和 SSH 密钥
- 一个命令中的错误不会影响其他命令
