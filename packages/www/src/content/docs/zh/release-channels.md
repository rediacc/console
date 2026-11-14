---
title: "发布通道"
description: "Edge 与 Stable 的区别，以及该运行哪个通道。"
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: zh
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc 通过两个通道发布 CLI 更新：**Stable** 和 **Edge**。两个通道连接的是同一个产品，因此账户、计划和限制在两者上完全一致。区别只在于新版本多快到达您手上。

## Stable 通道

Stable 是默认通道。版本只有在 Edge 上经过 7 天无报告问题的浸泡期后，才会到达 Stable。

- 当您偏好保守的升级节奏时推荐
- 在 Edge 上测试 7 天后部署
- 紧急热修复可直接推送

## Edge 通道

Edge 在每次变更合并到主分支的瞬间就会接收到，是软件的实时版本，持续部署。

- 每次合并到主分支即发布
- 账户、计划和限制与 Stable 相同
- 适合尽早体验新功能

## 一个产品，两个通道

无论使用哪个通道，您的账户都位于所选数据区域的 `eu.rediacc.cloud`、`us.rediacc.cloud` 或 `asia.rediacc.cloud` 上。切换通道不会影响账户、数据或订阅。区域详情请参阅[数据区域](/zh/docs/data-regions)。

## 对比

| | Stable | Edge |
|---|---|---|
| **部署节奏** | 经过 7 天浸泡期后部署 | 每次合并到主分支即部署 |
| **稳定性** | 经过 7 天测试 | 最新代码，浸泡时间较短 |
| **计划与限制** | 相同 | 相同 |
| **账户与数据** | 共用 | 共用 |
| **适合** | 生产环境、付费工作负载 | 抢先体验、评估 |

## 推广流程

1. 每次合并到主分支后，立即部署到 Edge。
2. 经过 7 天无问题后，Edge 自动推广到 Stable。
3. 紧急热修复可同时推送到两个通道。

因此 Stable 最多落后 Edge 7 天。浸泡窗口会在回归到达 Stable 之前就在 Edge 上捕获它。

## 如何选择通道？

**选择 Stable，如果：**
- 您偏好具有 7 天浸泡窗口的保守升级节奏
- 您更注重最高稳定性而非最新功能

**选择 Edge，如果：**
- 您希望提前试用新功能
- 您正在评估该平台
- 您能接受更新的、测试时间较短的代码

## 安装

有关各通道的安装命令、包管理器配置和 Docker 标签，请参阅 [安装](/zh/docs/installation)。

## CLI 通道管理

CLI 使用安装时配置的通道。切换方法：

```bash
rdc update --channel edge      # 切换到 Edge
rdc update --channel stable    # 切换到 Stable
```
