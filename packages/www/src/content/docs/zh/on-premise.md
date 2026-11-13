---
title: "本地部署安装"
description: "在您自己的基础设施上运行账户服务器和 CLI 分发端点。"
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: zh
sourceHash: "7216d032580dd4e1"
sourceCommit: "48fd8400c9f2754ab1653f0247fb0d77a1835c5b"
---

Rediacc 可以完全运行在您自己的基础设施上。独立 Docker 镜像包含账户服务器、Web 管理门户、营销网站和 CLI 分发端点，无需依赖 Rediacc 托管服务。

## 使用 rdc 安装

`rdc server install` 把账户服务器作为仓库安装到 CLI 能通过 SSH 访问的机器上。一条命令涵盖机器检查、renet 设置、DNS、TLS、密钥生成、授权、启动和所有者账户。每个值都有对应的标志。在终端中,缺失的值会被询问;使用 `--yes` 时不会询问任何内容,缺失的值会被拒绝。每个步骤都会被记录,因此重新运行会跳过已完成的部分。

步骤依次为:`preflight`(免密 sudo、架构、80 和 443 端口、磁盘空间、时钟偏差)、`setup`(仅在缺少 renet 时运行 `rdc machine setup`)、`dns`、`tls`、`repo`、`keys`、`licence`、`image`、`up` 和 `owner`。

### 优先使用现有机器

安装的目标是已经存在的机器:数据中心的服务器或局域网中的设备。已配置的机器以参数形式给出。尚未注册的机器通过地址添加:

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` 和 `--name` 分别设置 SSH 端口和机器的注册名称。云虚拟机需先用 `rdc machine provision` 创建;安装本身从不创建虚拟机。

### DNS

安装会打印服务器域名及其备份存储域名(`--store-domain`,默认为 `<名称>-store.<域名其余部分>`)的 A 和 AAAA 记录,然后等待两者都解析到该机器。记录绝不会被写入任何区域。`--no-dns-wait` 打印记录后直接继续,适合由本地解析器提供的局域网名称。

### TLS

`--tls` 从三种方式中选择一种:

| 方式 | 需要 | 说明 |
|---|---|---|
| `letsencrypt` | 80 和 443 端口可从互联网访问 | HTTP-01 质询。`--cert-email` 接收到期通知;默认为所有者。 |
| `cloudflare` | `--cf-token` | 通过 Cloudflare API 令牌完成 DNS-01 质询。 |
| `byo` | `--tls-cert` 和 `--tls-key` | 覆盖两个域名的现有 PEM 证书。`--tls-ca` 指定健康检查所信任的 CA。 |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### 镜像

镜像步骤默认在机器上拉取 `ghcr.io/rediacc/server:latest`。`--image` 选择其他引用。`--image-file` 传送由 `docker save` 生成的 tar,`--local-image` 则从本地 Docker 保存 `--image` 并传送。两者都不需要机器访问镜像仓库。

### 授权与免费版

`--licence auto`(默认)使用已登录账户的委托证书,没有时以免费版启动。`--licence free` 始终以免费版启动。在安装命令出现之前登录的账户,需要重新运行 `rdc subscription login` 才能获得正确的 scope。

对于无法连接账户服务器的机器,`--cert <file>` 接受在别处获得的委托证书。证书必须指明机器上生成的密钥,因此通常的顺序是先以免费版安装,再应用证书:

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence` 把免费版服务器切换到已登录账户或 `--cert` 提供的证书。服务器会检查什么,见下文授权部分的第 3 步。

### 恢复包

所有密钥都在机器上生成,并且只写入仓库的 `secrets.env`。在终端中,安装结束时会一次性打印恢复包:委托密钥对、账户配置服务器密钥和对象存储凭据。恢复包不会写入日志,也不属于 `--output json` 的内容。没有终端时不会打印,结尾一行会提示 `rdc server backup`。

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` 以 0600 模式写入文件;不带它时,恢复包输出到 stdout。安装时的 `--bws-project <id>` 还会把密钥复制到 Bitwarden Secrets Manager 项目,`--rotate` 会替换与之不同的已存储值。没有 `--bws-project` 时,任何密钥都不会离开机器。

### 状态

```bash
rdc server status accounts.example.com
```

状态显示服务器的健康状况、套餐、证书和镜像。设备上没有该域名的安装记录时,用 `--machine` 和 `--repo` 指明目标。

### 更新

| 组件 | 命令 |
|---|---|
| CLI | `rdc update` |
| 机器上的 renet | `rdc machine setup <machine>` |
| 服务器镜像和模板 | `rdc server upgrade <domain>` |

`rdc server upgrade` 会 fork 仓库作为回退点,放置新镜像,在内置模板更新时重新应用模板,然后重启。它与安装一样接受 `--image`、`--image-file` 和 `--local-image`,因此隔离网络的机器可以从保存的镜像 tar 升级。

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
3. 将服务器 URL、更新通道和加密密钥写入默认配置（`rediacc.json`）的 `account.*` 字段下
4. 配置 `rdc update`，使其从您的服务器检查后续更新

无需设置 `REDIACC_CHANNEL` 变量。安装脚本会自动从服务器配置中读取通道。

## 使用命名配置管理 CLI

对于需要连接多个服务器（本地部署、生产环境、edge 环境）的用户，命名配置可以将每个环境隔离管理：

```bash
# 为本地部署服务器创建配置
rdc config init myserver --server https://account.example.com

# 使用该配置登录
rdc --config myserver subscription login

# 所有带 --config 的命令均使用本地部署服务器
rdc --config myserver machine status prod-1
```

每个命名配置存储其独立的账户服务器 URL（位于 `account.*` 下）以及独立的账户 API 令牌，令牌保存在配置旁边的 `api-token-<name>.json` 文件中。切换配置即切换整个服务器上下文。

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
| `REDIACC_UPDATE_CHANNEL` | CLI 运行时 | 覆盖 `rdc update` 使用的更新通道 |

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

服务器只从数据卷上的一个文件读取委托证书：`/data/delegation-cert.json`（`DELEGATION_CERT_PATH`）。没有其他途径可以传入证书，也没有对应的环境变量。`rdc server install` 会把下载的证书放到该位置，之后可用 `rdc server licence` 替换：

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

两条命令都通过证书收件箱（`data/web/cert-inbox/new.json`）把证书交给运行中的服务器。服务器验证证书后，以 `applied.json` 或 `rejected.json` 作答，命令再用 `rdc server status` 确认新证书的 id（与第 6 步的 `cert-status` 数据相同）。`rdc server upgrade` 使用同一个收件箱。升级中有一步会把遗留在 `secrets.env` 里的 `DELEGATION_CERT_BASE64` 移入收件箱，因此在收件箱出现之前安装的机器也能保留其证书。

服务器在启动时加载证书，并与它签署许可证所用的密钥核对：签名密钥的指纹必须与证书中 `delegatedPublicKey` 的指纹一致，因为用证书未授权的密钥签署的许可证无法在任何机器上通过验证。请保持签名密钥对与证书的 `delegatedPublicKey` 一致。

服务器在启动时拒绝的证书（签名无效、密钥不符、缺少 `UPSTREAM_PUBLIC_KEY` 或文件格式错误）不会使其停止。服务器会以免费版启动，并把有问题的文件移到原文件旁的 `delegation-cert.rejected.json`。在有效证书就位之前，仓库许可证签署会返回 `503 DELEGATION_CERT_REFUSED`，`rdc server status` 会显示 `cert REFUSED (reason)`。用有效证书运行 `rdc server licence` 即可修复。已过期的证书仍会加载：它会平滑降级，而不是被拒绝。

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

`POST /onprem/cert-upload` 成功时返回 `{uploaded: true, bootstrap, certId}`。证书被拒绝时返回 `{error, code}`，其中 `error` 为详细信息，`code` 为下表中的某个原因。每张已应用或被拒绝的证书都会记入日志，并通过邮件通知该机器的所有者。

`rdc server licence` 通过 SSH 把证书放入机器的收件箱（`data/web/cert-inbox`），再读回 `applied.json` 或 `rejected.json`，然后通过 `cert-status` 确认新的证书 ID。被拒绝时的原因与下表相同，另外还有收件箱自身给出的 `not-a-regular-file` 和 `too-large`。

| 代码 | HTTP | 原因 |
|---|---|---|
| `malformed` | 400 | 上传的内容不是有效证书 |
| `bad-signature` | 400 | 证书不是由已配置的 `UPSTREAM_PUBLIC_KEY` 签名的 |
| `wrong-key` | 400 | 证书是为另一把密钥签发的，不属于这个本地部署 |
| `expired` | 400 | 证书已超过其 `validUntil` |
| `not-newer` | 409 | 证书并不比当前生效的证书更新 |
| `other-subscription` | 409 | 证书属于另一个订阅 |
| `chain-ahead` | 409 | 证书的 `genesisSequence` 超过本地链头 |
| `chain-fork` | 409 | 证书 `genesisSequence` 处的链哈希与本地账本不匹配 |
| `no-upstream-key` | 500 | 未配置 `UPSTREAM_PUBLIC_KEY` |
| `write-failed` | 500 | 无法将证书写入磁盘 |
| `adoption-failed` | 500 | 服务器无法加载已写入的证书 |

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
| `DELEGATION_CERT_PATH` | 可选 | 已签名证书 JSON 文件的文件系统路径。默认为数据卷上的 `/data/delegation-cert.json`。请用 `rdc server licence` 替换证书，不要手动改动。 |
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
