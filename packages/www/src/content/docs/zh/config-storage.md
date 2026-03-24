---
title: 配置存储
description: 基于通行密钥加密的零知识加密配置同步
category: Guides
order: 8
language: zh
sourceHash: "d20655e3e306b85b"
---

# 配置存储

配置存储提供跨设备的零知识加密CLI配置同步。您的配置使用从通行密钥派生的密钥进行加密 — 服务器永远无法看到明文数据。

## 先决条件

- **双因素认证**已在您的账户上启用
- **支持PRF的通行密钥提供商**: FIDO2安全密钥（如YubiKey）、iCloud Keychain、Google Password Manager、1Password或Dashlane
- **浏览器**: Chrome 133+、Edge 133+、Firefox 130+或Safari 17+

## 设置

1. 在侧边栏导航至**配置存储**，然后点击**设置配置存储**
2. 需求检查表验证您的浏览器、双因素认证和会话状态
3. 点击**开始设置** — 您需要触摸安全密钥两次：
   - 第一次触摸：注册通行密钥
   - 第二次触摸：通过PRF派生加密密钥
4. 设置完成 — 您的通行密钥密钥存储在操作系统的密钥环中

设置完成后，日常CLI操作（push/pull）无需通行密钥即可工作。

## PRF提供商兼容性

| 提供商 | PRF支持 | 平台 |
|----------|:-----------:|-----------|
| YubiKey / FIDO2安全密钥 | ✅ | Windows 11、macOS、Linux |
| iCloud Keychain | ✅ | macOS 15+、iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android、iOS |
| Dashlane | ✅ | 跨平台 |
| Bitwarden扩展 | ❌ | 开发中 |
| Windows Hello | ❌ | 不支持 |

## 成员管理

配置存储按组织划定范围。成员通过Web门户管理：

- **查看成员**：配置存储 → 成员
- **添加成员**：目前仅通过CLI（Web界面计划中）
- **移除成员**：点击成员页面上的移除按钮（需要双因素认证 + 重新认证）

安全保护措施防止移除最后一个活跃成员或移除自己。

## 安全性

- **零知识**：服务器存储其无法解密的三重加密数据
- **分割密钥**：解密需要您的通行密钥密钥（客户端）和服务器密钥（服务器）
- **轮换令牌**：每次API调用使用新令牌；旧令牌自动销毁
- **IP绑定**：令牌在首次使用时绑定到您的IP
- **即时撤销**：被移除的成员在30秒内失去访问权限

## 故障排除

| 错误 | 原因 | 修复方法 |
|-------|-------|-----|
| PRF not supported | 认证器缺少PRF扩展 | 使用YubiKey、iCloud Keychain、1Password或Dashlane |
| X25519 not supported | 浏览器版本过旧 | 更新至Chrome 133+、Edge 133+、Firefox 130+或Safari 17+ |
| Already configured | 您的组织已存在存储 | 访问/account/config-storage进行管理 |
| Config storage not configured | 服务器缺少blob存储 | 联系管理员配置R2/RustFS |
| Token expired | 24小时无活动 | 运行任意配置存储命令以刷新 |
| Cannot remove last member | 将永久锁定存储 | 先添加另一个成员 |
