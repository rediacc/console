---
title: "HIPAA 合规"
description: "Rediacc 的加密和隔离架构如何满足 HIPAA 保护医疗信息的保障措施要求。"
category: "Legal"
order: 3
language: zh
sourceHash: "13bf006e6e3d481f"
---

《健康保险流通与责任法案》(HIPAA) 是一部美国联邦法律，为保护敏感的患者健康信息 (PHI) 制定了标准。它适用于受覆盖实体（医疗保健提供者、健康计划、医疗信息交换所）及其业务伙伴。

全文: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## 保障措施映射

HIPAA 要求管理、技术和物理保障措施。下表将其映射到 Rediacc 的功能。

### 技术保障措施

| 要求 | HIPAA 参考 | Rediacc 功能 |
|------|----------|-------------|
| 访问控制 | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | SSH 密钥认证。带 IP 绑定和范围限制的 API 令牌。每仓库 Docker daemon 隔离防止跨仓库访问。 |
| 审计控制 | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | 40 多种账户级事件类型，涵盖身份验证、API 令牌、配置操作和许可。按用户和团队追踪。通过管理面板或 `rdc audit` CLI 导出。 |
| 完整性控制 | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | CoW 快照在修改前保存原始数据。`rdc repo validate` 验证仓库完整性和备份健康状况（LUKS 容器、文件系统一致性、配置）。 |
| 静态加密 | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | 所有仓库卷使用 LUKS2 AES-256 加密。凭据仅存储在操作员的本地配置中，从不在服务器上。配置存储使用分割密钥派生的零知识 AES-256-GCM 加密。即使服务器也无法解密存储的配置。 |
| 传输安全 | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | 所有远程操作使用 SSH。备份传输端到端加密。无未加密的数据传输。 |

### 管理保障措施

| 要求 | Rediacc 功能 |
|------|-------------|
| 员工访问管理 | 范围限定权限的 API 令牌。基于团队的访问控制。从团队移除时自动撤销令牌。 |
| 安全事件程序 | 审计日志提供所有操作的取证线索。每仓库隔离限制影响范围。 |
| 应急计划 | `rdc repo backup push/pull` 支持多目标加密备份。CoW 快照实现即时恢复。 |

### 物理保障措施

| 要求 | Rediacc 功能 |
|------|-------------|
| 设施访问控制 | 自托管：您的组织控制服务器的物理安全。核心操作不依赖第三方数据中心。 |
| 工作站安全 | LUKS 加密所有静态数据。未挂载的仓库是磁盘上的加密 blob，没有操作员凭据无法读取。 |

## 业务伙伴协议 (BAA)

由于 Rediacc 是在您基础设施上运行的自托管软件，它不通过 Rediacc（公司）的系统处理、存储或传输 PHI。典型的 BAA 要求适用于您的基础设施提供商（云提供商或托管设施），而非 Rediacc。

Rediacc 作为服务器上的软件工具运行，类似于操作系统或数据库引擎。它无权访问您的数据。可选的配置存储通过 Rediacc 的服务器同步加密 blob，但其零知识设计意味着服务器无法解密内容。它只存储不透明的密文。

## 包含 PHI 的开发环境

为开发目的克隆包含 PHI 的生产环境时，使用 Rediaccfile 的 `up()` 生命周期钩子运行清理脚本：

- 从数据库表中去除 PHI
- 将患者标识符替换为合成数据
- 移除会话令牌和 API 密钥

开发人员获得具有脱敏数据的类生产基础设施，满足 HIPAA 的最小必要标准。
