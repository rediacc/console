---
title: "PCI DSS 合规"
description: "Rediacc 如何满足 PCI DSS 要求：不可变备份、自动网络隔离和基础设施级别的访问控制。"
category: "Legal"
order: 6
language: zh
sourceHash: "d8391036876231a0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

简单来说，如果你处理持卡人数据，PCI DSS v4.0.1 不是可选的。PCI DSS v4.0.1 的核心就是一个要求：基础设施级别的隔离。

参考: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## 要求映射

| PCI DSS 要求 | 描述 | Rediacc 功能 |
|-------------|------|-------------|
| **要求 1**，网络安全控制 | 安装和维护网络安全控制 | 每仓库 iptables 规则阻止所有跨仓库流量。每个仓库获得自己的环回 IP 子网（/26）。 |
| **要求 2**，安全配置 | 对所有系统组件应用安全配置 | Rediaccfile 生命周期钩子强制执行确定性、可重现的配置。无默认凭据。LUKS 密钥由操作员生成。 |
| **要求 3**，保护存储的账户数据 | 用加密保护存储的账户数据 | 所有仓库卷上的 LUKS2 AES-256 加密。加密是强制性的，不是可选的。通过 LUKS 密钥销毁进行加密擦除。 |
| **要求 4**，保护传输中的数据 | 在传输过程中使用强加密保护持卡人数据 | 所有远程操作通过 SSH。备份传输端到端加密。无未加密的数据路径。 |
| **要求 6**，安全开发 | 开发和维护安全的系统和软件 | CoW 克隆创建隔离的测试环境，不将生产持卡人数据暴露给开发网络。fork-test-promote 工作流程。 |
| **要求 7**，限制访问 | 按业务需要限制对系统组件和持卡人数据的访问 | 每仓库 Docker daemon 套接字。访问一个仓库不授予对另一个的访问。SSH 密钥认证。 |
| **要求 8**，识别用户和认证 | 识别用户并认证对系统组件的访问 | SSH 密钥认证。带 IP 绑定和范围限定权限的 API 令牌。双因素认证 (TOTP)。 |
| **要求 9**，限制物理访问 | 限制对持卡人数据的物理访问 | 自托管：物理安全在您的直接控制之下。LUKS 加密使被盗驱动器不可读。 |
| **要求 10**，日志和监控 | 记录和监控对系统组件和持卡人数据的所有访问 | 70 多种事件类型（认证、API 令牌、配置、许可、机器操作）。支持按用户、团队、类型和日期过滤的管理面板和门户。`rdc audit` CLI 进行程序化导出。机器操作也记录在系统日志中以实现深度防御。 |
| **要求 12**，组织政策 | 用组织政策和计划支持信息安全 | 自托管消除了第三方处理者范围（要求 12.8）。缩小 PCI DSS 合规边界。 |

## 网络分段

PCI DSS 在网络分段方面要求很高。我经常看到团队试图在隔离不足的基础上堆叠 iptables 规则。这是行不通的。通过审计的团队是将分段构建到架构中。Rediacc 默认为您提供这种分段：

- 每个仓库在 `/var/run/rediacc/docker-<networkId>.sock` 中运行自己的 Docker daemon
- 仓库具有隔离的环回 IP 子网（127.0.x.x/26，每个网络 61 个可用 IP）
- renet 强制执行的 iptables 规则阻止所有跨 daemon 流量
- 不同仓库的容器无法在网络层面通信

支付处理仓库运行在自己的 Docker daemon 和自己的回环子网上，与同一机器上的所有其他应用程序在网络层面隔离。无需编写额外的防火墙规则。

## 范围缩减

自托管 Rediacc 缩小了 PCI DSS 合规范围。您无需手动配置网络分段，它在设计中是自动的。这部分的文档仍需改进，但隔离是可靠的。

- 持卡人数据流中无第三方云提供商
- 无需根据要求 12.8 评估的 SaaS 供应商（第三方服务提供商）
- 物理安全控制在您的直接管理之下
- 加密密钥仅存储在操作员的本地配置中

## 执法案例

大多数 PCI 审计失败归结为两点之一：从未正确隔离的分段，或从未针对真实攻击测试的加密。

- Heartland Payment Systems（2008年）：由于网络分段不佳，攻击者横向移动穿越 48 个数据库，暴露了 1.3 亿张卡号。[总成本超过 2 亿美元。](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target（2013年）：由于扁平网络架构，攻击者从 HVAC 供应商的网络访问转向销售点系统，获取了 4000 万张支付卡。[与 47 位州总检察长达成 1850 万美元和解。](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
