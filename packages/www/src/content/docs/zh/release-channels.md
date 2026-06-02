---
title: "发布通道"
description: "Edge 与 Stable 的区别，以及该运行哪个通道。"
category: "Concepts"
order: 2
language: zh
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc 通过两个通道发布更新：**Stable** 和 **Edge**。两者运行在独立的基础设施上，各有不同的权衡。

## Stable 通道

Stable 是默认通道。版本只有在 Edge 上经过 7 天无报告问题的浸泡期后，才会到达 Stable。

- 当您偏好保守的升级节奏并希望使用付费计划时推荐
- 在 Edge 上测试 7 天后部署
- 紧急热修复可直接推送
- 域名：`eu.rediacc.com`、`us.rediacc.com`、`asia.rediacc.com`

## Edge 通道

Edge 在每次变更合并到主分支的瞬间就会接收到，是软件的实时版本，持续部署。

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

在 Community 计划上使用 Edge，资源限制翻倍，无需额外费用：

| 资源 | Stable Community | Edge Community |
|---|---|---|
| 仓库大小 | 10 GB | 20 GB |
| 每月许可证颁发次数 | 500 | 1,000 |
| 机器激活数 | 2 | 4 |

需要更高限制或付费功能？在 Stable 上创建账户并在那里升级。

## 独立账户

Edge 和 Stable 运行在独立的基础设施和独立的数据库上。一个通道上的账户在另一个通道上不存在，且没有迁移路径。如果从 Edge 开始，后来决定需要付费计划，你将从头在 Stable 上创建全新账户。

## 推广流程

1. 每次合并到主分支后，立即部署到 Edge。
2. 经过 7 天无问题后，Edge 自动推广到 Stable。
3. 紧急热修复可同时推送到两个通道。

因此 Stable 最多落后 Edge 7 天。浸泡窗口会在回归到达 Stable 之前就在 Edge 上捕获它。

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

有关各通道的安装命令、包管理器配置和 Docker 标签，请参阅 [安装](/zh/docs/installation)。

## CLI 通道管理

CLI 使用安装或登录时配置的通道。切换方法：

```bash
rdc update --channel edge      # 切换到 Edge
rdc update --channel stable    # 切换到 Stable
```

运行 `rdc subscription login` 并选择 Edge 区域时，CLI 会自动为你设置 Edge 更新通道，无需 `--channel` 标志。
