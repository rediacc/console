---
title: "合规的实际要求"
description: "Rediacc 在您的基础设施上运行。您控制您的数据。以下介绍其如何与主要合规框架保持一致。"
category: "Legal"
order: 0
language: zh
sourceHash: "e6044a3b067b54d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc 完全在您的基础设施上运行。在克隆、备份和部署期间，您的数据保留在您的机器上。您既是数据控制者，也是数据处理者。无第三方 SaaS，无外部访问。

我们将 Rediacc 的技术能力映射到主要合规框架的要求。每个页面都阐述一项特定法规，并提供对官方法律文本的参考。

## 合规矩阵

| 框架 | 范围 | Rediacc 关键能力 |
|------|------|------------------|
| [GDPR](/zh/docs/legal-gdpr) | 欧盟数据保护和隐私 | 同一机器上的 CoW 克隆、LUKS2 加密、零知识配置存储、审计日志、通过 `rdc repo delete` 实现删除权 |
| [SOC 2](/zh/docs/legal-soc2) | 服务组织的信任服务标准 | 静态加密、零知识配置同步、网络隔离、审计追踪、备份和恢复 |
| [HIPAA](/zh/docs/legal-hipaa) | 美国医疗信息保护 | LUKS2 加密、零知识配置存储、仅 SSH 访问、隔离的 Docker daemon、传输安全 |
| [CCPA](/zh/docs/legal-ccpa) | 加州消费者隐私权 | 自托管（无数据出售/共享）、零知识加密、加密删除、按仓库的数据清单 |
| [ISO 27001](/zh/docs/legal-iso27001) | 信息安全管理控制 | 资产管理、加密控制、零知识配置存储、访问控制、运营安全 |
| [PCI DSS](/zh/docs/legal-pci-dss) | 支付卡数据保护 | 架构级网络分段、强制加密、审计日志、通过自托管缩小范围 |
| [NIS2 和 DORA](/zh/docs/legal-nis2-dora) | 欧盟网络安全和金融韧性 | 消除供应链风险、通过 CoW 克隆进行韧性测试、加密、事件检测 |
| [数据主权](/zh/docs/legal-data-sovereignty) | 全球数据驻留法（PIPL、LGPD、KVKK、PIPA 等） | 自托管 = 数据永远不会离开您的管辖区。无跨境传输，无充分性评估 |

## 架构基础

本节中所有合规框架都映射回相同的技术基础。

- **静态加密**：每个仓库均使用 LUKS2 AES-256 加密。凭据仅存储在操作员的本地配置中，从不在服务器上。
- **网络隔离**：每个仓库拥有自己的 Docker daemon、环回 IP 子网（/26）和 iptables 规则。不同仓库的容器无法相互通信。
- **写时复制克隆**：`rdc repo fork` 使用文件系统 reflink（`cp --reflink=always`）。数据在同一机器上复制，无需任何网络传输。
- **审计日志**：70 多种事件类型，涵盖身份验证（登录、2FA、密码更改、会话撤销）、API 令牌生命周期、配置存储操作、订阅/许可活动以及 CLI 机器操作（仓库生命周期、备份、同步、终端会话）。可通过管理仪表板和门户活动页面访问（带组织范围筛选和 JSON 导出）。机器操作也记录在您的系统日志中，以实现纵深防御。
- **加密备份**：`rdc repo push/pull` 通过 SSH 传输数据。备份目标接收 LUKS 加密的卷。
- **零知识配置存储**：可选的跨设备加密配置同步。配置在上传前在客户端使用 AES-256-GCM 加密。服务器仅存储不透明的 blob。服务器无法读取 SSH 密钥、凭据、IP 地址或任何明文配置数据。密钥派生使用 passkey PRF extension + HKDF 并进行域分离。成员访问通过 X25519 密钥交换管理，撤销即时生效。

有关这些功能的详细信息，请参阅[架构](/zh/docs/architecture)、[仓库](/zh/docs/repositories)、[配置存储](/zh/docs/config-storage)和[账户安全](/zh/docs/account-security)。

## 为什么重要

合规失败的代价非常高昂。以下案例展示了 Rediacc 的架构在结构上可以防止的问题：

| 事件 | 罚款 | 问题所在 |
|------|------|---------|
| [Meta：欧盟-美国数据传输](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 12 亿欧元 | 个人数据在没有充分保障的情况下跨境传输。自托管意味着没有传输。 |
| [Equifax：未加密数据](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 7 亿美元 | 1.47 亿条记录在网络分段不佳的情况下未加密存储。LUKS2 是强制性的，不是可选的。 |
| [Target：横向移动](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 1850 万美元 | 攻击者通过扁平网络从 HVAC 供应商转向支付系统。按仓库隔离可防止此类情况。 |
| [Anthem：未加密的 PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 1600 万美元 | 7900 万条健康记录未加密存储。LUKS2 AES-256 始终开启。 |
| [Blackbaud：SaaS 连锁泄露](https://www.sec.gov/newsroom/press-releases/2023-48) | 4950 万美元 | 一家 SaaS 供应商遭勒索软件攻击，导致 13,000 多个客户组织的数据泄露。自托管意味着供应商泄露无法触及您的数据。 |
| [British Airways：分段不佳](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 2000 万英镑 | 攻击者因网络控制不足注入恶意代码。隔离的 Docker daemon 和 iptables 防止横向访问。 |
| [Google：删除权](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 5000 万欧元 | 难以在分布式系统中完全删除数据。通过 LUKS 销毁进行的加密擦除即时且彻底。 |

## 重要提示

这些页面说明了 Rediacc 的架构如何与合规要求保持一致。但现实是这样的：合规涉及的范围远超软件。您需要制定政策、流程、培训，并可能需要第三方审计。Rediacc 处理基础设施部分。请与您的法律和合规团队讨论其余事项。
