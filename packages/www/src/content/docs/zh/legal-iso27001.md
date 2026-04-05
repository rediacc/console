---
title: "ISO 27001 合规"
description: "Rediacc 如何满足 ISO 27001 加密、访问管理和运营安全的信息安全控制要求。"
category: "Legal"
order: 5
language: zh
sourceHash: "fdea800f46a7d3ec"
---

ISO/IEC 27001 是由国际标准化组织 (ISO) 和国际电工委员会 (IEC) 发布的信息安全管理体系 (ISMS) 国际标准。当前版本为 ISO/IEC 27001:2022。

参考: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc 是 ISMS 中技术控制层的一个组成部分。下表将 Rediacc 的功能映射到相关的附录 A 控制域。

## 附录 A 控制映射

| 控制域 | 控制 | Rediacc 功能 |
|--------|------|-------------|
| **A.8**，资产管理 | A.8.1 资产清单 | 每个仓库是具有唯一 GUID 的独立可识别资产。`rdc machine query <machine> --repositories` 列出所有仓库及其大小、挂载状态和容器数量。 |
| **A.8**，资产管理 | A.8.24 加密使用 | 所有仓库强制使用 LUKS2 AES-256 加密。密钥管理：凭据仅存储在操作员的本地配置中，从不在服务器上。 |
| **A.9**，访问控制 | A.9.2 用户访问管理 | SSH 密钥认证。带 IP 绑定、团队范围限定和团队移除时自动撤销的 API 令牌。双因素认证 (TOTP)。 |
| **A.10**，加密 | A.10.1 加密控制 | 可配置密钥参数的 LUKS2。每仓库加密凭据。所有远程传输通过 SSH。配置存储实现零知识加密：HKDF 密钥派生的 AES-256-GCM、X25519 成员密钥交换和用于即时撤销的时间窗口 SDK 密钥。 |
| **A.12**，运营安全 | A.12.3 备份 | `rdc repo backup push/pull` 支持到多个目标（SSH、S3、B2、Azure、GDrive）的加密异地存储。CoW 快照实现时间点恢复。`rdc repo validate` 验证备份健康状况和仓库完整性。 |
| **A.12**，运营安全 | A.12.4 日志和监控 | 40 多种账户级事件类型（认证、API 令牌、配置、许可）。通过 `rdc machine query` 监控机器健康。容器状态和资源监控。 |
| **A.13**，通信安全 | A.13.1 网络安全管理 | 每仓库 Docker daemon 隔离。iptables 规则阻止跨仓库流量。每仓库环回 IP 子网（/26）。TLS 终端反向代理用于外部访问。 |
| **A.14**，系统开发 | A.14.2 开发安全 | 基于 Fork 的开发环境在不暴露生产数据的情况下提供生产环境对等。Rediaccfile 生命周期钩子支持克隆环境中的自动数据清理。 |

## 资产管理

Rediacc 的仓库模型自然支持资产清单要求：

- 每个仓库在创建时分配唯一的 GUID
- 仓库可按机器枚举（`rdc machine query --repositories`）
- 每个仓库的加密状态、挂载状态、容器数量和磁盘使用量可见
- Fork 关系跟踪克隆环境的谱系

## 变更管理

fork-test-promote 工作流程符合 ISO 27001 的变更管理要求：

1. **Fork**：创建生产环境的隔离副本
2. **测试**：在 Fork 上应用和验证更改
3. **提升**：使用 `rdc repo takeover` 将 Fork 切换到生产环境
4. **审计**：所有操作均记录时间戳和执行者标识

## 持续改进

- 审计日志导出支持定期安全审查
- 机器健康检查（`rdc machine query --system`）支持运营监控
- `rdc repo validate` 在每次操作后验证备份健康状况
