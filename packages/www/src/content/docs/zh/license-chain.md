---
title: "许可证链与委托"
description: "可验证防篡改的许可证颁发、本地部署的委托签名以及分叉检测。"
category: "Guides"
order: 8
language: zh
sourceHash: "9b062d6866c1ccb4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 许可证链与委托

Rediacc 为许可证颁发使用可验证防篡改的哈希链，并为本地部署采用委托证书模型。本文介绍该系统如何防范篡改、重放攻击和许可证共享。

## 为什么需要证明链？

账户服务器颁发的每一张许可证都记录在一个只追加的账本中。每个条目通过 SHA-256 哈希链接到前一个条目，形成一条链。该链具有三个使篡改可被检测的特性：

1. **序列号**在每个订阅中是全局单调递增的。跳过或重排条目会破坏链。
2. **链哈希**将每个条目绑定到所有前序条目。修改任何历史条目会使其后所有条目失效。
3. **Renet 存储每个订阅所见的最高序列号**。回滚序列号的服务器会被立即检测到。

## 许可证颁发流程

CLI 请求机器激活或仓库许可证时，账户服务器会：

1. 读取该订阅当前的链头（最后的序列号和哈希）。
2. 构建包含下一个序列号和前一链哈希的许可证载荷。
3. 使用 Ed25519 对载荷进行签名。
4. 计算 `chainHash = SHA256(prevChainHash + ":" + signedPayload)`。
5. 原子性地将条目追加到颁发账本中。若两个并发请求在同一序列号上冲突，失败方重新获取下一个序列号并重新签名。
6. 将带有链哈希的已签名 blob 返回给 CLI。

`sequence` 和 `prevChainHash` 包含在已签名的载荷中（因此无法在不使签名失效的情况下修改）。`chainHash` 在信封上（签名后计算，以避免循环依赖）。

## Renet 的验证方式

每台运行 Renet 的机器在 `{licenseDir}/chain-state.json` 中存储其最后已知的链状态。每次验证许可证时，Renet 会执行以下检查：

| 检查项 | 失败意味着 |
|---|---|
| Ed25519 签名有效 | 许可证被伪造或篡改 |
| `sequence > lastKnownSequence` | 服务器回滚了链（重放攻击） |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | 链条目被修改 |
| `issuedAt >= lastKnownIssuedAt` | 时钟操纵（服务器时钟被回拨） |

任何检查失败时，许可证将被拒绝，并报告失败原因。

## 委托证书（本地部署）

对于离网或自托管部署，上游账户服务器颁发**委托证书**，授权本地部署服务器使用其自身的 Ed25519 密钥签名许可证。证书约束了本地部署服务器的操作范围。

### 证书结构

委托证书包含：

- `subscriptionId` - 该证书适用的订阅
- `planCode`、`maxMachines`、`maxRepositorySizeGb`、`maxRepoLicenseIssuancesPerMonth` - 内置的计划限制
- `maxTotalIssuances` - 链序列号的上限
- `delegatedPublicKey` - 本地部署服务器的 Ed25519 公钥（SPKI base64）
- `genesisHash` - 链的起始点（从前一个证书继续，或为"genesis"）
- `genesisSequence` - 颁发时的链序列号。用于 `/onprem/cert-upload` 在传输期间链已推进的情况下验证新证书链接到本地颁发账本的已知条目。向后兼容时为可选项（缺失时视为 0）
- `validFrom`、`validUntil` - 有效期窗口（受以下有效期策略约束）
- 由上游主 Ed25519 密钥签名

### 委托工作原理

1. 企业管理员在本地部署服务器上生成 Ed25519 密钥对。
2. 管理员从上游申请委托证书：
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. 上游使用主密钥对证书进行签名并返回。
4. 本地部署服务器存储证书及私钥，准备好签名许可证。
5. CLI 向本地部署服务器请求许可证时，服务器使用委托密钥签名，并包含对证书的引用。
6. Renet 执行**两级验证**：
   - 根据内置的上游主密钥验证证书签名。
   - 根据证书中的委托密钥验证 blob 签名。
   - 检查 `blob.sequence <= cert.maxTotalIssuances`。
   - 应用所有标准链检查。

本地部署服务器无法：
- 在委托证书计划限制之外伪造许可证（renet 会拒绝）。
- 颁发超过 `maxTotalIssuances` 的总操作数（renet 拒绝序列号溢出）。
- 修改证书（上游签名会失效）。

## 有效期策略

委托证书的有效期窗口由共享策略辅助函数（`computeDelegationCertValidity()`）计算，该函数同时运行在上游后端和客户门户前端。相同的输入始终产生相同的 `validUntil`，因此客户可以在提交前在创建对话框中预览有效的有效期。

### 各计划默认值和上限

| 计划 | 默认有效期 | 计划上限 |
|---|---|---|
| COMMUNITY | 15 天 | 30 天 |
| PROFESSIONAL | 60 天 | 120 天 |
| BUSINESS | 90 天 | 180 天 |
| ENTERPRISE | 120 天 | 365 天 |

默认值是调用方省略 `validDays` 时创建端点采用的值。上限是调用方可请求的最大值。

### 每订阅自定义覆盖

管理员可以通过管理员订阅详情页面为特定订阅设置自定义 `delegationCertDefaultDays` 值。**该覆盖会替换该订阅的默认值和上限两者**，是针对特殊客户的应急出口（例如需要在 COMMUNITY 计划上使用 200 天证书的企业合同）。Zod 模式仍然强制执行绝对 `1..365` 范围。

### 硬性上限：订阅结束时间加 3 天宽限期

无论计划上限和覆盖如何，每个证书都被硬性限制在 `subscription.expiresAt + 3 天`（现有的 `SUBSCRIPTION_CONFIG.gracePeriodDays`）。这意味着：

- 对于永久订阅（`expiresAt = null`），不应用到期上限，仅受计划上限约束。
- 对于 Stripe 按月计费的订阅，上限大约是下一个账单日期加 3 天。当 Stripe 每月将 `expiresAt` 向前滚动时，上限随之移动。
- 对于试用订阅，上限是试用结束时间加 3 天。

### 有效天数与原因

每次创建/续期响应都包含 `effectiveDays` 和 `reason`，便于调用方了解证书获得该有效期的原因：

| 原因 | 含义 |
|---|---|
| `plan_default` | 无请求，无覆盖，使用计划默认值 |
| `subscription_override` | 无请求，使用每订阅覆盖作为默认值 |
| `requested` | 调用方请求在所有上限范围内被满足 |
| `plan_max_clamp` | 调用方请求超出计划上限，被向下截断 |
| `override_max_clamp` | 调用方请求超出每订阅覆盖，被向下截断 |
| `subscription_cap_clamp` | 否则有效的目标会超过订阅的 `expiresAt + 3 天` |

客户门户创建对话框使用这些原因呈现实时预览（"您将收到一个 18 天的证书。截断原因：证书不能超过您的订阅结束日期 3 天以上。"），避免客户盲目提交。

### 自适应续期阈值

本地部署自动续期循环使用模仿 Let's Encrypt 的自适应阈值：

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

15 天的 COMMUNITY 证书在剩余 5 天时续期。90 天的 BUSINESS 证书在剩余 14 天时续期（环境配置上限生效）。120 天的 ENTERPRISE 证书在剩余 14 天时续期。这防止短期证书立即触发续期，同时为长期证书提供足够的缓冲。

## 单一有效性约束

一个订阅在同一时间内**最多只能有一个有效的委托证书**（`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`）。

### 为什么只允许一个？

每个本地部署实例针对其本地颁发账本独立执行 `maxRepoLicenseIssuancesPerMonth`、`maxActivations` 和链完整性。本地部署不向上游同步使用量。这正是离线可用委托的核心设计。

如果一个订阅有多个有效证书（每个实例一个），每个实例将独立执行限制：

- 一个 500 次/月的订阅配备 3 个有效证书，实际上允许每月 **1,500 次**颁发。
- 三条并行链，各自锚定到 genesis，无法进行任何审计对账。

上游无法检测到这种绕过，因为本地部署被设计为离线运行。**单一有效性是唯一可执行的模型。** 需要多环境（生产、预发布、灾备）的客户必须为每个实例单独购买订阅。

### 冲突行为

`POST /admin/delegation-certs` 和 `POST /portal/delegation-certs` 对第二次创建请求返回以下拒绝响应：

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

客户门户通过专用对话框呈现此情况，说明后果：

- **续期（推荐）** - 延伸现有链。所有先前颁发的仓库许可证继续有效。
- **撤销并重建** - 丢弃现有链，从 genesis 重新开始。一旦旧证书的 `validUntil` 过期，先前颁发的仓库许可证将无法验证。仅在迁移到使用不同签名密钥的新本地部署实例，或从已泄露密钥中恢复时使用。

`renew()` 是保留单一有效性的原子交换，**不受** 409 冲突检查约束。

### 速率限制

即使有单一有效性约束，恶意调用方仍可循环 `revoke -> create -> revoke -> create` 以消耗上游主密钥签名周期。两个创建端点均通过现有 `rateLimits` 表对每个订阅限制**每滚动 24 小时 10 次尝试**：

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

无论结果如何，每次尝试都会递增计数器（冲突垃圾循环同样受到限制）。

## 分叉检测

如果客户将委托证书共享给其他方（或从同一证书运行两个本地部署服务器），链将产生分叉。上游在续期时检测到此情况。

### 续期流程

1. 本地部署管理员调用 `POST /admin/delegation-certs/renew`，提供当前链头：
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. 上游将链条目与其自身账本记录进行比对。
3. 如果 `currentChainHash` 与上游在 `currentSequence` 处记录的链不匹配，则检测到分叉：
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. 新证书的 `genesisHash` 被设为当前链哈希，使具有旧链状态的机器可以从上次中断处继续。

如果证书被共享给非客户方：
- 他们可以在证书有效期内使用它。
- 首次续期时，上游只看到一条链（合法的那条）。
- 新证书的 `genesisHash` 仅匹配合法链。
- 使用共享链的机器将立即拒绝新许可证，因为其存储的 `chainHash` 无法连接到新证书的 `genesisHash`。

## 离网续期

对于无法通过 HTTPS 访问上游的本地部署实例，续期流程完全离线。有三个新端点用于闭环：

**在本地部署上（auth、root、requireElevated()）：**
- `GET /onprem/cert-current` - 下载当前已加载的已签名证书（备份、审计、重新导入）
- `GET /onprem/renewal-request` - 生成包含本地链头和委托公钥的已签名清单，由本地部署私钥签名

**在上游（管理员或组织范围的门户）：**
- `POST /admin/delegation-certs/process-renewal-request`（跨客户系统 root）
- `POST /portal/delegation-certs/process-renewal-request`（组织所有者/管理员）

### 续期请求清单

续期请求是一个小型 JSON 文档：

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

签名使用本地部署私钥对清单的规范编码（键按字母顺序排序，然后 `JSON.stringify`）进行计算。这确保无论对象构造顺序如何，双方都计算出相同的字节。

### 上游的验证流程

`processRenewalManifest()` 运行五项检查：

1. **存在有效证书**，对应清单的订阅。否则返回 `404 NO_ACTIVE_CERT`，客户应使用创建流程而非续期。
2. **委托公钥匹配**有效证书。否则返回 `400 DELEGATED_KEY_MISMATCH`，防止来自不同本地部署实例的重放。
3. **清单签名验证**通过有效证书的 `delegatedPublicKey`。否则返回 `400 MANIFEST_SIGNATURE_INVALID`，证明清单来自本地部署私钥的持有者。
4. **清单年龄**在 7 天以内（`RENEWAL_MANIFEST_MAX_AGE_MS`）。否则返回 `400 MANIFEST_EXPIRED`，防重放锚点。
5. **链哈希链接**在清单的 `currentSequence` 处与上游账本匹配。否则返回 `409 CHAIN_FORK_DETECTED`，防止分叉链。

所有检查通过后，`processRenewalManifest` 调用现有的 `renew()` 流程，原子性地使旧证书过期并插入新证书。**它不受创建端单一有效性 409 的约束**，因为这是原子交换，而非两步撤销加创建。

### 传输期间的序列推进

续期请求清单在生成时捕获链头。清单在传输途中（USB 传输、加密邮件），本地部署可能继续颁发仓库许可证，推进其本地链。

当新证书上传回本地部署时，`/onprem/cert-upload` 验证新证书的 `genesisSequence` 仍链接到本地颁发账本中的已知条目：

- 若 `cert.genesisSequence > localHead.sequence`，返回 `409 CHAIN_HEAD_BEHIND`（上游处于分叉链上）。
- 若 `cert.genesisSequence > 0` 且该序列处的本地账本条目的 `chainHash` 与 `cert.genesisHash` 不同，返回 `409 CHAIN_FORK_ON_UPLOAD`（本地链已与上游分叉）。
- 否则，证书被接受。后续颁发从 `localHead.sequence + 1` 继续。

这意味着**传输期间无需写入冻结**。链在两端自然延伸，与 X.509 证书续期处理在途序列号的方式相同。

## 定期审计

上游提供审计端点，可在不续期证书的情况下验证链完整性：

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

上游遍历条目并返回 `{ valid: true }` 或 `{ valid: false, divergedAtSequence: N, expected, actual }`。

本地部署服务器应定期调用此端点（默认：每周，通过 `UPSTREAM_AUDIT_URL` 环境变量配置）以尽早检测分叉。

### 机器端审计证明

Renet 可以使用 `VerifyAuditProof` 在本地验证链连续性。当机器在较长时间后续期许可证时，服务器可以返回中间链条目作为证明。机器遍历证明，验证每个 `chainHash` 通过 SHA-256 从前一个 `prevHash + blobHash` 派生，无需联系上游即可检测篡改。

## 并发安全

D1（Cloudflare 的数据库）不支持交互式事务。针对同一订阅的并发许可证颁发可能在序列号上发生冲突。账户服务器通过以下方式处理：

1. 读取下一个序列号和前一链哈希。
2. 使用该序列号构建并签名 blob。
3. 使用 `onConflictDoNothing` 插入账本条目。
4. 若插入返回 0 行变更，序列号已被另一请求占用，重新获取序列号，重新构建，**重新签名**，然后重试。
5. 10 次尝试失败后，返回错误。

关键细节：重试会**重新签名** blob。仅更新账本条目的简单重试会留下带有过期序列号的已签名 blob，从而破坏链。

## 邮件传输

账户服务器可通过两种可插拔传输发送事务性邮件（魔法链接、密码重置、安全通知）：

| 传输方式 | 配置 |
|---|---|
| `ses`（默认） | `AWS_SES_ACCESS_KEY_ID`、`AWS_SES_SECRET_ACCESS_KEY`、`AWS_SES_REGION`、`AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`、`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASSWORD`、`SMTP_SECURE`、`SMTP_FROM` |

两种传输方式均适用于云部署和本地部署。根据您的基础设施选择：使用自有 AWS 账户的 AWS SES，或任意 SMTP 服务器（Microsoft Exchange、Postfix、SendGrid、Mailgun 等）。

传输方式通过 `EMAIL_TRANSPORT` 环境变量在启动时选择。SMTP 使用连接池和延迟加载，因此 SMTP 客户端库仅在选择 SMTP 时才初始化。

所有邮件模板和公共邮件 API 在各传输方式之间完全相同。

## 相关文档

- [本地部署安装](/zh/docs/on-premise) - 如何部署本地部署服务器
- [订阅与许可](/zh/docs/subscription-licensing) - 计划限制和机器槽位
- [发布通道](/zh/docs/release-channels) - edge 与 stable 通道
- [数据区域](/zh/docs/data-regions) - 区域数据驻留
