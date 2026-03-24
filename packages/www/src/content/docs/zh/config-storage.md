---
title: "Config Storage (Rediacc Provider)"
description: "使用零知识加密在设备和团队之间安全同步CLI配置。"
category: "Guides"
order: 9
language: zh
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

Rediacc配置存储提供程序使用零知识加密在设备和团队之间同步您的CLI配置。您的SSH密钥、机器IP和凭据在离开您的机器之前在客户端加密 -- 即使Rediacc运营商也无法读取您的数据。

## 前提条件

- **支持PRF的Passkey提供程序**：FIDO2安全密钥（如YubiKey）、iCloud Keychain、Google Password Manager、1Password或Dashlane
- **已启用2FA** 组织所有者/管理员需要（设置存储和成员管理所需）
- **账户订阅** 已启用config storage

## 快速开始

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## 设置

### 桌面端（有浏览器）

```bash
rdc store add my-config --type rediacc
```

1. 浏览器窗口打开Rediacc账户门户
2. 注册一个passkey（YubiKey/iCloud Keychain/1Password弹窗）
3. Passkey的PRF扩展派生您的加密密钥
4. 密钥存储在操作系统的原生安全存储中（Keychain/keyctl/DPAPI）
5. 完成 -- 无需记住密码

### 无头服务器（无浏览器）

```bash
rdc store add my-config --type rediacc --headless
```

1. CLI显示带有设备代码的URL
2. 在手机或笔记本电脑上打开该URL
3. 在浏览器中完成passkey注册
4. CLI通过安全中继自动接收您的加密密钥
5. 零知识得以保持 -- 服务器仅中继不透明的加密blob

### 自定义服务器URL

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

设置完成后，push和pull无需任何密码或提示即可工作：

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

每个操作使用一次性自毁的轮换令牌。没有静态凭据。

## 团队管理

团队成员通过`/account/config-storage/members`的Web门户进行管理。

### 添加成员

1. 管理员打开config storage成员页面
2. 点击"Add Member"（需要2FA）
3. 管理员的浏览器为新成员加密团队加密密钥
4. 新成员登录并接受邀请
5. 双方现在可以push/pull相同的配置

### 移除成员

1. 管理员点击成员旁边的"Remove"（需要2FA）
2. 成员的加密密钥立即被删除
3. 在30秒内，成员将失去对加密配置的所有访问权限

无需密钥轮换 -- 服务器只是停止向被移除的成员提供解密密钥。

## 安全属性

| 属性 | 方式 |
|------|------|
| **零知识** | 客户端在发送前加密；服务器只能看到不透明的blob |
| **无主密码** | Passkey生物识别完全取代密码 |
| **分割密钥派生** | CEK需要passkey_secret（客户端）+ server_secret（服务器） |
| **轮换令牌** | 每次API调用生成新令牌；旧令牌失效 |
| **IP绑定** | 令牌在首次使用时绑定到客户端IP |
| **三重加密** | SDK（时间窗口）+ CEK（客户端）+ 组织口令（服务器） |
| **即时撤销** | 停止向被移除成员提供SDK；最大延迟30秒 |
| **篡改检测** | 对加密blob的HMAC；每次pull时验证 |

完整的安全架构请参阅[Security Guide](/docs/SECURITY-CONFIG-STORAGE.md)。

## 故障排除

### "Passkey must support PRF extension"

您的passkey提供程序不支持PRF扩展。请使用：
- FIDO2安全密钥（如YubiKey）
- iCloud Keychain（macOS/iOS上的Safari）
- Google Password Manager（Android/ChromeOS上的Chrome）
- 1Password
- Dashlane

### "Two-factor authentication required"

组织所有者和管理员必须在设置config storage之前启用2FA。前往Account Settings -> Security -> Enable 2FA。

### "Version conflict"

另一个团队成员推送了更新的版本。请先拉取：
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

令牌在24小时不活动后过期。运行任何命令以刷新：
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

加密密钥从操作系统的安全存储中丢失（Linux上重启、钥匙串重置）。重新运行设置：
```bash
rdc store add my-config --type rediacc
```
