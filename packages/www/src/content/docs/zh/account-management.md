---
title: 账户管理
description: Rediacc中的组织、团队、成员和订阅。
category: Guides
order: 12
language: zh
sourceHash: "dddc18692cb1583b"
sourceCommit: "dabe1a33844b3b7ec8a2c4ab44dc2de6683283c9"
---

### 组织

注册时，Rediacc会自动为您创建一个组织。您的组织是所有资源的顶级容器 -- 机器、仓库、订阅和团队成员。

![Registration Flow](/img/account-registration-flow.svg)

每个组织包含：
- 唯一名称（默认为您的电子邮件地址）
- 订阅计划（从COMMUNITY开始）
- 默认团队（所有成员自动加入）

### 成员与角色

组织支持三种角色：

![Role Hierarchy](/img/account-role-hierarchy.svg)

| 角色 | 能力 |
|------|------|
| **Owner** | 完全控制：计费、转让所有权、管理所有成员和团队 |
| **Admin** | 邀请和移除成员、创建和管理团队、撤销API令牌 |
| **Member** | 查看组织数据、创建API令牌、访问分配的团队 |

邀请成员：
```bash
# From the portal: Organization > Members > Invite
# Or via API
```

当成员被移除时，其API令牌和Config Storage令牌会自动被撤销。

### 团队

团队允许您在组织内限定资源范围。每个组织都以一个默认团队开始。

![Team Structure](/img/account-team-structure.svg)

团队角色：
- **Team Admin**：可以在团队内添加/移除团队成员
- **Member**：可以访问团队范围内的资源

组织所有者和管理员无需显式成员资格即可自动访问所有团队。

### 订阅与计划

Rediacc提供四种计划：

| 计划 | 机器 | 仓库许可证/月 | 功能 |
|------|------|---------------|------|
| COMMUNITY | 2 | 500 | 基础 |
| PROFESSIONAL | 10 | 2,000 | 权限组、队列优先级 |
| BUSINESS | 25 | 5,000 | Ceph、高级分析、审计日志 |
| ENTERPRISE | 无限制 | 无限制 | 自定义品牌、专属账户 |

![Subscription Flow](/img/account-subscription-flow.svg)

所有计划均以3天宽限期开始。机器激活按团队跟踪，不活跃后自动释放。

### 计费

只有组织的**所有者**可以管理计费：
- 创建Stripe结账会话以升级计划
- 访问Stripe计费门户以更改支付方式
- 申请自助退款（14天内，30天冷却期）
