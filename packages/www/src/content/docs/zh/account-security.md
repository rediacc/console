---
title: 账户安全与API
description: 身份验证、API令牌、会话管理和权限模型。
category: Guides
order: 13
language: zh
sourceHash: "009d0d8033c591a3"
sourceCommit: "dabe1a33844b3b7ec8a2c4ab44dc2de6683283c9"
---

### 身份验证

Rediacc支持多种身份验证方法：

![Auth Flow](/img/account-auth-flow.svg)

- **密码**：传统的电子邮件加密码登录
- **Magic Link**：通过电子邮件链接进行无密码登录（15分钟过期）
- **双因素认证（2FA）**：基于TOTP，附带备用码

启用2FA后，登录需要密码（或Magic Link）和6位TOTP码。

### API令牌

API令牌用于验证机器间操作（CLI许可证激活、状态检查）。

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**作用域：**
- `license:read` -- 查询订阅和许可证状态
- `license:activate` -- 激活机器并颁发仓库许可证
- `subscription:read` -- 读取订阅详情

**安全功能：**
- IP绑定：首次请求将令牌锁定到该IP地址
- 团队范围限定：令牌可限制为特定团队
- 自动撤销：当创建者从组织中被移除时，令牌会被撤销

创建令牌：
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### 设备码流程

CLI可以使用设备码流程在无界面机器上进行身份验证：

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

有关加密的服务器同步配置，请参阅[Config Storage](/en/docs/config-storage)完整指南。Config Storage使用：
- 零知识加密（服务器永远看不到明文）
- 基于Passkey的密钥派生（WebAuthn + PRF）
- 按请求轮换的轮换令牌

### 会话安全

| 令牌类型 | 有效期 | 存储 | 刷新 |
|----------|--------|------|------|
| Access Token (JWT) | 15分钟 | HttpOnly cookie | 通过refresh token自动刷新 |
| Refresh Token | 7天 | HttpOnly cookie | 每次使用时轮换 |
| Elevated Session | 10分钟 | 服务器端 | 通过重新认证触发 |

敏感操作需要提升会话：密码更改、电子邮件更改、2FA设置、所有权转让和管理员破坏性操作。

### 权限模型

Rediacc使用三个独立的权限层：

![Permission Flow](/img/account-permission-flow.svg)

**第1层：系统角色** -- 决定对系统管理端点的访问权限。

**第2层：组织角色** -- 控制用户在其组织内可以执行的操作（owner、admin、member）。

**第3层：团队角色** -- 将访问范围限定为特定团队资源（team_admin、member）。组织所有者和管理员可绕过团队角色检查。

每个API请求按顺序通过所有适用的层。对团队范围端点的请求必须满足会话认证、组织成员资格和团队访问权限。

### 更新渠道

CLI支持两个发布渠道：
- **stable**（默认）：经过 7 天浸泡期后从 edge 升级而来；若偏好保守的升级节奏请选择此通道
- **edge**：最新功能，每次发布时更新

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
