---
title: 订阅与许可
description: 了解 account、rdc 和 renet 如何处理机器槽位、仓库许可证和计划限制。
category: Guides
order: 7
language: zh
sourceHash: "e7a65f722fbb1093"
---

# 订阅与许可

Rediacc 许可管理由三个组成部分：

- `account` 签署权利并追踪使用情况
- `rdc` 进行身份验证、请求许可证、将其传递给机器并在运行时强制执行
- `renet`（机器上的运行时）在本地验证已安装的许可证，无需调用账户服务器

本页说明这些部分如何在本地部署中协同工作。

## 许可管理的作用

许可管理控制两件不同的事情：

- 通过**浮动许可证**进行**机器访问核算**
- 通过**仓库许可证**进行**仓库运行时授权**

这两者相关，但不是同一个制品。

## 许可管理的工作原理

`account` 是计划、合同覆盖、机器激活状态和每月仓库许可证发放的真实来源。

`rdc` 在您的工作站上运行。它将您登录到账户服务器，请求所需的许可证，并通过 SSH 将其安装到远程机器上。当您运行仓库命令时，`rdc` 确保所需许可证已就位，并在运行时在机器上验证它们。

正常流程如下：

1. 您使用 `rdc subscription login` 进行身份验证
2. 您运行仓库命令，如 `rdc repo create`、`rdc repo up` 或 `rdc repo down`
3. 如果所需许可证缺失或已过期，`rdc` 向 `account` 请求
4. `rdc` 将签名的许可证写入机器
5. 许可证在机器上本地验证，操作继续进行

有关工作站与服务器的分工，请参阅 [rdc vs renet](/zh/docs/rdc-vs-renet)；有关仓库生命周期本身，请参阅[仓库](/zh/docs/repositories)。

对于自动化和 AI 代理，请使用范围受限的订阅令牌而非浏览器登录：

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

您也可以直接通过环境注入令牌，使 CLI 无需任何交互式登录步骤即可发放和刷新仓库许可证：

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## 机器许可证与仓库许可证

### 机器激活

机器激活承担双重角色：

- **服务器端**：浮动机器槽位核算、机器级激活检查、将账户支持的仓库发放与特定机器桥接
- **磁盘上**：`rdc` 在激活期间将签名的订阅 blob 写入 `/var/lib/rediacc/license/machine.json`。此 blob 在本地针对配置操作（`rdc repo create`、`rdc repo fork`）进行验证。机器许可证自上次激活起 1 小时内有效。

### 仓库许可证

仓库许可证是针对一台机器上的一个仓库的签名许可证。

用于：

- `rdc repo resize` 和 `rdc repo expand` — 包括到期在内的完整验证
- `rdc repo up`、`rdc repo down`、`rdc repo delete` — **跳过到期**验证
- `rdc backup push`、`rdc backup pull`、`rdc backup sync` — **跳过到期**验证
- 机器重启时的仓库自动启动 — **跳过到期**验证

仓库许可证绑定到机器和目标仓库，Rediacc 通过仓库身份元数据加强该绑定。对于加密仓库，这包括底层卷的 LUKS 身份。

实际上：

- 机器激活回答："此机器可以配置新仓库吗？"
- 仓库许可证回答："此特定仓库可以在此特定机器上运行吗？"

## 默认限制

仓库大小取决于权利级别：

- Community：最多 `10 GB`
- 付费计划：计划或合同限制

付费计划默认限制：

| 计划 | 浮动许可证 | 仓库大小 | 每月仓库许可证发放次数 |
|------|-----------|----------|------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5,000 |
| Business | 20 | 500 GB | 20,000 |
| Enterprise | 50 | 2048 GB | 100,000 |

特定合同限制可以为特定客户提高或降低这些值。

## 仓库创建、启动、停止和重启期间发生的情况

### 创建和分叉仓库

创建或分叉仓库时：

1. `rdc` 确保您的订阅令牌可用（如需要则触发设备代码身份验证）
2. `rdc` 激活机器并将签名的订阅 blob 写入远程机器
3. 机器许可证在本地验证（必须在激活后 1 小时内）
4. 成功创建后，`rdc` 为新仓库发放仓库许可证

该账户支持的发放计入您的每月**仓库许可证发放**使用量。

### 启动、停止和删除仓库

`rdc` 验证机器上安装的仓库许可证，但**跳过到期检查**。签名、机器 ID、仓库 GUID 和身份仍会被验证。即使订阅过期，用户也不会被锁定无法操作其仓库。

### 调整和扩展仓库

`rdc` 执行包括到期和大小限制在内的完整仓库许可证验证。

### 机器重启和自动启动

自动启动使用与 `rdc repo up` 相同的规则 — 跳过到期，因此仓库总是可以自由重启。

仓库许可证使用长期有效性模型：

- `refreshRecommendedAt` 是软刷新点
- `hardExpiresAt` 是阻塞点

如果仓库许可证已过时但仍在硬到期之前，运行时可以继续。一旦达到硬到期，`rdc` 必须为调整/扩展操作刷新它。

### 其他仓库操作

列出仓库、检查仓库信息和挂载等操作不需要任何许可证验证。

## 检查状态和刷新许可证

人工登录：

```bash
rdc subscription login
```

自动化或 AI 代理登录：

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

对于非交互式环境，设置 `REDIACC_SUBSCRIPTION_TOKEN` 是最简单的选项。令牌应仅限于代理所需的订阅和仓库许可证操作。

显示账户支持的订阅状态：

```bash
rdc subscription status
```

显示一台机器的机器激活详情：

```bash
rdc subscription activation-status -m hostinger
```

显示一台机器上已安装的仓库许可证详情：

```bash
rdc subscription repo-status -m hostinger
```

刷新机器激活并批量刷新仓库许可证：

```bash
rdc subscription refresh -m hostinger
```

在机器上发现但本地 `rdc` 配置中缺少的仓库在批量刷新期间被拒绝。它们被报告为失败，不会自动分类。

强制刷新现有仓库的仓库许可证：

```bash
rdc subscription refresh-repo my-app -m hostinger
```

首次使用时，找不到可用仓库许可证的已授权仓库或备份操作可以自动触发账户授权移交。CLI 打印授权 URL，尝试在交互式终端中打开浏览器，并在授权和发放成功后重试一次操作。

在非交互式环境中，CLI 不等待浏览器批准。相反，它告诉您使用 `rdc subscription login --token ...` 或 `REDIACC_SUBSCRIPTION_TOKEN` 提供范围受限的令牌。

有关机器首次设置，请参阅[机器设置](/zh/docs/setup)。

## 离线行为和到期

许可证验证在机器本地进行 — 不需要与账户服务器的实时连接。

这意味着：

- 运行中的环境不需要在每个命令上都有账户实时连接
- 即使许可证过期，所有仓库也可以随时启动、停止和删除 — 用户永远不会被锁定无法操作自己的仓库
- 配置操作（`create`、`fork`）需要有效的机器许可证，增长操作（`resize`、`expand`）需要有效的仓库许可证
- 真正过期的仓库许可证必须在调整/扩展之前通过 `rdc` 刷新

机器激活和仓库运行时许可证是独立的层面。机器在账户状态中可能处于非活动状态，而某些仓库仍有有效的已安装仓库许可证。发生这种情况时，请分别检查两个层面，而不是假设它们意味着同样的事情。

## 恢复行为

自动恢复有意保持在较窄的范围：

- `missing`：`rdc` 可能会在需要时授权账户访问、批量刷新仓库许可证并重试一次
- `expired`：`rdc` 可能会批量刷新仓库许可证并重试一次
- `machine_mismatch`：快速失败并告诉您从当前机器上下文重新发放
- `repository_mismatch`：快速失败并告诉您明确刷新仓库许可证
- `sequence_regression`：作为仓库许可证完整性/状态问题快速失败
- `invalid_signature`：作为仓库许可证完整性/状态问题快速失败
- `identity_mismatch`：快速失败 — 仓库身份与已安装许可证不匹配

这些快速失败情况不会自动消耗账户支持的刷新或发放调用。

## 每月仓库许可证发放次数

此指标统计当前 UTC 日历月内成功的账户支持仓库许可证发放活动。

包括：

- 首次仓库许可证发放
- 返回新签名许可证的成功仓库许可证刷新

不包括：

- 未更改的批量条目
- 失败的发放尝试
- 在发放前被拒绝的未追踪仓库

如果您需要面向客户的使用情况和近期仓库许可证发放历史视图，请使用账户门户。如果您需要机器端检查，请使用 `rdc subscription activation-status -m` 和 `rdc subscription repo-status -m`。
