---
title: "发布通道"
description: "了解 Edge 与 Stable 发布通道的区别及如何选择。"
category: "Concepts"
order: 2
language: zh
sourceHash: "b0f431fd1bcc22c1"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Rediacc 通过两个发布通道推送更新：**Stable** 和 **Edge**。每个通道面向不同的使用场景，各有其权衡。

## Stable 通道

Stable 是所有用户的默认通道。版本在 Edge 上经过 7 天浸泡期且无报告问题后，才会被推广到 Stable。

- 当您偏好保守的升级节奏并希望使用付费计划时推荐
- 在 Edge 上测试 7 天后部署
- 紧急热修复可直接推送
- 域名：`eu.rediacc.com`、`us.rediacc.com`、`asia.rediacc.com`

## Edge 通道

Edge 在每次变更合并到主分支后立即接收，是软件的最新版本，持续部署。

- 最新功能和修复，每次合并后部署
- Community 计划限制翻倍（见下表）
- 永久免费，Edge 上不提供付费计划
- 与 Stable 账户独立，数据不在通道间迁移
- 域名：`edge-eu.rediacc.com`、`edge-us.rediacc.com`、`edge-asia.rediacc.com`

## 对比

| | Stable | Edge |
|---|---|---|
| **部署节奏** | 经过 7 天浸泡期后部署 | 每次合并到主分支即部署 |
| **稳定性** | 经过 7 天测试 | 最新代码，浸泡时间较短 |
| **Community 计划限制** | 10 GB 仓库，500 次/月颁发，2 台机器 | 20 GB 仓库，1,000 次/月颁发，4 台机器 |
| **付费计划** | 可用（Professional、Business、Enterprise） | 不可用 |
| **账户** | 独立 | 独立（与 Stable 分离） |
| **适合场景** | 生产环境、付费工作负载 | 测试、评估、个人项目、抢先体验 |

## Edge 翻倍限制

使用 Community 计划的 Edge 用户可免费获得翻倍的资源限制：

| 资源 | Stable Community | Edge Community |
|---|---|---|
| 仓库大小 | 10 GB | 20 GB |
| 每月许可证颁发次数 | 500 | 1,000 |
| 机器激活数 | 2 | 4 |

如需更高的限制或付费计划功能，请在 Stable 通道创建账户并在那里升级。

## 独立账户

Edge 和 Stable 运行在独立的基础设施和独立的数据库上。在 Edge 创建的账户在 Stable 上不存在，反之亦然。通道之间没有迁移路径。如果您从 Edge 开始使用，后续需要付费计划，则需要在 Stable 上重新创建账户。

## 推广流程

1. 每次合并到主分支后，立即部署到 Edge。
2. 经过 7 天无问题后，Edge 自动推广到 Stable。
3. 紧急热修复可同时推送到两个通道。

这意味着 Stable 最多落后 Edge 7 天。浸泡期可在回归从 Edge 传播到 Stable 之前将其捕获。

## 如何选择通道？

**选择 Stable，如果：**
- 您偏好具有 7 天浸泡窗口的保守升级节奏
- 您需要付费计划（Professional、Business、Enterprise）
- 您更注重最高稳定性而非最新功能

**选择 Edge，如果：**
- 您希望提前试用新功能
- 您正在评估该平台
- 您希望为个人项目获得更慷慨的免费限制
- 您能接受更新的、测试时间较短的代码

## 安装

有关从任一通道安装的命令，包括包管理器配置和 Docker 标签，请参阅 [安装](/zh/docs/installation)。

## CLI 通道管理

CLI 自动使用安装或登录时配置的通道。切换通道的方法：

```bash
rdc update --channel edge      # 切换到 Edge
rdc update --channel stable    # 切换到 Stable
```

运行 `rdc subscription login` 并选择 Edge 区域时，CLI 会自动配置 Edge 更新通道，无需手动添加 `--channel` 标志。
