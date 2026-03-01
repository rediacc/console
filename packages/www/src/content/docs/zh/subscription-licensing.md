---
title: "订阅与许可"
description: "管理本地部署的订阅和机器许可证。"
category: "Guides"
order: 7
language: zh
sourceHash: "84215f54750ac4a4"
---

# 订阅与许可

在本地部署中运行的机器需要订阅许可证来执行基于计划的资源限制。CLI 通过 SSH 自动将签名的许可证 blob 传递到远程机器 — 服务器端无需手动激活或云连接。

## 概述

1. 使用 `rdc subscription login` 登录（打开浏览器进行身份验证）
2. 使用任何机器命令 — 许可证会自动处理

当您运行针对机器的命令（`rdc machine info`、`rdc repo up` 等）时，CLI 会自动检查机器是否有有效的许可证。如果没有，它会从账户服务器获取许可证并通过 SSH 传递。

## 登录

```bash
rdc subscription login
```

通过设备代码流打开浏览器进行身份验证。批准后，CLI 将 API 令牌本地存储在 `~/.config/rediacc/api-token.json`。

| 选项 | 必需 | 默认值 | 描述 |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | API 令牌（跳过浏览器流程） |
| `--server <url>` | No | `https://account.rediacc.com` | 账户服务器 URL |

## 检查状态

```bash
# 账户级别状态（计划、机器）
rdc subscription status

# 包含特定机器的许可证详情
rdc subscription status -m hostinger
```

显示来自账户服务器的订阅详情。使用 `-m` 时，还会通过 SSH 连接到机器并显示其当前的许可证信息。

## 强制刷新许可证

```bash
rdc subscription refresh -m <machine>
```

强制重新签发并将新的许可证传递到指定的机器。通常不需要此操作 — 在正常 CLI 使用期间，许可证每 50 分钟自动刷新。

## 工作原理

1. **登录** 在您的工作站上存储 API 令牌
2. **任何机器命令** 通过 SSH 触发自动许可证检查
3. 如果远程许可证缺失或超过 50 分钟，CLI 将：
   - 通过 SSH 读取远程机器的硬件 ID
   - 调用账户 API 签发新许可证
   - 通过 SSH 将机器许可证和订阅 blob 传递到远程机器
4. 50 分钟的内存缓存防止同一会话内的冗余 SSH 往返

每次机器激活会消耗订阅中的一个名额。要释放名额，请从账户门户停用机器。

## 宽限期与降级

如果许可证过期且在 3 天宽限期内无法刷新，机器的资源限制将降级为 Community 计划默认值。许可证刷新后（恢复连接并运行任何 `rdc` 命令），原始计划限制将立即恢复。

## 计划限制

### 浮动许可证限制

| 计划 | Floating Licenses |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### 资源限制

| 资源 | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### 功能可用性

| 功能 | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
