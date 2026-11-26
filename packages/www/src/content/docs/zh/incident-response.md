---
title: "事件响应：调查、声明并保全证据"
description: "对仓库或机器发起调查，阅读由审计、运行、网络流和文件打开组成的统一时间线，验证哈希链，声明事件以冻结证据并启动 24 小时、72 小时和一个月的计时，所有操作都可通过 rdc 完成。"
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 10
language: zh
sourceHash: "07d8b9d09d0e2191"
sourceCommit: "d93166e47a19c588a2284e21d263cca7f8a3578d"
---

# 事件响应

这里的事件指发生在客户自己仓库内部的事件。调查页面、`rdc incident` 命令以及 `rdc repo flows` 和 `rdc repo opens` 读取器，都基于[取证](/zh/docs/forensics)中描述的记录工作。Rediacc 自身系统中的事件遵循[安全事件响应](/zh/docs/security-incident-response)。

## 访问

调查需要付费套餐以及所有者或管理员角色。发起调查时会要求最近一次重新认证，已发起的调查有效期为 60 分钟。每次查看都会写入审计日志。

Rediacc 支持人员只有在客户签发的支持授权下才能看到取证数据。授权最长 7 天，并且可以随时撤销。

CLI 读取需要 `forensics:read` 范围，声明和关闭需要 `incident:manage`。所有者和管理员在浏览器中完成提升权限的批准后，CLI 登录会同时带有这两项。当命令提示需要最近一次提升权限的批准时，账户门户会请求批准，然后命令即可重新运行。

## 时间线

Investigate 页面把一个范围（一个仓库或一台机器）合并为一条时间线，包含五种行：控制台审计事件、运行、网络流、文件打开和异常。可以与上一次快照对比自那以来的变化。时间窗口滑块用来设定窗口，一个窗口最长 31 天。

没有证据的时间段会显示为一行空白，注明机器和原因，绝不会是一段空白。行的上方有每分钟出站字节数的图表和主要目的地列表。

同样的读取也可以在命令行中完成：

```bash
rdc repo flows mail --since 24h
rdc repo flows mail --since 2026-11-20T00:00:00Z --until 2026-11-21T00:00:00Z
rdc repo opens mail --since 7d
```

`--since` 和 `--until` 接受 ISO 8601 时刻，或从现在向前推的时间跨度，例如 `90m`、`24h` 或 `7d`。默认窗口为最近 24 小时。流行显示时间、进程、目的地、出入字节数，以及已知时的 ASN 和国家或地区。打开行显示时间、进程和路径，敏感路径会有标记。

## 验证证据

Verify evidence 会在浏览器中重新计算该窗口内审计日文件的哈希链和取证记录的签名批次链，并列出每一处空白和修改。批次签名使用账户服务器为每台机器固定的 spool 密钥来检查。证据内部写入的密钥永远不会被信任。结果会盖章到导出的报告中。

超过 2 GiB 的证据对浏览器来说太大。同一个模块可以在命令行运行：

```bash
rdc forensics verify --dir ./incident-evidence
rdc forensics verify --dir ./incident-evidence --since 7d --machine-key web-1=<public-key-hex>
```

发现任何空白或修改时，命令以退出码 1 结束。`--machine-key <machine>=<64 hex characters>` 提供来自目录之外的密钥，可以重复使用。没有外部密钥的机器会验证失败。

## 声明事件

声明会冻结证据。先写入账户记录，然后为调查准备仓库：

1. 记录事件及其窗口、声明人以及组织得知事件的时间。
2. 清除保留覆盖该窗口，存储桶锁定规则也延伸到这段时间，因此 FIFO 无法删除这些天的数据。
3. 仓库被 fork 为取证快照，标签为 `incident-<id>`。
4. 仓库的采集级别切换到 Full。

三个计时从得知时间开始。得知时间可以设为早于声明时间，但不能晚于声明时间：预警在得知后 24 小时到期，通知在得知后 72 小时到期，最终报告在通知后一个日历月到期（在记录通知之前，从通知截止时间起算）。页面把每个计时显示为待处理、6 小时内到期、已逾期或已完成。

```bash
rdc incident declare mail
rdc incident declare mail --since 48h --aware-at 2026-11-20T09:30:00Z
rdc incident status
rdc incident status <id>
```

机器上某一步失败时，记录及其保留会保持不变，命令以退出码 1 结束，并给出只重新运行失败步骤的命令：

```bash
rdc incident declare mail --resume <id>
```

`--resume` 沿用原始声明的窗口和得知时间，因此 `--since`、`--until` 和 `--aware-at` 不能与它同时使用。

## 导出证据

`rdc incident export` 把事件的窗口写入一个目录：带计时的事件记录、合并后的时间线、出站字节聚合、原始链清单，以及清单中列出的原始文件。当清单列出审计日文件或取证头文件时，会在过程中验证这些链，结果写入 `verification.json`。证据显示存在空白或修改时，命令以退出码 1 结束。

```bash
rdc incident export <id>
rdc incident export <id> --out ./incident-evidence
```

加上 `--stage` 后，同一命令会改为写出签名报告。参见[事件报告](/zh/docs/incident-reports)。

## 关闭事件

```bash
rdc incident close <id>
```

不会立即释放任何内容。清除保留和存储桶锁定规则在关闭 30 天后结束。

## 询问 AI

调查页面有一个助手，可以回答关于当前范围和窗口的问题。它只读取该范围和窗口，使用由已打开的调查生成的一次性票据，票据在 15 分钟内可兑换。问题及其读取的行会发送给组织自己的 AI 提供方。助手可以运行上述 `rdc` 命令，权限规则与其他任何命令相同。

## 命令

| 命令 | 用途 |
|---|---|
| `rdc repo flows <ref>` | 仓库在某个窗口内的网络流 |
| `rdc repo opens <ref>` | 仓库在某个窗口内的敏感文件打开 |
| `rdc forensics level <ref> <level>` | 设置采集级别 |
| `rdc forensics verify` | 验证证据目录或签名报告 |
| `rdc incident declare <ref>` | 记录事件，fork 仓库并切换到 Full |
| `rdc incident status [id]` | 列出事件，或显示某个事件及其计时 |
| `rdc incident export <id>` | 写出证据窗口，加 `--stage` 则写出签名报告 |
| `rdc incident close <id>` | 关闭事件 |
