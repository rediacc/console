---
title: "本地部署安装"
description: "在您自己的基础设施上运行账户服务器和 CLI 分发端点。"
category: "Guides"
order: 5
language: zh
sourceHash: "eea76db2d612133f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc 可以完全运行在您自己的基础设施上。独立 Docker 镜像包含账户服务器、Web 管理门户、营销网站和 CLI 分发端点，无需依赖 Rediacc 托管服务。

## Docker 镜像

拉取独立镜像：

```bash
docker pull ghcr.io/rediacc/server:stable
```

使用默认配置运行：

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

镜像提供以下服务：
- 账户 API：`/account/api/v1/`
- Web 管理门户：`/account/`
- 营销网站：`/`
- CLI 构件：`/releases/`
- Renet 二进制文件：`/bin/`

## 从您的服务器安装 CLI

直接从本地部署服务器安装 CLI。安装脚本会自动检测更新通道，并将 CLI 配置为从您的服务器检查更新。

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

此单条命令将：
1. 从服务器的 `/releases/` 端点下载 CLI 二进制文件
2. 查询 `/account/api/v1/.well-known/server-info` 以发现更新通道
3. 将服务器 URL、更新通道和加密密钥写入 `server.json`
4. 配置 `rdc update`，使其从您的服务器检查后续更新

无需设置 `REDIACC_CHANNEL` 变量。安装脚本会自动从服务器配置中读取通道。

## 使用命名配置管理 CLI

对于需要连接多个服务器（本地部署、生产环境、edge 环境）的用户，命名配置可以将每个环境隔离管理：

```bash
# 为本地部署服务器创建配置
rdc config init --name myserver --server https://account.example.com

# 使用该配置登录
rdc --config myserver subscription login

# 所有带 --config 的命令均使用本地部署服务器
rdc --config myserver machine query --name prod-1
```

每个命名配置存储其独立的账户服务器 URL 和订阅令牌。切换配置即切换整个服务器上下文。

## 离网环境（Air-Gapped）

对于无法访问互联网的环境，可同时设置服务器 URL 和自定义发布地址：

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

CLI 将从 `account.example.com/releases/cli/stable/manifest.json` 检查更新，而不是公共发布 CDN。

如果服务器完全离线，可通过 npm 从捆绑的 tarball 安装 CLI：

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## 环境变量参考

| 变量 | 使用方 | 用途 |
|---|---|---|
| `REDIACC_SERVER_URL` | 安装脚本 | 账户服务器 URL，自动发现通道和加密密钥 |
| `REDIACC_RELEASES_URL` | 安装脚本、CLI 更新器 | CLI 二进制文件的自定义发布端点，默认值：`https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | 安装脚本 | 覆盖更新通道，未设置时从服务器自动检测 |
| `REDIACC_ACCOUNT_SERVER` | CLI 运行时 | 覆盖所有 CLI 命令使用的账户服务器 URL |
| `RDC_UPDATE_CHANNEL` | CLI 运行时 | 覆盖 `rdc update` 使用的更新通道 |

## 服务器配置

本地部署 Docker 镜像使用与托管服务相同的 `ENVIRONMENT` 变量。在 Docker 环境或编排配置中进行设置：

- `ENVIRONMENT=production`（默认）：标准资源限制；连接到此服务器的 CLI 默认使用 **stable** 更新通道。值名 `production` 是旧的部署标识符。`production` 与 `edge` 两种模式均为生产级质量。
- `ENVIRONMENT=edge`：Community 计划限制翻倍；CLI 默认使用 **edge** 更新通道

有关每个环境提供内容的详情，请参阅 [发布通道](/zh/docs/release-channels)。

## 服务器向 CLI 传递的信息

CLI 连接到服务器时，会查询 `/.well-known/server-info` 以发现：

- **E2E 加密公钥**：用于零知识配置存储
- **最低 CLI 版本**：阻止过时的 CLI 连接
- **更新通道**：告知 CLI 使用哪个发布通道进行更新
- **环境**：服务器运行的部署配置（标准限制 vs. 带 2X 限制的 edge）

此自动配置意味着用户只需提供服务器 URL，其余信息均自动发现。

## 离网部署授权许可

离网和自托管本地部署服务器使用由上游主密钥签名的**委托证书**在本地颁发许可证。该证书将本地部署服务器约束在其计划限制内，并形成可验证的证明链。有关密码学设计（链完整性、分叉检测、审计证明）的详情，请参阅 [许可证链与委托](/zh/docs/license-chain)。

本节介绍操作配置：生成密钥、申请证书、配置自动续期，以及离线（离网）续期流程。

### 一个订阅，一个本地部署实例

每个订阅在同一时间内**最多只能有一个有效的委托证书**。每个本地部署实例针对其本地颁发账本执行每月和每台机器的限额，多个有效证书会在无法对账的情况下将有效配额倍增。

如果您需要独立的环境（生产、预发布、灾备、多地区），请为每个实例单独购买订阅。单一有效性约束将此契约编码化：尝试创建第二个有效证书将返回 `409 DELEGATION_CERT_ALREADY_ACTIVE`，同时附带现有证书 ID 以及续期（推荐，可保留证明链）或撤销后重建（重置证明链）的操作指引。

### 1. 生成本地部署 Ed25519 密钥对

本地部署服务器使用独立的 Ed25519 密钥对对许可证进行签名。上游的委托证书将授权此特定公钥。

```bash
# 生成新密钥对
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# 转换为 base64（本地部署在环境变量中所需的格式）
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

将私钥与其他密钥一同妥善保管（例如使用 Docker secret 或 Kubernetes Secret）。私钥永不离开本地部署服务器。

### 2. 从上游申请委托证书

您可以通过以下三种方式从上游账户门户申请证书：

**方式 A：客户自助服务（推荐）。** 以组织所有者或管理员身份登录上游门户，前往 **/account/delegation-certs**。点击 **Create New**，粘贴本地部署公钥（base64 SPKI），选择有效期（或接受计划默认值），然后下载生成的 `.json` 文件。

**方式 B：管理员（跨客户）。** Rediacc 支持人员或上游系统管理员可使用相同参数调用 `POST /admin/delegation-certs`。

**方式 C：`rdc` CLI（规划中）。** 未来 CLI 命令将封装门户流程。

返回的 `.json` 格式如下：

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

证书的有效期由有效期策略决定（每种计划的默认值和上限、每个订阅的自定义覆盖，以及订阅到期时间加 3 天宽限期的硬性上限）。响应中还包含 `effectiveDays` 和 `reason`，便于了解有效期的计算依据。完整规则请参阅 [许可证链 - 有效期策略](/zh/docs/license-chain)。

### 3. 在本地部署服务器上安装证书

将下载的 `.json` 保存到已知路径，并在本地部署中指向该文件：

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

或者，对于临时容器 / Docker secrets 工作流，可将证书以 base64 形式嵌入环境变量：

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. 配置上游验证与自动续期（可选但推荐）

如果本地部署服务器可以通过 HTTPS 访问上游，建议配置自动续期，使证书在到期前自动刷新，无需人工干预：

```bash
# /onprem/cert-upload 需要此项以验证上传的证书是否由上游主密钥签名。
# 若设置了 UPSTREAM_API_KEY 但未设置此项，则在启动时快速失败。
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# 自动续期循环所需。通过门户获取：
#   组织所有者/管理员 → /account/delegation-certs → "Get auto-renew token"
# 这是获取 delegation:renew 范围 API 令牌的唯一途径。
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# 可选调优参数（显示默认值）。
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

本地部署自动续期循环在启动时运行一次，之后按配置的间隔运行。它使用**自适应阈值**（`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`），使 15 天的 COMMUNITY 证书在剩余 5 天时续期，而不是在第 1 天就触发续期；90 天的 BUSINESS 证书则在剩余 14 天时续期（受环境配置上限约束）。

如果续期失败，证书将继续使用至自然到期。失败后退避 1 小时，并记录在 `${DELEGATION_CERT_PATH}.status.json` 中，同时通过 `GET /onprem/cert-status` 暴露状态。

### 5. 离网续期（无出站 HTTPS）

如果本地部署无法访问上游，可使用手动传输流程：

1. **从本地部署管理门户下载续期请求。** 以本地部署系统 root 身份请求 `GET /onprem/renewal-request`，返回包含本地链头、委托公钥以及本地部署私钥 Ed25519 签名的 JSON 清单。
2. **通过 USB、加密邮件或其他带外渠道将清单传输至上游。** 清单体积小（几 KB），不含任何密钥。
3. **在上游处理清单。** 组织所有者/管理员打开 **/account/delegation-certs** → **Upload renewal request** → 选择清单文件。上游验证清单签名与有效证书的 `delegatedPublicKey` 匹配（证明清单来自本地部署私钥持有者），检查防重放（超过 7 天的清单将被拒绝），然后颁发新证书。
4. **从上游门户下载新证书**（`.json` 文件）。
5. **将证书传回**本地部署服务器。
6. **通过本地管理门户上传证书**（`POST /onprem/cert-upload`）。本地部署将验证新证书与 `UPSTREAM_PUBLIC_KEY` 匹配，并验证证书的 `genesisSequence` 仍链接至本地颁发账本中的已知条目（支持传输期间的链序列推进，链自然延伸）。

整个流程无需本地部署服务器进行任何网络出站访问。

#### 清单失败代码

| 代码 | 原因 | 解决方法 |
|---|---|---|
| `NO_ACTIVE_CERT` | 上游对该订阅没有有效证书 | 通过创建流程颁发新证书，而非续期 |
| `DELEGATED_KEY_MISMATCH` | 清单的 `delegatedPublicKey` 与有效证书不符 | 该清单可能是来自不同本地部署实例的重放 |
| `MANIFEST_SIGNATURE_INVALID` | 签名无法通过委托公钥验证 | 清单在传输中被篡改，或在不同本地部署实例上生成 |
| `MANIFEST_EXPIRED` | 清单超过 7 天 | 从本地部署服务器重新生成续期请求 |

#### 证书上传失败代码

| 代码 | 原因 | 解决方法 |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | 新证书的 `genesisSequence` 超过本地链头 | 上游处于分叉链上，请调查 |
| `CHAIN_FORK_ON_UPLOAD` | 证书 `genesisSequence` 处的链哈希与本地账本不匹配 | 本地链已与上游分叉，请调查 |
| `Signature verification failed` | 证书未由配置的 `UPSTREAM_PUBLIC_KEY` 签名 | 检查 `UPSTREAM_PUBLIC_KEY` 是否与上游主公钥匹配 |

### 6. 状态与监控

随时查询本地部署的证书状态：

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

返回已加载证书的 `subscriptionId`、`planCode`、`validUntil`、`daysUntilExpiry`，以及 `autoRenew` 块（`enabled`、`lastSuccessAt`、`lastErrorAt`、`lastError`）。将此接口接入监控系统，对 `lastSuccessAt` 过期或 `lastError` 非空的情况发出告警。

本地部署管理员还可以通过 `GET /onprem/cert-current` 下载当前已加载的签名证书，用于备份和审计（需要提升权限的会话）。

### 委托证书环境变量参考

| 变量 | 是否必填 | 用途 |
|---|---|---|
| `ON_PREMISE_MODE` | 是 | 设为 `true` 以启用本地部署路由子集 |
| `ON_PREMISE_PRIVATE_KEY` | 是 | Base64 PKCS8 Ed25519 私钥，用于委托签名 |
| `ON_PREMISE_PUBLIC_KEY` | 是 | Base64 SPKI Ed25519 公钥（须与证书的 `delegatedPublicKey` 匹配） |
| `DELEGATION_CERT_PATH` | 二选一 | 已签名证书 JSON 文件的文件系统路径 |
| `DELEGATION_CERT_BASE64` | 二选一 | Base64 编码的证书 JSON（文件路径的替代方案） |
| `UPSTREAM_PUBLIC_KEY` | 若设置了 `UPSTREAM_API_KEY` 或需要 `/onprem/cert-upload` 正常工作则必填 | 上游主公钥的 Base64 SPKI，缺失时启动快速失败 |
| `UPSTREAM_URL` | 用于自动续期 | 上游账户服务器基础 URL，例如 `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | 用于自动续期 | `delegation:renew` 范围的 API 令牌，通过门户获取，见第 4 步 |
| `AUTO_RENEW_INTERVAL_HOURS` | 可选 | 默认 24。检查证书是否需要续期的间隔小时数 |
| `RENEW_THRESHOLD_DAYS` | 可选 | 默认 14。自适应 1/3 有效期阈值的上限 |

### 威胁模型概述

委托证书模型可防御以下威胁：

- **伪造许可证**：本地部署只能在其计划限制内签名；renet 会拒绝超出证书范围的任何内容。
- **跨部署共享证书**：链分叉在续期时被检测到（返回 `CHAIN_FORK_DETECTED`）。
- **通过多实例绕过配额**：上游通过单一有效性约束强制执行（每个订阅只有一个证书）。
- **链回滚**：renet 存储每个订阅所见的最高序列号，并拒绝任何序列号较低的 blob。
- **上游凭据泄露**：启动 `delegation:renew` 令牌只能通过专用门户端点获取，并受管理员权限控制。该令牌仅授予续期权限，不能读取或修改任何其他资源。
- **清单重放攻击**：超过 7 天的清单将被拒绝。

以下威胁**无法防御**：

- **本地部署私钥泄露**：泄露的私钥允许攻击者在证书的 `validUntil` 之前签名许可证。缓解措施：轮换密钥对（撤销旧证书并使用新密钥创建新证书），并将旧密钥签名的所有许可证视为可疑。
- **上游主密钥泄露**：此为信任根。轮换程序不在本文讨论范围内。
